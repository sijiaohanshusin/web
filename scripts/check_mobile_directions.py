"""Touch navigation and readable guide content without an animation dependency."""
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
            # The guide must render without requesting the optional animation.
            ctx = browser.new_context(**options)
            pending = []
            ctx.route("**/js/view-transitions*.js", lambda route: pending.append(route))
            page = ctx.new_page()
            page.goto(base + "/recruit/#hardware", wait_until="commit")
            expect(page.locator("#hardware h2")).to_be_visible(timeout=6000)
            expect(page.locator("#hardware .fold-body").first).to_be_visible()
            page.wait_for_load_state("load")
            assert not pending, "The guide must not request the transition script"
            for route in pending:
                route.abort()
            ctx.close()
            print(f"{engine}: guide readable without animation script", flush=True)

            for script_enabled, cancel in ((True, False), (True, True), (False, False)):
                ctx = browser.new_context(**options, java_script_enabled=script_enabled)
                if cancel:
                    # Outgoing transitions can be canceled without activation
                    # details. The site's listener must handle that early exit.
                    ctx.add_init_script("""addEventListener('pageswap', event => {
                        if (event.viewTransition) {
                            Object.defineProperty(event, 'activation', {value: null});
                            event.viewTransition.skipTransition();
                        }
                    });""")
                page = ctx.new_page()
                errors = []
                page.on("pageerror", lambda error, sink=errors: sink.append(str(error)))
                for target in (("hardware",) if cancel else ("hardware", "software", "training")):
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
                    if not script_enabled:
                        # Native chapter summaries remain operable without JS;
                        # the enhanced hash handler opens them automatically otherwise.
                        page.locator(f"#{target} > .rg-details > summary").tap()
                    expect(page.locator(f"#{target} .fold-body").first).to_be_visible()
                    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth + 1")
                    page.screenshot(path=str(SHOTS / f"{engine}-{target}-js{int(script_enabled)}-cancel{int(cancel)}.png"))
                    print(f"{engine}: touch {target}, JS={script_enabled}, canceled={cancel}, visible content", flush=True)
                assert not errors, errors
                ctx.close()
            browser.close()


if __name__ == "__main__":
    run()
