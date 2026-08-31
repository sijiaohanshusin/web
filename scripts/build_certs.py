# -*- coding: utf-8 -*-
"""把获奖证书的照片处理成入库的 webp。

    python scripts/build_certs.py            # 全部
    python scripts/build_certs.py --list     # 只看清单与源文件在不在

**为什么产物要提交进仓库**：`Honor.certificate` 是 `ImageField`，落在 `MEDIA_ROOT`
下，而 `app/media/` 是 gitignore 的 —— 也就是说本地导入的图**到不了生产**。所以
处理后的 webp 放在 `app/news/data/honors/`（跟着代码走），由
`manage.py import_honors` 在生产上把它们喂给 `ImageField`。这是一次性数据导入，
不是运行时依赖。

源文件是招新 PPT 里内嵌的照片（`.artsrc/certs/`，母图不入库，和美术资产同一个
约定）。抽取方式见 docs/荣誉数据来源.md。

尺寸：长边压到 1400。证书是拍下来的纸，要能读清奖项名与赛事，但不需要原始
分辨率 —— 1400 长边下正文字号约 20px，够读，而体积只有原图的几分之一。

**姓名区域要打码。** 记录里的姓名已经脱敏（`夏*元`，见 `scripts/mask_names.py`），
但证书照片上印着真名 —— 图一贴上去等于没脱敏，而且这张图是公开可直链的。
所以每条都带一组归一化坐标的遮罩框，处理时打成马赛克。

三点说明：

- **用马赛克而不是高斯模糊。** 模糊对小字并不可靠（半径不够就还认得出），
  而马赛克是把一块像素直接抹平成几个色块，不存在「调对参数才安全」这回事。
  视觉上它也明确读作「这里刻意遮了」，不像模糊会被当成拍虚了。
- **不靠缩小来遮。** 试过：条带那一格是 235×176，DPR2 要 470 宽，portrait 证书
  换算下来长边至少 640 —— 而 640 下姓名还有 11~12px，放大就读得出。
  「缩到看不清」和「遮掉」是两件事。
- **遮罩坐标只能人工标，没法自动验。** 程序不知道姓名在图上哪个位置，
  所以 `--proof` 会把处理结果单独输出一份供逐张看图确认，
  `preflight.py` 的人工确认清单里也列了这一条。
"""
import argparse
import sys
from dataclasses import dataclass, field
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SRC = REPO / ".artsrc" / "certs"
OUT = REPO / "app" / "news" / "data" / "honors"

LONG_EDGE = 1400
QUALITY = 86
# 遮罩框的**长边**最多分成这么多个色块。
#
# 第一版写的是「块边长 = 短边 ÷ 6」，那是错的：一行 23px 高的小字，短边就是 23，
# 每块只有 7px，而一个汉字宽约 15px —— 一个字还占两块，打完照样认得出
# （`datang-2024-hlj-second` 的校对图上「雷成清、陈晗卉」清清楚楚）。
#
# 按长边定块数就与框的绝对尺寸无关了：不论框是 116×23 还是 490×60，
# 长边都只剩 10 个色块，每块必然比一个字还大，没有任何字形能活下来。
# 代价是宽扁的框看起来很粗 —— 但那正好读作「这里刻意遮了」。
MOSAIC_BLOCKS_LONG = 10


@dataclass(frozen=True)
class Cert:
    """一张证书的处理指令。"""

    name: str
    """输出名（不含扩展名）。`import_honors.py` 的 HONORS 里引用的就是它。"""

    src: str
    """源文件名。PPT 里的内嵌图编号，保留它是为了能回溯（见 docs/PPT素材清单.md）。"""

    masks: tuple[tuple[float, float, float, float], ...] = ()
    """要打码的区域，归一化坐标 `(x0, y0, x1, y1)`，取值 0~1，相对整幅图。

    用归一化而不是像素：源图尺寸各不相同（从 469×642 到 1920×1080），
    而且处理时还要缩放 —— 写像素的话缩放一次坐标就全废了。

    **空元组的意思是「这张确认过、没有姓名」**，不是「还没标」。
    没有姓名的情形是真实存在的：软著登记证书上是作品名与登记号，
    赛道类证书有的只印学校与队号。
    """

    rotate: int = 0
    """先逆时针转多少度再处理（只用 0 / 90 / 180 / 270）。

    有的证书是横躺着拍的。**转正不只是为了好看** —— 遮罩坐标是照着正立的图标的，
    躺着标等于在脑子里做一次坐标变换，标错的概率高得多。而且一张横躺的证书摆在
    荣誉墙上本身就像出了错，跟脱敏无关也该转。

    `--grid` 会先转再画网格，所以读出来的坐标直接能用。
    """

    note: str = ""
    """标坐标时的依据，一句话。下一个人要复核时能对着看。"""

    extra: dict = field(default_factory=dict)
    """备用，暂未使用。"""

# (输出名, 源文件名)。源文件名是 PPT 里的内嵌图编号，保留它是为了能回溯。
#
# **刻意没收进来的两张**：image106（第十八届智能车 独轮车组 国一）与 image109
# （TRIZ 杯创新方法大赛 国一）在 PPT 里只有 309x433 —— 那个尺寸放到证书墙上是
# 一块糊斑。这两项的奖项信息照样录（PPT 正文里有），只是没有证书照。
CERTS: list[Cert] = [
    # ---- 上一轮已收录的 13 张 ----
    Cert("esdc-2026-chip-first", "esdc-2026-chip-first.jpg",
         masks=((0.23, 0.552, 0.41, 0.692),),
         note="「参赛队员：」三个名字竖排各占一行，一个框连着遮。"
              "下面「指导老师：」两位留着；上面「作品名称」也留着"),
    Cert("esdc-2025-chip-second", "image89.jpeg",
         masks=((0.28, 0.522, 0.47, 0.678),),
         note="同一套版式（上一届），三个名字竖排"),
    Cert("datang-2025-ict-first", "image91.jpeg",
         masks=((0.02, 0.292, 0.18, 0.352),
                (0.18, 0.518, 0.41, 0.572)),
         note="**同一张里两次**：开头「XXX同学：」称呼，中部「参赛队员：」再列一遍。"
              "第一处 --rows 量不到 —— 它顶在左页边（x≈0.03），"
              "而 text_rows 默认从 x=0.08 才开始看，正好把它排除在窗口外"),
    Cert("smartcar-2025-hover-first", "image90.png",
         masks=((0.355, 0.344, 0.51, 0.378),),
         note="正文「哈尔滨工程大学 XXX 同学在…」中间一个名字（--rows 的**行6**，"
              "y 0.350~0.368）。第一版认成了行3，那是顶上绿色页眉里的赛事名。"
              "下方竞赛组委会那三位（院士/主任）是赛事署名，按口径留着"),
    Cert("nuedc-2024-ti-second", "image88.jpeg",
         masks=((0.16, 0.212, 0.47, 0.278),
                (0.75, 0.542, 0.93, 0.588)),
         note="换成 image88：与原来用的 image77 是同一条（2024 TI 杯国二），但更清楚。"
              "**中英文两处**；「指导教师 朱海峰」在中间那行留着"),
    Cert("copyright-2024-rsta", "image85.png",
         masks=((0.295, 0.356, 0.43, 0.390),),
         note="只遮「著作权人」。前两版都打偏了（一次在「权利范围」、一次在"
              "「权利取得方式」）—— 这一版是裁网格图放大量出来的：y 0.363~0.382。"
              "软件名称、登记号 2024SR0981408、证书号全部留着 —— "
              "这张的分量全在那几项上"),
    Cert("icm-2024-meritorious", "image79.jpeg",
         masks=((0.33, 0.283, 0.67, 0.445),),
         note="三个名字居中各占一行；「With Faculty Advisor」那位留着。"
              "第一版上边界 0.312 差一点，第一个名字整行露在框外"),
    Cert("nuedc-2023-second-b2356", "image78.jpg",
         masks=((0.21, 0.312, 0.48, 0.398),),
         note="「参赛队学生」一行三个名字"),
    Cert("nuedc-2023-second-b2363", "image102.jpeg",
         masks=((0.175, 0.374, 0.44, 0.424),),
         note="同上版式（同一届另一支队），但**位置和 b2356 不一样** —— "
              "两张的裁切边距不同。第一版照 b2356 的坐标抄，结果打在"
              "「参赛学校 哈尔滨工程大学」上（那一行在 0.306~0.334），"
              "姓名整行露着。同版式也要各自量"),
    Cert("esdc-2023-fpga-second", "image86.jpg",
         masks=((0.28, 0.628, 0.79, 0.692),),
         note="「参赛队员：」一行。这一张的字段行间距只有 0.04，前三版分别落在"
              "「作品名称」（两次，把该留的作品名遮了）和它下面的空续行上。"
              "最后是拿两次落点之差算出行距、再往下推一行定的。"
              "下面「指导老师：林云」与证书编号 CIE-03012332118 都留着"),
    Cert("nuedc-2021-first-b1058", "image51.jpeg",
         masks=((0.16, 0.376, 0.44, 0.430),),
         note="「参赛队学生」一行三个名字。第一版压在姓名上半截 —— "
              "字被切了一半却照样认得出，比完全没遮更危险（看着像遮过了）。"
              "电证字编号在左下角，留着"),
    Cert("nuedc-2021-first-b1059", "image74.png",
         masks=((0.185, 0.358, 0.50, 0.428),),
         note="同一届的另一支队，但**裁切边距和 b1058 不同**，坐标不能照抄。"
              "改了四轮：打在英文标题上 / 左边界太右漏掉第一个名字 / 右边界 0.65 "
              "越过书脊把右页的「（本科组）」也糊掉 / 只压住姓名上半截。"
              "两条教训：**对页证书的右边界必须卡在书脊（≈0.50）以内**；"
              "**只遮住上半截比完全没遮更危险** —— 字仍认得出，但看着像遮过了"),
    Cert("smartcar-2021-emag-first", "image73.png",
         masks=((0.42, 0.292, 0.60, 0.358),),
         note="正文第一行「哈尔滨工程大学 XXX 同学在2021年第十」里的名字。"
              "y 靠两次落点（下一行 / 上面的标题）插值定出来；x 第三版还偏左，"
              "遮掉的是校名「工程大学」而名字在它右边 —— "
              "**y 对了不等于 x 对了，两个轴要分开确认**"),

    # ---- 本轮新增（清单第 ② 节）----
    Cert("qihang-2010-first", "image65.jpeg",
         masks=((0.09, 0.35, 0.385, 0.43),),
         note="「XXX XXX XXX 同学:」在标题下方左侧。两次修：第一版把 y 读高了 0.1，"
              "遮罩打在标题「荣誉证书」上、姓名整行露着；第二版右边界 0.34 又把"
              "第三个人的末字「慧」留在了外面。**校对图必看**，这两次都是看图才发现的"),
    Cert("qihang-2010-second", "image66.jpeg",
         masks=((0.05, 0.355, 0.33, 0.445),),
         note="同上版式，位置略低。右边界第一版给到 0.28，末字「玉」露在外面；"
              "左边界从 0.03 收到 0.05 —— 再往左就压到红色花边上了，遮挡本身"
              "不该看起来像涂坏了"),
    Cert("wusi-2011-first", "image64.jpeg",
         masks=((0.07, 0.28, 0.63, 0.35),),
         note="五个人一行，横向占到 0.6"),
    Cert("nuedc-2011-national-second", "image53.jpeg",
         masks=(),
         note="**确认无姓名**：这本证书拍成两张，image52 是队员页、image53 是奖项页，"
              "这里取奖项页（整页只有赛事、奖次、颁发单位与日期）。"
              "队员页刻意不收 —— 那一页整页就是姓名，遮完等于一张白纸"),
    Cert("nuedc-2011-hlj-first", "image55.jpeg",
         masks=((0.28, 0.285, 0.78, 0.345),),
         note="「学生姓名：」之后那一段。下一行的「指导教师」按口径不遮"),
    Cert("eic-2011-national-first", "image58.jpeg",
         masks=((0.27, 0.655, 0.74, 0.73),),
         note="只遮「获奖者：」那一行。上面「获奖单位：…学生科协」要留着 —— "
              "那是这张证书最值钱的一处"),
    Cert("lierda-2012-iot-second", "image57.jpeg",
         masks=((0.25, 0.372, 0.60, 0.438),),
         note="队员名在第一行的括号里，紧跟「哈尔滨工程大学（」（左边界收到 0.25，"
              "免得把校名的「学」也吃掉）。"
              "同一行后半是「指导老师：…」，按口径留着 —— 所以右边界要卡在"
              "「；指导老师」之前，不能整行遮掉"),
    Cert("beidou-2012-excellent", "image56.jpeg",
         masks=((0.08, 0.302, 0.38, 0.352),
                (0.575, 0.362, 1.0, 0.445)),
         note="**中英文两处都有名字。** 中文侧在「（作者：」之后（同一行末尾是"
              "「；指导教」，要留）；英文侧「WANG …, WU …, TAO / Xuhui, PAN …」"
              "折成两行，一个框连着遮。漏掉英文侧是这一批最容易犯的错"),
    Cert("nuedc-2012-ti-second", "image60.jpeg",
         masks=((0.17, 0.342, 0.47, 0.402),
                (0.83, 0.532, 1.0, 0.582)),
         note="**中英文两处。** 左半「参赛队员」一行三个名字；"
              "右半英文正文「certify that Mr./Ms. XXX」句末还有一个"),
    Cert("xuefeng-2012-wu", "image62.jpeg",
         masks=((0.15, 0.322, 0.33, 0.378),),
         note="「XXX 同学」在标题下方，只有一个名字"),
    Cert("xuefeng-2012-wang", "image63.jpeg",
         masks=((0.09, 0.325, 0.32, 0.385),),
         note="和 xuefeng-2012-wu 是同一批证书，但**取景差得很远** —— wu 那张是斜着"
              "拍的照片、这张是正面扫的。改了三轮（照 wu 的坐标挪一点 / 打到"
              "「证书」标题上 / 再回落一行）。**同批证书也要各自量**"),
    Cert("bisheng-2013-third", "image59.jpeg",
         masks=((0.355, 0.275, 0.465, 0.325),),
         note="正文里「兹 哈尔滨工程大学 XXX 同学在…」中间那一个名字。"
              "下面「本届特邀评委」那五位是外校教授、印在证书上的评委署名，"
              "按「指导教师不脱敏」同一条口径留着"),
    Cert("nuedc-2022-intel-second", "image67.jpeg", rotate=270,
         masks=((0.20, 0.460, 0.50, 0.525),),
         note="源图横躺，转 270° 才正（先试的 90° 转成了倒的）。"
              "遮的是**左半**「参赛队员 / TEAM MEMBERS」那一行三个名字 —— "
              "第一版按右半的坐标标，结果打在英文「CERTIFICATE」上、名字整行露着。"
              "「指导教师 / SUPERVISOR 侯长波」在下方留着"),
    Cert("nuedc-2022-ti-third", "image72.png",
         masks=((0.17, 0.208, 0.53, 0.268),
                (0.845, 0.522, 1.0, 0.575)),
         note="**中英文两处。** 左半「参赛队员」三个名字；右半英文正文句末一个。"
              "「指导教师 侯长波」在队员下一行，按口径留着"),
    Cert("icm-2022-meritorious-a", "image68.jpeg",
         masks=((0.35, 0.302, 0.65, 0.415),),
         note="三个名字居中各占一行，一个框连着遮。第一版上边界差一行，"
              "第一个名字露在框外。下面「With Faculty Advisor」那一位按口径留着"),
    Cert("icm-2022-meritorious-b", "image76.png",
         masks=((0.39, 0.265, 0.65, 0.40),),
         note="三个名字居中各占一行；「With Faculty Advisor」那位留着"),
    Cert("lanqiao-2022-eda-hlj-first", "image75.jpeg",
         masks=((0.32, 0.326, 0.51, 0.362),
                (0.39, 0.608, 0.83, 0.640)),
         note="**第二个框是 18 位「证件号码」—— 身份证号。** 比姓名敏感得多，"
              "而它就印在证书上，只看文字字段是发现不了的。"
              "上面那个「证书编号：191300631」是奖项编号，留着（记录里也有）。"
              "第一个框是姓名，紧跟在校名后面没有分隔符"),
    Cert("mcm-2023-hlj-first", "image103.jpeg",
         masks=((0.23, 0.365, 0.55, 0.635),),
         note="三个名字竖排在「学 生：」之后，一个框连着遮。第一版下边界差一点，"
              "第三个名字露在外面 —— 竖排多行的框宁可给大：多遮一点背景没代价，"
              "漏一个名字有代价。「指导教师：」在框外，留着"),
    Cert("datang-2024-hlj-second", "image105.jpeg",
         masks=((0.08, 0.288, 0.27, 0.332),
                (0.255, 0.516, 0.55, 0.564)),
         note="**同一张里出现两次**：开头「XXX同学：」称呼一次，中部「参赛队员：」"
              "又列一次。只遮一处等于没遮。第二个框的下边界要卡在 0.564 —— "
              "再往下就把「指导教师：侯长波」也吃掉了（0.577 起）"),
    Cert("hlj-2024-ti-first-a", "image80.jpeg",
         masks=((0.29, 0.438, 0.64, 0.482),),
         note="「学生姓名：」那一行。目测连错两轮（先打在「获奖证书」上、"
              "再打在「学校名称」上），最后是靠裁网格图放大量出来的 —— "
              "这张的粉色缠枝底纹让 --rows 也失灵。"
              "下一行「指导教师：肖易寒」与「参赛题目」都留着"),
    Cert("hlj-2024-ti-first-b", "image71.jpeg",
         masks=((0.53, 0.40, 0.97, 0.63),),
         note="一叠证书扇形摊开，只有最上面那张读得出 —— 也只有它需要遮。"
              "那几行是斜排的，矩形框套斜排文字只能给大：第一版右边界 0.90，"
              "「、曹鹏」正好露在外面"),
    Cert("wusi-2024-innovator", "image111.jpeg",
         masks=((0.18, 0.336, 0.58, 0.408),),
         note="「授予 XXX：」那一行 —— 紧贴在「荣誉证书」标题下面。源图只有 307×433，"
              "是这一批里最小的一张，目测 y 的绝对误差反而最大：改了四轮，"
              "最后一版是拿上一次的落点（正好压在标题上）往下推一行、并把框给足"),
]


def mosaic(im, boxes):
    """把每个归一化框内的区域打成马赛克。

    做法是「缩到几个像素再放回去」：块内信息被真的丢掉了，不像模糊只是把它摊开。
    用 NEAREST 放回去 —— 用平滑插值会让色块之间过渡出渐变，看着像失焦而不是遮挡。
    """
    from PIL import Image

    w, h = im.size
    for x0, y0, x1, y1 in boxes:
        box = (max(0, round(x0 * w)), max(0, round(y0 * h)),
               min(w, round(x1 * w)), min(h, round(y1 * h)))
        bw, bh = box[2] - box[0], box[3] - box[1]
        if bw < 2 or bh < 2:
            continue
        # 长边压到 MOSAIC_BLOCKS_LONG 个像素，短边按比例（至少 1）
        if bw >= bh:
            sw = min(bw, MOSAIC_BLOCKS_LONG)
            sh = max(1, round(bh * sw / bw))
        else:
            sh = min(bh, MOSAIC_BLOCKS_LONG)
            sw = max(1, round(bw * sh / bh))
        small = im.crop(box).resize((sw, sh), Image.BOX)
        im.paste(small.resize((bw, bh), Image.NEAREST), box)
    return im


def text_rows(im, x_lo=0.08, x_hi=0.92, y_lo=0.03, y_hi=0.97):
    """把图里的**文字行**自动量出来，返回 [(y0, y1, x0, x1), …] 归一化坐标。

    **为什么要有这一步**：靠眼睛在网格图上读 y 坐标，我连错了三轮 —— 遮罩打在标题上、
    打在上一行、打在页边，而姓名整行露在外面。y 方向的目测误差稳定在 0.05~0.13，
    足够让每一次都落空。行位置是可以量的，就不该猜。

    做法：先只看中间区域（跳过花边与印章），逐行统计「墨量」= 比该行背景暗多少，
    超过阈值的连续行归成一段。证书底纹是浅色大面积、文字是深色细线，两者的行均值
    差得很开，所以这个朴素办法在这一批上足够用。

    x 范围是那一段里实际有墨的横向跨度 —— 顺带把「这一行文字从哪到哪」也给出来，
    免得右边界又切掉最后一个字。

    **它不是万能的，两种情况会失灵**，遇到就换下面那个办法：
      - 底纹重的证书（`hlj-2024-ti-first-a` 的粉色缠枝纹）：细字压不出行峰，
        806x1140 只量出 5 行，字段行全丢；
      - 花边带文字的证书（`lanqiao` 的「蓝桥杯」水印列）：x 跨度被边框污染，
        每一行都报成 0.08 起。

    **失灵时的办法**：把网格图裁一段放大再读 ——
        python scripts/build_certs.py --grid --only NAME
        python scripts/crop.py .artsrc/certs-grid/NAME.png --box 0 280 806 520 --zoom 2
    放大到 2 倍之后每一行落在哪一格是能直接看清的，再按
    `y = (裁剪上边 + 显示y/缩放) / 原图高` 换算。这一批里最后三张就是这么定下来的。
    """
    import statistics

    g = im.convert("L")
    w, h = g.size
    box = (round(w * x_lo), round(h * y_lo), round(w * x_hi), round(h * y_hi))
    crop = g.crop(box)
    cw, ch = crop.size
    px = crop.load()

    # 每行的「暗像素占比」。用占比而不是均值：均值会被大面积浅底纹拉平，
    # 而一行细黑字的暗像素占比很突出。
    dark_cut = 140          # 灰度低于此算「墨」
    ratios = []
    for y in range(ch):
        n = sum(1 for x in range(0, cw, 2) if px[x, y] < dark_cut)
        ratios.append(n / max(1, cw // 2))

    base = statistics.median(ratios)
    peak = max(ratios)
    if peak <= base:
        return []
    thr = base + (peak - base) * 0.18

    bands, start = [], None
    for y, r in enumerate(ratios):
        if r >= thr and start is None:
            start = y
        elif r < thr and start is not None:
            if y - start >= max(3, ch // 200):     # 太薄的是花边或噪点
                bands.append((start, y))
            start = None
    if start is not None:
        bands.append((start, ch))

    out = []
    for y0, y1 in bands:
        xs = [x for x in range(cw)
              for y in range(y0, y1, max(1, (y1 - y0) // 4) or 1)
              if px[x, y] < dark_cut]
        if not xs:
            continue
        out.append((
            (box[1] + y0) / h, (box[1] + y1) / h,
            (box[0] + min(xs)) / w, (box[0] + max(xs)) / w,
        ))
    return out


def draw_grid(im):
    """叠一层 10% 网格与标注，用来人工读出遮罩框的坐标。

    没有这一步就只能盯着图猜百分比，然后跑一遍、看一遍、再调 —— 一张图要来回三四次。
    有网格是一次读图就能把框写下来。
    """
    from PIL import ImageDraw

    im = im.convert("RGB")
    w, h = im.size
    d = ImageDraw.Draw(im, "RGBA")
    for i in range(1, 10):
        x, y = round(w * i / 10), round(h * i / 10)
        strong = i == 5
        color = (255, 40, 40, 220) if strong else (0, 200, 255, 150)
        d.line([(x, 0), (x, h)], fill=color, width=2 if strong else 1)
        d.line([(0, y), (w, y)], fill=color, width=2 if strong else 1)
        d.text((x + 3, 3), f".{i}", fill=(255, 255, 0, 255))
        d.text((3, y + 3), f".{i}", fill=(255, 255, 0, 255))
    return im


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description="证书照片 → webp（含姓名区域打码）")
    ap.add_argument("--list", action="store_true", help="只列清单，不处理")
    ap.add_argument("--only", help="只处理这一个输出名")
    ap.add_argument("--grid", action="store_true",
                    help="不处理，改为把源图叠上 10%% 网格写到 .artsrc/certs-grid/，"
                         "用来人工读出遮罩框坐标")
    ap.add_argument("--rows", action="store_true",
                   help="不处理，改为把每一行文字的归一化坐标量出来打印 —— "
                        "标遮罩框请用它，别靠眼睛读网格")
    ap.add_argument("--proof", action="store_true",
                    help="额外把处理结果按原尺寸另存一份到 .artsrc/certs-proof/，"
                         "供逐张看图确认姓名真的遮住了")
    args = ap.parse_args()

    try:
        from PIL import Image
    except ImportError:
        print("需要 Pillow：python -m pip install pillow（开发工具，不进 requirements）")
        return 2

    certs = [c for c in CERTS if not args.only or c.name == args.only]
    if args.only and not certs:
        print(f"没有叫 {args.only} 的证书。--list 看全部。")
        return 1

    missing = [c.src for c in certs if not (SRC / c.src).exists()]
    if args.list or missing:
        print(f"源目录 {SRC}")
        for c in certs:
            path = SRC / c.src
            mark = "OK " if path.exists() else "缺 "
            size = f"{path.stat().st_size / 1024:.0f} KB" if path.exists() else "—"
            flag = f"{len(c.masks)} 处遮罩" if c.masks else "**未标遮罩**"
            print(f"  {mark} {c.name:30s} ← {c.src:26s} {size:>9s}  {flag}")
        if missing:
            print(f"\n缺 {len(missing)} 个源文件，先把它们放进 {SRC}")
            print("（母图从 PPT 里挖：python scripts/dump_pptx.py，"
                  "然后按 docs/PPT素材清单.md 把用到的那些复制进 .artsrc/certs/）")
            return 1
        if args.list:
            return 0

    if args.rows:
        for c in certs:
            im = Image.open(SRC / c.src)
            if c.rotate:
                im = im.rotate(c.rotate, expand=True)
            rows = text_rows(im)
            print(f"\n{c.name}  {im.size[0]}x{im.size[1]}  共 {len(rows)} 行")
            for i, (y0, y1, x0, x1) in enumerate(rows):
                print(f"  行{i:<3d} y {y0:.3f}~{y1:.3f}   x {x0:.3f}~{x1:.3f}"
                      f"   （高 {(y1 - y0):.3f}）")
        return 0

    if args.grid:
        grid_dir = REPO / ".artsrc" / "certs-grid"
        grid_dir.mkdir(parents=True, exist_ok=True)
        for c in certs:
            im = Image.open(SRC / c.src)
            if c.rotate:
                im = im.rotate(c.rotate, expand=True)
            im = draw_grid(im)
            im.save(grid_dir / f"{c.name}.png")
            print(f"  {c.name:30s} {im.size[0]}x{im.size[1]}")
        print(f"\n写到 {grid_dir.relative_to(REPO)}/ —— 读图定出框，"
              "再写进 CERTS 的 masks（归一化坐标）")
        return 0

    OUT.mkdir(parents=True, exist_ok=True)
    proof_dir = REPO / ".artsrc" / "certs-proof"
    if args.proof:
        proof_dir.mkdir(parents=True, exist_ok=True)

    total_in = total_out = 0
    unmasked = []
    for c in certs:
        im = Image.open(SRC / c.src).convert("RGB")
        if c.rotate:
            im = im.rotate(c.rotate, expand=True)
        w, h = im.size
        # **先打码再缩放。** 反过来也行，但归一化坐标是照着源图标的，
        # 在源尺寸上打完再缩，马赛克块会跟着一起被重采样、边缘变软 ——
        # 那正好让「这里是刻意遮的」这件事读起来更自然。
        if c.masks:
            im = mosaic(im, c.masks)
        else:
            unmasked.append(c.name)
        if args.proof:
            im.save(proof_dir / f"{c.name}.png")
        scale = min(1.0, LONG_EDGE / max(w, h))
        if scale < 1.0:
            im = im.resize((round(w * scale), round(h * scale)), Image.LANCZOS)
        dest = OUT / f"{c.name}.webp"
        im.save(dest, "WEBP", quality=QUALITY, method=6)
        size_in = (SRC / c.src).stat().st_size
        size_out = dest.stat().st_size
        total_in += size_in
        total_out += size_out
        print(f"  {c.name:30s} {w}x{h} → {im.size[0]}x{im.size[1]}  "
              f"{size_in / 1024:6.0f} KB → {size_out / 1024:5.0f} KB  "
              f"{len(c.masks)} 处遮罩")

    print(f"\n合计 {total_in / 1024 / 1024:.1f} MB → {total_out / 1024:.0f} KB  "
          f"（{len(certs)} 张，写到 {OUT.relative_to(REPO)}）")
    if args.proof:
        print(f"原尺寸校对图在 {proof_dir.relative_to(REPO)}/ —— 逐张看一遍")
    if unmasked:
        print(f"\n**{len(unmasked)} 张没有标遮罩**："+ "、".join(unmasked))
        print("  空的 masks 表示「确认过、这张没有姓名」。要是还没标，先跑 --grid。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
