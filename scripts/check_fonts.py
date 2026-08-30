# -*- coding: utf-8 -*-
"""校验自托管字体子集与当前模板同步。

四个字体、三种判据（**判据不一样是关键**）：
  - mono（JetBrains Mono）：拉丁 + 符号 + 箭头的固定码位表全覆盖。
  - 标题（Heavy）：按模板用字取子集 → 判据是「模板里的字都在」。
  - 正文（Regular + Bold）：承载站务以后随时写的内容，模板扫不到 →
    判据是 **GB2312 一级字全集**，而且两档覆盖必须逐字一致。


**这是一个静默故障。** `SourceHanSansCN-Heavy-subset.woff2` 是按「模板里出现过
哪些汉字」子集化出来的。改版期间新加了作品墙、荣誉墙、团队页、注册三页、新生
指南……每一批新文案都可能带进子集里没有的字。那些字会按 `font-display: swap`
的规则回退到系统黑体 —— 于是一行大标题里混着两种字重两种字形，页面不报错、
控制台干净、`collectstatic` 也照常过。只有拿字库的 cmap 和模板对一遍才看得出来。

判据不是「文件在不在」，而是**模板里要用的每一个字都在字库的 cmap 里**。
「要用哪些字」直接从 `build_fonts.py` 里 import，不在这里抄第二份 —— 两份必然漂移。

跑法：
    python scripts/check_fonts.py            # 只检查
    python scripts/check_fonts.py --list     # 把缺的字打出来（要补进子集时看）

缺字的修法：拿到两个字体源文件后重跑
    python scripts/build_fonts.py <JetBrainsMono[wght].ttf> <SourceHanSansCN-Heavy.otf>
下载地址在 build_fonts.py 的文件头注释里。
"""
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

FONT_DIR = REPO / "app" / "static" / "fonts"
DISPLAY = FONT_DIR / "SmileySans-subset.woff2"
MONO = FONT_DIR / "JetBrainsMono-subset.woff2"
BODY = {
    400: FONT_DIR / "SourceHanSansCN-Regular-subset.woff2",
    700: FONT_DIR / "SourceHanSansCN-Bold-subset.woff2",
}
SERIF = FONT_DIR / "SourceHanSerifCN-SemiBold-subset.woff2"
DIGITS = FONT_DIR / "ESTADigits.woff2"

# mono 是全站数字与编号的主角，这些码位缺一个就会在版面上留一个豆腐块或跳字。
# 拉丁可见区间 + 常用排版符号 + 箭头（文案里到处是「→」）。
MONO_REQUIRED = (
    [c for c in range(0x20, 0x7F)]
    + [0x2013, 0x2014, 0x2018, 0x2019, 0x201C, 0x201D, 0x2026, 0x00B7]
    + [0x2190, 0x2192, 0x2191, 0x2193]
)

failures = []


def check(cond, label, detail=""):
    print(f"  {'OK  ' if cond else 'FAIL'} {label}" + (f"  {detail}" if detail else ""))
    if not cond:
        failures.append(label)


def coverage(path: Path) -> set[int]:
    """字库真正能渲染的码位集合（cmap 的并集）。"""
    from fontTools.ttLib import TTFont

    font = TTFont(str(path))
    covered: set[int] = set()
    for table in font["cmap"].tables:
        covered.update(table.cmap.keys())
    font.close()
    return covered


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    try:
        import fontTools  # noqa: F401
    except ImportError:
        print("需要 fontTools：python -m pip install fonttools brotli")
        print("（开发工具，不要写进 app/requirements.txt）")
        return 2

    print("字体文件就位")
    check(DISPLAY.exists(), "标题字体子集存在", DISPLAY.name)
    check(MONO.exists(), "mono 字体子集存在", MONO.name)
    if failures:
        return 1

    # 体积：这两个是首屏字体，超了就该重新收窄子集而不是默默变胖
    d_kb = DISPLAY.stat().st_size / 1024
    m_kb = MONO.stat().st_size / 1024
    check(d_kb <= 320, "标题字体体积在预算内（≤320KB）", f"{d_kb:.0f} KB")
    check(m_kb <= 160, "mono 字体体积在预算内（≤160KB）", f"{m_kb:.0f} KB")

    from build_fonts import collect_cjk_chars

    print("\nmono：数字与编号用的码位一个都不能缺")
    mono_cov = coverage(MONO)
    missing_mono = [c for c in MONO_REQUIRED if c not in mono_cov]
    check(
        not missing_mono,
        "拉丁 + 常用符号 + 箭头全覆盖",
        f"缺 {len(missing_mono)} 个：" + " ".join(f"U+{c:04X}" for c in missing_mono[:12])
        if missing_mono else f"{len(mono_cov)} 个码位",
    )

    print("\n标题字体：模板里要用的汉字必须都在子集里")
    print("（这是「子集是不是还跟得上模板」的唯一硬证据 —— 缺字只会静静回退系统黑体）")
    needed = collect_cjk_chars()
    disp_cov = coverage(DISPLAY)
    missing = sorted(ch for ch in needed if ord(ch) not in disp_cov)
    check(len(needed) > 500,
          "取字来源真的扫到东西了（不是空集合让断言空跑）", f"需要 {len(needed)} 字")
    check(not missing,
          "**模板里的汉字全部被子集覆盖**",
          f"缺 {len(missing)} 字（占 {len(missing) / max(len(needed), 1):.1%}）"
          if missing else f"{len(needed)} 字全覆盖")

    # 中文标点也走标题字体，缺了就是一行标题里混两种引号
    from build_fonts import CJK_PUNCT

    missing_punct = [c for c in CJK_PUNCT if ord(c) not in disp_cov]
    check(not missing_punct, "中文标点全覆盖", "缺 " + " ".join(missing_punct)
          if missing_punct else f"{len(CJK_PUNCT)} 个")

    # ---------------- 正文两档 ----------------
    # 正文和标题的判据不一样：标题按模板取字（内容作者改不到标题字体），
    # 正文要承载站务以后随时写的公告与简介，所以判据是 **GB2312 一级字全集**。
    print("\n正文两档：字表是 GB2312 全集（一级+二级），不是模板用字")
    print("（正文内容是站务以后写的，模板扫不到；一段话里混两种字形比标题缺字更难看）")
    from build_fonts import gb2312_hanzi

    for path in BODY.values():
        check(path.exists(), f"{path.name} 存在")
    if failures:
        return 1

    # 判据从「一级字」换成「一级+二级全集」：二级字区（3008 个）就是人名用字区。
    # 真踩到过 —— 导入 15 条获奖记录带进 5 个二级字（昊 晗 淏 琛 蹇），每个名字里
    # 混一个系统黑体的字，而页面照常渲染、控制台干净。站上大量文字在数据库里
    # （公告、作品简介、获奖记录的队员姓名），模板扫不到，用量不可预测。
    level1 = gb2312_hanzi((1, 2))
    check(len(level1) > 6700, "GB2312 全集字表取到了（不是空集合）", f"{len(level1)} 字")
    covs = {}
    for weight, path in BODY.items():
        cov = coverage(path)
        covs[weight] = cov
        kb = path.stat().st_size / 1024
        miss1 = [ch for ch in level1 if ord(ch) not in cov]
        miss_tpl = [ch for ch in needed if ord(ch) not in cov]
        # 1200 → 2000：字表从一级字（3755）扩到 GB2312 全集（6763），实测每档
        # 1841 / 1864KB。用户明确许可提高字体预算，理由是「任何中文姓名都可能
        # 缺字」这一类静默故障值得这个体积 —— 而站点的既有取舍是展示效果优先。
        check(kb <= 2000, f"{weight} 档体积在预算内（≤2000KB）", f"{kb:.0f} KB")
        check(not miss1, f"{weight} 档覆盖 GB2312 全集（一级+二级）",
              f"缺 {len(miss1)} 字" if miss1 else f"{len(level1)} 字全覆盖")
        # 标题字体缺字时会退到正文档，所以正文必须是标题的超集
        check(not miss_tpl, f"{weight} 档覆盖模板用字（标题缺字时的退路）",
              f"缺 {len(miss_tpl)} 字" if miss_tpl else f"{len(needed)} 字全覆盖")

    # 两档覆盖必须完全一致：不一致的话「加粗之后这个字变成另一种字体」——
    # 只在被加粗的那几个字上出现，最难发现的那一类
    only400 = covs[400] - covs[700]
    only700 = covs[700] - covs[400]
    check(not only400 and not only700,
          "**Regular 与 Bold 覆盖完全一致**（否则加粗会让个别字掉档）",
          f"只有 400 有 {len(only400)} 个 / 只有 700 有 {len(only700)} 个")

    # ---------------- 第二声音（宋体） ----------------
    # 它和标题字体同一份字表（按模板取字），所以判据也一样。
    # 之所以不按正文那份 GB2312 全集：宋体轮廓复杂，3760 字要 1456KB。
    # 代价是它**只能用在模板文案上**，而这条约束没法靠脚本证明 —— 只能靠
    # tokens.css 那段注释和 CSS 里逐处的说明（`.wk-detail-lede` 就是刻意不用的）。
    print("\n第二声音（宋体 SemiBold）：字表同标题，只服务模板文案")
    check(SERIF.exists(), "宋体子集存在", SERIF.name)
    if not SERIF.exists():
        return 1
    s_kb = SERIF.stat().st_size / 1024
    check(s_kb <= 560, "宋体体积在预算内（≤560KB）", f"{s_kb:.0f} KB")
    serif_cov = coverage(SERIF)
    miss_serif = sorted(ch for ch in needed if ord(ch) not in serif_cov)
    check(not miss_serif, "**模板里的汉字全部被宋体子集覆盖**",
          f"缺 {len(miss_serif)} 字" if miss_serif else f"{len(needed)} 字全覆盖")
    miss_punct_serif = [c for c in CJK_PUNCT if ord(c) not in serif_cov]
    check(not miss_punct_serif, "宋体的中文标点全覆盖",
          "缺 " + " ".join(miss_punct_serif) if miss_punct_serif else f"{len(CJK_PUNCT)} 个")

    # ---------------- 科协专属数字 ----------------
    # 这一套是自己画的（scripts/build_lettering.py），所以判据和别的字体不同：
    # 不是「跟得上模板」，而是「该有的字形一个都不少」。少一个数字的后果是
    # 那一位悄悄退回 mono —— 一个大数字里混进一个别的字体的数字，很显眼但很难
    # 归因（比如 2026 里只有 0 变了样）。
    print("\n科协专属数字：0-9 与记号一个都不能缺")
    check(DIGITS.exists(), "数字字体存在", DIGITS.name)
    if not DIGITS.exists():
        return 1
    dig_cov = coverage(DIGITS)
    need_dig = "0123456789.:+-/%"
    miss_dig = [c for c in need_dig if ord(c) not in dig_cov]
    check(not miss_dig, "**0-9 与 . : + - / % 全部有字形**",
          "缺 " + " ".join(miss_dig) if miss_dig else f"{len(need_dig)} 个")
    dg_kb = DIGITS.stat().st_size / 1024
    check(dg_kb <= 8, "数字字体体积在预算内（≤8KB，纯几何应该极小）", f"{dg_kb:.1f} KB")
    # 等宽：计数器每跳一位都会重排，字宽不一致就会左右抖
    from fontTools.ttLib import TTFont

    _f = TTFont(str(DIGITS))
    widths = {c: _f["hmtx"][_f.getBestCmap()[ord(c)]][0] for c in "0123456789"}
    _f.close()
    check(len(set(widths.values())) == 1,
          "**0-9 等宽**（否则计数器与倒计时每跳一位就抖一下）",
          f"{sorted(set(widths.values()))}")

    if missing and "--list" in sys.argv:
        print("\n缺的字（重跑 build_fonts.py 就会补上）：")
        for i in range(0, len(missing), 40):
            print("    " + "".join(missing[i:i + 40]))

    print()
    if failures:
        print(f"{len(failures)} 项未通过：" + "、".join(failures))
        if missing:
            print("修法：拿到字体源文件后重跑 build_fonts.py（下载地址见它的文件头）")
        return 1
    print("字体子集契约全部通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
