#!/usr/bin/env python3
"""CertPath Roadmap Studio Sovereign Server Launcher."""
import os
import sys
from pathlib import Path

# Add src to pythonpath
BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR / "src"))

from certpath_roadmap_studio.ui_server import run_server

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="CertPath Roadmap Studio Server")
    parser.add_argument("--host", default="127.0.0.1", help="Host interface to bind")
    parser.add_argument("--port", "-p", type=int, default=8093, help="Port to listen on (default: 8093)")
    parser.add_argument("--open", "-o", action="store_true", help="Open browser")
    args = parser.parse_args()

    pub_dir = BASE_DIR / "public"
    print(f"Starting CertPath Roadmap Studio on {args.host}:{args.port}...")
    run_server(host=args.host, port=args.port, open_browser=args.open, public_dir=pub_dir)
