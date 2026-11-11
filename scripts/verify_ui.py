"""
verify_ui.py
Automated Headless Playwright Verification Harness for CertPath Roadmap Studio.
Verifies triple-viewport responsiveness, zero console errors, zero horizontal overflow,
and unlocked open-access roadmap exports.
"""

import json
import os
import sys
import time
from pathlib import Path
from playwright.sync_api import sync_playwright

SHOT_DIR = Path(os.environ.get("SHOT_DIR", "/tmp/certpath_shots"))
SHOT_DIR.mkdir(parents=True, exist_ok=True)

PORT = int(os.environ.get("PORT", "8093"))
BASE_URL = f"http://127.0.0.1:{PORT}"


def verify() -> None:
    print(f"[TEST] Starting Playwright Headless Verification on {BASE_URL}...")

    viewports = [
        {"name": "home_mobile.jpg", "width": 390, "height": 844, "device": "Mobile (390x844)"},
        {"name": "home_tablet.jpg", "width": 820, "height": 1180, "device": "Tablet (820x1180)"},
        {"name": "home_desktop.jpg", "width": 1425, "height": 900, "device": "Desktop (1425x900)"},
    ]

    results = {
        "viewports": [],
        "openAccessPass": False,
        "consoleErrors": [],
    }

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-gpu", "--disable-dev-shm-usage"],
        )

        for vp in viewports:
            page = browser.new_page(viewport={"width": vp["width"], "height": vp["height"]})
            console_errors = []

            page.on("console", lambda msg: console_errors.append(msg.text) if msg.type == "error" else None)
            page.on("pageerror", lambda err: console_errors.append(str(err)))

            page.goto(BASE_URL, wait_until="networkidle")
            time.sleep(0.4)

            overflow = page.evaluate("() => document.documentElement.scrollWidth - document.documentElement.clientWidth")
            shot_path = SHOT_DIR / vp["name"]
            page.screenshot(path=str(shot_path), full_page=False, type="jpeg", quality=85)

            passed = len(console_errors) == 0 and overflow <= 1
            print(f"[VIEWPORT] {vp['device']}: ConsoleErrors={len(console_errors)}, Overflow={overflow}px -> {'PASS' if passed else 'FAIL'}")

            for err in console_errors:
                results["consoleErrors"].append(f"[{vp['device']}] {err}")

            results["viewports"].append({
                "device": vp["device"],
                "width": vp["width"],
                "height": vp["height"],
                "consoleErrors": len(console_errors),
                "overflow": f"{overflow}px",
                "passed": passed,
                "screenshot": str(shot_path),
            })

            if vp["width"] == 1425:
                badge = page.locator("#licenseBadge").inner_text().strip()
                results["openAccessPass"] = "UNLOCKED" in badge

            page.close()

        browser.close()

    with open(SHOT_DIR / "verification_results.json", "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)

    all_passed = (
        all(v["passed"] for v in results["viewports"])
        and results["openAccessPass"]
        and len(results["consoleErrors"]) == 0
    )

    if not all_passed:
        sys.exit(1)


if __name__ == "__main__":
    verify()
