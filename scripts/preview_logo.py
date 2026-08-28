# -*- coding: utf-8 -*-
"""生成会标预览对比页，供截图审阅。

纯几何校验能证明"坐标没画错"，但证明不了"接缝好不好看""小尺寸糊不糊"。
这个脚本把新矢量与原位图并排 + 叠加，并给出导航栏实际尺寸和暗底/亮底两种
场景，配合 scripts/shoot.py 一起用：

    python scripts/preview_logo.py
    python scripts/shoot.py --file .shots/logo-preview.html --desktop --viewport-only

叠加那一格是关键：矢量描成信号青半透明压在原位图上，任何偏移一眼可见。
"""
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SVG = REPO / "app" / "static" / "brand" / "logo-mark.svg"
PNG = REPO / "app" / "static" / "img" / "logo-mark.png"
OUT = REPO / ".shots" / "logo-preview.html"

import re  # noqa: E402

def inline(path: Path) -> str:
    """把 .svg 文件内容处理成可直接嵌进 HTML 的片段。"""
    markup = path.read_text(encoding="utf-8")
    markup = "<svg" + markup.split("<svg", 1)[1]
    return re.sub(r"<!--.*?-->", "", markup, flags=re.S)


svg_inline = inline(SVG)


def sized(markup: str, px: int, color: str) -> str:
    """把内联 SVG 套上尺寸与颜色。"""
    m = markup.replace("<svg", f'<svg width="{px}" height="{px}"', 1)
    return f'<span style="color:{color};display:inline-block;line-height:0">{m}</span>'


HTML = f"""<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8"><title>会标矢量审阅</title>
<style>
  :root {{ --ink:#0e1116; --paper:#f7f8fa; --black:#050506; --accent:#41d8e8; --copper:#c98a3d; }}
  * {{ box-sizing:border-box; margin:0; }}
  body {{ font:14px/1.6 "Segoe UI","Microsoft YaHei",sans-serif; background:var(--paper); color:var(--ink); padding:28px; }}
  h1 {{ font-size:19px; margin-bottom:4px; }}
  p.lead {{ color:#5f6774; margin-bottom:22px; }}
  .row {{ display:flex; gap:22px; flex-wrap:wrap; margin-bottom:26px; }}
  .cell {{ border:1px solid rgba(14,17,22,.12); border-radius:12px; overflow:hidden; background:#fff; }}
  .cell h2 {{ font-size:12px; font-weight:700; letter-spacing:.5px; padding:8px 12px;
             background:rgba(14,17,22,.045); border-bottom:1px solid rgba(14,17,22,.1); }}
  .cell .body {{ padding:16px; display:flex; align-items:center; justify-content:center; min-height:260px; }}
  /* 原位图是白色线稿，必须放暗底才看得见 */
  .dark .body, .onblack .body {{ background:var(--black); }}
  .overlay {{ position:relative; width:300px; height:300px; background:var(--black); }}
  .overlay img {{ position:absolute; inset:0; width:300px; height:300px; }}
  .overlay .vec {{ position:absolute; inset:0; color:var(--accent); opacity:.72; }}
  .overlay .vec svg {{ width:300px; height:300px; }}
  .strip {{ display:flex; align-items:flex-end; gap:20px; }}
  .strip figure {{ text-align:center; }}
  .strip figcaption {{ font:11px/1.4 ui-monospace,Consolas,monospace; color:#5f6774; margin-top:7px; }}
  .navbar {{ display:flex; align-items:center; gap:12px; height:74px; padding:0 20px;
            background:var(--black); border-radius:10px; }}
  .navbar .t strong {{ display:block; color:#fff; font-size:16.5px; letter-spacing:1.5px; }}
  .navbar .t small {{ display:block; color:#97a1b3; font:10.5px ui-monospace,Consolas,monospace; letter-spacing:3px; }}
  .navbar.light {{ background:var(--paper); border:1px solid rgba(14,17,22,.12); }}
  .navbar.light .t strong {{ color:var(--ink); }}
  .navbar.light .t small {{ color:#5f6774; }}
</style></head><body>
<h1>会标矢量审阅</h1>
<p class="lead">叠加格：矢量以信号青半透明压在原位图上，任何偏移一眼可见。小尺寸条：检查导航栏与 favicon 尺度下是否糊成一团。</p>

<div class="row">
  <div class="cell onblack"><h2>原位图 logo-mark.png 300px（白线，需暗底）</h2>
    <div class="body"><img src="{PNG.as_uri()}" width="300" height="300" alt="原位图"></div></div>
  <div class="cell onblack"><h2>完整版矢量 300px</h2>
    <div class="body">{sized(svg_inline, 300, '#e9edf4')}</div></div>
  <div class="cell"><h2>叠加：矢量(青) over 位图(白)</h2>
    <div class="body"><div class="overlay">
      <img src="{PNG.as_uri()}" alt="原位图">
      <span class="vec">{svg_inline}</span>
    </div></div></div>
</div>



<div class="row">
  <div class="cell dark"><h2>暗底 · 白线（站点主场景）</h2>
    <div class="body">{sized(svg_inline, 300, '#e9edf4')}</div></div>
  <div class="cell dark"><h2>暗底 · 焊锡铜</h2>
    <div class="body">{sized(svg_inline, 300, 'var(--copper)')}</div></div>
  <div class="cell dark"><h2>暗底 · 信号青</h2>
    <div class="body">{sized(svg_inline, 300, 'var(--accent)')}</div></div>
</div>

<div class="row">
  <div class="cell onblack"><h2>完整版 · 小尺寸（16→96）</h2>
    <div class="body"><div class="strip" style="color:#e9edf4">
      <figure>{sized(svg_inline, 16, '#e9edf4')}<figcaption>16</figcaption></figure>
      <figure>{sized(svg_inline, 24, '#e9edf4')}<figcaption>24</figcaption></figure>
      <figure>{sized(svg_inline, 32, '#e9edf4')}<figcaption>32</figcaption></figure>
      <figure>{sized(svg_inline, 40, '#e9edf4')}<figcaption>40 导航</figcaption></figure>
      <figure>{sized(svg_inline, 64, '#e9edf4')}<figcaption>64</figcaption></figure>
      <figure>{sized(svg_inline, 96, '#e9edf4')}<figcaption>96</figcaption></figure>
    </div></div></div>
</div>

<div class="row">
  <div class="cell"><h2>导航栏实景（暗底 / 白区反色）</h2>
    <div class="body" style="flex-direction:column;gap:14px;align-items:stretch">
      <div class="navbar">{sized(svg_inline, 40, '#fff')}
        <span class="t"><strong>电子科技协会</strong><small>HEU ESTA</small></span></div>
      <div class="navbar light">{sized(svg_inline, 40, 'var(--ink)')}
        <span class="t"><strong>电子科技协会</strong><small>HEU ESTA</small></span></div>
    </div></div>
</div>
</body></html>
"""

OUT.parent.mkdir(exist_ok=True)
OUT.write_text(HTML, encoding="utf-8")
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
print(f"已生成 {OUT.relative_to(REPO)}")
print("接着跑： python scripts/shoot.py --file .shots/logo-preview.html --desktop --viewport-only")
