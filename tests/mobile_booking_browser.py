"""Isolated mobile browser smoke test; the payment and calendar APIs are mocked.
No checkout session, reservation, payment or production system is touched.
"""
import json
import os
from pathlib import Path
from playwright.sync_api import sync_playwright

BASE = os.environ.get("MOBILE_TEST_BASE", "http://127.0.0.1:8765")
OUT = Path(os.environ.get("MOBILE_TEST_OUTPUT", "mobile-qa"))
OUT.mkdir(exist_ok=True, parents=True)

quote = {
    "status": "free", "available": True, "message": "Termin frei.",
    "total": 115.0,
    "breakdown": {
        "room_total": 115.0, "extras": [], "discounts": [],
        "total": 115.0, "online_total": 115.0,
        "overnight_tax": {"known": True, "amount": 5.20},
        "stay_total": 120.20, "stay_total_known": True,
    },
}

with sync_playwright() as playwright:
    browser = playwright.chromium.launch(headless=True, args=["--no-sandbox"])
    for width in (320, 360, 390, 768, 1280):
        page = browser.new_page(viewport={"width": width, "height": 850}, device_scale_factor=1)
        page.route("**/api/calendar?*", lambda route: route.fulfill(
            status=200, content_type="application/json", body=json.dumps({
                "live": True, "days": {}, "updatedAt": "Isolierter Test"
            })))
        page.route("**/api/availability", lambda route: route.fulfill(
            status=200, content_type="application/json", body=json.dumps(quote)))
        page.route("**/api/stripe/status", lambda route: route.fulfill(
            status=200, content_type="application/json", body='{"ok":true,"configured":true}'))
        page.goto(BASE, wait_until="domcontentloaded", timeout=45000)
        page.wait_for_timeout(600)
        assert page.locator("#bookingForm").count() == 1
        assert page.locator("#bankDetailsAfterBooking").count() == 1
        assert not page.locator("body").inner_text().find("IBAN:") >= 0
        viewport_metrics = page.evaluate("""() => ({
            inner: window.innerWidth,
            doc: document.documentElement.scrollWidth,
            body: document.body.scrollWidth,
            offenders: [...document.querySelectorAll('body *')]
              .map(el => ({tag: el.tagName.toLowerCase(), id: el.id,
                  cls: String(el.className || '').slice(0,70),
                  right: Math.round(el.getBoundingClientRect().right)}))
              .filter(el => el.right > window.innerWidth + 3)
              .sort((a,b) => b.right-a.right).slice(0,12)
        })""")
        screenshot = page.screenshot(path=str(OUT / f"guest-home-{width}.png"), full_page=True)
        from io import BytesIO
        from PIL import Image
        png_width = Image.open(BytesIO(screenshot)).width
        print("MOBILE METRICS:", width, "image width", png_width, viewport_metrics, flush=True)
        assert png_width <= width + 2, f"Full-page screenshot wider than viewport at {width}px: {png_width}px"
        assert viewport_metrics["doc"] <= width + 2, f"Document overflow at {width}px"
        if width == 390:
            page.locator("#arrival").fill("2026-11-12")
            page.locator("#departure").fill("2026-11-13")
            page.locator("#checkAvailability").click()
            page.locator("#stayTotal").get_by_text("120", exact=False).wait_for(timeout=20000)
            assert "5,20" in page.locator("#taxAmount").inner_text()
            assert "120,20" in page.locator("#stayTotal").inner_text()
            assert "115,00" in page.locator("#totalPrice").inner_text()
            page.locator("#continueBooking").click()
            page.locator('input[value="Banküberweisung"]').check()
            assert page.locator("#bankDetailsAfterBooking").is_visible()
            assert "IBAN:" not in page.locator("#bookingForm").inner_text()
            assert page.locator("#bookingSubmit").is_visible()
            page.screenshot(path=str(OUT / "guest-checkout-390.png"), full_page=True)
        print(f"MOBILE PASS: {width}px; screenshot {png_width}px")
        page.close()
    browser.close()
