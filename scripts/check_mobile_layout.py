"""Regressions from QQ browser screenshots: dark menu, forge overflow and fallbacks."""
import re
import sys
from pathlib import Path

from playwright.sync_api import expect, sync_playwright
from shoot import DevServer, port_open

ROOT = Path(__file__).resolve().parent.parent
SHOTS = ROOT / ".shots" / "mobile-layout"
PORT = 8875


def scroll_to(page, selector, offset=0):
    page.evaluate("""({selector, offset}) => {
        const y = document.querySelector(selector).getBoundingClientRect().top + scrollY + offset;
        const lenis = window.ESTA?.motion?.lenis;
        if (lenis) lenis.scrollTo(y, {immediate:true}); else scrollTo(0, y);
    }""", {"selector": selector, "offset": offset})
    page.wait_for_timeout(400)


def run():
    assert not port_open(PORT)
    SHOTS.mkdir(parents=True, exist_ok=True)
    with DevServer(PORT), sync_playwright() as pw:
        for engine in sys.argv[1:] or ["chromium"]:
            browser = getattr(pw, engine).launch()
            for width, height in ((360, 570), (390, 700), (390, 844), (768, 700)):
                ctx = browser.new_context(viewport={"width": width, "height": height}, is_mobile=True, has_touch=True)
                page = ctx.new_page()
                # QQ may expose WebGL yet fail to import or initialize the 3D renderer.
                page.route("**/logo-3d*.js", lambda route: route.fulfill(status=404, body=""))
                page.goto(f"http://127.0.0.1:{PORT}/", wait_until="load")
                page.wait_for_function("!document.documentElement.classList.contains('esta-pre-lock')")
                scroll_to(page, ".nf-forge-steps", -120)
                assert page.locator(".nf-forge-pin").evaluate("el => getComputedStyle(el).position") != "sticky"
                expect(page.locator(".nf-forge-steps span").last).to_be_visible()
                assert page.evaluate("""() => document.querySelector('.nf-forge-steps').getBoundingClientRect().bottom <=
                    document.querySelector('#nf-forge').getBoundingClientRect().bottom""")
                page.screenshot(path=str(SHOTS / f"{engine}-{width}x{height}-fallback.png"))
                scroll_to(page, "[data-nav=light]", 150)
                expect(page.locator("#site-nav")).to_have_class(re.compile(r".*nav-on-light.*"))
                page.locator("#nav-burger").tap()
                expect(page.locator("#nav-burger")).to_have_attribute("aria-expanded", "true")
                page.wait_for_timeout(450)
                colors = page.locator(".nav-title strong, .nav-links > a, .nav-group > summary").evaluate_all(
                    "els => els.map(el => getComputedStyle(el).color)")
                assert not any("14, 17, 22" in color for color in colors), colors
                expect(page.locator(".nav-links")).to_be_visible()
                page.locator(".nav-group > summary").first.tap()
                expect(page.locator(".nav-group-menu").first).to_be_visible()
                assert page.locator(".nav-group-menu a").first.evaluate("el => getComputedStyle(el).color") != "rgba(14, 17, 22, 0.66)"
                page.screenshot(path=str(SHOTS / f"{engine}-{width}x{height}-menu.png"))
                assert page.evaluate("document.documentElement.scrollWidth <= innerWidth + 1")
                print(f"{engine} {width}x{height}: fallback fits, menu remains readable on light section", flush=True)
                ctx.close()
            ctx = browser.new_context(viewport={"width": 360, "height": 570}, is_mobile=True, has_touch=True)
            page = ctx.new_page()
            page.goto(f"http://127.0.0.1:{PORT}/", wait_until="load")
            page.wait_for_selector("#nf-forge-stage.is-3d", timeout=25000)
            page.wait_for_function("!document.documentElement.classList.contains('esta-pre-lock')")
            scroll_to(page, "#nf-forge", 300)
            assert page.evaluate("""() => {
                const section = document.querySelector('#nf-forge');
                const grid = document.querySelector('.nf-forge-grid').getBoundingClientRect();
                const pin = document.querySelector('.nf-forge-pin').getBoundingClientRect();
                return !section.classList.contains('is-pinned') || (grid.top >= 74 && grid.bottom <= innerHeight + 1);
            }""")
            page.screenshot(path=str(SHOTS / f"{engine}-short-3d.png"))
            print(f"{engine}: mounted 3D fits short viewport or uses natural flow", flush=True)
            ctx.close()
            browser.close()


if __name__ == "__main__":
    run()
