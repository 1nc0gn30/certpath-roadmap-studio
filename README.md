# 🗺️ CertPath Roadmap Studio

> **Intelligent Certification Directed Acyclic Graph (DAG) Solver, Career Roadmap Planner & FastMCP Protocol Server** with Interactive Canvas UI (design influenced by Material 3). Built with **100% pure Python standard library** (zero runtime dependencies).

[![CI](https://github.com/1nc0gn30/certpath-roadmap-studio/actions/workflows/ci.yml/badge.svg)](https://github.com/1nc0gn30/certpath-roadmap-studio/actions/workflows/ci.yml)
[![Python 3.9+](https://img.shields.io/badge/python-3.9+-blue.svg)](https://www.python.org/downloads/)
[![MCP 2024-11-05](https://img.shields.io/badge/MCP-2024--11--05-green.svg)](https://modelcontextprotocol.io/)
[![Zero Runtime Dependencies](https://img.shields.io/badge/dependencies-0%20runtime-brightgreen.svg)](#architecture)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

---

## 🌟 Highlights

- **🎯 137+ Tracked Certifications**: Comprehensive certification graph spanning AWS, Azure, Google Cloud, CompTIA, Cisco, ISC2, Offensive Security, Linux Foundation, HashiCorp, Kubernetes, Docker, Python, and AI/ML ecosystems.
- **⚡ Directed Acyclic Graph (DAG) Solver**: Recursive prerequisite resolution in topological order, downstream unlock calculations, critical path duration analysis, and difficulty scoring.
- **🚀 Personalized Career Roadmapping**: Multi-stage learning paths for 8+ career roles (`cloud_security_architect`, `ai_ml_engineer`, `fullstack_devops_lead`, `penetration_tester`, `data_platform_architect`, `soc_analyst`, `cloud_solutions_architect`, `devops_platform_engineer`).
- **🧠 Skill Gap Analyzer**: Computes match percentage between user-acquired competencies and target certifications or career archetypes with bridge credential recommendations.
- **📊 Universal Matrix Exporters**: Real-time export to valid **Mermaid flowcharts (`flowchart LR`/`TD`)**, **Markdown study guides with milestone checklists**, **ASCII prerequisite trees**, and **Schema.org JSON-LD**.
- **🌐 Interactive Web UI (Design influenced by Material 3)**: Crisp typography, subtle elevation cards, interactive SVG DAG roadmap canvas, career path wizard, and dark mode toggle.
- **🤖 FastMCP Model Context Protocol Server**: Direct stdio JSON-RPC 2.0 integration for Claude Desktop, Cursor, and Cline.
- **🛡️ 100% Pure Python Standard Library**: Zero third-party runtime dependencies. Compatible with Python 3.9–3.13 across Linux, macOS, Windows, and Termux.

---

## 🏗️ Architecture

```
                                  ┌───────────────────────────────┐
                                  │      Certification Catalog     │
                                  │  (137+ Tracked Credentials)   │
                                  └───────────────┬───────────────┘
                                                  │
                                                  ▼
                                  ┌───────────────────────────────┐
                                  │       DAG Graph Solver        │
                                  │  • Topological Sorting        │
                                  │  • Prerequisite Resolution    │
                                  │  • Critical Path Analysis     │
                                  └───────┬───────────────┬───────┘
                                          │               │
                     ┌────────────────────┴───┐       ┌───┴───────────────────┐
                     ▼                        ▼       ▼                       ▼
           ┌──────────────────┐     ┌──────────────────┐     ┌──────────────────┐
           │ Roadmap Planner  │     │ Matrix Exporter  │     │  FastMCP Server  │
           │ • 4-Phase Paths  │     │ • Mermaid DAG    │     │  • JSON-RPC 2.0  │
           │ • Skill-Gap Calc │     │ • Markdown Guide │     │  • 8 Native Tools│
           │ • Budget Tracker │     │ • ASCII Trees    │     │  • stdio Transp. │
           └─────────┬────────┘     └────────┬─────────┘     └────────┬─────────┘
                     │                       │                        │
                     └───────────────────────┼────────────────────────┘
                                             │
                     ┌───────────────────────┴────────────────────────┐
                     │                                                │
                     ▼                                                ▼
       ┌───────────────────────────┐                    ┌───────────────────────────┐
       │   Multi-OS Terminal CLI   │                    │  Material 3 Studio Web UI │
       │ • 13 Interactive Commands │                    │ • SVG DAG Visualizer      │
       │ • --no-color Support      │                    │ • Career Planner Wizard   │
       │ • Cross-Platform Native   │                    │ • 1-Click Code Exporter   │
       └───────────────────────────┘                    └───────────────────────────┘
```

---

## 🚀 Quick Start

### 1. Installation

```bash
# Clone the repository
git clone https://github.com/1nc0gn30/certpath-roadmap-studio.git
cd certpath-roadmap-studio

# No external runtime dependencies required!
python3 -m certpath_roadmap_studio.cli --version
```

### 2. Launch the Material 3 Studio Web UI

```bash
python3 -m certpath_roadmap_studio.cli serve --port 8080
```
Open [http://localhost:8080](http://localhost:8080) to explore the visual DAG roadmap canvas, career wizard, and prerequisite trees.

---

## 💻 CLI Command Guide

```bash
# Search certifications by keyword, category, or level
python3 -m certpath_roadmap_studio.cli search "Kubernetes" --level Advanced

# Calculate complete prerequisite chain in topological order
python3 -m certpath_roadmap_studio.cli prereqs cloud-cks

# View certifications unlocked by a foundational credential
python3 -m certpath_roadmap_studio.cli unlocked soft-comptia-sec-plus

# Generate a personalized career roadmap for a target role
python3 -m certpath_roadmap_studio.cli plan --role cloud_security_architect --hours 15 --format text

# Export a customized study guide to Markdown
python3 -m certpath_roadmap_studio.cli plan --role ai_ml_engineer --format md > study_plan.md

# Compare 2+ certifications side-by-side
python3 -m certpath_roadmap_studio.cli compare cyber-sec-plus cyber-cysa-plus cyber-cissp

# Output Mermaid flowchart syntax for a roadmap or category
python3 -m certpath_roadmap_studio.cli mermaid cloud_security_architect

# Output ASCII prerequisite tree
python3 -m certpath_roadmap_studio.cli tree cyber-cissp

# View catalog telemetry and DAG diagnostics
python3 -m certpath_roadmap_studio.cli stats
python3 -m certpath_roadmap_studio.cli doctor
```

---

## 🌐 REST API Endpoints

When running `python3 -m certpath_roadmap_studio.cli serve` or `ui_server.py`, the embedded HTTP server exposes full REST API endpoints:

| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `GET` | `/api/catalog` | Filter and list certifications (`?q=`, `?category=`, `?provider=`, `?level=`, `?limit=`) |
| `GET` | `/api/cert/<id>` | Retrieve full certification details with resolved prerequisites and difficulty score |
| `GET` | `/api/prereqs/<id>` | Return complete prerequisite dependency chain in topological order |
| `GET` | `/api/unlocked/<id>` | Return all downstream certifications unlocked directly or transitively |
| `GET`/`POST` | `/api/plan` | Generate personalized career roadmap (`?role=`, `?target=`, `?hours=`, `?current=`) |
| `GET`/`POST` | `/api/compare` | Compare 2+ certifications side-by-side (`?ids=id1,id2`) |
| `GET` | `/api/roles` | List all built-in career role templates |
| `GET` | `/api/mermaid` | Generate live Mermaid flowchart syntax for a role or target cert |
| `GET` | `/api/stats` | Telemetry, category distribution, and DAG validation metrics |
| `GET` | `/api/diagnostics` | System health check and toolchain diagnostics |

---

## 🤖 MCP Server Setup

Add **CertPath Roadmap Studio** to your AI client configuration:

### Claude Desktop (`claude_desktop_config.json`)
```json
{
  "mcpServers": {
    "certpath-roadmap": {
      "command": "python3",
      "args": [
        "-m",
        "certpath_roadmap_studio.cli",
        "mcp"
      ],
      "cwd": "/path/to/certpath-roadmap-studio"
    }
  }
}
```

### Cursor (`.cursor/mcp.json`)
```json
{
  "mcpServers": {
    "certpath-roadmap": {
      "command": "python3",
      "args": ["-m", "certpath_roadmap_studio.cli", "mcp"],
      "cwd": "/path/to/certpath-roadmap-studio"
    }
  }
}
```

### Cline (`cline_mcp_settings.json`)
```json
{
  "mcpServers": {
    "certpath-roadmap": {
      "command": "python3",
      "args": ["-m", "certpath_roadmap_studio.cli", "mcp"]
    }
  }
}
```

### Registered FastMCP Tools

| Tool | Description |
| :--- | :--- |
| `certpath_search` | Search 137+ certifications by keyword, provider, level, or skill. |
| `certpath_resolve_prereqs` | Return complete prerequisite dependency chain in topological order. |
| `certpath_plan_career` | Generate customized 4-phase learning journey for a career role or target credential. |
| `certpath_compare` | Side-by-side comparison matrix across difficulty, domains, fees, and study hours. |
| `certpath_export_dag` | Export roadmap DAG to Mermaid, ASCII tree, or JSON-LD format. |
| `certpath_roles` | List all built-in career role templates. |
| `certpath_catalog_stats` | Retrieve catalog telemetry, domain distribution, and DAG validation metrics. |
| `certpath_diagnostics` | Check toolchain health, filesystem integrity, and OS compatibility. |

---

## 🧪 Running Tests

```bash
pytest -v
```

87/87 tests passing with 100% standard library compliance across Linux, macOS, and Windows.

---

## 📜 License

MIT License &copy; 2026 1nc0gn30
