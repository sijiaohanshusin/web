"""Local-only browser acceptance for v4 editor and task help; never accepts a remote URL."""
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "app"))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.dev")
os.environ.setdefault("DJANGO_ALLOW_ASYNC_UNSAFE", "1")
from shoot import DevServer, do_login, port_open
from playwright.sync_api import sync_playwright, expect

PORT = 8805
SHOTS = ROOT / ".shots" / "experience"
ASSETS = ROOT / "app" / "helpcenter" / "assets"


def settle_images(page):
    # Full-page screenshots do not scroll, so lazy images need explicit activation.
    page.evaluate("""async () => {
        const images = [...document.querySelectorAll('img')];
        images.forEach(img => { img.loading = 'eager'; });
        await Promise.all(images.map(img => img.decode().catch(() => {})));
    }""")
    for img in page.locator('.hc-prose img').all():
        img.scroll_into_view_if_needed()
        expect(img).to_be_visible()
        assert img.evaluate('(img) => img.complete && img.naturalWidth > 0'), 'help screenshot failed to decode'
    page.evaluate('scrollTo(0, 0)')
    page.wait_for_timeout(250)


def run():
    import django
    django.setup()
    from django.conf import settings
    from django.core.management import call_command
    assert settings.DEBUG and settings.DATABASES["default"]["ENGINE"].endswith("sqlite3")
    assert not port_open(PORT), "Refuse to reuse an unknown server for write tests"
    call_command("migrate", verbosity=0)
    call_command("seed_showcase_editor")
    SHOTS.mkdir(parents=True, exist_ok=True)
    errors, checks = [], []
    with DevServer(PORT), sync_playwright() as pw:
        browser = pw.chromium.launch()
        ctx = browser.new_context(viewport={"width": 1440, "height": 1000}, reduced_motion="reduce")
        page = ctx.new_page()
        page.on("pageerror", lambda error: errors.append(str(error)))
        base = f"http://127.0.0.1:{PORT}"
        for width in (1440, 1024, 768, 390, 320):
            page.set_viewport_size({"width": width, "height": 920})
            for url, slug in (("/team/", "wall-empty"), ("/team/design-demo/", "wall-six"), ("/help/", "help"), ("/help/recruit/", "recruit"), ("/help/recruit/identity/", "article")):
                assert page.goto(base + url).status == 200
                page.evaluate("document.fonts.ready")
                settle_images(page)
                assert page.evaluate("document.documentElement.scrollWidth <= innerWidth + 1"), (width, url)
                if slug == 'article' and width < 1024:
                    expect(page.locator('.hc-sidebar details')).not_to_have_attribute('open')
                if url == "/team/":
                    assert page.locator(".sc-filters").count() == 0
                    assert page.locator(".sc-wall-heading").is_visible()
                page.screenshot(path=str(SHOTS / f"{slug}-{width}.png"), full_page=True)
                checks.append(f"{width} {url}: no overflow, HTTP 200")
        do_login(ctx, base, "showcase-review:LocalReview-Only-2026!")
        page.set_viewport_size({"width": 1440, "height": 1000})
        page.goto(base + "/accounts/showcase/")
        expect(page.locator("#field-nickname")).to_be_visible()
        expect(page.locator("#preview-status")).to_contain_text("预览已更新", timeout=25000)
        # A delayed save must not disable typing or replace newer input on response.
        pending = []
        def delay_save(route):
            data = route.request.post_data_json
            if data.get("action") == "save":
                pending.append(route)
            else:
                route.continue_()
        page.route("**/accounts/showcase/action/", delay_save)
        page.locator("#field-nickname").fill("演示成员初稿")
        page.wait_for_timeout(1800)
        assert pending, "autosave was not scheduled"
        expect(page.locator("#field-nickname")).to_be_enabled()
        page.locator("#field-nickname").fill("林序 · 示例")
        pending.pop(0).continue_()
        page.unroute("**/accounts/showcase/action/", delay_save)
        expect(page.locator("#save-state")).to_contain_text("草稿已保存", timeout=20000)
        expect(page.locator("#field-nickname")).to_have_value("林序 · 示例")
        checks.append("autosave preserves typing while request is pending")
        # Failed save pauses, preserves input, and can be retried manually.
        failed = []
        def fail_save(route):
            if route.request.post_data_json.get("action") == "save":
                failed.append(1)
                route.fulfill(status=503, content_type="application/json", body='{"error":"测试网络故障"}')
            else:
                route.continue_()
        page.route("**/accounts/showcase/action/", fail_save)
        page.locator("#field-nickname").fill("林序 · 网络恢复测试")
        expect(page.locator("#save-state")).to_contain_text("暂停", timeout=10000)
        page.wait_for_timeout(2800)
        assert len(failed) == 1, "failed autosave must not loop"
        expect(page.locator("#field-nickname")).to_have_value("林序 · 网络恢复测试")
        page.unroute("**/accounts/showcase/action/", fail_save)
        page.locator('[data-operation="save"]').first.click()
        expect(page.locator("#save-state")).to_contain_text("草稿已保存")
        page.locator("#field-nickname").fill("林序 · 示例")
        expect(page.locator("#save-state")).to_contain_text("草稿已保存", timeout=10000)
        checks.append("failed autosave pauses, retains input, manual retry succeeds")
        mapping = {"card-layout":"start", "card-content":"card", "page-layout":"page", "assets":"assets", "publish":"publish"}
        for section, name in mapping.items():
            page.goto(base + "/accounts/showcase/?section=" + section)
            expect(page.locator("#section-content h1")).to_be_visible()
            if section != "assets":
                expect(page.locator("#preview-status")).to_contain_text("预览已更新", timeout=20000)
            page.evaluate("document.fonts.ready")
            page.wait_for_timeout(900)
            page.screenshot(path=str(ASSETS / f"workspace-{name}.png"))
        for width in (1440, 1024, 768, 390, 320):
            page.set_viewport_size({"width":width, "height":920})
            for section in ("card-layout", "card-background", "page-layout", "publish"):
                page.goto(base + "/accounts/showcase/?section=" + section)
                expect(page.locator("#section-content h1")).to_be_visible()
                expect(page.locator("#preview-status")).to_contain_text("预览已更新", timeout=20000)
                assert page.evaluate("document.documentElement.scrollWidth <= innerWidth + 1"), (width, section)
                if width < 768:
                    expect(page.locator(".se-mobile-actions")).to_be_visible()
                    page.locator("#mobile-preview").click()
                    expect(page.locator("#mobile-preview")).to_have_attribute("aria-pressed", "true")
                    page.screenshot(path=str(SHOTS / f"editor-preview-{section}-{width}.png"))
                    page.locator("#mobile-preview").click()
                page.screenshot(path=str(SHOTS / f"editor-{section}-{width}.png"))
                checks.append(f"{width} editor {section}: no overflow, preview ready")
        page.set_viewport_size({"width":1440, "height":1000})
        page.goto(base + "/accounts/showcase/?section=publish")
        expect(page.locator("#publish-consent")).to_be_enabled(timeout=20000)
        page.locator("[data-publication-page]").uncheck()
        expect(page.locator("#publish-consent")).to_be_enabled(timeout=20000)
        page.locator("#publish-consent").check()
        page.locator('[data-operation="publish"]').click()
        expect(page.locator(".se-public-state")).to_contain_text("成员卡片已公开", timeout=20000)
        state = ctx.request.get(base + "/accounts/showcase/state/").json()
        guest = browser.new_context()
        assert guest.request.get(base + state["public_url"]).status == 404
        assert "林序 · 示例" in guest.request.get(base + "/team/").text()
        page.goto(base + "/accounts/showcase/")
        page.locator("#field-nickname").fill("尚未公开的新草稿")
        expect(page.locator("#save-state")).to_contain_text("草稿已保存", timeout=12000)
        wall = guest.request.get(base + "/team/").text()
        assert "尚未公开的新草稿" not in wall and "林序 · 示例" in wall
        checks.append("card-only UI publication is visible on wall, detail is 404, draft remains private")
        page.locator("#field-nickname").fill("林序 · 示例")
        expect(page.locator("#save-state")).to_contain_text("草稿已保存", timeout=12000)
        page.goto(base + "/accounts/showcase/?section=publish")
        expect(page.locator('[data-operation="withdraw"]')).to_be_visible()
        page.locator('[data-operation="withdraw"]').click()
        page.locator('[data-confirm-accept]').click()
        expect(page.locator(".se-public-state")).to_contain_text("已撤回", timeout=20000)
        assert "林序 · 示例" not in guest.request.get(base + "/team/").text()
        checks.append("UI withdrawal removes public card and preserves private draft")
        browser.close()
    assert not errors, errors
    (SHOTS / "checks.json").write_text(json.dumps(checks, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"PASS: {len(checks)} browser checks; screenshots: {SHOTS}")


if __name__ == "__main__":
    run()
