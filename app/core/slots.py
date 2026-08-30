# -*- coding: utf-8 -*-
"""素材槽登记表。

**槽位的声明在代码里，槽位的内容在数据库里。** 这个分工是有意的：

- 模板才知道「这个位置存在、需要一张 4:3 的合照」。让声明跟着模板走，改版时
  增删槽位和改模板是同一次提交，评审时能一起看到。
- 驾驶舱要能列出**还没有人上传**的槽位，否则站务不知道缺什么。如果声明也放
  数据库，一个还没建行的槽位就无从展示，「缺图清单」这个功能根本做不出来。
- 拍摄要求（brief）写在这里，占位框直接把它显示给用户看 —— 缺图不是异常状态，
  而是「等你来拍」的邀请，得说清要拍什么。

新增槽位的步骤：在下面 SLOTS 里加一条，然后在模板里 `{% slot "那个 key" %}`。
两边不一致会被 `SlotRegistryTests` 抓出来（扫描全部模板比对 key）。

key 的命名：`页面.区块.名字`，全小写，用点分段。例如 `home.gallery.group`。
"""
import re
from dataclasses import dataclass

KEY_RE = re.compile(r"^[a-z0-9]+(\.[a-z0-9_]+)+$")

IMAGE = "image"
VIDEO = "video"
KINDS = (IMAGE, VIDEO)


@dataclass(frozen=True)
class SlotSpec:
    """一个素材槽的声明。"""

    key: str
    label: str
    """人类可读的名字，占位框和驾驶舱清单都用它。"""

    ratio: str
    """CSS `aspect-ratio` 的值，例如 `"4 / 3"`。

    必填，且填了就一定要准：它负责在图片加载完成前把版面高度占住。没有它，
    一屏十几张图会在加载过程里反复把下面的内容顶来顶去。
    """

    brief: str
    """拍摄要求。会原样显示在占位框里，也显示在驾驶舱的缺图清单里。

    写「要什么」而不是「没有什么」。用户看到的是这句话，它决定他会不会去拍。
    """

    group: str
    """归组，驾驶舱按它分段。"""

    fallback: str = ""
    """兜底静态图，相对 static/ 的路径。

    只放**协会自己的**、已经提交进仓库的照片。这不是「找张图凑数」的口子 ——
    没有合适的自有素材就留空，让它显示成占位框，这比放一张不相干的图诚实。
    """

    priority: int = 50
    """缺图清单的排序，小的排前面。用来告诉站务先补哪张。"""

    kind: str = IMAGE
    """`image` 或 `video`。

    视频槽是图片槽的**超集**，不是另一套东西：`image` 字段继续用，只是身份变成
    「封面帧」。所以一个视频槽在只上传了封面时就退化成图片槽，在
    `prefers-reduced-motion` 下也是显示这一帧 —— 不需要为降级再准备一份素材。
    """


SLOTS: tuple[SlotSpec, ...] = (
    # ---------------- 首页 · 图片走廊「科协日常」 ----------------
    SlotSpec(
        key="home.gallery.pcb",
        label="PCB 设计与打样",
        ratio="4 / 3",
        brief="工位上的裸板特写，能看清丝印与焊盘；侧光，别用闪光灯直打。",
        group="首页 · 科协日常",
        fallback="img/carousel/pcb.webp",
        priority=30,
    ),
    SlotSpec(
        key="home.gallery.group",
        label="科协合影",
        # 走廊里唯一一格宽幅。60 人排开就是一条横带：塞进 4:3 的框里，上下会是
        # 四成天花板加三成地砖，人脸只剩 7px；而横向裁到 4:3 就要切掉两端的人。
        # 走廊已经改成等高胶片条（见 home.css 的 .nf-tile），宽照片自然变宽。
        ratio="12 / 5",
        brief="全员合照，横幅构图，人脸别太小；室内就开顶灯避免逆光。这一格是招新页面最想看到的一张。",
        group="首页 · 科协日常",
        # 2024 年全员合影（约 60 人）。来源与裁切见 scripts/build_photos.py。
        fallback="img/photo/group-2024.webp",
        priority=1,
    ),
    SlotSpec(
        key="home.gallery.etched",
        label="自制腐蚀板",
        ratio="4 / 3",
        brief="自己腐蚀出来的板子，最好带一点工艺痕迹（药水边、手工钻孔）。",
        group="首页 · 科协日常",
        fallback="img/carousel/etched-board.webp",
        priority=40,
    ),
    SlotSpec(
        key="home.gallery.lab",
        label="实验室日常",
        ratio="4 / 3",
        brief="有人在工作的实验室广角，示波器/电源/焊台入画；抓拍胜过摆拍。",
        group="首页 · 科协日常",
        # 2024 TI 杯赛场：指导老师 + 三名队员围着示波器调试。是抓拍不是摆拍。
        fallback="img/photo/lab-debug.webp",
        priority=10,
    ),
    SlotSpec(
        key="home.gallery.solder",
        label="焊接实践",
        ratio="4 / 3",
        brief="烙铁头与焊点的近景，手部入画；焊锡的亮点是这张的重点。",
        group="首页 · 科协日常",
        fallback="img/carousel/soldering.webp",
        priority=45,
    ),
    SlotSpec(
        key="home.gallery.award",
        label="电赛获奖合影",
        ratio="4 / 3",
        brief="领奖台或奖状合影，能看出赛事名称最好。证书单独拍一张也可以。",
        group="首页 · 科协日常",
        # 2024 TI 杯颁奖台。裁切时刻意只从两侧裁 —— 横幅上「2024 年 TI 杯模拟
        # 电子系统设计专题赛决赛 / 二等奖」正是 brief 要的「能看出赛事名称」。
        fallback="img/photo/award-ti-2024.webp",
        priority=5,
    ),

    # ---------------- 首页 · 影像区 ----------------
    SlotSpec(
        key="home.movie.teaser",
        label="招新片头循环",
        ratio="16 / 9",
        brief="5~8 秒无声循环片段，从招新视频里切一段最有画面感的（焊接火花、"
              "示波器波形、板子上电）。首尾能接上最好，看不出接缝。"
              "只上传封面帧也可以，那就是一张静态封面。",
        group="首页 · 影像区",
        kind=VIDEO,
        priority=20,
    ),

    # ---------------- 新生指南 · 每章一张现场照 ----------------
    # 这一页有 69 张器材/软件的参考图（元件特写、软件界面截图），那些是**图鉴**：
    # 一张干净的钽电容棚拍比实验室里的模糊抓拍更能说明问题，所以它们继续走
    # 静态 <img> 的「标本板」样式，不进素材槽。
    #
    # 真正该进素材槽的是另一类：**证明这些事我们真的在做**。三章各一张现场照，
    # 拍到之前显示成空焊盘，比放一张网图诚实，也比不放更有说服力。
    SlotSpec(
        key="recruit.training.session",
        label="培训现场",
        ratio="16 / 9",
        brief="培训课上的广角：投影/白板上有内容，底下有人在记笔记或动手。"
              "抓拍胜过摆拍，能看出「一屋子人在学同一件事」就对了。",
        group="新生指南 · 现场照",
        # **刻意留空。** 手上那批照片里没有一张是「培训课现场」—— 最接近的是赛场
        # 调试（已用在 home.gallery.lab）。按 fallback 那段说明：没有合适的自有
        # 素材就留空显示占位框，比放一张不相干的图诚实。这一格仍在缺图清单里。
        priority=8,
    ),
    SlotSpec(
        key="recruit.hardware.bench",
        label="协会的工作台",
        ratio="16 / 9",
        brief="我们自己的硬件工位：焊台、示波器、电源、工具墙同框，桌面别收拾得太干净，"
              "有在用的痕迹才可信。这一张替代网上的器材图。",
        group="新生指南 · 现场照",
        # 两台 RIGOL（示波器上有波形、信号源显示 1MHz）+ 一排开发板与射频板，
        # 同轴线还接着 —— brief 要的「有在用的痕迹」就是这个。
        fallback="img/photo/bench-scopes.webp",
        priority=12,
    ),
    SlotSpec(
        key="recruit.software.debug",
        label="调试中的单片机",
        ratio="16 / 9",
        brief="屏幕上是代码或串口输出，桌上板子接着调试器/示波器探头，手在键盘上。"
              "要拍出「软件方向也在和硬件打交道」这件事。",
        group="新生指南 · 现场照",
        priority=14,
    ),
)

REGISTRY: dict[str, SlotSpec] = {spec.key: spec for spec in SLOTS}


def get(key: str) -> SlotSpec | None:
    return REGISTRY.get(key)


def placeholder_spec(key: str) -> SlotSpec:
    """给未登记的 key 造一个能渲染的壳。

    只在生产环境兜底用：宁可显示一个没有拍摄要求的占位框，也不要因为一个
    拼错的 key 让整页 500。DEBUG 下和测试里都是直接报错，别让它蒙混过关。
    """
    return SlotSpec(key=key, label=key, ratio="4 / 3",
                    brief="这个素材槽没有在 core/slots.py 里登记。", group="未登记")


def video_keys() -> set[str]:
    return {s.key for s in SLOTS if s.kind == VIDEO}


def by_group() -> dict[str, list[SlotSpec]]:
    """按组分段、组内按 priority 排序，供驾驶舱的缺图清单使用。"""
    grouped: dict[str, list[SlotSpec]] = {}
    for spec in SLOTS:
        grouped.setdefault(spec.group, []).append(spec)
    for items in grouped.values():
        items.sort(key=lambda s: (s.priority, s.key))
    return grouped
