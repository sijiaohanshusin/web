# -*- coding: utf-8 -*-
"""生成 3D 会标的隔离预览页，供 shoot.py 截图审阅。

为什么单独做一页而不是直接塞进首页：Task 10 会整体重做 Hero，现在往首页里
装一遍、回头再拆一遍是白做。隔离页还有个好处 —— 排查时不受首页其他动效干扰。

**必须走 HTTP，不能用 file://**：ES module 有同源要求，file:// 下 import 会被
CORS 直接拒掉。所以页面里的路径全用根相对写法，由 shoot.py --serve 把仓库根
目录供出来。

跑法：
    python scripts/preview_logo3d.py
    python scripts/shoot.py --serve . --url /.shots/logo3d.html --desktop --wait 3000

页面挂了 window.__logo3d 句柄，配合 --eval 可以查装配结果与显存：
    --eval "__logo3d.probe()"
    --eval "__logo3d.destroyOne()"
"""
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
OUT = REPO / ".shots" / "logo3d.html"

# 全部用根相对路径：shoot.py --serve . 会把仓库根供在 http://127.0.0.1:8800
S = "/app/static"


def inline_svg() -> str:
    markup = (REPO / "app" / "static" / "brand" / "logo-mark.svg").read_text(encoding="utf-8")
    markup = "<svg" + markup.split("<svg", 1)[1]
    return re.sub(r"<!--.*?-->", "", markup, flags=re.S)


HTML = f"""<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8"><title>3D 会标预览</title>
<link rel="stylesheet" href="{S}/css/tokens.css">
<script type="importmap">
{{
  "imports": {{
    "three": "{S}/vendor/three.module.min.js",
    "three/addons/loaders/SVGLoader.js": "{S}/vendor/SVGLoader.js",
    "three/addons/utils/BufferGeometryUtils.js": "{S}/vendor/BufferGeometryUtils.js"
  }}
}}
</script>
<style>
  body {{ margin:0; background:var(--black); color:var(--text);
          font:14px/1.6 "Segoe UI","Microsoft YaHei",sans-serif; }}
  header {{ padding:18px 22px 10px; }}
  h1 {{ font-size:17px; margin:0 0 4px; color:#fff; }}
  header p {{ margin:0; color:var(--muted); font-size:12.5px; }}
  .grid {{ display:grid; grid-template-columns:repeat(2,1fr); gap:16px; padding:16px 22px 22px; }}
  .cell {{ border:1px solid var(--line-d); border-radius:14px; overflow:hidden; background:#07090c; }}
  .cell h2 {{ margin:0; padding:8px 12px; font:600 11.5px/1.5 var(--font-mono);
              letter-spacing:1px; color:var(--muted);
              border-bottom:1px solid var(--line-d); background:rgba(255,255,255,.02); }}
  .stage {{ height:420px; }}
  .hidden-src {{ position:absolute; width:0; height:0; overflow:hidden; }}
  #log {{ font:11.5px/1.7 var(--font-mono); color:var(--muted);
          padding:10px 22px 24px; white-space:pre-wrap; }}
</style></head>
<body>
<header>
  <h1>3D 会标预览</h1>
  <p>左上默认姿态 · 右上正面无脉冲 · 左下竖屏比例（检查是否裁掉图形）· 右下脉冲头定位 0.45</p>
</header>

<div class="hidden-src">{inline_svg()}</div>

<div class="grid">
  <div class="cell"><h2>默认 · 空闲自转</h2><div class="stage" id="s1"></div></div>
  <div class="cell"><h2>正面 · 脉冲关闭</h2><div class="stage" id="s2"></div></div>
  <div class="cell"><h2>竖屏 390 宽</h2><div class="stage" id="s3" style="max-width:390px"></div></div>
  <div class="cell"><h2>脉冲头 = 0.45</h2><div class="stage" id="s4"></div></div>
</div>

<header style="padding-top:6px"><h1>逐层制造过程（分镜 01 主叙事）</h1>
  <p>按真实 PCB 工艺顺序加层：基板 → 蚀刻铜箔 → 沉金焊盘 → 覆阻焊 → 印丝印。
     铜箔用弧长推进做蚀刻效果，前沿带一道热边。</p></header>
<div class="grid" id="tuning"></div>
<div id="log">初始化…</div>

<script type="module">
  import {{ mountLogo3D }} from "{S}/js/logo-3d.js";

  const logEl = document.getElementById('log');
  const log = (msg) => {{ logEl.textContent += "\\n" + msg; }};

  const handles = {{}};
  try {{
    handles.s1 = await mountLogo3D(document.getElementById('s1'), {{ autoRotate: true, idleDelay: 0 }});
    handles.s2 = await mountLogo3D(document.getElementById('s2'), {{ autoRotate: false }});
    handles.s2.setPulse(-1);
    handles.s3 = await mountLogo3D(document.getElementById('s3'), {{ autoRotate: false }});
    handles.s4 = await mountLogo3D(document.getElementById('s4'), {{ autoRotate: false }});
    handles.s4.setPulse(0.45);

    // 解构：需要倾斜视角才看得出层间距
    // 解构姿态候选网格：一次把几组 pitch/yaw/进度 铺开，靠一张截图选型，
    // 比一次改一个数字反复截图快得多
    // 逐层制造过程的关键帧：这是分镜 01 的主叙事
    const stages = [0.08, 0.28, 0.45, 0.60, 0.72, 0.88, 1.0, 0.0];
    const tuning = document.getElementById('tuning');
    for (const t of stages) {{
      const cell = document.createElement('div');
      cell.className = 'cell';
      cell.innerHTML = `<h2>制造进度 ${{t.toFixed(2)}}</h2>`;
      const stage = document.createElement('div');
      stage.className = 'stage';
      cell.appendChild(stage);
      tuning.appendChild(cell);
      const h = await mountLogo3D(stage, {{ autoRotate: false }});
      h.setPulse(-1);
      h.setOrientation(-0.30, 0.24, true);   // 立即落位，不等阻尼
      h.setAssembly(t);
      handles[`a_${{t}}`] = h;
    }}

    logEl.textContent = "四个实例装配完成";
    const h = handles.s1;
    log(`走线网格 ${{h.traceMeshes.length}} · 焊盘网格 ${{h.padMeshes.length}}`);
    for (const m of h.traceMeshes) {{
      const g = m.geometry;
      const u = m.material.userData.uniforms;
      log(`  ${{m.userData.traceName.padEnd(10)}} 顶点 ${{String(g.attributes.position.count).padStart(5)}}`
        + ` · aArc ${{g.attributes.aArc ? '有' : '缺失!'}}`
        + ` · 弧长 ${{(g.userData.arcLength || 0).toFixed(1)}}`
        + ` · 时间窗 [${{u.uArcOffset.value.toFixed(3)}}, ${{(u.uArcOffset.value + u.uArcScale.value).toFixed(3)}}]`);
    }}
    const info = h.renderer.info;
    log(`draw calls ${{info.render.calls}} · 三角面 ${{info.render.triangles}}`
      + ` · 几何 ${{info.memory.geometries}} · 贴图 ${{info.memory.textures}}`);
    log("层叠（自下而上）：" + h.layerInfo.map(l => `${{l.label}}(${{l.explodeZ}})`).join(" → "));

    window.__logo3d = {{
      handles,
      probe() {{
        const r = handles.s1.renderer;
        return {{
          traces: handles.s1.traceMeshes.map(m => ({{
            name: m.userData.traceName,
            verts: m.geometry.attributes.position.count,
            hasArc: !!m.geometry.attributes.aArc,
            win: [ +m.material.userData.uniforms.uArcOffset.value.toFixed(3),
                   +(m.material.userData.uniforms.uArcOffset.value
                     + m.material.userData.uniforms.uArcScale.value).toFixed(3) ],
          }})),
          pads: handles.s1.padMeshes.map(m => ({{
            name: m.userData.padName,
            emissive: +m.material.emissiveIntensity.toFixed(3),
          }})),
          render: {{ calls: r.info.render.calls, tris: r.info.render.triangles }},
          memory: {{ geometries: r.info.memory.geometries, textures: r.info.memory.textures }},
          contextLost: r.getContext().isContextLost(),
        }};
      }},
      destroyOne() {{
        const before = handles.s4.renderer.info.memory;
        const snapshot = {{ geometries: before.geometries, textures: before.textures }};
        handles.s4.destroy();
        return {{ before: snapshot, canvasRemoved: !document.querySelector('#s4 canvas') }};
      }},
      /** 逐个实例报告真实姿态与相机，用来定位"某一格角度不对"这类问题 */
      probeAll() {{
        const out = {{}};
        for (const [k, h] of Object.entries(handles)) {{
          const r = h.object3D.rotation;
          const el = h.renderer.domElement;
          out[k] = {{
            rot: [+r.x.toFixed(3), +r.y.toFixed(3)],
            camZ: +h.camera.position.z.toFixed(2),
            size: [el.clientWidth, el.clientHeight],
          }};
        }}
        return out;
      }},
      /** 验证无基板模式（Hero 里叠在粒子波场上时用） */
      async mountBoardless() {{
        const host = document.createElement('div');
        host.style.cssText = 'position:fixed;left:-9999px;width:400px;height:400px';
        document.body.appendChild(host);
        const h = await mountLogo3D(host, {{ showBoard: false, autoRotate: false }});
        const result = {{
          meshes: h.object3D.children.length,
          traces: h.traceMeshes.length,
          pads: h.padMeshes.length,
          textures: h.renderer.info.memory.textures,
        }};
        h.destroy();
        host.remove();
        return result;
      }},
    }};
  }} catch (err) {{
    logEl.textContent = "装配失败：" + (err && err.stack || err);
    throw err;
  }}
</script>
</body></html>
"""

OUT.parent.mkdir(exist_ok=True)
OUT.write_text(HTML, encoding="utf-8")
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
print(f"已生成 {OUT.relative_to(REPO)}")
print("接着跑： python scripts/shoot.py --serve . --url /.shots/logo3d.html --desktop --wait 3000")
