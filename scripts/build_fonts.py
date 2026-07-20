"""
自托管字体构建脚本（一次性/字库更新时运行）。

产出（写入 app/static/fonts/）:
    JetBrainsMono-subset.woff2        可变字重 100-800，拉丁+数字+常用符号
    SourceHanSansCN-Heavy-subset.woff2 思源黑体 Heavy，按站内标题用字子集化

用法:
    .venv/Scripts/python scripts/build_fonts.py <jbmono_variable.ttf> <SourceHanSansCN-Heavy.otf>

字体源文件下载:
    https://github.com/JetBrains/JetBrainsMono/releases/download/v2.304/JetBrainsMono-2.304.zip
        -> fonts/variable/JetBrainsMono[wght].ttf
    https://github.com/adobe-fonts/source-han-sans/raw/release/SubsetOTF/CN/SourceHanSansCN-Heavy.otf

设计说明:
- mono 数字是全站视觉主角（大数字/编号/群号），不能依赖访客本机装没装字体；
- 中文标题只在 display 层使用 Heavy 字重，按模板实际出现的汉字子集化，
  新增内容中的生僻字会回退到系统黑体（font-display: swap 保证先渲染）。
"""
import re
import sys
from pathlib import Path

from fontTools.subset import Options, Subsetter, parse_unicodes
from fontTools.ttLib import TTFont

REPO = Path(__file__).resolve().parent.parent
OUT_DIR = REPO / "app" / "static" / "fonts"

# 标题字体的取字来源：Django 模板 + 学习中心入口页 + 兜底文案所在的 Python 源
TEXT_SOURCES = [
    REPO / "app" / "templates",
    REPO / "learn" / "electronics" / "index.html",
    REPO / "app" / "core" / "views.py",
    REPO / "app" / "core" / "models.py",
]

# 常用汉字兜底（GB2312 一级常用字前段之外，站点后台随手改标题也大多在这里面）
COMMON_EXTRA = (
    "的一是了我不人在他有这个上们来到时大地为子中你说生国年着就那和要她出也得里后自以会家可下而过天去能对小多然于心学么之都好看起发当没成只如事把还用第样道想作种开美总从无情己面最女但现前些所同日手又行意动方期它头经长儿回位分爱老因很给名法间斯知世什两次使身者被高已亲其进此话常与活正感"
)

CJK_PUNCT = "，。、；：？！「」『』（）《》〈〉——……·【】"


def collect_cjk_chars() -> set[str]:
    chars: set[str] = set()
    files: list[Path] = []
    for src in TEXT_SOURCES:
        if src.is_dir():
            files.extend(src.rglob("*.html"))
        elif src.exists():
            files.append(src)
    for f in files:
        text = f.read_text(encoding="utf-8", errors="ignore")
        # 去掉 Django 模板标签/变量，保留可见文案
        text = re.sub(r"{%.*?%}|{{.*?}}|{#.*?#}", "", text, flags=re.S)
        chars.update(re.findall(r"[\u3400-\u9fff]", text))
    chars.update(COMMON_EXTRA)
    return chars


def subset_font(src: Path, out: Path, text: str, unicodes: str = "") -> None:
    options = Options()
    options.flavor = "woff2"
    options.layout_features = ["*"]
    options.name_IDs = ["*"]
    options.notdef_outline = True
    options.recalc_bounds = True
    options.drop_tables += ["FFTM"]
    font = TTFont(str(src))
    subsetter = Subsetter(options=options)
    codepoints: list[int] = []
    for token in unicodes.split():
        codepoints.extend(parse_unicodes(token.removeprefix("U+")))
    subsetter.populate(text=text, unicodes=codepoints)
    subsetter.subset(font)
    out.parent.mkdir(parents=True, exist_ok=True)
    font.save(str(out))
    print(f"  {out.name}: {out.stat().st_size / 1024:.0f} KB")


def main() -> None:
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    jbmono, shs = Path(sys.argv[1]), Path(sys.argv[2])

    print("== JetBrains Mono（可变字重，拉丁全集）==")
    latin = "".join(chr(c) for c in range(0x20, 0x7F))
    subset_font(
        jbmono, OUT_DIR / "JetBrainsMono-subset.woff2",
        text=latin,
        unicodes="U+00A0-00FF U+2013-2026 U+2190-2199 U+21D2 U+2500-257F",
    )

    print("== 思源黑体 Heavy（标题用字子集）==")
    cjk = collect_cjk_chars()
    print(f"  收集到 {len(cjk)} 个汉字")
    text = latin + CJK_PUNCT + "".join(sorted(cjk))
    subset_font(
        shs, OUT_DIR / "SourceHanSansCN-Heavy-subset.woff2",
        text=text,
        unicodes="U+00A0-00FF U+2013-2026 U+3000-303F U+FF00-FFEF",
    )


if __name__ == "__main__":
    main()
