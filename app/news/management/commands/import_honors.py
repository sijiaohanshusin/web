# -*- coding: utf-8 -*-
"""把协会历年获奖录进荣誉墙。

    python manage.py import_honors --dry-run     # 只说要做什么
    python manage.py import_honors               # 真的写

**为什么是管理命令而不是 fixture 或 SQL**：每条记录要顺带把证书照片喂给
`Honor.certificate`（`ImageField`），而 fixture 只能填文件**路径**、不会真的把文件
放进 `MEDIA_ROOT`。生产上跑一次这个命令，数据和图一起就位。

**为什么图片能跟着代码走**：`certificate` 落在 `MEDIA_ROOT` 下，而 `app/media/`
是 gitignore 的 —— 本地导入的图到不了生产。所以处理好的 webp 放在
`app/news/data/honors/`（跟着代码），这里再把它们喂进 ImageField。
产物由 `scripts/build_certs.py` 生成，母图在 `.artsrc/certs/`（不入库）。

数据来源是 2025 招新宣讲 PPT 里内嵌的证书照片，逐张读出来的；等级、年份、队员
姓名都以证书原件为准。

**姓名一律脱敏，保留首尾、中间打星（`夏*元`）。** 规则与理由见
`scripts/mask_names.py`：这个仓库是公开的，真名一旦进了这个文件就等于发布了，
所以真名只留在 `.artsrc/honors-names.txt`（不入库），仓库里从头到尾只有脱敏串。
`news/tests.py` 有一条独立断言扫这里的每个 `awardee`，漏一个就红。
**证书图片同样要遮**（`scripts/build_certs.py` 里逐张标了姓名区域），
不然图一贴上去等于没脱敏。

**指导教师不脱敏**：竞赛证书上的指导教师是职务署名，学院公众号发获奖通报时也是
指名写的。这是一处判断，不是漏做。

幂等：按「年份 + 奖项 + 获奖人」三者定位，重跑不会堆数据。证书只在这一条还没有
图的时候才写 —— 否则每跑一次 media 里就多一份同名文件（Django 会自动加随机后缀，
不报错，只是越攒越多）。

    python manage.py import_honors --reset

**改了 `awardee` 就必须用 `--reset`。** 幂等键里含 `awardee`，姓名一脱敏键就变了 ——
直接重跑不会更新那些行，而是照着新键**再建一批**，库里就成了「同一个奖两条记录，
一条真名一条脱敏」。真名那条还留在页面上，等于脱敏做了一半。
`--reset` 先把这份清单里认得出的记录连同证书文件一起删掉再重建。

它只删「这份清单能对上的」：按 (year, title) 匹配，不是 `Honor.objects.all()` ——
站务手工在驾驶舱录的记录不在清单里，不能被一次导入顺手清掉。
"""
from pathlib import Path

from django.core.files import File
from django.core.management.base import BaseCommand
from django.db import transaction

from news.models import Honor

DATA = Path(__file__).resolve().parents[2] / "data" / "honors"

N = Honor.Level.NATIONAL
P = Honor.Level.PROVINCIAL
S = Honor.Level.SCHOOL
OTHER = Honor.Level.OTHER

# (年份, 奖项, 赛事, 等级, 获奖人, 补充说明, 证书文件名或 None, 是否上首页)
#
# `title` 里带奖项等级（模型 help_text 的口径：「全国大学生电子设计竞赛 一等奖」）。
# `contest` 放赛事简称与赛道，荣誉墙上它是标题下面的小字。
#
# 两条**没有证书照**：第十八届智能车独轮车组国一、TRIZ 杯创新方法大赛国一 ——
# PPT 里那两张只有 309x433，放到证书墙上是一块糊斑。奖项信息照录（PPT 正文里有），
# 图留空，模型注释也写了「证书照片是可选的加分项，不是骨架」。
HONORS = [
    (2026, "全国大学生嵌入式芯片与系统设计竞赛 全国一等奖",
     "嵌入式芯片赛 · 芯片应用赛道", N, "贾*博、高*彬、夏*元",
     "作品《基于 STM32N657 声学成像仪：AI 优化双精度 SRP-PHAT 算法实现》，指导教师 于蕾、侯长波",
     "esdc-2026-chip-first", True),

    (2025, "大唐杯全国大学生新一代信息通信技术大赛 全国一等奖",
     "大唐杯 · ICT 基础通识赛道", N, "李*阳、石*宇",
     "第十二届全国总决赛，指导教师 侯长波",
     "datang-2025-ict-first", True),
    (2025, "全国大学生智能汽车竞赛 全国一等奖",
     "智能车 · 气垫越野组", N, "杨*一",
     "第二十届全国总决赛，全国第二名",
     "smartcar-2025-hover-first", True),
    (2025, "全国大学生嵌入式芯片与系统设计竞赛 全国二等奖",
     "嵌入式芯片赛 · 芯片应用赛道", N, "卫*轩、吴*宇、郝*雷",
     "作品《基于 STM32F407 的便携嵌入式开发工具》，指导教师 侯长波",
     "esdc-2025-chip-second", False),

    (2024, "全国大学生电子设计竞赛 全国二等奖",
     "电赛 · 模拟电子系统设计专题赛（TI 杯）", N, "杨*一、张*弛、王*",
     "指导教师 朱海峰；电证字(2024) M-2009 号",
     "nuedc-2024-ti-second", False),
    (2024, "美国大学生数学建模竞赛 Meritorious Winner",
     "美赛 ICM", N, "Zhao Y***i、Ruan H*****i、Wang J***i",
     "国际赛事，Meritorious 约为参赛队前 8%；指导教师 Li Jinru",
     "icm-2024-meritorious", False),
    # 软著不是竞赛获奖，放 OTHER 而不是 NATIONAL —— 混进「国家级」会让那个计数
    # 变成「国赛获奖 + 别的东西」，而荣誉墙顶部就是按等级计数的。分量由标题里的
    # 「国家版权局」交代。
    (2024, "国家版权局 计算机软件著作权登记",
     "软件著作权", OTHER, "张*驰",
     "《基于信号分析的实时音频分析和频谱显示软件（RSTA 播放器）V1.0》，登记号 2024SR0981408",
     "copyright-2024-rsta", False),

    (2023, "全国大学生电子设计竞赛 全国二等奖",
     "电赛（本科组）", N, "蹇*琛、苏*俊、杨*临",
     "电证字(2023) 第 B-2356 号",
     "nuedc-2023-second-b2356", False),
    (2023, "全国大学生电子设计竞赛 全国二等奖",
     "电赛（本科组）", N, "雷*清、阮*方、陈*卉",
     "电证字(2023) 第 B-2363 号",
     "nuedc-2023-second-b2363", False),
    (2023, "全国大学生嵌入式芯片与系统设计竞赛 全国二等奖",
     "嵌入式芯片赛 · FPGA 创新设计竞赛", N, "王*亭、张*、郑*运",
     "作品《复杂调制样式智能收发平台》，指导教师 林云",
     "esdc-2023-fpga-second", False),
    (2023, "全国大学生智能汽车竞赛 全国一等奖",
     "智能车 · 独轮车组", N, "雷*清",
     "第十八届全国总决赛",
     None, False),

    (2022, "中国大学生创新方法大赛 全国一等奖",
     "TRIZ 杯", N, "雷*清", "",
     None, False),

    (2021, "全国大学生电子设计竞赛 全国一等奖",
     "电赛（本科组）", N, "王*昊、沈*、李*瑶",
     "电证字(2021) 第 B-1058 号",
     "nuedc-2021-first-b1058", True),
    (2021, "全国大学生电子设计竞赛 全国一等奖",
     "电赛（本科组）", N, "张*坤、王*文、王*华",
     "电证字(2021) 第 B-1059 号",
     "nuedc-2021-first-b1059", True),
    (2021, "全国大学生智能汽车竞赛 全国一等奖",
     "智能车 · 电磁越野组", N, "张*坤",
     "第十六届全国总决赛",
     "smartcar-2021-emag-first", False),

    # ================================================================
    # 以下是第二轮从 PPT 的 slide 12 / 13 / 20 里挖出来的（docs/PPT素材清单.md）。
    # 把起点从 2021 推到 2010 —— 那不只是「多了几条」：协会 1995 年成立，
    # 而荣誉墙原来最早只到 2021，读起来像个新社团。
    # ================================================================

    (2024, "全国大学生电子设计竞赛 嵌入式系统专题邀请赛 全国一等奖",
     "电赛 · 嵌入式系统专题邀请赛（英特尔杯）", N, "",
     # note 是**渲染在公开页面上的**，只能写给访客看的话。
     # 「为什么没有证书照、信息取自哪一页」这类考证过程写在 docs/PPT素材清单.md，
     # 不要写进这里 —— 第一版就是那么写的，于是页面上印着「PPT 里只拍到三本证书
     # 叠在一起的封面（image87）」，还带着 `**` 原始标记（这个字段不过 Markdown）。
     # 不能写「全省唯一一项」：两个「一」连排渲染出来像一道长破折号（「全省唯——项」）。
     # 同一个坑在新生指南的对照表里也踩过一次。
     "全省仅此一项",
     None, True),
    (2024, "黑龙江省大学生电子设计竞赛 省一等奖",
     "省电赛 · TI 杯", P, "陈*、高*超、叶*敏",
     "指导教师 肖易寒；题目《无线传输信号模拟系统》；证书编号 2024080020",
     "hlj-2024-ti-first-a", False),
    (2024, "黑龙江省大学生电子设计竞赛 省一等奖",
     "省电赛 · TI 杯", P, "卢*坤、张*远、曹*",
     "同年拿下的六项省一之一",
     "hlj-2024-ti-first-b", False),
    (2024, "大唐杯全国大学生新一代信息通信技术大赛 省二等奖",
     "大唐杯 · 信息通信工程实践赛道", P, "雷*清、陈*卉",
     "第十一届黑龙江省赛区本科 A 组；指导教师 侯长波；证书编号 HJYDTX202405004085",
     "datang-2024-hlj-second", False),
    (2024, "哈尔滨工程大学「五四」评比表彰 学生创新创业先进个人",
     "校级表彰", S, "雷*清",
     "2023-2024 年度",
     "wusi-2024-innovator", False),

    (2023, "全国大学生数学建模竞赛 省一等奖",
     "高教社杯 · 黑龙江赛区", P, "雷*清、庄*锐、陈*卉",
     "指导教师 张晓威",
     "mcm-2023-hlj-first", False),

    (2022, "全国大学生电子设计竞赛 嵌入式系统专题邀请赛 全国二等奖",
     "电赛 · 嵌入式系统专题邀请赛（英特尔杯）", N, "王*昊、王*、郭*铭",
     "指导教师 侯长波；电证字 2022-2-08 1 号",
     "nuedc-2022-intel-second", False),
    (2022, "全国大学生电子设计竞赛 全国三等奖",
     "电赛 · 模拟电子系统设计专题邀请赛（TI 杯）", N, "张*坤、王*华、王*文",
     "指导教师 侯长波；电证字(2022) 3-22 号",
     "nuedc-2022-ti-third", False),
    (2022, "美国大学生数学建模竞赛 Meritorious Winner",
     "美赛 ICM", N, "Wang C*****o、Li S***o、Shen A*",
     "指导教师 Wang Shujuan",
     "icm-2022-meritorious-a", False),
    (2022, "美国大学生数学建模竞赛 Meritorious Winner",
     "美赛 ICM", N, "Zhang X******g、Shang J*****g、Zhang Z*****g",
     "同届第二支队；指导教师 Cai Xinyu",
     "icm-2022-meritorious-b", False),
    (2022, "蓝桥杯全国软件和信息技术专业人才大赛 省一等奖",
     "蓝桥杯 · EDA 设计与开发（大学组）", P, "张*坤",
     "第十三届黑龙江赛区；证书编号 191300631",
     "lanqiao-2022-eda-hlj-first", False),

    (2013, "「毕昇杯」全国电子创新设计竞赛 全国三等奖",
     "毕昇杯（本科组）", N, "吴*炎",
     "第八届；作品 BS2013-B270《高层火灾智能语音报警系统》",
     "bisheng-2013-third", False),

    (2012, "「利尔达」杯全国物联网应用设计大赛 全国二等奖",
     "利尔达杯 · 物联网应用设计", N, "王*震、张*、吴*炎、陶*辉、潘*敏",
     "第二届；指导教师 侯长波、王伞；"
     "作品《基于 ZigBee 的无线传感器网络森林火灾监测系统》；中国电子学会",
     "lierda-2012-iot-second", False),
    (2012, "全国大学生电子设计竞赛 全国二等奖",
     "电赛 · 模拟电子系统设计专题邀请赛（TI 杯）", N, "吴*炎、张*、陈*翔",
     "电证字(2012) 2-005 号",
     "nuedc-2012-ti-second", False),
    (2012, "「北斗杯」全国青少年科技创新大赛 大学组优秀奖",
     "北斗杯", N, "王*震、吴*炎、陶*辉、潘*敏",
     "第三届；指导教师 王伞、侯长波；作品《可变形履带式环境检测机器人》",
     "beidou-2012-excellent", False),
    (2012, "信通学院学风建设 科技创新先进个人",
     "院级表彰", S, "吴*炎",
     "2011 年度",
     "xuefeng-2012-wu", False),
    (2012, "信通学院学风建设 科技创新先进个人",
     "院级表彰", S, "王*震",
     "2011 年度",
     "xuefeng-2012-wang", False),

    (2011, "全国大学生电子设计竞赛 全国二等奖",
     "电赛（本科组）", N, "王*震、赵*、陶*辉",
     "电证字(2011) 第 20220 号；教育部高教司 + 工信部人教司",
     "nuedc-2011-national-second", True),
    (2011, "全国高校电子信息实践创新作品评选 本科综合组一等奖",
     "中国电子学会", N, "王*震、赵*、陶*辉、潘*敏",
     "作品《可变型履带式环境检测机器人》。"
     "**证书上的获奖单位写的是「信息与通信工程学院学生科协」** —— "
     "这一条是以协会名义拿的奖",
     "eic-2011-national-first", True),
    (2011, "全国大学生电子设计竞赛 省一等奖",
     "电赛 · 黑龙江赛区", P, "吴*炎、马*里、田*慧",
     "指导教师 侯长波；证书编号 2011-SDZ1026",
     "nuedc-2011-hlj-first", False),
    (2011, "哈尔滨工程大学「五四杯」大学生科技创新竞赛 一等奖",
     "校级 · 五四杯（第十七届）", S, "王*震、赵*、卢*霖、曾*泉、王*亮",
     "作品《可变型履带监测机器人》",
     "wusi-2011-first", False),

    (2010, "哈尔滨工程大学「启航杯」大学生科技创新普及竞赛 一等奖",
     "校级 · 启航杯（第二届）", S, "王*震、卢*霖、戎*", "",
     "qihang-2010-first", False),
    (2010, "哈尔滨工程大学「启航杯」大学生科技创新普及竞赛 二等奖",
     "校级 · 启航杯（第二届）", S, "吴*炎、刘*玉", "",
     "qihang-2010-second", False),
]


class Command(BaseCommand):
    help = "把协会历年获奖（含证书照片）录进荣誉墙。幂等，可重复跑。"

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true",
                            help="只打印将要做什么，不写库")
        parser.add_argument("--reset", action="store_true",
                            help="先删掉这份清单里的记录（含证书文件）再重建。"
                                 "改了 awardee（比如脱敏）之后必须用它，"
                                 "否则会新建一批而不是更新")

    def handle(self, *args, **options):
        dry = options["dry_run"]
        created = updated = attached = skipped_img = 0

        if options["reset"] and not dry:
            # 只删这份清单认得出的记录：按 (year, title) 匹配。
            # 用 Honor.objects.all() 会把站务在驾驶舱手工录的记录也顺手清掉 ——
            # 那是一次导入不该有的权力。
            pairs = {(row[0], row[1]) for row in HONORS}
            doomed = [h for h in Honor.objects.all() if (h.year, h.title) in pairs]
            for honor in doomed:
                if honor.certificate:
                    # 文件要显式删。只 delete() 行的话 media 里会留一堆孤儿文件，
                    # 而下一次导入又会写入同名文件、Django 加随机后缀，越攒越多。
                    honor.certificate.delete(save=False)
                honor.delete()
            self.stdout.write(self.style.WARNING(
                f"--reset：删掉 {len(doomed)} 条清单内的旧记录（含证书文件），"
                "站务手工录的不动"))

        for (year, title, contest, level, awardee, note, cert, featured) in HONORS:
            key = {"year": year, "title": title, "awardee": awardee}
            existing = Honor.objects.filter(**key).first()
            action = "更新" if existing else "新建"

            if dry:
                img = cert or "（无证书照）"
                self.stdout.write(f"  {action}  {year} {title} · {awardee}  ← {img}")
                continue

            with transaction.atomic():
                honor, was_created = Honor.objects.update_or_create(
                    **key,
                    defaults={
                        "contest": contest,
                        "level": level,
                        "note": note,
                        "is_public": True,
                        "is_featured": featured,
                    },
                )
                created += was_created
                updated += not was_created

                # 只在这一条还没有图时才写。重复写的话 Django 会给同名文件加随机
                # 后缀，不报错，只是 media 里越攒越多。
                if cert and not honor.certificate:
                    src = DATA / f"{cert}.webp"
                    if not src.exists():
                        self.stderr.write(f"  证书文件缺失：{src}（先跑 scripts/build_certs.py）")
                        skipped_img += 1
                    else:
                        with src.open("rb") as fh:
                            honor.certificate.save(f"{cert}.webp", File(fh), save=True)
                        attached += 1

        if dry:
            self.stdout.write(self.style.WARNING(
                f"\n--dry-run：{len(HONORS)} 条待处理，没有写库"))
            return

        summary = Honor.summary()
        self.stdout.write(self.style.SUCCESS(
            f"\n新建 {created} 条 · 更新 {updated} 条 · 附上证书 {attached} 张"
            + (f" · 证书缺失 {skipped_img} 张" if skipped_img else "")))
        self.stdout.write(f"荣誉墙现在：{summary}")
