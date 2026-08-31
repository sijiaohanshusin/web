# -*- coding: utf-8 -*-
"""部署之后走公网抽查线上内容（只读，不改任何东西）。

    python scripts/check_live.py
    python scripts/check_live.py --base https://heuesta.cn --pages / /honors/

`ops/verify.sh` 在服务器上验的是「服务起来了、响应头对了、装的是我刚推的那个
提交」。这份脚本从**外面**验它证明不了的另一件事：**页面上引的图到底取不取得到**。

碎图不会在 HTML 上露出来。`<img src>` 指着一个 404 的地址时，页面照常渲染、
状态码 200、`verify.sh` 全绿 —— 只有真去取那个地址才知道。而这一轮的产出全是图
（35 张证书 + 10 张现场照），它们走两条完全不同的链路：

  /static/…  仓库里的文件，经 collectstatic + ManifestStaticFilesStorage 带哈希
  /media/…   Django 存的上传文件，落在服务器的持久卷上

nginx 上还有一条「`/media/projects/` 与 `/media/resources/` 一律 403」的规则
（会员私有文件要经 `X-Accel-Redirect` 鉴权才发）。所以**公开可见的图放错前缀
就是一墙碎图**，而本地开发用 Django 自己服务 media，一切正常。

判据一律是「真去取一遍」：200 + Content-Type 是 image/* + 响应体非空。
只看状态码不够 —— 前面挂着 EdgeOne，错误页也可能是 200。

**用 requests 不用 urllib**：站点前面的 EdgeOne 在较大的响应上不发 TLS
close_notify 就关连接，OpenSSL 3.x 把这个报成
`SSL: UNEXPECTED_EOF_WHILE_READING`，于是 `urllib.request` 在 `/`、`/honors/`
这几页上直接抛异常 —— 而 curl 取同一个地址好好的。urllib3 在「Content-Length
已经收满」时容忍这种不干净的收尾，requests 因此能拿到完整正文。
requests 只是开发工具，**不进 `app/requirements.txt`**。
"""
import argparse
import re
import sys
import time
from urllib.parse import urljoin

import requests

DEFAULT_BASE = "https://heuesta.cn"

# 抽查哪些页面。都是不需要登录的页面 —— 这份脚本刻意不碰账号，
# 它要回答的是「一个刚点进来的人看到的图是不是齐的」。
DEFAULT_PAGES = [
    "/", "/honors/", "/recruit/", "/works/", "/team/", "/news/",
    "/events/", "/resources/", "/recruitment/",
    "/accounts/register/", "/accounts/login/", "/points/leaderboard/",
]

# 这一轮新上的图。写死文件名是有意的：**「所有图都能取到」在「页面上压根没有
# 这些图」时同样成立**，等于没测。所以还要点名问一句它们在不在。
# 名字是 build_photos.py 的输出名，经 {% static %} 之后会带哈希，所以用子串匹配。
EXPECT_ON_HOME = [
    "group-2024",        # 分镜 02 末尾的整宽合影带
    "group-ti-2025",     # 走廊「出征合影」
    "bench-wide",        # 「3 个理由」那张 4:5 主图
    "rf-modules-board",  # 方向卡 01
    "rf-amp-lcd",        # 方向卡 02
    "contest-inspect",   # 方向卡 03
]

# 私有前缀：公开页面上一张都不该出现（nginx 对它们返回 403）
PRIVATE_PREFIXES = ("/media/projects/", "/media/resources/")

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")

failures = []
session = requests.Session()
session.headers["User-Agent"] = UA


def check(cond, label, detail=""):
    print(f"  {'OK  ' if cond else 'FAIL'} {label}" + (f"  {detail}" if detail else ""))
    if not cond:
        failures.append(label)


def get(url, tries=4):
    """取一个 URL，返回 (状态码, Content-Type, 正文长度, 出错说明, 文本)。

    刻意用 GET 不用 HEAD：nginx 对某些 location 不见得允许 HEAD，而「HEAD 返回
    405 但 GET 好着呢」会被读成「这张图挂了」。证书一张几十 KB，全取一遍也就
    五六兆，为这点流量换一个确定的答案值得。

    **失败重试时要先把连接池扔掉。** EdgeOne 会在一部分 TLS 连接上不发
    close_notify 就关，OpenSSL 3.x 报成 `SSL: UNEXPECTED_EOF_WHILE_READING`。
    实测这是「冷启动」现象：进程里第一个请求最容易中，一旦有一条连接立起来，
    后面一百多个请求一个都不中（同一个地址 curl 从来没失败过，页面本身好着呢）。
    所以重试必须 `session.close()` 换一条新连接 —— 在同一个坏掉的池上重试三次
    等于同一个失败数了三遍，那正是第一版的样子。
    """
    last = ""
    for attempt in range(tries):
        try:
            r = session.get(url, timeout=30)
            ctype = r.headers.get("Content-Type", "")
            body = r.content
            text = r.text if "text/" in ctype else ""
            return r.status_code, ctype, len(body), "", text
        except Exception as e:
            last = f"{type(e).__name__}: {e}"
            session.close()                     # 换一条连接，别在坏池子上原地重试
            time.sleep(0.6 * (attempt + 1))
    return 0, "", 0, last, ""


IMG_RE = re.compile(r"<img\b[^>]*?\bsrc=[\"']([^\"']+)[\"']", re.I)
SRCSET_RE = re.compile(r"\bsrcset=[\"']([^\"']+)[\"']", re.I)


def images_in(html, base_url):
    """页面上引用到的图片地址（绝对化 + 去重，保持出现顺序）。"""
    urls = [m.group(1) for m in IMG_RE.finditer(html)]
    for m in SRCSET_RE.finditer(html):
        for part in m.group(1).split(","):
            u = part.strip().split(" ")[0]
            if u:
                urls.append(u)
    out, seen = [], set()
    for u in urls:
        if u.startswith("data:"):
            continue
        full = urljoin(base_url, u)
        if full not in seen:
            seen.add(full)
            out.append(full)
    return out


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--base", default=DEFAULT_BASE)
    ap.add_argument("--pages", nargs="*", default=DEFAULT_PAGES)
    args = ap.parse_args()
    base = args.base.rstrip("/")

    print(f"线上抽查 {base}（只读）")
    pages = {}

    print("\n页面本身")
    for path in args.pages:
        status, ctype, size, err, text = get(base + path)
        ok = status == 200 and "text/html" in ctype and size > 2000
        check(ok, f"{path} 可达且是一整页 HTML",
              err or f"HTTP {status} · {ctype.split(';')[0]} · {size // 1024} KB")
        pages[path] = text if ok else None

    # ---------------- 每张图真的取一遍 ----------------
    print("\n每张图真的取一遍（碎图不会在 HTML 上露出来）")
    all_imgs, per_page = {}, {}
    for path, html in pages.items():
        if not html:
            continue
        imgs = images_in(html, base + path)
        per_page[path] = imgs
        for u in imgs:
            all_imgs.setdefault(u, []).append(path)

    check(len(all_imgs) > 40, "抽到了足够多的图（不然这一节等于没跑）",
          f"{len(all_imgs)} 个不重复地址")

    broken = []
    static_n = media_n = total_kb = 0
    for u in all_imgs:
        status, ctype, size, err, _ = get(u)
        if not (status == 200 and ctype.startswith("image/") and size > 0):
            broken.append(f"{u.rsplit('/', 1)[-1]} → {err or f'HTTP {status} {ctype}'}")
        total_kb += size // 1024
        if "/static/" in u:
            static_n += 1
        elif "/media/" in u:
            media_n += 1
    check(not broken, "**每张图都取到了真图**（200 + image/* + 响应体非空）",
          f"/static/ {static_n} 张 · /media/ {media_n} 张 · 合计 {total_kb} KB"
          if not broken else f"{len(broken)} 张挂了：" + " | ".join(broken[:5]))

    # 两条链路都要有样本，否则「图都能取到」可能只证明了其中一条
    check(static_n > 0, "抽到了 /static/ 链路的图（仓库里的、带哈希）", f"{static_n} 张")
    check(media_n > 0, "抽到了 /media/ 链路的图（Django 存的上传文件）", f"{media_n} 张")

    print("\n公开页面上不许出现私有前缀（nginx 对它们返回 403）")
    leaked = [u for u in all_imgs if any(p in u for p in PRIVATE_PREFIXES)]
    check(not leaked, f"没有图指向 {' / '.join(PRIVATE_PREFIXES)}",
          " | ".join(leaked[:3]) if leaked else "0 张")

    # ---------------- 荣誉墙：证书条带 ----------------
    print("\n荣誉墙：38 条记录 + 35 张证书")
    html = pages.get("/honors/")
    if html:
        rows = len(re.findall(r'class="[^"]*\bhn-row\b', html))
        certs = re.findall(
            r'<figure class="[^"]*\bhn-cert\b[^"]*">\s*<img[^>]*?src="([^"]+)"',
            html, re.I)
        uniq = sorted(set(certs))
        check(rows >= 38, "清单行数 ≥ 38", f"{rows} 行")
        check(len(uniq) >= 35, "证书条带里 ≥ 35 张不重复的证书", f"{len(uniq)} 张")
        check(all("/media/honors/" in u for u in uniq),
              "证书都落在 /media/honors/ 下（不是被 403 的那两个前缀）",
              f"{len(uniq)} 张")
        # 折叠里那些也要能取到 —— 它们在 DOM 里，只是 <details> 默认收起
        bad = []
        for u in uniq:
            status, ctype, size, err, _ = get(urljoin(base + "/honors/", u))
            if not (status == 200 and ctype.startswith("image/") and size > 0):
                bad.append(f"{u.rsplit('/', 1)[-1]} → {err or f'HTTP {status}'}")
        check(not bad, "**证书逐张取图都成功**（含折叠里的那些）",
              f"{len(uniq)} 张全部可达" if not bad else " | ".join(bad[:5]))
        check("*" in html, "页面上的姓名是脱敏串（含 * ）")

    # ---------------- 首页：这一轮换上去的图点名问一遍 ----------------
    print("\n首页：这一轮新上的图点名问一遍")
    home = pages.get("/")
    if home:
        imgs = " ".join(per_page.get("/", []))
        for name in EXPECT_ON_HOME:
            check(name in imgs, f"首页引用了 {name}")
        check("nf-legacy-band" in home, "分镜 02 末尾的整宽合影带在页面上")
        check("科协全员合影" in home, "整宽带的图注在页面上")

    print()
    if failures:
        print(f"{len(failures)} 项未通过：" + "、".join(failures))
        return 1
    print("线上内容抽查全部通过")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
