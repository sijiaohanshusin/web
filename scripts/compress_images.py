# -*- coding: utf-8 -*-
"""
招新素材图片压缩脚本：把「科协招新综述」里的大图批量压缩成 WebP 放进站点静态目录。

用法（在仓库根目录）：
    .venv/Scripts/python scripts/compress_images.py <素材目录>

素材目录即包含「科协会标.png」和「硬件综述/」的文件夹。
重复运行是安全的（幂等，直接覆盖输出）。
"""
import sys
from pathlib import Path

from PIL import Image

REPO = Path(__file__).resolve().parent.parent
RECRUIT_OUT = REPO / "app" / "static" / "img" / "recruit"
CAROUSEL_OUT = REPO / "app" / "static" / "img" / "carousel"
IMG_OUT = REPO / "app" / "static" / "img"

# 硬件综述/<中文文件名> -> 站点内 slug（不带扩展名）
RECRUIT_MAP = {
    "电阻1.png": "resistor-1", "电阻2.png": "resistor-2", "电阻3.png": "resistor-3", "电阻4.png": "resistor-4",
    "电容1.png": "capacitor-1", "电容2.png": "capacitor-2", "电容3.png": "capacitor-3",
    "电容4.png": "capacitor-4", "电容5.png": "capacitor-5",
    "电感1.png": "inductor-1", "电感2.png": "inductor-2", "电感3.png": "inductor-3", "电感4.png": "inductor-4",
    "发光二极管.jpg": "diode-led", "整流二极管.jpg": "diode-rectifier",
    "稳压二极管.jpg": "diode-zener", "肖特基二极管.jpg": "diode-schottky",
    "三极管.png": "bjt", "MOS管.jpg": "mosfet", "IGBT.jpg": "igbt",
    "通用运放.avif": "opamp-general", "功率运放.avif": "opamp-power",
    "高频运放.png": "opamp-highfreq", "底噪运放.png": "opamp-lownoise",
    "电路图.png": "schematic",
    "PCB1.jpg": "pcb-1", "PCB2.jpg": "pcb-2",
    "面包板.jpg": "breadboard",
    "洞洞板1.jpg": "perfboard-1", "洞洞板2.jpg": "perfboard-2",
    "腐蚀板1.jpg": "etched-1", "腐蚀板2.jpg": "etched-2",
    "万用表.jpg": "multimeter", "烙铁.png": "soldering-iron", "热风枪.jpg": "hot-air-gun",
    "示波器.png": "oscilloscope", "信号发生器.png": "signal-generator",
    "Multisim.png": "multisim-logo", "Multisim1.png": "multisim-shot",
    "嘉立创.png": "jlc-logo", "嘉立创1.png": "jlc-1", "嘉立创2.png": "jlc-2",
    "嘉立创下单助手.webp": "jlc-order-logo", "嘉立创下单助手2.png": "jlc-order-shot",
    "STM32.png": "board-stm32", "MSPM0.png": "board-mspm0",
    "FPGA.jpg": "board-fpga", "树莓派.png": "board-raspi",
    "keil.webp": "keil-logo", "keil2.png": "keil-shot",
    "VScode.png": "vscode-logo", "VScode2.png": "vscode-shot",
    "CLion.webp": "clion-logo", "CLion2.png": "clion-shot",
    "CCS.png": "ccs-logo", "CCS2.png": "ccs-shot",
    "STM32cubeide.png": "cubeide-logo", "STMcubeide1.png": "cubeide-shot",
    "STM32cubemx.png": "cubemx-logo", "STM32cubemx1.png": "cubemx-shot",
    "串口助手.jpg": "serial-logo", "串口助手2.png": "serial-shot",
    "DAPLink.jpg": "daplink-1", "DAPLink2.jpg": "daplink-2",
    "STLINK.avif": "stlink-1", "STLINK2.avif": "stlink-2", "JLink.jpg": "jlink",
    "逻辑分析仪.avif": "logic-analyzer", "USB转串口.avif": "usb-ttl",
}

# 首页轮播兜底图（大尺寸）
CAROUSEL_MAP = {
    "PCB1.jpg": "pcb",
    "示波器.png": "oscilloscope",
    "烙铁.png": "soldering",
    "腐蚀板1.jpg": "etched-board",
    "面包板.jpg": "breadboard",
}

RECRUIT_MAX = 1100
CAROUSEL_MAX = 1600
QUALITY = 82


def convert(src: Path, dst: Path, max_dim: int) -> tuple[int, int]:
    with Image.open(src) as im:
        im.load()
        if im.mode not in ("RGB", "RGBA"):
            im = im.convert("RGBA" if "A" in im.getbands() or "P" in im.mode else "RGB")
        if max(im.size) > max_dim:
            im.thumbnail((max_dim, max_dim), Image.LANCZOS)
        dst.parent.mkdir(parents=True, exist_ok=True)
        im.save(dst, "WEBP", quality=QUALITY, method=6)
    return src.stat().st_size, dst.stat().st_size


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 1
    material_dir = Path(sys.argv[1])
    hw_dir = material_dir / "硬件综述"
    if not hw_dir.is_dir():
        print(f"找不到素材目录: {hw_dir}")
        return 1

    total_in = total_out = missing = 0

    for name, slug in RECRUIT_MAP.items():
        src = hw_dir / name
        if not src.exists():
            print(f"[缺失] {src}")
            missing += 1
            continue
        size_in, size_out = convert(src, RECRUIT_OUT / f"{slug}.webp", RECRUIT_MAX)
        total_in += size_in
        total_out += size_out

    for name, slug in CAROUSEL_MAP.items():
        src = hw_dir / name
        if not src.exists():
            print(f"[缺失] {src}")
            missing += 1
            continue
        size_in, size_out = convert(src, CAROUSEL_OUT / f"{slug}.webp", CAROUSEL_MAX)
        total_in += size_in
        total_out += size_out

    # 会标 -> logo.png（favicon / 导航栏用，保留 PNG 透明度）
    logo_src = material_dir / "科协会标.png"
    if logo_src.exists():
        with Image.open(logo_src) as im:
            im.load()
            im.thumbnail((256, 256), Image.LANCZOS)
            IMG_OUT.mkdir(parents=True, exist_ok=True)
            im.save(IMG_OUT / "logo.png", "PNG", optimize=True)
        print(f"[logo] {logo_src} -> {IMG_OUT / 'logo.png'}")
    else:
        print(f"[缺失] {logo_src}")
        missing += 1

    print(
        f"\n完成：输入 {total_in / 1024 / 1024:.1f} MB -> 输出 {total_out / 1024 / 1024:.1f} MB"
        f"（压缩率 {100 - total_out * 100 / max(total_in, 1):.0f}%），缺失 {missing} 个"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
