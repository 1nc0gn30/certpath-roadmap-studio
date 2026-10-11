"""
verify_ui.py
Automated Headless Playwright Verification Harness for CertPath Roadmap Studio Pro
Triple-Viewport Responsiveness, Zero Console Errors, Zero Horizontal Overflow,
Action Interception, Instant Key Activation, and Clean URL Parameter Strip.
"""

import sys
import time
import json
from pathlib import Path
from playwright.sync_api import sync_playwright

SHOT_DIR = Path('/home/zoth/.gemini/antigravity-cli/brain/302ed169-2fc4-4fe5-98e4-ebd229505405/pod_shots/certpath_roadmap_studio')
SHOT_DIR.mkdir(parents=True, exist_ok=True)

PORT = 8879
BASE_URL = f"http://127.0.0.1:{PORT}"

def verify():
    print(f"[TEST] Starting Python Playwright Headless Verification on {BASE_URL}...")

    viewports = [
        {"name": "home_mobile.jpg", "width": 390, "height": 844, "device": "Mobile (iPhone 14)"},
        {"name": "home_tablet.jpg", "width": 820, "height": 1180, "device": "Tablet (iPad Air)"},
        {"name": "home_desktop.jpg", "width": 1425, "height": 900, "device": "Desktop (HD)"},
    ]

    results = {
        "viewports": [],
        "interceptionPass": False,
        "keyActivationPass": False,
        "urlParamPass": False,
        "consoleErrors": []
    }

    with sync_playwright() as p:
        browser = p.chromium.launch(
            executable_path="/usr/bin/google-chrome",
            headless=True,
            args=["--no-sandbox", "--disable-gpu", "--disable-dev-shm-usage"]
        )

        # 1. Triple Viewport Tests
        for vp in viewports:
            page = browser.new_page(viewport={"width": vp["width"], "height": vp["height"]})
            console_errors = []

            page.on("console", lambda msg: console_errors.append(msg.text) if msg.type == "error" else None)
            page.on("pageerror", lambda err: console_errors.append(str(err)))

            page.goto(BASE_URL, wait_until="networkidle")
            time.sleep(0.5)

            overflow = page.evaluate("() => document.documentElement.scrollWidth - document.documentElement.clientWidth")

            shot_path = SHOT_DIR / vp["name"]
            page.screenshot(path=str(shot_path), full_page=False, type="jpeg", quality=85)

            passed = (len(console_errors) == 0 and overflow <= 1)
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
                "screenshot": str(shot_path)
            })

            page.close()

        # 2. Interactive Interception & Key Verification Test
        context = browser.new_context(viewport={"width": 1425, "height": 900})
        page = context.new_page()
        interactive_errors = []

        page.on("console", lambda msg: interactive_errors.append(msg.text) if msg.type == "error" else None)
        page.on("pageerror", lambda err: interactive_errors.append(str(err)))

        page.goto(BASE_URL, wait_until="networkidle")
        time.sleep(0.5)

        badge_el = page.locator("#licenseBadge")
        initial_badge = badge_el.inner_text().strip()
        print(f"[BADGE] Initial badge text: '{initial_badge}'")

        # Trigger action interception on #btn-paywall-key
        print("[ACTION] Triggering #btn-paywall-key to test paywall interception...")
        page.click("#btn-paywall-key")
        time.sleep(0.4)

        modal_open = page.evaluate("() => { const m = document.getElementById('certpathPaywallModal') || document.getElementById('licenseModal'); return m && (m.classList.contains('open') || window.getComputedStyle(m).display !== 'none'); }")
        print(f"[MODAL] Paywall modal is open: {modal_open}")
        results["interceptionPass"] = bool(modal_open)

        paywall_shot = SHOT_DIR / "paywall_modal.jpg"
        page.screenshot(path=str(paywall_shot), full_page=False, type="jpeg", quality=85)

        # Enter Key CERTPATH-PRO-2026 and Activate
        print("[LICENSE] Entering key 'CERTPATH-PRO-2026' in modal...")
        page.fill("#license-input", "CERTPATH-PRO-2026")
        page.click("#btnActivateKey")
        time.sleep(0.9)

        unlocked_badge = page.locator("#licenseBadge").inner_text().strip()
        banner_hidden = page.evaluate("() => { const b = document.getElementById('salesBanner') || document.querySelector('.sales-banner-top'); return !b || window.getComputedStyle(b).display === 'none'; }")
        modal_closed = page.evaluate("() => { const m = document.getElementById('certpathPaywallModal') || document.getElementById('licenseModal'); return !m || window.getComputedStyle(m).display === 'none'; }")

        print(f"[LICENSE] Unlocked badge: '{unlocked_badge}'")
        print(f"[LICENSE] Sales banner hidden: {banner_hidden}")
        print(f"[LICENSE] Paywall modal closed: {modal_closed}")

        results["keyActivationPass"] = ("PRO ACTIVE" in unlocked_badge and banner_hidden and modal_closed)

        unlocked_shot = SHOT_DIR / "pro_active_unlocked.jpg"
        page.screenshot(path=str(unlocked_shot), full_page=False, type="jpeg", quality=85)

        for err in interactive_errors:
            results["consoleErrors"].append(f"[Interactive] {err}")

        context.close()

        # 3. URL Parameter Licensing Test (?licensed=true)
        context_param = browser.new_context(viewport={"width": 1425, "height": 900})
        page_param = context_param.new_page()
        param_errors = []

        page_param.on("console", lambda msg: param_errors.append(msg.text) if msg.type == "error" else None)
        page_param.on("pageerror", lambda err: param_errors.append(str(err)))

        print(f"[URL_PARAM] Navigating to {BASE_URL}/?licensed=true...")
        page_param.goto(f"{BASE_URL}/?licensed=true", wait_until="networkidle")
        time.sleep(0.5)

        param_badge = page_param.locator("#licenseBadge").inner_text().strip()
        current_url = page_param.url
        print(f"[URL_PARAM] Badge after ?licensed=true: '{param_badge}'")
        print(f"[URL_PARAM] Cleaned URL: {current_url}")

        url_cleaned = ("licensed=true" not in current_url)
        results["urlParamPass"] = ("PRO ACTIVE" in param_badge and url_cleaned)

        for err in param_errors:
            results["consoleErrors"].append(f"[URL Param] {err}")

        context_param.close()
        browser.close()

    print("\n" + "="*50)
    print("PLAYWRIGHT HEADLESS VERIFICATION SUMMARY")
    print("="*50)
    print(f"Total Console Errors: {len(results['consoleErrors'])}")
    print(f"Action Interception Pass: {results['interceptionPass']}")
    print(f"Key Activation Pass: {results['keyActivationPass']}")
    print(f"URL Param Pass: {results['urlParamPass']}")
    all_vp = all(v["passed"] for v in results["viewports"])
    print(f"All Viewports Pass: {all_vp}")
    overall = (len(results['consoleErrors']) == 0 and results['interceptionPass'] and results['keyActivationPass'] and results['urlParamPass'] and all_vp)
    print(f"OVERALL STATUS: {'✅ ALL TESTS PASSED' if overall else '❌ TEST FAILURES DETECTED'}")

    # Write telemetry summary JSON
    with open(SHOT_DIR / "verification_results.json", "w") as f:
        json.dump(results, f, indent=2)

    if not overall:
        sys.exit(1)

if __name__ == "__main__":
    verify()
