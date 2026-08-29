"""
社交分享卡与 apple-touch-icon 生成脚本（一次性/品牌资产更新时运行）。

产出（写入 app/static/img/）:
    og-card.png            1200x630 分享卡：氛围底图 + 坐标纸 + 会标 + 站名
    apple-touch-icon.png   180x180 iOS 主屏图标（深底方形，系统自行圆角）

用法:
    python scripts/build_og_card.py

字体直接复用 app/static/fonts/ 下的 woff2 子集（fontTools 解包给 PIL 用），
无需重新下载字体源文件。

**标题字必须和站上一致。** 这个脚本原来用 `SourceHanSansCN-Heavy-subset.woff2`，
而标题字后来换成了得意黑（SmileySans），那个子集已经删掉 —— 于是脚本直接崩，
而 `og-card.png` 作为产物还躺在仓库里、还在被 `base.html` 引用。
分享卡是别人看到这个站的第一眼，字形不一致最不该发生在这里。

底图用 `img/banner-social-card.webp`（生图 AI 产出，右下是青色光轨与铜色散景，
左上刻意留黑）。所以版式是**左对齐**的：文字占左上那片干净区，右下让给光轨。
原来那道用 Pillow 画的正弦波去掉了 —— 底图自己有光轨，两条曲线会打架。
"""
import tempfile
from pathlib import Path

from fontTools.ttLib import TTFont
from PIL import Image, ImageDraw, ImageFont

REPO = Path(__file__).resolve().parent.parent
IMG_DIR = REPO / "app" / "static" / "img"
FONT_DIR = REPO / "app" / "static" / "fonts"

BLACK = (5, 5, 6, 255)
WHITE = (255, 255, 255, 255)
ACCENT = (13, 169, 205, 255)
ACCENT_2 = (65, 216, 232, 255)
MUTED = (151, 161, 179, 255)


def woff2_to_ttf(woff2_path: Path) -> str:
    """woff2 子集解包成临时 ttf，返回文件路径（PIL 不认 woff2）。"""
    font = TTFont(str(woff2_path))
    font.flavor = None
    tmp = tempfile.NamedTemporaryFile(suffix=".ttf", delete=False)
    font.save(tmp.name)
    tmp.close()
    return tmp.name


def draw_graticule(img: Image.Image) -> None:
    """示波器坐标纸：细格 40px、粗格 200px，独立图层合成保证低亮度。"""
    w, h = img.size
    layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    for x in range(0, w, 40):
        alpha = 16 if x % 200 == 0 else 7
        d.line([(x, 0), (x, h)], fill=(255, 255, 255, alpha), width=1)
    for y in range(0, h, 40):
        alpha = 16 if y % 200 == 0 else 7
        d.line([(0, y), (w, y)], fill=(255, 255, 255, alpha), width=1)
    img.alpha_composite(layer)


def tracked_text(draw, x, y, text, font, fill, spacing=0):
    """支持字间距的逐字绘制（PIL 没有 letter-spacing），返回绘完的右缘 x。"""
    for ch in text:
        draw.text((x, y), ch, font=font, fill=fill)
        x += draw.textlength(ch, font=font) + spacing
    return x - spacing


def base_plate(w: int, h: int) -> Image.Image:
    """氛围底图。缺文件时退回纯黑，不让分享卡因为一张图生不出来。"""
    src = IMG_DIR / "banner-social-card.webp"
    if not src.exists():
        print(f"  ! 缺 {src.name}，退回纯黑底")
        return Image.new("RGBA", (w, h), BLACK)
    plate = Image.open(src).convert("RGBA")
    if plate.size != (w, h):
        plate = plate.resize((w, h), Image.LANCZOS)
    return plate


def build_og_card(display_ttf: str, mono_ttf: str) -> None:
    W, H = 1200, 630
    # 左边距 88 兼作「干净区」的判据：底图上 x<600 全高、y<420 全宽都是纯黑
    # （p99 亮度 6），所以整块文字都落在 6 上，白字对比度是满的。
    X = 88
    img = base_plate(W, H)

    draw_graticule(img)
    draw = ImageDraw.Draw(img)

    mark = Image.open(IMG_DIR / "logo-mark.png").convert("RGBA")
    mark = mark.resize((84, 84), Image.LANCZOS)
    img.alpha_composite(mark, (X, 84))

    f_eyebrow = ImageFont.truetype(display_ttf, 28)
    f_title = ImageFont.truetype(display_ttf, 92)
    f_mono = ImageFont.truetype(mono_ttf, 24)
    try:  # 可变字体取 SemiBold 实例
        f_mono.set_variation_by_axes([600])
    except OSError:
        pass

    tracked_text(draw, X, 210, "哈尔滨工程大学", f_eyebrow, ACCENT_2, spacing=12)
    right = tracked_text(draw, X, 254, "电子科技协会", f_title, WHITE, spacing=8)
    # `//` 前缀是站上 `.nf-eyebrow` 的丝印语气，分享卡沿用同一个记号
    tracked_text(draw, X, 392, "// HEU ESTA · HEUESTA.CN", f_mono, MUTED, spacing=2)

    if right > 600:  # 越过干净区就会压到光轨上，字号得往回收
        print(f"  ! 标题右缘 {right:.0f} 越过了干净区 600，检查字号")

    out = IMG_DIR / "og-card.png"
    img.convert("RGB").save(out, "PNG", optimize=True)
    print(f"  {out.name}: {out.stat().st_size / 1024:.0f} KB")


def build_apple_touch_icon() -> None:
    """180x180 深底方形（iOS 自己做圆角遮罩）。"""
    size = 180
    canvas = Image.new("RGBA", (size, size), (11, 11, 14, 255))
    mark = Image.open(IMG_DIR / "logo-mark.png").convert("RGBA")
    inner = int(size * 0.68)
    mark = mark.resize((inner, inner), Image.LANCZOS)
    canvas.alpha_composite(mark, ((size - inner) // 2, (size - inner) // 2))
    out = IMG_DIR / "apple-touch-icon.png"
    canvas.convert("RGB").save(out, "PNG", optimize=True)
    print(f"  {out.name}: {out.stat().st_size / 1024:.0f} KB")


def main() -> None:
    display = woff2_to_ttf(FONT_DIR / "SmileySans-subset.woff2")
    mono = woff2_to_ttf(FONT_DIR / "JetBrainsMono-subset.woff2")
    build_og_card(display, mono)
    build_apple_touch_icon()


if __name__ == "__main__":
    main()
