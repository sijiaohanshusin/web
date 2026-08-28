# -*- coding: utf-8 -*-
"""校验 3D 会标模块的行为契约。

关注点不是"好不好看"（那靠 preview_logo3d.py + shoot.py 看图），而是几条
容易出事的工程约束：

  1. 几何真的来自 SVG：走线数、焊盘数、aArc 属性齐全
  2. 脉冲链路的并联结构正确：从 pad-mid 分出的两条走线共享同一时间窗
  3. 空闲自转与脉冲推进真的在动（不是渲染了一帧静止画面）
  4. 悬停高亮命中正确的那条走线
  5. destroy() 真的释放：几何/贴图归零、canvas 摘除、WebGL 上下文丢弃
     —— 这条最重要，一个常驻的 WebGL 上下文在手机上很快就会顶到上限
  6. 真实 Django 页面上能用裸标识符按需加载（importmap 接线是否生效）

跑法：python scripts/check_logo3d.py
"""
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

from shoot import PORT, DevServer, StaticServer  # noqa: E402

SHOTS = REPO / ".shots"
PREVIEW = "/.shots/logo3d.html"

failures = []


def check(cond, label, detail=""):
    print(f"  {'OK  ' if cond else 'FAIL'} {label}" + (f"  {detail}" if detail else ""))
    if not cond:
        failures.append(label)


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    # 预览页依赖最新的 SVG 与模块，先重新生成
    import subprocess
    subprocess.run([sys.executable, str(REPO / "scripts" / "preview_logo3d.py")],
                   check=True, capture_output=True)

    from playwright.sync_api import sync_playwright

    static_port = PORT + 1
    with StaticServer(REPO, static_port), sync_playwright() as p:
        browser = p.chromium.launch()
        ctx = browser.new_context(viewport={"width": 1280, "height": 900})
        page = ctx.new_page()
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.goto(f"http://127.0.0.1:{static_port}{PREVIEW}", wait_until="load")
        page.wait_for_function("() => !!window.__logo3d", timeout=20000)

        print("几何来自 SVG")
        probe = page.evaluate("() => __logo3d.probe()")
        check(len(probe["traces"]) == 3, "解析出 3 条走线",
              ", ".join(t["name"] for t in probe["traces"]))
        check(len(probe["pads"]) == 3, "解析出 3 个焊盘")
        check(all(t["hasArc"] for t in probe["traces"]), "每条走线都有 aArc 弧长属性")
        check(probe["render"]["calls"] <= 10, "draw call 受控",
              f"{probe['render']['calls']} 次 / {probe['render']['tris']} 三角面")

        print("\n脉冲链路结构")
        layers = page.evaluate(
            "() => __logo3d.handles.s1.traceMeshes.map(m => ({"
            "  name: m.userData.traceName,"
            "  off: +m.material.userData.uniforms.uArcOffset.value.toFixed(4),"
            "  scale: +m.material.userData.uniforms.uArcScale.value.toFixed(4)}))"
        )
        by = {t["name"]: t for t in layers}
        check("trunk-in" in by and by["trunk-in"]["off"] == 0, "trunk-in 是链路起点")
        parallel = (
            "spiral" in by and "trunk-out" in by
            and abs(by["spiral"]["off"] - by["trunk-out"]["off"]) < 1e-6
            and abs(by["spiral"]["scale"] - by["trunk-out"]["scale"]) < 1e-6
        )
        check(parallel, "spiral 与 trunk-out 并联（共享时间窗，电流在 pad-mid 分流）",
              f"spiral {by.get('spiral')}, trunk-out {by.get('trunk-out')}")

        print("\n动起来了没有")
        rot_before = page.evaluate("() => __logo3d.handles.s1.object3D.rotation.y")
        page.wait_for_timeout(1200)
        rot_after = page.evaluate("() => __logo3d.handles.s1.object3D.rotation.y")
        check(abs(rot_after - rot_before) > 0.01, "空闲自转在推进",
              f"{rot_before:.4f} → {rot_after:.4f}")

        head_before = page.evaluate(
            "() => __logo3d.handles.s1.traceMeshes[0].material.userData.uniforms.uHead.value")
        page.wait_for_timeout(900)
        head_after = page.evaluate(
            "() => __logo3d.handles.s1.traceMeshes[0].material.userData.uniforms.uHead.value")
        check(head_before != head_after, "脉冲头在推进",
              f"{head_before:.3f} → {head_after:.3f}")

        # 手动定位的实例不应被自动推进接管
        s4_head = page.evaluate(
            "() => __logo3d.handles.s4.traceMeshes[0].material.userData.uniforms.uHead.value")
        check(abs(s4_head - 0.45) < 1e-6, "setPulse 定位不被自动推进覆盖", f"{s4_head}")

        print("\n悬停高亮")
        box = page.evaluate(
            """() => {
                const c = document.querySelector('#s2 canvas');
                const r = c.getBoundingClientRect();
                return { x: r.x, y: r.y, w: r.width, h: r.height };
            }"""
        )
        # 往画布中心偏左下打一下，那里是 spiral/trunk-out 的密集区
        page.mouse.move(box["x"] + box["w"] * 0.5, box["y"] + box["h"] * 0.62)
        page.wait_for_timeout(320)
        hl = page.evaluate(
            "() => __logo3d.handles.s2.traceMeshes.map(m => ({"
            "  name: m.userData.traceName,"
            "  hl: m.material.userData.uniforms.uHighlight.value }))"
        )
        lit = [h["name"] for h in hl if h["hl"] > 0]
        check(len(lit) <= 1, "同时最多高亮一条走线", f"点亮 {lit}")

        print("\ndestroy 释放显存")
        before = page.evaluate(
            "() => ({ g: __logo3d.handles.s4.renderer.info.memory.geometries,"
            "         t: __logo3d.handles.s4.renderer.info.memory.textures })"
        )
        result = page.evaluate("() => __logo3d.destroyOne()")
        page.wait_for_timeout(200)
        after = page.evaluate(
            "() => ({ g: __logo3d.handles.s4.renderer.info.memory.geometries,"
            "         t: __logo3d.handles.s4.renderer.info.memory.textures,"
            "         lost: __logo3d.handles.s4.renderer.getContext().isContextLost() })"
        )
        check(result["canvasRemoved"], "canvas 已从 DOM 摘除")
        check(after["g"] == 0, "几何已全部 dispose", f"{before['g']} → {after['g']}")
        # three 内部的 BRDF LUT 不属于实例资源，不会归零；实例自己的
        # envMap render target 与丝印贴图必须释放掉
        check(after["t"] <= 1, "实例贴图已释放", f"{before['t']} → {after['t']}")
        check(after["lost"], "WebGL 上下文已主动丢弃（移动端上下文数有上限）")

        print("\n无基板模式（Hero 叠粒子波场时用）")
        boardless = page.evaluate("() => __logo3d.mountBoardless()")
        check(boardless["meshes"] == 6, "只有 3 走线 + 3 焊盘，没有基板",
              f"{boardless['meshes']} 个网格")
        check(boardless["traces"] == 3 and boardless["pads"] == 3, "走线与焊盘齐全")
        # 不建基板就不该生成丝印贴图，只剩 envMap
        check(boardless["textures"] <= 2, "未生成丝印贴图", f"贴图 {boardless['textures']}")

        check(not errors, "预览页无未捕获异常", "; ".join(errors[:2]))
        ctx.close()
        browser.close()

    # ---------------- 真实 Django 页面上的按需加载 ----------------
    print("\n真实站点：裸标识符按需加载")
    with DevServer(PORT), sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_context(viewport={"width": 1280, "height": 900}).new_page()
        page.goto(f"http://127.0.0.1:{PORT}/", wait_until="load")
        ok = page.evaluate(
            """async () => {
                try {
                    const mod = await import("esta/logo-3d");
                    return { ok: typeof mod.mountLogo3D === 'function' };
                } catch (e) {
                    return { ok: false, err: String(e) };
                }
            }"""
        )
        check(ok.get("ok"), "importmap 的 esta/logo-3d 可解析并导出 mountLogo3D",
              ok.get("err", ""))
        three_ok = page.evaluate(
            """async () => {
                try {
                    const T = await import("three");
                    const L = await import("three/addons/loaders/SVGLoader.js");
                    const U = await import("three/addons/utils/BufferGeometryUtils.js");
                    return { ok: !!T.Scene && !!L.SVGLoader && !!U.mergeGeometries,
                             rev: T.REVISION };
                } catch (e) { return { ok: false, err: String(e) }; }
            }"""
        )
        check(three_ok.get("ok"), "three 与两个 addon 都能按裸标识符加载",
              f"three r{three_ok.get('rev', '?')} {three_ok.get('err', '')}")
        browser.close()

    print()
    if failures:
        print(f"{len(failures)} 项未通过：" + "、".join(failures))
        return 1
    print("3D 会标行为契约全部通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
