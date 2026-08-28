"""
自托管字体构建脚本（一次性/字库更新时运行）。

产出（写入 app/static/fonts/）:
    JetBrainsMono-subset.woff2          可变字重 100-800，拉丁+数字+常用符号
    SourceHanSansCN-Heavy-subset.woff2  思源黑体 Heavy，按站内标题用字子集化
    SourceHanSansCN-Regular-subset.woff2  思源黑体 Regular，正文（GB2312 一级字全集）
    SourceHanSansCN-Bold-subset.woff2     思源黑体 Bold，正文加粗

用法（源文件放 .fontsrc/，那个目录不入库）:
    python scripts/build_fonts.py .fontsrc/JetBrainsMono[wght].ttf \
        .fontsrc/SourceHanSansCN-Heavy.otf

    # 连正文两档一起重建（第一次或换字库时）
    python scripts/build_fonts.py .fontsrc/JetBrainsMono[wght].ttf \
        .fontsrc/SourceHanSansCN-Heavy.otf --body .fontsrc/SourceHanSansCN

字体源文件下载:
    https://github.com/JetBrains/JetBrainsMono/releases/download/v2.304/JetBrainsMono-2.304.zip
        -> fonts/variable/JetBrainsMono[wght].ttf
    https://github.com/adobe-fonts/source-han-sans/raw/release/SubsetOTF/CN/SourceHanSansCN-Heavy.otf
    https://github.com/adobe-fonts/source-han-sans/raw/release/SubsetOTF/CN/SourceHanSansCN-Regular.otf
    https://github.com/adobe-fonts/source-han-sans/raw/release/SubsetOTF/CN/SourceHanSansCN-Bold.otf
    （思源黑体是 SIL OFL 1.1，许可记在 app/static/fonts/README.md）

设计说明:
- mono 数字是全站视觉主角（大数字/编号/群号），不能依赖访客本机装没装字体；
- 中文标题只在 display 层使用 Heavy 字重，按模板实际出现的汉字子集化，
  新增内容中的生僻字会回退到**自己的 Regular/Bold**（同一套设计，只差字重），
  而不是跳到系统黑体（那是换了一套字形）。`check_fonts.py` 盯着缺字。
- **正文两档不按模板取字，取 GB2312 一级字全集。** 理由：正文内容是站务以后
  随时写的（公告、活动、作品简介、成员名字），模板扫不到；而正文缺字的后果
  比标题缺字难看得多 —— 一段话里混进两种字形。用量不可预测的地方就别用
  「按现有文案取字」这种会过期的子集。
- **Regular 和 Bold 必须成对。** 只自托管 Regular 的话，`<strong>` 与
  `font-weight: 700` 会让浏览器**合成假粗**（把 Regular 描粗），那正是这套设计
  要摆脱的东西 —— 而现在系统黑体本来有真 Bold，等于自托管之后反倒变差。
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


def gb2312_hanzi(levels: tuple[int, ...] = (1,)) -> set[str]:
    """GB2312 里的汉字。level 1 = 一级字 3755 个（按拼音排序，现代汉语的常用字）；
    level 2 = 二级字 3008 个（生僻字与人名用字）。

    为什么从 GB2312 取而不是在网上找一份「常用 3500 字表」：Python 自带这个
    编码，所以字表是**确定的、离线的、可复现的**，不依赖某个网页哪天改内容。
    一级字区是 0xB0A1–0xD7F9，二级字区是 0xD8A1–0xF7FE。
    """
    ranges = {1: range(0xB0, 0xD8), 2: range(0xD8, 0xF8)}
    chars: set[str] = set()
    for level in levels:
        for hi in ranges[level]:
            for lo in range(0xA1, 0xFF):
                try:
                    ch = bytes((hi, lo)).decode("gb2312")
                except UnicodeDecodeError:
                    continue
                chars.add(ch)
    return chars


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
        # **注释要先整块摘掉，而且必须排在别的替换之前。**
        # 本项目的模板注释写得很长且全是中文（「为什么这里不能用 aspect-ratio」
        # 之类），而注释一个字都不会渲染。不摘的话它们全都进子集 —— 白白把
        # 标题字体撑大几十 KB，而且让 check_fonts.py 变成在要求「注释里的字也得
        # 在字库里」，那是个没有意义的约束。
        text = re.sub(r"{%\s*comment\s*%}.*?{%\s*endcomment\s*%}", "", text, flags=re.S)
        text = re.sub(r"<!--.*?-->", "", text, flags=re.S)
        # 再去掉 Django 模板标签/变量，保留可见文案
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
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    jbmono, shs = Path(sys.argv[1]), Path(sys.argv[2])
    body_prefix = None
    if "--body" in sys.argv:
        body_prefix = sys.argv[sys.argv.index("--body") + 1]

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

    if not body_prefix:
        print("\n（没给 --body，正文两档未重建；只有换字库或改字表时才需要）")
        return

    # 正文两档：GB2312 一级字 ∪ 模板里出现过的字（模板里可能有二级字，
    # 比如人名与专业名词 —— 标题有的字正文也必须有，否则同一个词在两处长得不一样）
    body_chars = gb2312_hanzi((1,)) | cjk
    print(f"\n正文字表：GB2312 一级字 + 模板用字 = {len(body_chars)} 个汉字")
    body_text = latin + CJK_PUNCT + "".join(sorted(body_chars))
    for weight, name in (("Regular", "Regular"), ("Bold", "Bold")):
        src = Path(f"{body_prefix}-{weight}.otf")
        if not src.exists():
            sys.exit(f"找不到 {src}（--body 传的是不带字重的前缀，例如 "
                     f".fontsrc/SourceHanSansCN）")
        print(f"== 思源黑体 {name}（正文）==")
        subset_font(
            src, OUT_DIR / f"SourceHanSansCN-{name}-subset.woff2",
            text=body_text,
            unicodes="U+00A0-00FF U+2013-2026 U+3000-303F U+FF00-FFEF",
        )


if __name__ == "__main__":
    main()
