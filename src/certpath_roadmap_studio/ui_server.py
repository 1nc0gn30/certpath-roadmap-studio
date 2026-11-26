"""CertPath Roadmap Studio Web Server (Hardened Loopback Workstation & REST API).

Provides a multi-threaded HTTP server with REST endpoints for certification catalog search,
DAG dependency resolution, topological prerequisite chains, personalized career roadmap planning,
Monte Carlo velocity simulation, financial ROI & skill overlap, Mermaid diagram synthesis,
and interactive dual-theme Studio UI delivery.
Zero third-party dependencies (100% Python Standard Library).
"""

from __future__ import annotations

import argparse
import html
import json
import math
import mimetypes
import os
import re
import sys
import urllib.parse
import webbrowser
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

from .catalog import Certification, CertificationCatalog
from .compat import get_platform_name, normalize_path
from .dag_engine import DAGEngine
from .roadmap_planner import RoadmapPlanner

try:
    from .matrix_exporter import export_ascii_tree, export_json_ld, export_markdown, export_mermaid
except ImportError:
    export_mermaid = None  # type: ignore
    export_markdown = None  # type: ignore
    export_ascii_tree = None  # type: ignore
    export_json_ld = None  # type: ignore

SERVER_VERSION = "2.6.0"
MAX_BODY_BYTES = 1_048_576  # 1 MiB strict request body cap

CSP_HEADER_VALUE = (
    "default-src 'self' data: blob:; "
    "script-src 'self' 'unsafe-inline'; "
    "style-src 'self' 'unsafe-inline'; "
    "img-src 'self' data: blob:; "
    "font-src 'self' data:; "
    "connect-src 'self' http://127.0.0.1:8093 http://localhost:8093; "
    "frame-ancestors 'self' http://127.0.0.1:* http://localhost:*"
)

_ALLOWED_NETLIFY_ORIGINS = frozenset({"https://certpath-roadmap-studio.netlify.app"})
_IPV6_HOST_RE = re.compile(r"^\[::1\](?::([0-9]{1,5}))?$")
_LOOPBACK_HOST_RE = re.compile(r"^(localhost|127\.0\.0\.1)(?::([0-9]{1,5}))?$", re.IGNORECASE)


EMBEDDED_STUDIO_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>CertPath Roadmap Studio (Embedded Fallback)</title>
  <style>
    body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background: #FAF8F3; color: #101828; padding: 32px; }
    .card { background: #FFFFFF; border-radius: 16px; padding: 24px; border: 1px solid #D5CEC0; max-width: 800px; margin: 0 auto; }
    h1 { color: #7A5808; margin-bottom: 8px; }
    p { color: #475467; line-height: 1.6; }
    .api-list { background: #F4F1EA; border-radius: 8px; padding: 16px; font-family: monospace; font-size: 13px; margin-top: 16px; }
  </style>
</head>
<body>
  <div class="card">
    <h1>CertPath Roadmap Studio v2.6.0</h1>
    <p>Loopback REST API server is active on 127.0.0.1:8093.</p>
    <div class="api-list">
      Available REST Endpoints:<br>
      - GET /health, /api/health, /api/diagnostics<br>
      - GET /api/catalog, /api/cert/&lt;id&gt;, /api/prereqs/&lt;id&gt;, /api/unlocked/&lt;id&gt;<br>
      - GET/POST /api/plan, /api/compare, /api/search, /api/roles, /api/stats<br>
      - GET/POST /api/roi, /api/overlap, /api/valuation, /api/simulate-velocity, /api/mermaid
    </div>
  </div>
</body>
</html>
"""


def _build_legal_page(title: str, heading: str, body_html: str) -> bytes:
    """Render a clean, dual-theme, zero-egress HTML page for /terms, /privacy, /support."""
    safe_title = html.escape(title)
    safe_heading = html.escape(heading)
    doc = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{safe_title} | CertPath Roadmap Studio v{SERVER_VERSION}</title>
  <style>
    :root {{ --bg: #FAF8F3; --card: #FFFFFF; --ink: #101828; --muted: #475467; --gold: #7A5808; --border: #D5CEC0; }}
    @media (prefers-color-scheme: dark) {{
      :root {{ --bg: #08080B; --card: #12121A; --ink: #EDEFF2; --muted: #A3AAB8; --gold: #D4AF37; --border: #2A2A33; }}
    }}
    body {{ margin: 0; font-family: system-ui, -apple-system, 'Segoe UI', sans-serif; background: var(--bg); color: var(--ink); padding: 32px 16px; line-height: 1.65; }}
    main {{ max-width: 780px; margin: 0 auto; background: var(--card); border: 1px solid var(--border); border-radius: 16px; padding: 28px 32px; }}
    h1 {{ margin: 0 0 12px; color: var(--gold); font-size: 1.75rem; }}
    p, li {{ color: var(--muted); }}
    a {{ color: var(--gold); font-weight: 600; }}
    code {{ font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 0.9em; }}
    footer {{ margin-top: 24px; padding-top: 16px; border-top: 1px solid var(--border); font-size: 0.85rem; color: var(--muted); }}
  </style>
</head>
<body>
  <main>
    <h1>{safe_heading}</h1>
    {body_html}
    <p><a href="/">← Return to CertPath Roadmap Studio</a></p>
    <footer>Engineered by Neal Frazier Tech (@1nc0gn30) • NullAI Platform · v{SERVER_VERSION}</footer>
  </main>
</body>
</html>
"""
    return doc.encode("utf-8")


LEGAL_ROUTES: Dict[str, bytes] = {
    "/terms": _build_legal_page(
        "Terms of Use",
        "Terms of Use — CertPath Roadmap Studio",
        "<p>CertPath Roadmap Studio is released under the MIT License and provided 100% free and open-access with zero paywalls or feature locks.</p>"
        "<p>Certification exam fees, study hour estimates, salary premiums, and Monte Carlo timelines are deterministic local heuristics for educational planning and do not constitute career or financial guarantees.</p>",
    ),
    "/privacy": _build_legal_page(
        "Privacy Policy",
        "Privacy Policy — Zero-Egress Local Architecture",
        "<p>CertPath Roadmap Studio runs 100% locally on loopback (<code>127.0.0.1:8093</code>) or entirely client-side in your browser.</p>"
        "<ul><li>Zero analytics, tracking pixels, cookies, or cloud telemetry.</li>"
        "<li>Zero external CDN font or script requests.</li>"
        "<li>All certification searches, roadmaps, velocity simulations, and ROI calculations stay on your machine.</li></ul>",
    ),
    "/support": _build_legal_page(
        "Support",
        "Community Support — CertPath Roadmap Studio",
        "<p>CertPath Roadmap Studio is 100% free and open-source software with zero paywalls. Optional community tips help sustain open engineering:</p>"
        "<ul><li><a href=\"https://buy.stripe.com/3cIfZg27PdKo2D64Ocfw40X\" target=\"_blank\" rel=\"noopener noreferrer\">Buy Us a Coffee (Stripe)</a></li>"
        "<li>Solana Tip Address: <code>GG2eQbVh8ut1BK6j1A2tz7pSySdLpD38BgyEhGcxdXoK</code> (<a href=\"solana:GG2eQbVh8ut1BK6j1A2tz7pSySdLpD38BgyEhGcxdXoK\">Open Wallet</a>)</li>"
        "<li>Source &amp; Issues: <a href=\"https://github.com/1nc0gn30/certpath-roadmap-studio\" target=\"_blank\" rel=\"noopener noreferrer\">github.com/1nc0gn30/certpath-roadmap-studio</a></li></ul>",
    ),
}


def _safe_rel(raw: str) -> str:
    """Request path -> safe relative path inside a static dir; '' if it tries to climb out."""
    from urllib.parse import unquote

    rel = unquote(str(raw or "")).replace("\\", "/").lstrip("/")
    parts = [p for p in rel.split("/") if p not in ("", ".")]
    if any(p == ".." for p in parts) or ":" in (parts[0] if parts else ""):
        return ""
    return "/".join(parts)


def _is_valid_host(host: Optional[str]) -> bool:
    """Strictly validate HTTP Host header against loopback allowlist (DNS rebinding guard)."""
    if not host or not isinstance(host, str):
        return False
    h = host.strip()
    if not h or any(c.isspace() for c in h):
        return False

    m6 = _IPV6_HOST_RE.match(h)
    if m6:
        port_s = m6.group(1)
        if port_s is None:
            return True
        port_i = int(port_s)
        return 1 <= port_i <= 65535

    m4 = _LOOPBACK_HOST_RE.match(h)
    if m4:
        port_s = m4.group(2)
        if port_s is None:
            return True
        port_i = int(port_s)
        return 1 <= port_i <= 65535

    return False


def _is_local_origin(origin: Optional[str]) -> bool:
    """True for absent Origin (CLI/curl/same-origin GET) or strict loopback/allowlisted origin."""
    if not origin:
        return True
    if not isinstance(origin, str):
        return False
    raw = origin.strip()
    if not raw or any(c.isspace() for c in raw):
        return False
    if raw in _ALLOWED_NETLIFY_ORIGINS:
        return True

    try:
        u = urllib.parse.urlparse(raw)
        port = u.port  # Raises ValueError on port-suffix spoofs like 127.0.0.1:8093.example.invalid
    except ValueError:
        return False
    except Exception:
        return False

    if u.scheme not in ("http", "https"):
        return False
    if u.username is not None or u.password is not None:
        return False
    if u.path not in ("", "/") or u.params or u.query or u.fragment:
        return False

    hostname = (u.hostname or "").lower()
    if hostname not in ("localhost", "127.0.0.1", "::1"):
        return False

    if port is not None and not (1 <= port <= 65535):
        return False

    if hostname == "::1":
        expected_netloc = f"[::1]:{port}" if port is not None else "[::1]"
    else:
        expected_netloc = f"{hostname}:{port}" if port is not None else hostname

    return u.netloc.lower() == expected_netloc


def _cors_origin(handler: BaseHTTPRequestHandler) -> str:
    """Echo the Origin only when it is strictly allowlisted; never '*'."""
    origin = handler.headers.get("Origin", "")
    if origin and _is_local_origin(origin):
        return origin.strip()
    return "http://127.0.0.1"


def _parse_int_param(
    raw: Any,
    name: str,
    default: Optional[int] = None,
    min_val: Optional[int] = None,
    max_val: Optional[int] = None,
) -> Optional[int]:
    """Safely parse bounded integer query/body parameters without crashing on malformed inputs."""
    if raw is None or raw == "":
        return default
    if isinstance(raw, bool):
        raise ValueError(f"Parameter '{name}' must be an integer, not boolean")
    if isinstance(raw, float):
        if not math.isfinite(raw) or not raw.is_integer():
            raise ValueError(f"Parameter '{name}' must be a finite integer")
        val = int(raw)
    elif isinstance(raw, int):
        val = raw
    elif isinstance(raw, str):
        s = raw.strip()
        if not s:
            return default
        try:
            val = int(s)
        except ValueError as exc:
            raise ValueError(f"Parameter '{name}' must be a valid integer") from exc
    else:
        raise ValueError(f"Parameter '{name}' must be an integer")

    if min_val is not None and val < min_val:
        raise ValueError(f"Parameter '{name}' must be >= {min_val}")
    if max_val is not None and val > max_val:
        raise ValueError(f"Parameter '{name}' must be <= {max_val}")
    return val


def _parse_float_param(
    raw: Any,
    name: str,
    default: Optional[float] = None,
    min_val: Optional[float] = None,
    max_val: Optional[float] = None,
) -> Optional[float]:
    """Safely parse finite bounded float query/body parameters."""
    if raw is None or raw == "":
        return default
    if isinstance(raw, bool):
        raise ValueError(f"Parameter '{name}' must be a number, not boolean")
    try:
        val = float(raw)
    except (ValueError, TypeError) as exc:
        raise ValueError(f"Parameter '{name}' must be a valid number") from exc
    if not math.isfinite(val):
        raise ValueError(f"Parameter '{name}' must be a finite number (NaN/Infinity disallowed)")
    if min_val is not None and val < min_val:
        raise ValueError(f"Parameter '{name}' must be >= {min_val}")
    if max_val is not None and val > max_val:
        raise ValueError(f"Parameter '{name}' must be <= {max_val}")
    return val


def _parse_str_list(raw: Any, name: str) -> List[str]:
    """Safely parse list of strings (or comma-separated string)."""
    if raw is None or raw == "":
        return []
    if isinstance(raw, str):
        return [x.strip() for x in raw.split(",") if x.strip()]
    if isinstance(raw, list):
        out: List[str] = []
        for item in raw:
            if not isinstance(item, str):
                raise ValueError(f"All items in '{name}' must be strings")
            s = item.strip()
            if s:
                out.append(s)
        return out
    raise ValueError(f"Parameter '{name}' must be a list of strings")


class StudioHTTPRequestHandler(BaseHTTPRequestHandler):
    """Hardened HTTP Request Handler providing REST API and static UI serving."""

    catalog: CertificationCatalog = None  # type: ignore
    dag: DAGEngine = None  # type: ignore
    planner: RoadmapPlanner = None  # type: ignore
    public_dir: Optional[Path] = None

    def log_message(self, format: str, *args: Any) -> None:
        """Silence terminal log noise unless CERTPATH_DEBUG is enabled."""
        if os.environ.get("CERTPATH_DEBUG"):
            super().log_message(format, *args)

    def _set_security_headers(self, include_cors: bool = True) -> None:
        """Emit mandatory security headers, Vary: Origin, and optional allowlisted CORS."""
        self.send_header("Vary", "Origin")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "strict-origin-when-cross-origin")
        self.send_header("Content-Security-Policy", CSP_HEADER_VALUE)
        if include_cors:
            self.send_header("Access-Control-Allow-Origin", _cors_origin(self))
            self.send_header("Access-Control-Allow-Methods", "GET, HEAD, POST, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization, X-Requested-With")

    def _guard_host_and_origin(self, head_only: bool = False) -> bool:
        """Enforce strict loopback Host and Origin allowlists; return 403 JSON with zero ACAO on reject."""
        host_header = self.headers.get("Host")
        if not _is_valid_host(host_header):
            self._send_error(
                "Forbidden: untrusted Host header",
                status=HTTPStatus.FORBIDDEN,
                include_cors=False,
                head_only=head_only,
            )
            return False

        origin_header = self.headers.get("Origin")
        if origin_header and not _is_local_origin(origin_header):
            self._send_error(
                "Forbidden: untrusted cross-origin request",
                status=HTTPStatus.FORBIDDEN,
                include_cors=False,
                head_only=head_only,
            )
            return False

        return True

    def _ensure_engines(self) -> Tuple[CertificationCatalog, DAGEngine, RoadmapPlanner]:
        """Lazily initialize shared catalog, DAG, and roadmap planner instances."""
        if StudioHTTPRequestHandler.catalog is None:
            StudioHTTPRequestHandler.catalog = CertificationCatalog()
        if StudioHTTPRequestHandler.dag is None:
            StudioHTTPRequestHandler.dag = DAGEngine(StudioHTTPRequestHandler.catalog)
        if StudioHTTPRequestHandler.planner is None:
            StudioHTTPRequestHandler.planner = RoadmapPlanner(
                StudioHTTPRequestHandler.catalog, StudioHTTPRequestHandler.dag
            )
        return (
            StudioHTTPRequestHandler.catalog,
            StudioHTTPRequestHandler.dag,
            StudioHTTPRequestHandler.planner,
        )

    def _send_json(
        self,
        data: Any,
        status: int = HTTPStatus.OK,
        include_cors: bool = True,
        head_only: bool = False,
    ) -> None:
        """Send strict RFC-8259 JSON response (allow_nan=False) with security headers."""
        try:
            payload = json.dumps(data, indent=2, default=str, allow_nan=False).encode("utf-8")
        except (ValueError, TypeError):
            fallback = json.dumps(
                {
                    "error": "Internal serialization error: non-finite numeric value",
                    "status": 500,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
            ).encode("utf-8")
            self.send_response(HTTPStatus.INTERNAL_SERVER_ERROR)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(fallback)))
            self._set_security_headers(include_cors=include_cors)
            self.end_headers()
            if not head_only:
                self.wfile.write(fallback)
            return

        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self._set_security_headers(include_cors=include_cors)
        self.end_headers()
        if not head_only:
            self.wfile.write(payload)

    def _send_bytes(
        self,
        content: bytes,
        content_type: str,
        status: int = HTTPStatus.OK,
        head_only: bool = False,
    ) -> None:
        """Send binary/HTML payload with mandatory security headers."""
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(content)))
        self._set_security_headers(include_cors=True)
        self.end_headers()
        if not head_only:
            self.wfile.write(content)

    def _send_error(
        self,
        message: str,
        status: int = HTTPStatus.BAD_REQUEST,
        include_cors: bool = True,
        head_only: bool = False,
    ) -> None:
        """Send standardized JSON error payload."""
        error_payload = {
            "error": message,
            "status": int(status),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        self._send_json(error_payload, status=status, include_cors=include_cors, head_only=head_only)

    def _get_public_dir(self) -> Path:
        """Determine path to public assets directory."""
        if self.public_dir and self.public_dir.exists():
            return self.public_dir

        candidates = [
            Path(__file__).resolve().parent.parent.parent / "public",
            Path("public"),
            Path.cwd() / "public",
        ]
        for c in candidates:
            if c.exists() and c.is_dir():
                return normalize_path(c)
        return Path.cwd()

    def _serve_file(
        self,
        file_path: Path,
        content_type: Optional[str] = None,
        head_only: bool = False,
    ) -> None:
        """Serve a static file after enforcing symlink containment inside public_dir."""
        try:
            pub_resolved = self._get_public_dir().resolve()
            resolved_target = file_path.resolve()
            if not resolved_target.is_relative_to(pub_resolved):
                self._send_error(
                    "Forbidden: path escapes static root",
                    status=HTTPStatus.FORBIDDEN,
                    head_only=head_only,
                )
                return

            if not resolved_target.exists() or not resolved_target.is_file():
                self._send_error(
                    f"File not found: {file_path.name}",
                    status=HTTPStatus.NOT_FOUND,
                    head_only=head_only,
                )
                return

            if content_type is None:
                guessed, _ = mimetypes.guess_type(str(resolved_target))
                content_type = guessed or "application/octet-stream"
                if content_type.startswith("text/") or content_type in (
                    "application/javascript",
                    "application/json",
                    "application/xml",
                ):
                    content_type = f"{content_type}; charset=utf-8"

            content = resolved_target.read_bytes()
            self._send_bytes(content, content_type, status=HTTPStatus.OK, head_only=head_only)
        except OSError:
            self._send_error(
                "Unable to read static asset",
                status=HTTPStatus.INTERNAL_SERVER_ERROR,
                head_only=head_only,
            )

    def _health_payload(self, cat: CertificationCatalog, dag: DAGEngine, planner: RoadmapPlanner) -> Dict[str, Any]:
        """Build standardized health and diagnostics JSON dictionary."""
        return {
            "status": "healthy",
            "version": SERVER_VERSION,
            "platform": get_platform_name(),
            "python_version": sys.version.split()[0],
            "total_certs": len(cat),
            "is_dag": dag.is_dag(),
            "cycles": dag.detect_cycles(),
            "total_roles": len(planner.get_roles()),
            "categories": cat.get_categories(),
            "providers_count": len(cat.get_providers()),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    def do_OPTIONS(self) -> None:
        """Handle CORS preflight requests with strict Host & Origin validation."""
        if not self._guard_host_and_origin():
            return
        self.send_response(HTTPStatus.NO_CONTENT)
        self.send_header("Content-Length", "0")
        self._set_security_headers(include_cors=True)
        self.end_headers()

    def do_HEAD(self) -> None:
        """Handle HEAD requests cleanly with 0-byte body and accurate headers."""
        if not self._guard_host_and_origin(head_only=True):
            return
        self._handle_get_or_head(head_only=True)

    def do_GET(self) -> None:
        """Dispatch GET requests to REST handlers or static files."""
        if not self._guard_host_and_origin(head_only=False):
            return
        self._handle_get_or_head(head_only=False)

    def _handle_get_or_head(self, head_only: bool = False) -> None:
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        query_params = urllib.parse.parse_qs(parsed.query)
        cat, dag, planner = self._ensure_engines()

        # 1. UI Root & HTML
        if path in ("", "/", "/index.html"):
            pub_dir = self._get_public_dir()
            index_file = pub_dir / "index.html"
            if index_file.exists():
                self._serve_file(index_file, "text/html; charset=utf-8", head_only=head_only)
            else:
                self._send_bytes(
                    EMBEDDED_STUDIO_HTML.encode("utf-8"),
                    "text/html; charset=utf-8",
                    status=HTTPStatus.OK,
                    head_only=head_only,
                )
            return

        # 1b. Legal & Support routes (parity with Netlify)
        if path in LEGAL_ROUTES:
            self._send_bytes(
                LEGAL_ROUTES[path],
                "text/html; charset=utf-8",
                status=HTTPStatus.OK,
                head_only=head_only,
            )
            return

        # 2. Raw certs.json
        if path in ("/certs.json", "/data/certs.json"):
            pub_dir = self._get_public_dir()
            c_file = pub_dir / "certs.json"
            if c_file.exists():
                self._serve_file(c_file, "application/json; charset=utf-8", head_only=head_only)
            else:
                self._send_json([c.to_dict(camel_case=True) for c in cat.get_all()], head_only=head_only)
            return

        # 3. REST API: /api/catalog
        if path == "/api/catalog":
            q = query_params.get("q", query_params.get("query", [""]))[0]
            provider = query_params.get("provider", [None])[0]
            level = query_params.get("level", [None])[0]
            category = query_params.get("category", [None])[0]
            skill = query_params.get("skill", [None])[0]
            limit_str = query_params.get("limit", [None])[0]

            try:
                limit = _parse_int_param(limit_str, "limit", default=None, min_val=1, max_val=500)
            except ValueError as exc:
                self._send_error(str(exc), status=HTTPStatus.BAD_REQUEST, head_only=head_only)
                return

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

            if limit is not None:
                results = results[:limit]

            self._send_json([c.to_dict(camel_case=True) for c in results], head_only=head_only)
            return

        # 4. REST API: /api/cert/<id> or /api/certs/<id>
        if path.startswith("/api/cert/") or path.startswith("/api/certs/"):
            cert_id = urllib.parse.unquote(path.split("/")[-1]).strip()
            cert = cat.get_by_id(cert_id)
            if not cert:
                self._send_error(
                    f"Certification with ID '{cert_id}' not found",
                    status=HTTPStatus.NOT_FOUND,
                    head_only=head_only,
                )
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

            self._send_json(cert_data, head_only=head_only)
            return

        # 5. REST API: /api/prereqs/<id>
        if path.startswith("/api/prereqs/"):
            cert_id = urllib.parse.unquote(path.split("/")[-1]).strip()
            cert = cat.get_by_id(cert_id)
            if not cert:
                self._send_error(
                    f"Certification with ID '{cert_id}' not found",
                    status=HTTPStatus.NOT_FOUND,
                    head_only=head_only,
                )
                return

            prereqs = dag.resolve_prerequisites(cert_id)
            self._send_json(
                {
                    "target_id": cert_id,
                    "target_title": cert.title,
                    "count": len(prereqs),
                    "prerequisites": [p.to_dict(camel_case=True) for p in prereqs],
                },
                head_only=head_only,
            )
            return

        # 6. REST API: /api/unlocked/<id>
        if path.startswith("/api/unlocked/"):
            cert_id = urllib.parse.unquote(path.split("/")[-1]).strip()
            cert = cat.get_by_id(cert_id)
            if not cert:
                self._send_error(
                    f"Certification with ID '{cert_id}' not found",
                    status=HTTPStatus.NOT_FOUND,
                    head_only=head_only,
                )
                return

            unlocked = dag.resolve_dependents(cert_id)
            self._send_json(
                {
                    "source_id": cert_id,
                    "source_title": cert.title,
                    "count": len(unlocked),
                    "unlocked": [u.to_dict(camel_case=True) for u in unlocked],
                },
                head_only=head_only,
            )
            return

        # 7. REST API: /api/plan
        if path == "/api/plan":
            role = query_params.get("role", [None])[0]
            target = query_params.get("target", [None])[0]
            current_raw = query_params.get("current", query_params.get("current_certs", [""]))[0]
            hours_str = query_params.get("hours", query_params.get("weekly_hours", ["10"]))[0]
            budget_str = query_params.get("budget", query_params.get("max_budget", [None]))[0]

            try:
                weekly_hours = _parse_int_param(hours_str, "hours", default=10, min_val=1, max_val=168)
                max_budget = _parse_float_param(budget_str, "max_budget", default=None, min_val=0.0, max_val=1_000_000.0)
            except ValueError as exc:
                self._send_error(str(exc), status=HTTPStatus.BAD_REQUEST, head_only=head_only)
                return

            target_spec = role if role else (target if target else "cloud_security_architect")
            current_certs = [c.strip() for c in current_raw.split(",") if c.strip()]

            try:
                plan = planner.generate_roadmap(
                    target_role_or_cert=target_spec,
                    current_certs=current_certs,
                    weekly_hours=weekly_hours or 10,
                    max_budget=max_budget,
                )
                self._send_json(plan.to_dict(), head_only=head_only)
            except ValueError as exc:
                self._send_error(str(exc), status=HTTPStatus.BAD_REQUEST, head_only=head_only)
            except Exception:
                self._send_error("Failed to generate roadmap plan", status=HTTPStatus.BAD_REQUEST, head_only=head_only)
            return

        # 8. REST API: /api/compare
        if path == "/api/compare":
            ids_raw = query_params.get("ids", [""])[0]
            cert_ids = [i.strip() for i in ids_raw.split(",") if i.strip()]
            if not cert_ids:
                self._send_error(
                    "Parameter 'ids' (comma-separated cert IDs) is required",
                    status=HTTPStatus.BAD_REQUEST,
                    head_only=head_only,
                )
                return

            compared = []
            for cid in cert_ids[:20]:
                c = cat.get_by_id(cid)
                if c:
                    d = c.to_dict(camel_case=True)
                    d["difficultyScore"] = dag.difficulty_score(cid)
                    d["prereqCount"] = len(dag.resolve_prerequisites(cid))
                    d["unlockedCount"] = len(dag.resolve_dependents(cid))
                    compared.append(d)

            self._send_json({"count": len(compared), "certifications": compared}, head_only=head_only)
            return

        # 9. REST API: /api/roles
        if path == "/api/roles":
            roles = planner.get_roles()
            self._send_json([r.to_dict() for r in roles], head_only=head_only)
            return

        # 10. REST API: /api/mermaid
        if path == "/api/mermaid":
            cert_id = query_params.get("cert_id", [None])[0]
            category = query_params.get("category", [None])[0]
            role_id = query_params.get("role", [None])[0]
            direction = (query_params.get("direction", ["LR"])[0] or "LR").upper()
            if direction not in ("LR", "TD", "TB", "RL"):
                self._send_error("Parameter 'direction' must be one of LR, TD, TB, RL", status=HTTPStatus.BAD_REQUEST, head_only=head_only)
                return

            try:
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
                    mermaid_syntax = f"flowchart {direction}\n"
                    for c in cat.get_all()[:25]:
                        safe_title = c.title.replace('"', "").replace("(", "[").replace(")", "]")
                        for p in c.prerequisites:
                            mermaid_syntax += f'  {p} --> {c.id}["{safe_title}"]\n'
            except ValueError as exc:
                self._send_error(str(exc), status=HTTPStatus.BAD_REQUEST, head_only=head_only)
                return

            self._send_json({"direction": direction, "mermaid": mermaid_syntax}, head_only=head_only)
            return

        # 11. REST API: /api/stats
        if path == "/api/stats":
            stats = cat.summary_statistics()
            stats["version"] = SERVER_VERSION
            stats["is_dag"] = dag.is_dag()
            stats["cycles_count"] = len(dag.detect_cycles())
            stats["total_roles"] = len(planner.get_roles())
            self._send_json(stats, head_only=head_only)
            return

        # 12. REST API: /health, /api/diagnostics or /api/health
        if path in ("/health", "/api/health", "/api/diagnostics"):
            self._send_json(self._health_payload(cat, dag, planner), head_only=head_only)
            return

        # 13. REST API: /api/simulate-velocity
        if path == "/api/simulate-velocity":
            target = query_params.get("target", query_params.get("role", ["cloud_security_architect"]))[0]
            hours_raw = query_params.get("hours", query_params.get("weekly_hours", ["10"]))[0]
            exp_lvl = (query_params.get("experience_level", query_params.get("level", ["intermediate"]))[0] or "intermediate").lower()
            trials_raw = query_params.get("trials", ["300"])[0]

            try:
                hours = _parse_float_param(hours_raw, "hours", default=10.0, min_val=1.0, max_val=168.0)
                trials = _parse_int_param(trials_raw, "trials", default=300, min_val=10, max_val=5000)
                if exp_lvl not in ("beginner", "intermediate", "advanced", "expert"):
                    raise ValueError("Parameter 'experience_level' must be beginner, intermediate, advanced, or expert")
            except ValueError as exc:
                self._send_error(str(exc), status=HTTPStatus.BAD_REQUEST, head_only=head_only)
                return

            try:
                from .velocity_simulator import simulate_velocity

                plan = planner.generate_roadmap(target_role_or_cert=target, weekly_hours=max(1, int(hours or 10)))
                report = simulate_velocity(
                    plan,
                    weekly_hours=hours or 10.0,
                    experience_level=exp_lvl,
                    simulation_trials=trials or 300,
                )
                self._send_json(report.to_dict(), head_only=head_only)
            except ValueError as exc:
                self._send_error(str(exc), status=HTTPStatus.BAD_REQUEST, head_only=head_only)
            except Exception:
                self._send_error("Error simulating velocity", status=HTTPStatus.BAD_REQUEST, head_only=head_only)
            return

        # 14. REST API: /api/roi
        if path == "/api/roi":
            cid = query_params.get("cert_id", query_params.get("cert", query_params.get("id", [None])))[0]
            if not cid:
                self._send_error("Parameter 'cert_id' is required", status=HTTPStatus.BAD_REQUEST, head_only=head_only)
                return
            cert = cat.get(cid) or (cat.search(query=cid) or [None])[0]
            if not cert:
                self._send_error(f"Certification '{cid}' not found", status=HTTPStatus.NOT_FOUND, head_only=head_only)
                return
            from .roi_calculator import calculate_cert_roi

            self._send_json(calculate_cert_roi(cert).to_dict(), head_only=head_only)
            return

        # 15. REST API: /api/overlap
        if path == "/api/overlap":
            cid_a = query_params.get("cert_a", [None])[0]
            cid_b = query_params.get("cert_b", [None])[0]
            if not cid_a or not cid_b:
                self._send_error(
                    "Parameters 'cert_a' and 'cert_b' are both required",
                    status=HTTPStatus.BAD_REQUEST,
                    head_only=head_only,
                )
                return
            c_a = cat.get(cid_a) or (cat.search(query=cid_a) or [None])[0]
            c_b = cat.get(cid_b) or (cat.search(query=cid_b) or [None])[0]
            if not c_a or not c_b:
                self._send_error(
                    "One or both certifications not found in catalog",
                    status=HTTPStatus.NOT_FOUND,
                    head_only=head_only,
                )
                return
            from .roi_calculator import calculate_skill_overlap

            self._send_json(calculate_skill_overlap(c_a, c_b).to_dict(), head_only=head_only)
            return

        # 16. REST API: /api/valuation
        if path == "/api/valuation":
            certs_raw = query_params.get("certs", query_params.get("ids", [""]))[0]
            role = query_params.get("role", [None])[0]
            try:
                if certs_raw:
                    cert_ids = [x.strip() for x in certs_raw.split(",") if x.strip()]
                elif role:
                    plan = planner.generate_roadmap(role)
                    cert_ids = [c.id for c in plan.all_certifications]
                else:
                    plan = planner.generate_roadmap("cloud_solutions_architect")
                    cert_ids = [c.id for c in plan.all_certifications]
            except ValueError as exc:
                self._send_error(str(exc), status=HTTPStatus.BAD_REQUEST, head_only=head_only)
                return

            from .roi_calculator import evaluate_portfolio

            self._send_json(evaluate_portfolio(cert_ids, catalog=cat).to_dict(), head_only=head_only)
            return

        # 17. Static file handling from public directory (with strict symlink containment)
        pub_dir = self._get_public_dir()
        clean_rel_path = _safe_rel(path)
        if clean_rel_path:
            target_file = pub_dir / clean_rel_path
            try:
                pub_resolved = pub_dir.resolve()
                resolved_target = target_file.resolve()
            except OSError:
                resolved_target = None
                pub_resolved = None

            if resolved_target is not None and pub_resolved is not None:
                if not resolved_target.is_relative_to(pub_resolved):
                    self._send_error(
                        "Forbidden: path escapes static root",
                        status=HTTPStatus.FORBIDDEN,
                        head_only=head_only,
                    )
                    return
                if resolved_target.exists() and resolved_target.is_file():
                    self._serve_file(resolved_target, head_only=head_only)
                    return

        self._send_error(f"Endpoint '{path}' not found", status=HTTPStatus.NOT_FOUND, head_only=head_only)

    def _read_json_body(self) -> Optional[Dict[str, Any]]:
        """Safely validate Content-Length, enforce MAX_BODY_BYTES, and parse dict JSON body."""
        raw_cl = self.headers.get("Content-Length")
        if raw_cl is None or not raw_cl.strip():
            self._send_error("Missing or invalid Content-Length header", status=HTTPStatus.BAD_REQUEST)
            return None

        try:
            content_length = int(raw_cl.strip())
        except ValueError:
            self._send_error("Invalid Content-Length header: must be a non-negative integer", status=HTTPStatus.BAD_REQUEST)
            return None

        if content_length < 0:
            self._send_error("Invalid Content-Length header: negative length rejected", status=HTTPStatus.BAD_REQUEST)
            return None

        if content_length > MAX_BODY_BYTES:
            self._send_error(
                f"Payload too large: exceeds maximum allowed size of {MAX_BODY_BYTES} bytes",
                status=HTTPStatus.REQUEST_ENTITY_TOO_LARGE,
            )
            return None

        if content_length == 0:
            return {}

        try:
            raw_bytes = self.rfile.read(content_length)
            raw_text = raw_bytes.decode("utf-8")
            parsed = json.loads(raw_text)
        except (UnicodeDecodeError, json.JSONDecodeError):
            self._send_error("Invalid JSON request body", status=HTTPStatus.BAD_REQUEST)
            return None
        except Exception:
            self._send_error("Failed to read request body", status=HTTPStatus.BAD_REQUEST)
            return None

        if not isinstance(parsed, dict):
            self._send_error("JSON request body must be an object", status=HTTPStatus.BAD_REQUEST)
            return None

        return parsed

    def do_POST(self) -> None:
        """Handle POST requests for roadmap generation, comparison, ROI, velocity, and search."""
        if not self._guard_host_and_origin():
            return

        body = self._read_json_body()
        if body is None:
            return

        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        cat, dag, planner = self._ensure_engines()

        if path == "/api/plan":
            role = body.get("role") or body.get("target_role")
            target = body.get("target") or body.get("target_cert")
            if role is not None and not isinstance(role, str):
                self._send_error("Parameter 'role' must be a string", status=HTTPStatus.BAD_REQUEST)
                return
            if target is not None and not isinstance(target, str):
                self._send_error("Parameter 'target' must be a string", status=HTTPStatus.BAD_REQUEST)
                return
            try:
                current = _parse_str_list(body.get("current") if "current" in body else body.get("current_certs"), "current_certs")
                hours_raw = body.get("weekly_hours") if "weekly_hours" in body else body.get("hours")
                hours = _parse_int_param(hours_raw, "weekly_hours", default=10, min_val=1, max_val=168)
                budget = _parse_float_param(body.get("max_budget"), "max_budget", default=None, min_val=0.0, max_val=1_000_000.0)
            except ValueError as exc:
                self._send_error(str(exc), status=HTTPStatus.BAD_REQUEST)
                return

            target_spec = role if role else (target if target else "cloud_security_architect")
            try:
                plan = planner.generate_roadmap(
                    target_role_or_cert=target_spec,
                    current_certs=current,
                    weekly_hours=hours or 10,
                    max_budget=budget,
                )
                self._send_json(plan.to_dict())
            except ValueError as exc:
                self._send_error(str(exc), status=HTTPStatus.BAD_REQUEST)
            except Exception:
                self._send_error("Error generating roadmap plan", status=HTTPStatus.BAD_REQUEST)
            return

        if path == "/api/compare":
            try:
                cert_ids = _parse_str_list(body.get("ids") if "ids" in body else body.get("cert_ids"), "ids")
            except ValueError as exc:
                self._send_error(str(exc), status=HTTPStatus.BAD_REQUEST)
                return
            if not cert_ids:
                self._send_error("JSON body must contain non-empty 'ids' list", status=HTTPStatus.BAD_REQUEST)
                return

            compared = []
            for cid in cert_ids[:20]:
                c = cat.get_by_id(cid)
                if c:
                    d = c.to_dict(camel_case=True)
                    d["difficultyScore"] = dag.difficulty_score(cid)
                    d["prereqCount"] = len(dag.resolve_prerequisites(cid))
                    d["unlockedCount"] = len(dag.resolve_dependents(cid))
                    compared.append(d)

            self._send_json({"count": len(compared), "certifications": compared})
            return

        if path == "/api/search":
            q = body.get("query") if "query" in body else body.get("q")
            provider = body.get("provider")
            level = body.get("level")
            category = body.get("category")
            skill = body.get("skill")
            for k, v in (("query", q), ("provider", provider), ("level", level), ("category", category), ("skill", skill)):
                if v is not None and not isinstance(v, str):
                    self._send_error(f"Parameter '{k}' must be a string", status=HTTPStatus.BAD_REQUEST)
                    return

            try:
                limit = _parse_int_param(body.get("limit"), "limit", default=None, min_val=1, max_val=500)
            except ValueError as exc:
                self._send_error(str(exc), status=HTTPStatus.BAD_REQUEST)
                return

            results = cat.search(query=q, provider=provider, level=level, category=category, skill=skill)
            if limit is not None:
                results = results[:limit]
            self._send_json([c.to_dict(camel_case=True) for c in results])
            return

        if path == "/api/simulate-velocity":
            target = body.get("target") or body.get("role") or "cloud_security_architect"
            if not isinstance(target, str):
                self._send_error("Parameter 'target' must be a string", status=HTTPStatus.BAD_REQUEST)
                return
            exp_lvl = body.get("experience_level") or "intermediate"
            if not isinstance(exp_lvl, str) or exp_lvl.lower() not in ("beginner", "intermediate", "advanced", "expert"):
                self._send_error("Parameter 'experience_level' must be beginner, intermediate, advanced, or expert", status=HTTPStatus.BAD_REQUEST)
                return
            try:
                hours_raw = body.get("weekly_hours") if "weekly_hours" in body else body.get("hours")
                hours = _parse_float_param(hours_raw, "weekly_hours", default=10.0, min_val=1.0, max_val=168.0)
                current = _parse_str_list(body.get("current_certs") if "current_certs" in body else body.get("current"), "current_certs")
                trials = _parse_int_param(body.get("trials"), "trials", default=300, min_val=10, max_val=5000)
            except ValueError as exc:
                self._send_error(str(exc), status=HTTPStatus.BAD_REQUEST)
                return

            try:
                from .velocity_simulator import simulate_velocity

                plan = planner.generate_roadmap(
                    target_role_or_cert=target,
                    current_certs=current,
                    weekly_hours=max(1, int(hours or 10)),
                )
                report = simulate_velocity(
                    plan,
                    weekly_hours=hours or 10.0,
                    experience_level=exp_lvl.lower(),
                    simulation_trials=trials or 300,
                )
                self._send_json(report.to_dict())
            except ValueError as exc:
                self._send_error(str(exc), status=HTTPStatus.BAD_REQUEST)
            except Exception:
                self._send_error("Error simulating velocity", status=HTTPStatus.BAD_REQUEST)
            return

        if path == "/api/roi":
            cid = body.get("cert_id") or body.get("cert") or body.get("id")
            if not cid or not isinstance(cid, str):
                self._send_error("Body must contain string 'cert_id'", status=HTTPStatus.BAD_REQUEST)
                return
            cert = cat.get(cid) or (cat.search(query=cid) or [None])[0]
            if not cert:
                self._send_error(f"Certification '{cid}' not found", status=HTTPStatus.NOT_FOUND)
                return
            from .roi_calculator import calculate_cert_roi

            self._send_json(calculate_cert_roi(cert).to_dict())
            return

        if path == "/api/overlap":
            cid_a = body.get("cert_a") or body.get("cert_a_id")
            cid_b = body.get("cert_b") or body.get("cert_b_id")
            if not cid_a or not cid_b or not isinstance(cid_a, str) or not isinstance(cid_b, str):
                self._send_error("Body must contain string 'cert_a' and 'cert_b'", status=HTTPStatus.BAD_REQUEST)
                return
            c_a = cat.get(cid_a) or (cat.search(query=cid_a) or [None])[0]
            c_b = cat.get(cid_b) or (cat.search(query=cid_b) or [None])[0]
            if not c_a or not c_b:
                self._send_error("One or both certifications not found in catalog", status=HTTPStatus.NOT_FOUND)
                return
            from .roi_calculator import calculate_skill_overlap

            self._send_json(calculate_skill_overlap(c_a, c_b).to_dict())
            return

        if path == "/api/valuation":
            role = body.get("role")
            if role is not None and not isinstance(role, str):
                self._send_error("Parameter 'role' must be a string", status=HTTPStatus.BAD_REQUEST)
                return
            try:
                cert_ids = _parse_str_list(body.get("cert_ids") if "cert_ids" in body else body.get("certs"), "cert_ids")
            except ValueError as exc:
                self._send_error(str(exc), status=HTTPStatus.BAD_REQUEST)
                return

            try:
                if role and not cert_ids:
                    plan = planner.generate_roadmap(role)
                    cert_ids = [c.id for c in plan.all_certifications]
                elif not cert_ids:
                    plan = planner.generate_roadmap("cloud_solutions_architect")
                    cert_ids = [c.id for c in plan.all_certifications]
            except ValueError as exc:
                self._send_error(str(exc), status=HTTPStatus.BAD_REQUEST)
                return

            from .roi_calculator import evaluate_portfolio

            self._send_json(evaluate_portfolio(cert_ids, catalog=cat).to_dict())
            return

        self._send_error(f"POST endpoint '{path}' not found", status=HTTPStatus.NOT_FOUND)


def create_server(
    host: str = "127.0.0.1",
    port: int = 8093,
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
    port: int = 8093,
    open_browser: bool = False,
    public_dir: Optional[Union[str, Path]] = None,
) -> None:
    """Start and run the CertPath Roadmap Studio HTTP Server."""
    server = create_server(host=host, port=port, public_dir=public_dir)
    url = f"http://{host}:{port}"
    print("============================================================")
    print(f"  CertPath Roadmap Studio UI Server v{SERVER_VERSION} Active")
    print(f"  URL: {url}")
    print("  Interactive Roadmap DAG, ROI & Velocity Studio Ready")
    print("  Press Ctrl+C to stop.")
    print("============================================================")

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
    parser = argparse.ArgumentParser(description="CertPath Roadmap Studio UI & REST Server")
    parser.add_argument("--host", default="127.0.0.1", help="Host interface to bind (default: 127.0.0.1)")
    parser.add_argument("--port", "-p", type=int, default=8093, help="Port to listen on (default: 8093)")
    parser.add_argument("--open", "-o", action="store_true", help="Automatically open studio in default browser")
    parser.add_argument("--public-dir", default=None, help="Custom public directory path")

    args = parser.parse_args()
    run_server(host=args.host, port=args.port, open_browser=args.open, public_dir=args.public_dir)


if __name__ == "__main__":
    main()
