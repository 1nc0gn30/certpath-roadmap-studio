"""Google Material 3 Studio UI Web Server for CertPath Roadmap Studio.

Provides a multi-threaded HTTP server with REST endpoints for certification catalog search,
DAG dependency resolution, topological prerequisite chains, personalized career roadmap planning,
Mermaid diagram synthesis, and rich Material 3 interactive studio UI delivery.
Zero third-party dependencies (100% Python Standard Library).
"""

from __future__ import annotations

import argparse
import json
import mimetypes
import os
import sys
import urllib.parse
import webbrowser
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, HTTPServer, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

from .catalog import Certification, CertificationCatalog
from .compat import get_platform_name, normalize_path, read_text_safe
from .dag_engine import DAGEngine
from .roadmap_planner import CareerRole, RoadmapPlan, RoadmapPlanner

# Try importing exporters if available
try:
    from .matrix_exporter import export_ascii_tree, export_json_ld, export_markdown, export_mermaid
except ImportError:
    export_mermaid = None  # type: ignore
    export_markdown = None  # type: ignore
    export_ascii_tree = None  # type: ignore
    export_json_ld = None  # type: ignore


# High quality embedded fallback HTML if public/index.html is missing
EMBEDDED_STUDIO_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Google CertPath Studio (Embedded Fallback)</title>
  <style>
    body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #f8fafd; color: #202124; padding: 32px; }
    .card { background: white; border-radius: 16px; padding: 24px; box-shadow: 0 2px 8px rgba(0,0,0,0.08); max-width: 800px; margin: 0 auto; }
    h1 { color: #1a73e8; margin-bottom: 8px; }
    p { color: #5f6368; line-height: 1.6; }
    .api-list { background: #f1f3f4; border-radius: 8px; padding: 16px; font-family: monospace; font-size: 13px; margin-top: 16px; }
  </style>
</head>
<body>
  <div class="card">
    <h1>Google CertPath Studio</h1>
    <p>Studio UI server is active and serving REST endpoints.</p>
    <div class="api-list">
      Available REST Endpoints:<br>
      - GET /api/catalog (Search & Filter certifications)<br>
      - GET /api/cert/&lt;id&gt; (Certification details with prerequisites & unlocked)<br>
      - GET /api/prereqs/&lt;id&gt; (Topological prerequisite chain)<br>
      - GET /api/unlocked/&lt;id&gt; (Unlocked credentials)<br>
      - GET /api/plan?role=&lt;role&gt; (Career path roadmap generator)<br>
      - GET /api/roles (Career role archetypes)<br>
      - GET /api/stats (Catalog telemetry)<br>
      - GET /api/diagnostics (System diagnostics)
    </div>
  </div>
</body>
</html>
"""


class StudioHTTPRequestHandler(BaseHTTPRequestHandler):
    """HTTP Request Handler providing REST API and static UI serving."""

    catalog: CertificationCatalog = None  # type: ignore
    dag: DAGEngine = None  # type: ignore
    planner: RoadmapPlanner = None  # type: ignore
    public_dir: Optional[Path] = None

    def log_message(self, format: str, *args: Any) -> None:
        """Override standard log message to silence unnecessary terminal noise in tests."""
        if os.environ.get("CERTPATH_DEBUG"):
            super().log_message(format, *args)

    def _set_cors_headers(self) -> None:
        """Set standard permissive CORS headers for local/cross-origin studio development."""
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization, X-Requested-With")

    def do_OPTIONS(self) -> None:
        """Handle CORS preflight requests."""
        self.send_response(HTTPStatus.NO_CONTENT)
        self._set_cors_headers()
        self.end_headers()

    def _send_json(self, data: Any, status: int = HTTPStatus.OK) -> None:
        """Send JSON response with UTF-8 encoding and content length."""
        try:
            payload = json.dumps(data, indent=2, default=str).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(payload)))
            self._set_cors_headers()
            self.end_headers()
            self.wfile.write(payload)
        except Exception as e:
            self._send_error(f"Internal server error serializing JSON: {e}", status=500)

    def _send_error(self, message: str, status: int = HTTPStatus.BAD_REQUEST) -> None:
        """Send standardized JSON error payload."""
        error_payload = {
            "error": message,
            "status": status,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        self._send_json(error_payload, status=status)

    def _get_public_dir(self) -> Path:
        """Determine path to public assets directory."""
        if self.public_dir and self.public_dir.exists():
            return self.public_dir
        
        # Check standard locations
        candidates = [
            Path("public"),
            Path(__file__).parent.parent.parent / "public",
            Path.cwd() / "public",
        ]
        for c in candidates:
            if c.exists() and c.is_dir():
                return normalize_path(c)
        return Path.cwd()

    def _serve_file(self, file_path: Path, content_type: Optional[str] = None) -> None:
        """Serve a static file with appropriate content type."""
        try:
            if not file_path.exists() or not file_path.is_file():
                self._send_error(f"File not found: {file_path.name}", status=HTTPStatus.NOT_FOUND)
                return

            if content_type is None:
                content_type, _ = mimetypes.guess_type(str(file_path))
                if content_type is None:
                    content_type = "application/octet-stream"

            content = file_path.read_bytes()
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(content)))
            self._set_cors_headers()
            self.end_headers()
            self.wfile.write(content)
        except Exception as e:
            self._send_error(f"Error reading file {file_path.name}: {e}", status=HTTPStatus.INTERNAL_SERVER_ERROR)

    def do_GET(self) -> None:
        """Dispatch GET requests to REST handlers or static files."""
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        query_params = urllib.parse.parse_qs(parsed.query)

        # Initialize engines if not set
        if StudioHTTPRequestHandler.catalog is None:
            StudioHTTPRequestHandler.catalog = CertificationCatalog()
        if StudioHTTPRequestHandler.dag is None:
            StudioHTTPRequestHandler.dag = DAGEngine(StudioHTTPRequestHandler.catalog)
        if StudioHTTPRequestHandler.planner is None:
            StudioHTTPRequestHandler.planner = RoadmapPlanner(StudioHTTPRequestHandler.catalog, StudioHTTPRequestHandler.dag)

        cat = StudioHTTPRequestHandler.catalog
        dag = StudioHTTPRequestHandler.dag
        planner = StudioHTTPRequestHandler.planner

        # 1. UI Root & HTML
        if path in ("", "/", "/index.html"):
            pub_dir = self._get_public_dir()
            index_file = pub_dir / "index.html"
            if index_file.exists():
                self._serve_file(index_file, "text/html; charset=utf-8")
            else:
                # Embedded fallback
                fallback_bytes = EMBEDDED_STUDIO_HTML.encode("utf-8")
                self.send_response(HTTPStatus.OK)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(fallback_bytes)))
                self._set_cors_headers()
                self.end_headers()
                self.wfile.write(fallback_bytes)
            return

        # 2. Raw certs.json
        if path in ("/certs.json", "/data/certs.json"):
            pub_dir = self._get_public_dir()
            c_file = pub_dir / "certs.json"
            if c_file.exists():
                self._serve_file(c_file, "application/json; charset=utf-8")
            else:
                self._send_json([c.to_dict(camel_case=True) for c in cat.get_all()])
            return

        # 3. REST API: /api/catalog
        if path == "/api/catalog":
            q = query_params.get("q", query_params.get("query", [""]))[0]
            provider = query_params.get("provider", [None])[0]
            level = query_params.get("level", [None])[0]
            category = query_params.get("category", [None])[0]
            skill = query_params.get("skill", [None])[0]
            limit_str = query_params.get("limit", [None])[0]

            if any([q, provider, level, category, skill]):
                results = cat.search(
                    query=q if q else None,
                    provider=provider,
                    level=level,
                    category=category,
                    skill=skill,
                )
            else:
                results = cat.get_all()

            if limit_str and limit_str.isdigit():
                results = results[: int(limit_str)]

            self._send_json([c.to_dict(camel_case=True) for c in results])
            return

        # 4. REST API: /api/cert/<id> or /api/certs/<id>
        if path.startswith("/api/cert/") or path.startswith("/api/certs/"):
            cert_id = path.split("/")[-1].strip()
            cert = cat.get_by_id(cert_id)
            if not cert:
                self._send_error(f"Certification with ID '{cert_id}' not found", status=HTTPStatus.NOT_FOUND)
                return

            prereqs = dag.resolve_prerequisites(cert_id)
            dependents = dag.resolve_dependents(cert_id)
            critical_path = dag.calculate_critical_path(cert_id)
            diff_score = dag.difficulty_score(cert_id)

            cert_data = cert.to_dict(camel_case=True)
            cert_data["resolvedPrerequisites"] = [p.to_dict(camel_case=True) for p in prereqs]
            cert_data["unlockedCredentials"] = [d.to_dict(camel_case=True) for d in dependents]
            cert_data["criticalPath"] = [cp.to_dict(camel_case=True) for cp in critical_path]
            cert_data["difficultyScore"] = diff_score

            self._send_json(cert_data)
            return

        # 5. REST API: /api/prereqs/<id>
        if path.startswith("/api/prereqs/"):
            cert_id = path.split("/")[-1].strip()
            cert = cat.get_by_id(cert_id)
            if not cert:
                self._send_error(f"Certification with ID '{cert_id}' not found", status=HTTPStatus.NOT_FOUND)
                return

            prereqs = dag.resolve_prerequisites(cert_id)
            self._send_json({
                "target_id": cert_id,
                "target_title": cert.title,
                "count": len(prereqs),
                "prerequisites": [p.to_dict(camel_case=True) for p in prereqs],
            })
            return

        # 6. REST API: /api/unlocked/<id>
        if path.startswith("/api/unlocked/"):
            cert_id = path.split("/")[-1].strip()
            cert = cat.get_by_id(cert_id)
            if not cert:
                self._send_error(f"Certification with ID '{cert_id}' not found", status=HTTPStatus.NOT_FOUND)
                return

            unlocked = dag.resolve_dependents(cert_id)
            self._send_json({
                "source_id": cert_id,
                "source_title": cert.title,
                "count": len(unlocked),
                "unlocked": [u.to_dict(camel_case=True) for u in unlocked],
            })
            return

        # 7. REST API: /api/plan
        if path == "/api/plan":
            role = query_params.get("role", [None])[0]
            target = query_params.get("target", [None])[0]
            current_raw = query_params.get("current", query_params.get("current_certs", [""]))[0]
            hours_str = query_params.get("hours", query_params.get("weekly_hours", ["10"]))[0]
            budget_str = query_params.get("budget", query_params.get("max_budget", [None]))[0]

            target_spec = role if role else (target if target else "cloud_security_architect")
            current_certs = [c.strip() for c in current_raw.split(",") if c.strip()]
            weekly_hours = int(hours_str) if hours_str.isdigit() else 10
            max_budget = float(budget_str) if budget_str and budget_str.replace(".", "", 1).isdigit() else None

            try:
                plan = planner.generate_roadmap(
                    target_role_or_cert=target_spec,
                    current_certs=current_certs,
                    weekly_hours=weekly_hours,
                    max_budget=max_budget,
                )
                self._send_json(plan.to_dict())
            except Exception as e:
                self._send_error(f"Failed to generate roadmap plan: {e}")
            return

        # 8. REST API: /api/compare
        if path == "/api/compare":
            ids_raw = query_params.get("ids", [""])[0]
            cert_ids = [i.strip() for i in ids_raw.split(",") if i.strip()]
            if not cert_ids:
                self._send_error("Parameter 'ids' (comma-separated cert IDs) is required")
                return

            compared = []
            for cid in cert_ids:
                c = cat.get_by_id(cid)
                if c:
                    d = c.to_dict(camel_case=True)
                    d["difficultyScore"] = dag.difficulty_score(cid)
                    d["prereqCount"] = len(dag.resolve_prerequisites(cid))
                    d["unlockedCount"] = len(dag.resolve_dependents(cid))
                    compared.append(d)

            self._send_json({
                "count": len(compared),
                "certifications": compared,
            })
            return

        # 9. REST API: /api/roles
        if path == "/api/roles":
            roles = planner.get_roles()
            self._send_json([r.to_dict() for r in roles])
            return

        # 10. REST API: /api/mermaid
        if path == "/api/mermaid":
            cert_id = query_params.get("cert_id", [None])[0]
            category = query_params.get("category", [None])[0]
            role_id = query_params.get("role", [None])[0]
            direction = query_params.get("direction", ["LR"])[0]

            if export_mermaid:
                if role_id:
                    plan = planner.generate_roadmap(role_id)
                    mermaid_syntax = export_mermaid(plan, direction=direction)
                elif cert_id:
                    prereqs = dag.resolve_prerequisites(cert_id, include_target=True)
                    mermaid_syntax = export_mermaid(prereqs, direction=direction)
                elif category:
                    certs = cat.search(category=category)
                    mermaid_syntax = export_mermaid(certs, direction=direction)
                else:
                    mermaid_syntax = export_mermaid(cat.get_all()[:35], direction=direction)
            else:
                # Built-in fallback mermaid generator
                mermaid_syntax = f"flowchart {direction}\n"
                sample_certs = cat.get_all()[:25]
                for c in sample_certs:
                    safe_title = c.title.replace('"', "").replace("(", "[").replace(")", "]")
                    for p in c.prerequisites:
                        mermaid_syntax += f'  {p} --> {c.id}["{safe_title}"]\n'

            self._send_json({
                "direction": direction,
                "mermaid": mermaid_syntax,
            })
            return

        # 11. REST API: /api/stats
        if path == "/api/stats":
            stats = cat.summary_statistics()
            stats["is_dag"] = dag.is_dag()
            stats["cycles_count"] = len(dag.detect_cycles())
            stats["total_roles"] = len(planner.get_roles())
            self._send_json(stats)
            return

        # 12. REST API: /api/diagnostics
        if path == "/api/diagnostics":
            self._send_json({
                "status": "healthy",
                "platform": get_platform_name(),
                "python_version": sys.version,
                "total_certs": len(cat),
                "is_dag": dag.is_dag(),
                "cycles": dag.detect_cycles(),
                "total_roles": len(planner.get_roles()),
                "categories": cat.get_categories(),
                "providers_count": len(cat.get_providers()),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })
            return

        # 13. Static file handling from public directory
        pub_dir = self._get_public_dir()
        clean_rel_path = path.lstrip("/")
        target_file = pub_dir / clean_rel_path
        if target_file.exists() and target_file.is_file():
            self._serve_file(target_file)
            return

        # Unknown route 404
        self._send_error(f"Endpoint '{path}' not found", status=HTTPStatus.NOT_FOUND)

    def do_POST(self) -> None:
        """Handle POST requests for roadmap generation, comparison, and searches."""
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        # Read JSON body
        content_length = int(self.headers.get("Content-Length", 0))
        body = {}
        if content_length > 0:
            try:
                raw_data = self.rfile.read(content_length).decode("utf-8")
                body = json.loads(raw_data)
            except Exception as e:
                self._send_error(f"Invalid JSON request body: {e}", status=HTTPStatus.BAD_REQUEST)
                return

        # Initialize engines
        if StudioHTTPRequestHandler.catalog is None:
            StudioHTTPRequestHandler.catalog = CertificationCatalog()
        if StudioHTTPRequestHandler.dag is None:
            StudioHTTPRequestHandler.dag = DAGEngine(StudioHTTPRequestHandler.catalog)
        if StudioHTTPRequestHandler.planner is None:
            StudioHTTPRequestHandler.planner = RoadmapPlanner(StudioHTTPRequestHandler.catalog, StudioHTTPRequestHandler.dag)

        cat = StudioHTTPRequestHandler.catalog
        dag = StudioHTTPRequestHandler.dag
        planner = StudioHTTPRequestHandler.planner

        if path == "/api/plan":
            role = body.get("role") or body.get("target_role")
            target = body.get("target") or body.get("target_cert")
            current = body.get("current") or body.get("current_certs") or []
            hours = int(body.get("weekly_hours") or body.get("hours") or 10)
            budget = float(body["max_budget"]) if body.get("max_budget") is not None else None

            target_spec = role if role else (target if target else "cloud_security_architect")
            try:
                plan = planner.generate_roadmap(
                    target_role_or_cert=target_spec,
                    current_certs=current,
                    weekly_hours=hours,
                    max_budget=budget,
                )
                self._send_json(plan.to_dict())
            except Exception as e:
                self._send_error(f"Error generating roadmap plan: {e}")
            return

        if path == "/api/compare":
            cert_ids = body.get("ids") or body.get("cert_ids") or []
            if not cert_ids:
                self._send_error("JSON body must contain 'ids' list")
                return

            compared = []
            for cid in cert_ids:
                c = cat.get_by_id(str(cid))
                if c:
                    d = c.to_dict(camel_case=True)
                    d["difficultyScore"] = dag.difficulty_score(str(cid))
                    d["prereqCount"] = len(dag.resolve_prerequisites(str(cid)))
                    d["unlockedCount"] = len(dag.resolve_dependents(str(cid)))
                    compared.append(d)

            self._send_json({"count": len(compared), "certifications": compared})
            return

        if path == "/api/search":
            q = body.get("query") or body.get("q")
            provider = body.get("provider")
            level = body.get("level")
            category = body.get("category")
            skill = body.get("skill")
            limit = int(body["limit"]) if body.get("limit") else None

            results = cat.search(query=q, provider=provider, level=level, category=category, skill=skill)
            if limit:
                results = results[:limit]
            self._send_json([c.to_dict(camel_case=True) for c in results])
            return

        self._send_error(f"POST endpoint '{path}' not found", status=HTTPStatus.NOT_FOUND)


def create_server(
    host: str = "127.0.0.1",
    port: int = 8080,
    catalog: Optional[CertificationCatalog] = None,
    dag: Optional[DAGEngine] = None,
    planner: Optional[RoadmapPlanner] = None,
    public_dir: Optional[Union[str, Path]] = None,
) -> ThreadingHTTPServer:
    """Create a configured ThreadingHTTPServer instance for CertPath Studio."""
    if catalog is not None:
        StudioHTTPRequestHandler.catalog = catalog
    if dag is not None:
        StudioHTTPRequestHandler.dag = dag
    if planner is not None:
        StudioHTTPRequestHandler.planner = planner
    if public_dir is not None:
        StudioHTTPRequestHandler.public_dir = normalize_path(public_dir)

    server = ThreadingHTTPServer((host, port), StudioHTTPRequestHandler)
    return server


def run_server(
    host: str = "127.0.0.1",
    port: int = 8080,
    open_browser: bool = False,
    public_dir: Optional[Union[str, Path]] = None,
) -> None:
    """Start and run the CertPath Roadmap Studio HTTP Server."""
    server = create_server(host=host, port=port, public_dir=public_dir)
    url = f"http://{host}:{port}"
    print(f"============================================================")
    print(f"  Google CertPath Studio UI Server Active")
    print(f"  URL: {url}")
    print(f"  Interactive Roadmap DAG & Career Planner Ready")
    print(f"  Press Ctrl+C to stop.")
    print(f"============================================================")

    if open_browser:
        try:
            webbrowser.open(url)
        except Exception:
            pass

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down CertPath Studio server...")
    finally:
        server.server_close()


def main() -> None:
    """CLI entrypoint for standalone UI server."""
    parser = argparse.ArgumentParser(description="Google CertPath Studio UI & REST Server")
    parser.add_argument("--host", default="127.0.0.1", help="Host interface to bind (default: 127.0.0.1)")
    parser.add_argument("--port", "-p", type=int, default=8080, help="Port to listen on (default: 8080)")
    parser.add_argument("--open", "-o", action="store_true", help="Automatically open studio in default browser")
    parser.add_argument("--public-dir", default=None, help="Custom public directory path")

    args = parser.parse_args()
    run_server(host=args.host, port=args.port, open_browser=args.open, public_dir=args.public_dir)


if __name__ == "__main__":
    main()
