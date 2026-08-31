"""
自托管字体构建脚本（一次性/字库更新时运行）。

产出（写入 app/static/fonts/）:
    JetBrainsMono-subset.woff2            可变字重 100-800，拉丁+数字+常用符号
    SmileySans-subset.woff2               得意黑，**标题**（按模板取字）
    SourceHanSansCN-Regular-subset.woff2  思源黑体 Regular，正文（GB2312 一级字全集）
    SourceHanSansCN-Bold-subset.woff2     思源黑体 Bold，正文加粗
    SourceHanSerifCN-SemiBold-subset.woff2 思源宋体，第二声音（各页导语）

标题字为什么从思源黑体 Heavy 换成得意黑：Heavy 是最中性的一款黑体，和微软雅黑、
苹方同一类 —— 自托管之后「看起来还是黑体、艺术性不足」正是它造成的。得意黑是
倾斜 + 紧缩的展示体，字形本身带态度，而且按模板取字后 270KB < Heavy 的 333KB。

用法（源文件放 .fontsrc/，那个目录不入库）:
    python scripts/build_fonts.py .fontsrc/JetBrainsMono[wght].ttf \
        .fontsrc/smiley/SmileySans-Oblique.ttf

    # 连正文两档、第二声音一起重建（第一次或换字库时）
    python scripts/build_fonts.py .fontsrc/JetBrainsMono[wght].ttf \
        .fontsrc/smiley/SmileySans-Oblique.ttf \
        --body .fontsrc/SourceHanSansCN --serif .fontsrc/SourceHanSerifCN-SemiBold.otf

字体源文件下载:
    https://github.com/JetBrains/JetBrainsMono/releases/download/v2.304/JetBrainsMono-2.304.zip
        -> fonts/variable/JetBrainsMono[wght].ttf
    https://github.com/atelier-anchor/smiley-sans/releases  -> SmileySans-Oblique.ttf
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

# GB2312 之外还要补的字（留给「连二级字都没收」的罕见字）。
#
# 正文字表现在取 **GB2312 全集**（一级 3755 + 二级 3008），二级字区就是人名用字区
# —— 所以正常中文姓名不会再缺字。这一条留着是因为确实有姓名用到 GB2312 之外的字
# （生僻姓氏、异体字），那种情况把字加到这里。
#
# 怎么知道该加什么：`python scripts/check_content_fonts.py` 扫数据库里所有会渲染
# 出来的文本，报出不在子集里的字并指出来自哪个模型。导入内容之后跑一次。
#
# 换过一版的记录：一开始正文只收一级字，导入 15 条获奖记录就带进 5 个二级字
# （昊 晗 淏 琛 蹇）—— 每个名字里混一个系统黑体的字，而页面照常渲染。当时想过
# 手工策展一份清单，但那等于「每加一个人名都要记得改字体」，下一次必然忘。
CONTENT_EXTRA = (
    # 获奖记录（news.Honor）里 GB2312 二级字区都没收的字。
    #   淏  队员姓名（第一批 15 条时发现）
    #   昇  赛事名「毕昇杯」（第二批扩到 38 条时发现）
    # 姓名现在一律脱敏成「首*末」，所以这个口子往后主要是**赛事名**在用 ——
    # 老赛事的名字里生僻字不少，而赛事名比人名更没法预测。
    "淏昇"
)

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
    # 不刷新 head.modified，少一个变动来源。
    # **但这个脚本的输出仍然不是逐字节可复现的**：连续两次构建同一个字体，
    # woff2 的字节就不一样（实测哈希不同、体积一样）。所以重建会把所有产出都
    # 标成 modified，入库后哈希全变一遍、回访用户白下一次。
    # 结论：**只在真的要改字表时重建，并且把没必要变的那几个 `git checkout` 回去。**
    options.recalc_timestamp = False
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
    jbmono, display_src = Path(sys.argv[1]), Path(sys.argv[2])
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

    # 标题字：得意黑（Smiley Sans，SIL OFL）。按模板取字 —— 标题文案由我们写，
    # 扫得到；而且得意黑覆盖 9440 个码位，模板用字与 GB2312 一级字都不缺。
    print("== 得意黑（标题用字子集）==")
    cjk = collect_cjk_chars()
    print(f"  收集到 {len(cjk)} 个汉字")
    text = latin + CJK_PUNCT + "".join(sorted(cjk))
    subset_font(
        display_src, OUT_DIR / "SmileySans-subset.woff2",
        text=text,
        unicodes="U+00A0-00FF U+2013-2026 U+3000-303F U+FF00-FFEF",
    )

    serif = None
    if "--serif" in sys.argv:
        serif = Path(sys.argv[sys.argv.index("--serif") + 1])

    if serif:
        # 第二声音：思源宋体 SemiBold。
        #
        # **字表按模板取字（和标题一样，不是正文那份 GB2312 全集）。**
        # 一开始按正文的字表做了一版：1456KB —— 宋体的轮廓比黑体复杂，同样
        # 3760 个字要多花 40%。而它的用途只有「页头导语」和「长文开篇」这几处
        # 模板文案，所以按模板取字就够，代价降到三分之一。
        # 代价是**它只能用在模板文案上**：站务写的正文（公告引用块、作品简介）
        # 里可能有子集外的字，那会在一段引文里混进黑体 —— 所以那些地方不用它。
        # 这条约束写进 tokens.css 的注释里，不然下一个人很容易顺手拿去用。
        #
        # 只做 SemiBold 一档：宋体的横画在黑底上本来就细，Regular 会发虚；
        # 而它的用途全是「大一号的短句」，不需要字重变化。
        print("== 思源宋体 SemiBold（第二声音，按模板取字）==")
        subset_font(
            serif, OUT_DIR / "SourceHanSerifCN-SemiBold-subset.woff2",
            text=text,   # 和标题字体同一份字表
            unicodes="U+00A0-00FF U+2013-2026 U+3000-303F U+FF00-FFEF",
        )

    if not body_prefix:
        print("\n（没给 --body，正文两档未重建；只有换字库或改字表时才需要）")
        return

    # 正文两档：GB2312 一级字 ∪ 模板里出现过的字（模板里可能有二级字，
    # 比如人名与专业名词 —— 标题有的字正文也必须有，否则同一个词在两处长得不一样）
    # **一级 + 二级**。二级字区（3008 个）就是人名用字区 —— 站上大量文字是数据库
    # 里的内容（公告、作品简介、获奖记录里的队员姓名），模板扫不到，而人名缺一个
    # 字就是一个名字里混两种字形。用量不可预测的地方按全集收，不按用量收。
    body_chars = gb2312_hanzi((1, 2)) | cjk | set(CONTENT_EXTRA)
    print(f"\n正文字表：GB2312 全集（一级+二级） + 模板用字 = {len(body_chars)} 个汉字")
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
