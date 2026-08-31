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
"""
from pathlib import Path

from django.core.files import File
from django.core.management.base import BaseCommand
from django.db import transaction

from news.models import Honor

DATA = Path(__file__).resolve().parents[2] / "data" / "honors"

N = Honor.Level.NATIONAL
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
]


class Command(BaseCommand):
    help = "把协会历年获奖（含证书照片）录进荣誉墙。幂等，可重复跑。"

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true",
                            help="只打印将要做什么，不写库")

    def handle(self, *args, **options):
        dry = options["dry_run"]
        created = updated = attached = skipped_img = 0

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
