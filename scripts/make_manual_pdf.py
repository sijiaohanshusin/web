"""
生成《HEU ESTA 官网使用手册 v1.0》PDF。
用法: python make_manual_pdf.py <输出路径.pdf>
"""
import sys
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    KeepTogether,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

# ---------------- 字体 ----------------
FONTS = Path(r"C:\Windows\Fonts")
pdfmetrics.registerFont(TTFont("YaHei", str(FONTS / "msyh.ttc"), subfontIndex=0))
pdfmetrics.registerFont(TTFont("YaHeiB", str(FONTS / "msyhbd.ttc"), subfontIndex=0))

# ---------------- 配色 ----------------
NAVY = colors.HexColor("#0b1c3a")
NAVY_DEEP = colors.HexColor("#071228")
CYAN = colors.HexColor("#0ea5e9")
ORANGE = colors.HexColor("#f97316")
INK = colors.HexColor("#1e293b")
MUTED = colors.HexColor("#64748b")
LINE = colors.HexColor("#dbe4f0")
ROW_ALT = colors.HexColor("#f2f7fd")

PAGE_W, PAGE_H = A4
M = 18 * mm

VERSION = "v1.0（内测版）"
DATE = "2026 年 7 月"

# ---------------- 样式 ----------------
def st(name, **kw):
    base = dict(fontName="YaHei", fontSize=10.5, leading=17, textColor=INK)
    base.update(kw)
    return ParagraphStyle(name, **base)


S_H1 = st("h1", fontName="YaHeiB", fontSize=16, leading=22, textColor=NAVY,
          spaceBefore=16, spaceAfter=8)
S_H2 = st("h2", fontName="YaHeiB", fontSize=12, leading=18, textColor=NAVY,
          spaceBefore=10, spaceAfter=4)
S_BODY = st("body", spaceAfter=5)
S_LI = st("li", leftIndent=14, firstLineIndent=0, spaceAfter=3, bulletIndent=4)
S_NOTE = st("note", fontSize=9.5, leading=15, textColor=MUTED, spaceAfter=5)
S_TOC = st("toc", fontSize=11.5, leading=24, textColor=INK)


def h1(text):
    # 带青色左条的章节标题
    tbl = Table([[Paragraph(text, S_H1)]], colWidths=[PAGE_W - 2 * M])
    tbl.setStyle(TableStyle([
        ("LINEBEFORE", (0, 0), (0, 0), 3, CYAN),
        ("LEFTPADDING", (0, 0), (-1, -1), 10),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
    ]))
    return tbl


def li(text):
    return Paragraph(text, S_LI, bulletText="•")


def link(url):
    return f'<font color="#0ea5e9">{url}</font>'


# ---------------- 页面装饰 ----------------
def draw_cover(canvas, doc):
    c = canvas
    c.saveState()
    c.setFillColor(NAVY_DEEP)
    c.rect(0, 0, PAGE_W, PAGE_H, stroke=0, fill=1)

    # PCB 走线风装饰
    c.setStrokeColor(colors.HexColor("#123059"))
    c.setLineWidth(1.2)
    for i, y in enumerate(range(40, int(PAGE_H), 52)):
        x0 = 0 if i % 2 == 0 else PAGE_W * 0.55
        x1 = PAGE_W * 0.45 if i % 2 == 0 else PAGE_W
        c.line(x0, y, x1, y)
        c.setFillColor(colors.HexColor("#123059"))
        c.circle(x1 if i % 2 == 0 else x0, y, 2.6, stroke=0, fill=1)

    c.setFillColor(CYAN)
    c.setFont("YaHeiB", 13)
    c.drawString(M, PAGE_H - 60 * mm, "哈尔滨工程大学电子科技协会")

    c.setFillColor(colors.white)
    c.setFont("YaHeiB", 34)
    c.drawString(M, PAGE_H - 78 * mm, "HEU ESTA 官网")
    c.drawString(M, PAGE_H - 92 * mm, "使 用 手 册")

    # 版本徽章
    c.setFillColor(ORANGE)
    c.roundRect(M, PAGE_H - 106 * mm, 52 * mm, 9 * mm, 4.5 * mm, stroke=0, fill=1)
    c.setFillColor(colors.white)
    c.setFont("YaHeiB", 11)
    c.drawCentredString(M + 26 * mm, PAGE_H - 103.2 * mm, f"第一版 · {VERSION}")

    c.setFillColor(colors.HexColor("#9db7dc"))
    c.setFont("YaHei", 11.5)
    c.drawString(M, PAGE_H - 122 * mm, "官网  https://heuesta.cn")
    c.drawString(M, PAGE_H - 129 * mm, "论坛  https://bbs.heuesta.cn")

    c.setFont("YaHei", 9.5)
    c.drawString(M, 22 * mm, f"{DATE} 发布 · 内测阶段文档，功能以线上实际为准")
    c.restoreState()


def draw_body(canvas, doc):
    c = canvas
    c.saveState()
    # 页眉
    c.setFillColor(MUTED)
    c.setFont("YaHei", 8.5)
    c.drawString(M, PAGE_H - 12 * mm, "HEU ESTA 官网使用手册")
    c.drawRightString(PAGE_W - M, PAGE_H - 12 * mm, VERSION)
    c.setStrokeColor(LINE)
    c.setLineWidth(0.8)
    c.line(M, PAGE_H - 14 * mm, PAGE_W - M, PAGE_H - 14 * mm)
    # 页脚
    c.line(M, 14 * mm, PAGE_W - M, 14 * mm)
    c.setFont("YaHei", 8.5)
    c.drawCentredString(PAGE_W / 2, 9 * mm, f"第 {doc.page - 1} 页 · 哈尔滨工程大学电子科技协会")
    c.restoreState()


def on_page(canvas, doc):
    if doc.page == 1:
        draw_cover(canvas, doc)
    else:
        draw_body(canvas, doc)


# ---------------- 内容 ----------------
def build_story():
    story = [PageBreak()]
    W = PAGE_W - 2 * M

    # 目录
    story.append(h1("目录"))
    toc_items = [
        "一、网站总览", "二、注册账号", "三、登录与找回密码", "四、个人中心",
        "五、会员等级体系", "六、资料站", "七、论坛", "八、内测反馈（重要）",
        "九、管理功能速览（干事及以上）", "十、常见问题 FAQ",
    ]
    rows = [[Paragraph(toc_items[i], S_TOC),
             Paragraph(toc_items[i + 1] if i + 1 < len(toc_items) else "", S_TOC)]
            for i in range(0, len(toc_items), 2)]
    toc = Table(rows, colWidths=[W / 2, W / 2])
    toc.setStyle(TableStyle([
        ("TOPPADDING", (0, 0), (-1, -1), 2), ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
    ]))
    story.append(toc)
    story.append(Spacer(1, 6))

    # 一、总览
    story.append(h1("一、网站总览"))
    story.append(Paragraph(
        "科协网站由两部分组成，共用同一套账号（在官网登录后，进入论坛自动登录）：", S_BODY))
    tbl = Table([
        ["站点", "网址", "用来做什么"],
        ["官网（主站）", "https://heuesta.cn", "了解科协、注册会员、下载资料、个人中心"],
        ["论坛", "https://bbs.heuesta.cn", "技术讨论、灌水交流、新人报到、意见反馈"],
    ], colWidths=[W * 0.2, W * 0.32, W * 0.48])
    tbl.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, -1), "YaHei"),
        ("FONTNAME", (0, 0), (-1, 0), "YaHeiB"),
        ("FONTSIZE", (0, 0), (-1, -1), 9.5),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("BACKGROUND", (0, 0), (-1, 0), NAVY),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, ROW_ALT]),
        ("GRID", (0, 0), (-1, -1), 0.6, LINE),
        ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
    ]))
    story.append(tbl)
    story.append(Spacer(1, 4))
    story.append(Paragraph(
        "内测阶段全站开放注册，新用户自动获得「干事」权限以便体验全部功能；"
        "正式上线后会统一调整为正常等级。", S_NOTE))

    # 二、注册
    story.append(h1("二、注册账号"))
    for i, t in enumerate([
        f"打开注册页：{link('https://heuesta.cn/accounts/register/')}",
        "填写用户名（登录用）、姓名、学号、学院、年级（入学年份，如 2025）、邮箱、手机号；QQ 号选填",
        "点击邮箱栏旁的「获取验证码」按钮，到邮箱查收 6 位验证码（QQ 邮箱即可；第一次请留意垃圾箱，"
        "发件人为 noreply@heuesta.cn，可标记为「非垃圾邮件」）",
        "输入验证码、设置密码（至少 8 位，不能是纯数字），提交后即注册成功并自动登录",
    ], start=1):
        story.append(li(f"<b>第 {i} 步</b>　{t}"))
    story.append(Paragraph(
        "注意：学号、邮箱、手机号都是一人一号，重复会提示已注册；密码请勿使用你在其它网站的常用密码。", S_NOTE))

    # 三、登录
    story.append(h1("三、登录与找回密码"))
    story.append(li("<b>密码登录</b>　用户名 + 密码，登录页右上角「登录」进入"))
    story.append(li("<b>验证码登录</b>　登录页下方「验证码登录」：输入邮箱收码登录，忘带密码时最方便"))
    story.append(li("<b>忘记密码</b>　登录页下方「忘记密码？」：邮箱收码后直接设置新密码"))
    story.append(li("<b>修改密码</b>　登录后进入个人中心，点「修改密码」"))
    story.append(li("<b>论坛登录</b>　先在官网登录，再打开论坛即自动登录，无需单独注册"))

    # 四、个人中心
    story.append(h1("四、个人中心"))
    story.append(Paragraph("登录后点击右上角自己的名字进入。可以做这些事：", S_BODY))
    story.append(li("查看自己的届别与等级头衔（如「25届 · 干事」）、职位徽章"))
    story.append(li("勋章墙：协会活动、竞赛获奖等获得的勋章都显示在这里"))
    story.append(li("编辑资料：修改姓名、学院、年级、QQ、手机号，上传头像"))
    story.append(li("查看自己上传过的资料及其下载量"))

    # 五、等级
    story.append(h1("五、会员等级体系"))
    story.append(Paragraph(
        "全站用统一的六级体系（对应招新流程），等级决定能看到的资料和版块：", S_BODY))
    lv = Table([
        ["等级", "名称", "如何获得", "主要权限"],
        ["0", "待审核", "注册后等待审核（自动审核开启时跳过）", "仅公开内容"],
        ["1", "报名会员", "报名参加科协", "报名级资料"],
        ["2", "预备会员", "通过第一轮面试", "预备级资料"],
        ["3", "正式会员", "通过第二轮面试", "正式级资料、论坛内部版块"],
        ["4", "干事", "担任协会干事", "上传资料、管理驾驶舱、审核会员"],
        ["5", "管理员", "协会管理层任命", "全部管理权限、站点设置"],
    ], colWidths=[W * 0.09, W * 0.15, W * 0.4, W * 0.36])
    badge_colors = ["#94a3b8", "#38bdf8", "#0ea5e9", "#2563eb", "#f59e0b", "#ef4444"]
    style = [
        ("FONTNAME", (0, 0), (-1, -1), "YaHei"),
        ("FONTNAME", (0, 0), (-1, 0), "YaHeiB"),
        ("FONTSIZE", (0, 0), (-1, -1), 9.5),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("BACKGROUND", (0, 0), (-1, 0), NAVY),
        ("GRID", (0, 0), (-1, -1), 0.6, LINE),
        ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("ALIGN", (0, 0), (0, -1), "CENTER"),
    ]
    for r, hexc in enumerate(badge_colors, start=1):
        style.append(("TEXTCOLOR", (1, r), (1, r), colors.HexColor(hexc)))
        style.append(("FONTNAME", (1, r), (1, r), "YaHeiB"))
    lv.setStyle(TableStyle(style))
    story.append(lv)
    story.append(Paragraph(
        "等级在论坛显示为 ID 旁的彩色徽章，晋升后自动更换；有职位（主席、硬件主席、软件主席等）"
        "的成员会额外显示金色系职位徽章。", S_NOTE))

    # 六、资料站
    story.append(h1("六、资料站"))
    story.append(li(f"入口：导航栏「资料下载」或 {link('https://heuesta.cn/resources/')}"))
    story.append(li("支持按分类（培训 / 竞赛 / 工具 / 其他）筛选和关键词搜索"))
    story.append(li("每份资料标有「可见等级」，达到等级即可下载；下载次数公开可见"))
    story.append(li("干事及以上可上传资料（单文件最大 200MB），上传时设置分类与可见等级"))

    # 七、论坛
    story.append(h1("七、论坛"))
    story.append(li("官网登录后打开论坛自动登录；首次进入会自动创建论坛账号"))
    story.append(li("版块：站务中心（公告 / 意见反馈 / 内部事务）、新人专区、硬件天地、嵌入式与软件、竞赛与项目、生活广场"))
    story.append(li("「内部事务」版块仅正式会员及以上可见——看不到它是正常的"))
    story.append(li("发帖：进入目标版块点「发布新主题」；支持 Markdown、图片上传、@ 成员、表情"))
    story.append(li("楼层号、作者信息栏是科协自制的 MCBBS 复古风格，欢迎体验找茬"))

    # 八、反馈
    story.append(h1("八、内测反馈（重要）"))
    story.append(Paragraph(
        "这是内测阶段最重要的功能——你们的每条反馈都会进入系统，由管理组统一审阅、逐条处理。", S_BODY))
    story.append(li("<b>入口 1</b>　任意页面右下角的橙色「内测反馈」大按钮，弹窗里直接写、直接交"))
    story.append(li(f"<b>入口 2</b>　独立反馈页 {link('https://heuesta.cn/feedback/')}（论坛右下角按钮也跳这里）"))
    story.append(li("<b>入口 3</b>　想公开讨论的话题，去论坛「意见反馈」版块发帖"))
    story.append(Paragraph("反馈时请写清三件事：", S_BODY))
    story.append(li("在<b>哪个页面</b>（贴网址或页面名）"))
    story.append(li("做了<b>什么操作</b>（点了什么、输入了什么）"))
    story.append(li("遇到<b>什么问题</b>，或者你期望的效果"))
    story.append(Paragraph(
        "提交后可随时回到反馈页查看处理状态和管理组回复。功能建议、界面吐槽同样欢迎。", S_NOTE))

    # 九、管理
    story.append(KeepTogether([
        h1("九、管理功能速览（干事及以上）"),
        Paragraph(
            "内测期间人人都是干事，都可以进「管理驾驶舱」体验（右上角名字旁的入口）：", S_BODY),
        li("<b>数据总览</b>　注册趋势、年级分布、资料下载排行、B 站粉丝走势"),
    ]))
    story.append(li("<b>会员管理</b>　按等级 / 年级筛选成员，批量通过审核、晋升等级（设干事、设管理员为管理员专属）"))
    story.append(li("<b>资料管理</b>　上传、搜索、删除资料"))
    story.append(li("<b>反馈管理</b>　审阅内测反馈，标记已处理并回复备注"))
    story.append(li("<b>勋章 / 职位管理</b>（管理员）　创建勋章授予成员；任命职位（同步为论坛彩色头衔）"))
    story.append(li("<b>站点设置</b>（管理员）　改首页轮播图、招新视频 BV 号、内测模式与自动审核开关"))
    story.append(Paragraph("体验管理功能时请手下留情：不要删改别人的账号和数据。", S_NOTE))

    # 十、FAQ
    story.append(h1("十、常见问题 FAQ"))
    faqs = [
        ("收不到验证码？",
         "先看垃圾箱（发件人 noreply@heuesta.cn）；60 秒内只能发一次，别连点；单个邮箱每天上限 10 条。"),
        ("提示「该学号 / 邮箱 / 手机号已注册」？",
         "说明之前注册过，直接登录；忘了密码就走「忘记密码」用邮箱找回。"),
        ("论坛没有自动登录？",
         "先确认官网右上角是登录状态，再刷新论坛页面；仍不行请清一下浏览器 Cookie 后重试，并反馈给我们。"),
        ("看不到「内部事务」版块？",
         "该版块仅正式会员及以上可见，属于正常现象。"),
        ("手机上页面排版乱 / 按钮点不到？",
         "截图 + 手机型号，用右下角反馈按钮发给我们，这类问题优先修。"),
        ("内测账号以后还能用吗？",
         "能。正式上线时账号保留，仅等级会按真实身份统一调整。"),
    ]
    for q, a in faqs:
        story.append(Paragraph(f"<b>Q：{q}</b>", st("q", spaceBefore=6, spaceAfter=2)))
        story.append(Paragraph(f"A：{a}", st("a", textColor=MUTED, leftIndent=14, spaceAfter=2)))

    story.append(Spacer(1, 14))
    story.append(Paragraph(
        "—— 感谢每一位内测玩家，你们的反馈决定正式版的样子 ——",
        st("end", alignment=1, textColor=CYAN, fontName="YaHeiB", fontSize=11)))
    return story


def main():
    out = sys.argv[1] if len(sys.argv) > 1 else "manual.pdf"
    doc = SimpleDocTemplate(
        out, pagesize=A4,
        leftMargin=M, rightMargin=M, topMargin=20 * mm, bottomMargin=20 * mm,
        title="HEU ESTA 官网使用手册 v1.0",
        author="哈尔滨工程大学电子科技协会",
    )
    doc.build(build_story(), onFirstPage=on_page, onLaterPages=on_page)
    print("written:", out)


if __name__ == "__main__":
    main()
