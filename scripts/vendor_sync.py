# -*- coding: utf-8 -*-
"""同步自托管前端库到 app/static/vendor/。

本项目不引 Node 构建链，第三方库以压缩产物直接提交进仓库（原因见
app/static/vendor/README.md）。这个脚本把"下载 → 解包 → 清理 → 覆盖"
固化下来，避免每次升级手工操作出错。

用法：
    python scripts/vendor_sync.py            # 按下面 PACKAGES 里钉死的版本同步
    python scripts/vendor_sync.py --check    # 只比对，不写入（CI/提交前自查）

需要本机有 npm（仅用于 `npm pack` 下载 tarball，不安装任何依赖、不产生
node_modules）。版本一律钉死：前端动效是首页的地基，不接受"自动升级到最新"
带来的随机破坏。

为什么要剥掉 sourceMappingURL：
    生产用 ManifestStaticFilesStorage，它会解析 JS 里的 sourceMappingURL 并
    要求那个 .map 文件也在静态目录里，否则 collectstatic 直接抛
    ValueError 中断部署。压缩库的 map 文件对线上排障没有价值（还要多传
    1MB 以上），所以统一剥除。这个坑真实发生过，见 lenis.min.js。
"""
import argparse
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
VENDOR = REPO / "app" / "static" / "vendor"

# 包名 -> (钉死的版本, {tarball 内路径: 落地文件名})
PACKAGES = {
    "gsap": ("3.15.0", {
        "package/dist/gsap.min.js": "gsap.min.js",
        "package/dist/ScrollTrigger.min.js": "ScrollTrigger.min.js",
        "package/dist/SplitText.min.js": "SplitText.min.js",
    }),
    "lenis": ("1.3.26", {
        "package/dist/lenis.min.js": "lenis.min.js",
        "package/dist/lenis.css": "lenis.css",
    }),
    "three": ("0.185.1", {
        # three.module 内部 `export * from "./three.core.min.js"`，两个必须同时存在
        "package/build/three.module.min.js": "three.module.min.js",
        "package/build/three.core.min.js": "three.core.min.js",
        # 官方只发未压缩源码，用裸标识符 import three，由 importmap 解析
        "package/examples/jsm/loaders/SVGLoader.js": "SVGLoader.js",
        # 合并几何体：3D 会标要把几十个 box/cylinder 拼成每条走线一个网格，
        # 手写索引偏移容易错，用官方工具
        "package/examples/jsm/utils/BufferGeometryUtils.js": "BufferGeometryUtils.js",
    }),
}

SOURCEMAP_RE = re.compile(rb"^\s*(//|/\*)[#@]\s*sourceMappingURL=.*$\r?\n?", re.M)


def strip_sourcemap(data: bytes) -> tuple[bytes, bool]:
    cleaned = SOURCEMAP_RE.sub(b"", data)
    return cleaned, cleaned != data


def fetch(tmp: Path) -> dict[str, Path]:
    specs = [f"{name}@{ver}" for name, (ver, _) in PACKAGES.items()]
    print("npm pack " + " ".join(specs))
    subprocess.run(
        ["npm", "pack", *specs, "--pack-destination", str(tmp)],
        check=True, capture_output=True, shell=(sys.platform == "win32"),
    )
    tarballs = {}
    for name, (ver, _) in PACKAGES.items():
        # npm 对 scoped 包会换名，这里的包都不是 scoped
        matches = list(tmp.glob(f"{name}-{ver}.tgz"))
        if not matches:
            raise SystemExit(f"没找到 {name}@{ver} 的 tarball，检查版本号是否存在")
        tarballs[name] = matches[0]
    return tarballs


def main() -> int:
    ap = argparse.ArgumentParser(description="同步自托管前端库")
    ap.add_argument("--check", action="store_true", help="只比对差异，不写入")
    args = ap.parse_args()

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    VENDOR.mkdir(parents=True, exist_ok=True)
    changed, same, stripped = [], [], []

    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        tarballs = fetch(tmp)

        for name, (ver, files) in PACKAGES.items():
            with tarfile.open(tarballs[name]) as tf:
                for member_path, out_name in files.items():
                    try:
                        member = tf.extractfile(member_path)
                    except KeyError:
                        raise SystemExit(f"{name}@{ver} 的 tarball 里没有 {member_path}")
                    if member is None:
                        raise SystemExit(f"{member_path} 不是普通文件")
                    data = member.read()

                    data, did_strip = strip_sourcemap(data)
                    if did_strip:
                        stripped.append(out_name)

                    dst = VENDOR / out_name
                    old = dst.read_bytes() if dst.exists() else None
                    if old == data:
                        same.append(out_name)
                        continue
                    changed.append(f"{out_name}  ({name}@{ver}, {len(data) / 1024:.0f} KB)")
                    if not args.check:
                        dst.write_bytes(data)

    if stripped:
        print("已剥除 sourceMappingURL：" + "、".join(sorted(set(stripped))))
    print(f"未变化 {len(same)} 个")
    if changed:
        verb = "需要更新" if args.check else "已写入"
        print(f"{verb} {len(changed)} 个：")
        for c in changed:
            print(f"  {c}")
    else:
        print("全部与钉死版本一致")

    if args.check and changed:
        print("\nvendor 目录与 PACKAGES 声明不一致，运行 python scripts/vendor_sync.py 同步")
        return 1

    if changed and not args.check:
        print("\n下一步：更新 app/static/vendor/README.md 的版本表，"
              "并在本地跑一次 collectstatic 确认静态管线没断链")
    return 0


if __name__ == "__main__":
    sys.exit(main())
