"""Touch navigation and readable guide content while an animation request stalls."""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "app"))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.dev")
os.environ.setdefault("DJANGO_ALLOW_ASYNC_UNSAFE", "1")

from playwright.sync_api import expect, sync_playwright
from shoot import DevServer, port_open

PORT = 8873
SHOTS = ROOT / ".shots" / "mobile-directions"


def run():
    import django
    django.setup()
    from django.conf import settings
    from django.core.management import call_command
    assert settings.DEBUG and settings.DATABASES["default"]["ENGINE"].endswith("sqlite3")
    assert not port_open(PORT), "Do not reuse an unknown server"
    call_command("migrate", verbosity=0)
    SHOTS.mkdir(parents=True, exist_ok=True)
    base = f"http://127.0.0.1:{PORT}"
    engines = sys.argv[1:] or ["chromium"]
    with DevServer(PORT), sync_playwright() as pw:
        for engine in engines:
            browser = getattr(pw, engine).launch()
            options = dict(viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True)
            # A pending request must not prevent the guide body being parsed.
            ctx = browser.new_context(**options)
            pending = []
            ctx.route("**/js/view-transitions*.js", lambda route: pending.append(route))
            page = ctx.new_page()
            page.goto(base + "/recruit/#hardware", wait_until="commit")
            expect(page.locator("#hardware h2")).to_be_visible(timeout=6000)
            expect(page.locator("#hardware .fold-body").first).to_be_visible()
            for route in pending:
                route.abort()
            ctx.close()
            print(f"{engine}: guide remains readable with animation script pending", flush=True)

            for script_enabled in (True, False):
                ctx = browser.new_context(**options, java_script_enabled=script_enabled)
                page = ctx.new_page()
                errors = []
                page.on("pageerror", lambda error: errors.append(str(error)))
                for target in ("hardware", "software", "training"):
                    page.goto(base + "/", wait_until="load")
                    link = page.locator(f'.nf-dir-card[href$="#{target}"]')
                    link.scroll_into_view_if_needed()
                    # Wait for the reveal transform before tapping the text.
                    if script_enabled:
                        page.wait_for_timeout(1500)
                    link.locator(".nf-link-more").tap()
                    page.wait_for_url(f"**/recruit/#{target}", wait_until="load")
                    heading = page.locator(f"#{target} h2")
                    expect(heading).to_be_in_viewport(timeout=10000)
                    expect(page.locator(f"#{target} .fold-body").first).to_be_visible()
                    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth + 1")
                    page.screenshot(path=str(SHOTS / f"{engine}-{target}-js{int(script_enabled)}.png"))
                    print(f"{engine}: touch {target}, JS={script_enabled}, visible content", flush=True)
                assert not errors, errors
                ctx.close()
            browser.close()


if __name__ == "__main__":
    run()
