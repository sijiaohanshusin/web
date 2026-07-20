"""
学习中心章节页翻页导航注入脚本（幂等，可重复运行）。

在每个 learn/electronics/pages/*.html 的 </main> 前插入
「上一章 / 目录 / 下一章」导航，顺序按课程目录（00 → 21 → 附录 A-F）。

用法:
    .venv/Scripts/python scripts/inject_chapter_pager.py
"""
import re
from pathlib import Path

PAGES = Path(__file__).resolve().parent.parent / "learn" / "electronics" / "pages"

# 课程目录顺序（与 index.html 一致）
ORDER = [
    "00-前言与使用说明.html",
    *[f for f in ("01-第1章-电路理论基础.html", "02-第2章-理想运算放大器基础.html",
                  "03-第3章-运算放大器的非理想特性.html", "04-第4章-运放高级应用.html",
                  "05-第5章-固态二极管与二极管特性.html", "06-第6章-整流、倍压与稳压.html",
                  "07-第7章-二极管应用专题.html", "08-第8章-晶体管基本概念.html",
                  "09-第9章-单管放大级.html", "10-第10章-多级放大器与共射共基结构.html",
                  "11-第11章-电流镜.html", "12-第12章-差分放大器.html",
                  "13-第13章-跨阻前端与电流反馈放大器.html", "14-第14章-电压基准.html",
                  "15-第15章-MOSFET应用.html", "16-第16章-高级放大器专题.html",
                  "17-第17章-电源管理电路.html", "18-第18章-数据转换器电路总览.html",
                  "19-第19章-电流舵数模转换器.html", "20-第20章-模数转换.html",
                  "21-第21章-数字电子学（第一部分）.html")],
    "附录-photodiodes-附录A-光电二极管与其他光传感器.html",
    "附录-transistor-selection-附录B-分立晶体管选型.html",
    "附录-opamp-equations-附录C-运放设计公式速查.html",
    "附录-opamp-comparators-附录D-使用运放作比较器.html",
    "附录-current-output-附录E-电流输出电路技巧.html",
    "附录-4000-series-附录F-4000系列逻辑与模拟电路.html",
]

PAGER_RE = re.compile(r'\s*<nav class="chapter-pager".*?</nav>', re.S)


def page_title(path: Path) -> str:
    text = path.read_text(encoding="utf-8")
    m = re.search(r"<title>(.*?)</title>", text)
    title = m.group(1) if m else path.stem
    return title.split(" - ")[0].strip()


def build_pager(prev_: tuple | None, next_: tuple | None) -> str:
    parts = ['  <nav class="chapter-pager" aria-label="章节导航">']
    if prev_:
        parts.append(
            f'    <a class="pager-card pager-prev" href="{prev_[0]}">'
            f'<span class="pager-label">← PREV</span>'
            f'<span class="pager-title">{prev_[1]}</span></a>'
        )
    else:
        parts.append('    <span class="pager-card pager-empty" aria-hidden="true"></span>')
    parts.append('    <a class="pager-index" href="../index.html">目录</a>')
    if next_:
        parts.append(
            f'    <a class="pager-card pager-next" href="{next_[0]}">'
            f'<span class="pager-label">NEXT →</span>'
            f'<span class="pager-title">{next_[1]}</span></a>'
        )
    else:
        parts.append('    <span class="pager-card pager-empty" aria-hidden="true"></span>')
    parts.append("  </nav>\n  ")
    return "\n".join(parts)


def main() -> None:
    missing = [n for n in ORDER if not (PAGES / n).exists()]
    if missing:
        raise SystemExit(f"目录顺序表与实际文件不符，缺少: {missing}")

    titles = {name: page_title(PAGES / name) for name in ORDER}
    count = 0
    for i, name in enumerate(ORDER):
        path = PAGES / name
        html = path.read_text(encoding="utf-8")
        html = PAGER_RE.sub("", html)  # 幂等：先移除旧导航

        prev_ = (ORDER[i - 1], titles[ORDER[i - 1]]) if i > 0 else None
        next_ = (ORDER[i + 1], titles[ORDER[i + 1]]) if i < len(ORDER) - 1 else None
        pager = build_pager(prev_, next_)

        idx = html.rfind("</main>")
        if idx == -1:
            print(f"  跳过（无 </main>）: {name}")
            continue
        html = html[:idx] + pager + html[idx:]
        path.write_text(html, encoding="utf-8", newline="\n")
        count += 1
    print(f"已注入 {count} 个章节页")


if __name__ == "__main__":
    main()
