"""
社交分享卡与 apple-touch-icon 生成脚本（一次性/品牌资产更新时运行）。

产出（写入 app/static/img/）:
    og-card.png            1200x630 分享卡：黑底 + 坐标纸 + 信号波形 + 会标 + 站名
    apple-touch-icon.png   180x180 iOS 主屏图标（深底方形，系统自行圆角）

用法:
    .venv/Scripts/python scripts/build_og_card.py

字体直接复用 app/static/fonts/ 下的 woff2 子集（fontTools 解包给 PIL 用），
无需重新下载字体源文件。
"""
import math
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


def wave_points(w: int, base_y: int, amp: float, period: float, phase: float = 0.0):
    return [
        (x, base_y + amp * math.sin((x / period) * 2 * math.pi + phase))
        for x in range(-10, w + 10, 4)
    ]


def draw_wave(img: Image.Image, base_y: int) -> None:
    """信号青正弦波 + 辉光（多次描边叠加）。"""
    glow = Image.new("RGBA", img.size, (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow)
    pts = wave_points(img.width, base_y, amp=26, period=190)
    for width, alpha in ((14, 26), (8, 50), (4, 110)):
        gd.line(pts, fill=(13, 169, 205, alpha), width=width, joint="curve")
    gd.line(pts, fill=(190, 245, 255, 220), width=2, joint="curve")
    img.alpha_composite(glow)


def centered_text(draw, y, text, font, fill, spacing=0, canvas_w=1200):
    """支持字间距的水平居中绘制。"""
    widths = [draw.textlength(ch, font=font) for ch in text]
    total = sum(widths) + spacing * (len(text) - 1)
    x = (canvas_w - total) / 2
    for ch, cw in zip(text, widths):
        draw.text((x, y), ch, font=font, fill=fill)
        x += cw + spacing


def build_og_card(heavy_ttf: str, mono_ttf: str) -> None:
    W, H = 1200, 630
    img = Image.new("RGBA", (W, H), BLACK)

    draw_graticule(img)
    draw_wave(img, base_y=520)
    draw = ImageDraw.Draw(img)

    mark = Image.open(IMG_DIR / "logo-mark.png").convert("RGBA")
    mark = mark.resize((92, 92), Image.LANCZOS)
    img.alpha_composite(mark, ((W - 92) // 2, 78))

    f_eyebrow = ImageFont.truetype(heavy_ttf, 30)
    f_title = ImageFont.truetype(heavy_ttf, 104)
    f_mono = ImageFont.truetype(mono_ttf, 26)
    try:  # 可变字体取 SemiBold 实例
        f_mono.set_variation_by_axes([600])
    except OSError:
        pass

    centered_text(draw, 214, "哈尔滨工程大学", f_eyebrow, ACCENT_2, spacing=14)
    centered_text(draw, 272, "电子科技协会", f_title, WHITE, spacing=10)
    centered_text(draw, 430, "HEU ESTA · HEUESTA.CN", f_mono, MUTED, spacing=2)

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
    heavy = woff2_to_ttf(FONT_DIR / "SourceHanSansCN-Heavy-subset.woff2")
    mono = woff2_to_ttf(FONT_DIR / "JetBrainsMono-subset.woff2")
    build_og_card(heavy, mono)
    build_apple_touch_icon()


if __name__ == "__main__":
    main()
