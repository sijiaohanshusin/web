# -*- coding: utf-8 -*-
"""上线前的地面检查：把「能在本地证伪的事」全部证一遍。

**这个脚本不碰生产，也不改任何东西。** 它只回答一个问题：现在跑
`sudo /opt/heuesta/web/ops/deploy.sh` 会不会出事。

为什么需要它：`deploy.sh` 是**从 GitHub main 分支下载归档**来更新代码的
（服务器直连 git 协议不通，走 codeload tarball）。也就是说本地写了多少都不算，
**没推到 main 上的东西一行都不会上线** —— 而部署脚本会「成功」，只是把旧站又
装了一遍。这是最容易犯、也最难当场看出来的错。

检查项分三类：
  会挡住上线    —— 代码没提交/没推、缺迁移、collectstatic 会炸、缺文件
  上线后才发作  —— .env 少一个变量（容器起不来）、requirements 混进开发工具
  只能人工确认  —— 明确列出来，不假装检查过

跑法：python scripts/preflight.py
"""
import os
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
APP = REPO / "app"
sys.path.insert(0, str(REPO / "scripts"))

failures = []
warnings = []


def check(cond, label, detail=""):
    print(f"  {'OK  ' if cond else 'FAIL'} {label}" + (f"  {detail}" if detail else ""))
    if not cond:
        failures.append(label)


def warn(cond, label, detail=""):
    print(f"  {'OK  ' if cond else 'WARN'} {label}" + (f"  {detail}" if detail else ""))
    if not cond:
        warnings.append(label)


def git(*args) -> str:
    return subprocess.run(["git", *args], cwd=REPO, capture_output=True,
                          text=True, encoding="utf-8", errors="replace").stdout.strip()


# ---------------------------------------------------------------- 1. 代码到位
def check_git():
    print("\n1. 代码到位（deploy.sh 装的是 GitHub main 上的东西，不是本地的）")
    branch = git("branch", "--show-current")
    dirty = [ln for ln in git("status", "--porcelain").splitlines() if ln.strip()]
    check(not dirty,
          "**工作区干净（没有未提交的改动）**"
          " —— 没提交的东西不会上线，而 deploy.sh 照样会说部署成功",
          f"{len(dirty)} 个文件未提交" if dirty else "")
    check(branch == "main", "当前在 main 分支上（deploy.sh 拉的是 refs/heads/main）",
          branch or "(游离 HEAD)")

    git("fetch", "--quiet", "origin", "main")
    local = git("rev-parse", "HEAD")
    remote = git("rev-parse", "origin/main")
    ahead = git("rev-list", "--count", "origin/main..HEAD")
    behind = git("rev-list", "--count", "HEAD..origin/main")
    check(local == remote and local != "",
          "**本地 main 和 origin/main 一致**（推上去了才算数）",
          f"领先 {ahead} 个提交 / 落后 {behind} 个" if local != remote else local[:9])


# ---------------------------------------------------------------- 2. 迁移
def check_migrations():
    print("\n2. 迁移：模型改了但没生成迁移，容器起来时 migrate 不会报错，"
          "而后面第一次写库就 500")
    env = dict(os.environ, DJANGO_SETTINGS_MODULE="config.settings.dev")
    r = subprocess.run([sys.executable, "manage.py", "makemigrations",
                        "--check", "--dry-run"],
                       cwd=APP, capture_output=True, text=True,
                       encoding="utf-8", errors="replace", env=env)
    check(r.returncode == 0, "没有「模型改了但缺迁移」",
          (r.stdout or r.stderr).strip().splitlines()[0] if r.returncode else "无变更")


# ---------------------------------------------------------------- 3. 生产配置
# 这两条是**明知故犯**，不是漏掉的：
#   W004 HSTS —— 打开之后浏览器会记住「这个域只走 HTTPS」很长时间，证书出问题时
#         不能靠退回 HTTP 救场。要开就得先确认证书自动续期稳了，属于人工决策。
#   W008 SECURE_SSL_REDIRECT —— nginx 已经在做（EdgeOne 回源那条 301 + certbot
#         的 80→443 块）。Django 再做一次的收益是零，而配错代理头就是重定向死循环。
#   W002 X-Frame-Options —— django-simpleui 在 ready() 里把那个中间件从
#         settings.MIDDLEWARE 里 pop 掉了（它的后台靠 iframe 开标签页），Django
#         这一侧发不出来。改由 nginx 在 location / 里发 SAMEORIGIN，
#         `DeployPerfContractTests` 两头都钉住了。
ACCEPTED_DEPLOY_WARNINGS = {
    "security.W002": "simpleui 摘掉了那个中间件，改由 nginx 发 SAMEORIGIN",
    "security.W004": "HSTS 由人工决定（见 preflight.py 注释）",
    "security.W008": "HTTPS 跳转在 nginx 那一层做",
}


def check_deploy_settings():
    print("\n3. 生产配置（用 prod 设置跑 check --deploy，只放过明确接受的两条）")
    env = {
        **os.environ,
        "DJANGO_SETTINGS_MODULE": "config.settings.prod",
        # 只为让 settings 能 import；长度够长以免触发 W009 那条误报
        "DJANGO_SECRET_KEY": "preflight-placeholder-" + "x" * 40,
        "POSTGRES_DB": "heuesta",
        "POSTGRES_USER": "heuesta",
        "POSTGRES_PASSWORD": "preflight",
    }
    r = subprocess.run([sys.executable, "manage.py", "check", "--deploy"],
                       cwd=APP, capture_output=True, text=True,
                       encoding="utf-8", errors="replace", env=env)
    out = r.stdout + r.stderr
    codes = set(re.findall(r"\((security\.\w+)\)", out))
    unexpected = sorted(codes - set(ACCEPTED_DEPLOY_WARNINGS))
    for code in sorted(codes & set(ACCEPTED_DEPLOY_WARNINGS)):
        print(f"  --   {code} 已知并接受：{ACCEPTED_DEPLOY_WARNINGS[code]}")
    check(r.returncode == 0, "check --deploy 本身没有报错（ERRORS 级）")
    check(not unexpected, "没有预期之外的部署告警", ", ".join(unexpected))


# ---------------------------------------------------------------- 4. 静态管线
def check_static():
    print("\n4. 静态管线：collectstatic 在生产存储下会不会中断部署")
    env = dict(os.environ, DJANGO_SETTINGS_MODULE="config.settings.dev")
    r = subprocess.run([sys.executable, "manage.py", "check_static_pipeline"],
                       cwd=APP, capture_output=True, text=True,
                       encoding="utf-8", errors="replace", env=env)
    check(r.returncode == 0, "check_static_pipeline 通过",
          "" if r.returncode == 0 else "跑 python manage.py check_static_pipeline 看详情")


# ---------------------------------------------------------------- 5. 依赖清单
# 只在开发机上用的东西，一个都不该进生产镜像：装了要花构建时间、占镜像体积，
# playwright 还会想下浏览器（服务器 2 核 1.6G，构建就在上面做）。
DEV_ONLY = ["playwright", "fonttools", "fontTools", "brotli", "pytest", "ruff", "black"]


def check_requirements():
    print("\n5. 依赖清单：开发工具不能混进 app/requirements.txt")
    text = (APP / "requirements.txt").read_text(encoding="utf-8")
    lines = [ln.strip() for ln in text.splitlines()
             if ln.strip() and not ln.strip().startswith("#")]
    leaked = [p for p in DEV_ONLY
              if any(re.match(rf"^{re.escape(p)}\b", ln, re.I) for ln in lines)]
    check(not leaked, "没有开发工具混进去", ", ".join(leaked))
    check(len(lines) >= 8, "清单看着完整（不是被截断了）", f"{len(lines)} 条")
    # 生产真正 import 的几个包必须在
    for pkg in ("Django", "psycopg", "gunicorn", "Pillow"):
        with_it = any(re.match(rf"^{re.escape(pkg)}\b", ln, re.I) for ln in lines)
        check(with_it, f"{pkg} 在清单里")


# ---------------------------------------------------------------- 6. 环境变量
def check_env_example():
    """`os.environ["X"]` 这种没有默认值的读法，少一个变量容器就起不来。

    entrypoint.sh 里也有一份（连数据库那段），一起扫。
    """
    print("\n6. 环境变量：没有默认值的那些，env.example 里必须都有")
    required: set[str] = set()
    for path in list(APP.rglob("*.py")) + [REPO / "ops" / "entrypoint.sh"]:
        if "__pycache__" in str(path) or not path.exists():
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        required.update(re.findall(r'os\.environ\[[\'"]([A-Z_][A-Z0-9_]*)[\'"]\]', text))
    # prod.py 里显式 raise 的那一个不是下标读法，单独加上
    required.add("DJANGO_SECRET_KEY")

    example = (REPO / "ops" / "env.example").read_text(encoding="utf-8")
    documented = set(re.findall(r"^#?\s*([A-Z_][A-Z0-9_]*)=", example, re.M))
    missing = sorted(required - documented)
    check(len(required) >= 3, "确实扫到了必需变量（不然这条空跑）",
          f"{len(required)} 个：{', '.join(sorted(required))}")
    check(not missing, "**env.example 覆盖了全部必需变量**（少一个容器就起不来）",
          ", ".join(missing))


# ---------------------------------------------------------------- 7. 部署脚本引用的文件
def check_deploy_files():
    print("\n7. deploy.sh 引用的文件都在（少一个，部署会跑到一半才失败）")
    needed = [
        "ops/docker-compose.yml", "ops/Dockerfile", "ops/entrypoint.sh",
        "ops/env.example", "ops/nginx/heuesta.cn.conf",
        "ops/heuesta-backup.service", "ops/heuesta-backup.timer",
        "ops/heuesta-event-reminder.service", "ops/heuesta-event-reminder.timer",
        "ops/backup.sh", "learn",
    ]
    for rel in needed:
        check((REPO / rel).exists(), f"{rel} 存在")


# ---------------------------------------------------------------- 8. 必须入库的产物
def check_tracked_assets():
    """无 Node 构建链 = 压缩产物直接进仓库。**它们一个都不能被 .gitignore 挡掉**，
    否则服务器拉下来的归档里压根没有这些文件，页面一片碎图 + 没有样式。

    判据刻意是「**没有被忽略**」而不是「已经被跟踪」：还没提交的新文件本来就不在
    `git ls-files` 里，拿「已跟踪」当判据会在每次有新文件时都红一片，把真正的问题
    （被 .gitignore 挡掉）淹掉。「有没有提交」由第 1 项负责。
    """
    print("\n8. 该入库的产物没有被 .gitignore 挡掉（无 Node 构建链，产物即源码）")
    groups = {
        "字体": ["app/static/fonts/JetBrainsMono-subset.woff2",
                 "app/static/fonts/SmileySans-subset.woff2",
                 "app/static/fonts/SourceHanSansCN-Regular-subset.woff2",
                 "app/static/fonts/SourceHanSansCN-Bold-subset.woff2",
                 "app/static/fonts/SourceHanSerifCN-SemiBold-subset.woff2",
                 "app/static/fonts/ESTADigits.woff2"],
        "会标": ["app/static/brand/logo-mark.svg"],
        "vendor": ["app/static/vendor/gsap.min.js", "app/static/vendor/lenis.min.js",
                   "app/static/vendor/three.module.min.js",
                   "app/static/vendor/three.core.min.js"],
        "样式": ["app/static/css/tokens.css", "app/static/css/core.css",
                 "app/static/css/home.css"],
    }
    tracked = set(git("ls-files").splitlines())
    for name, paths in groups.items():
        gone = [p for p in paths if not (REPO / p).exists()]
        # `git check-ignore` 退出码 0 = 这个路径被某条忽略规则命中
        ignored = [
            p for p in paths
            if subprocess.run(["git", "check-ignore", "-q", p], cwd=REPO).returncode == 0
        ]
        check(not gone, f"{name} 文件在磁盘上", ", ".join(gone))
        check(not ignored, f"**{name} 没有被 .gitignore 挡掉**", ", ".join(ignored))
        pending = [p for p in paths if p not in tracked and (REPO / p).exists()]
        if pending:
            warn(False, f"{name} 还没提交（第 1 项已经说了，这里只是列一下）",
                 f"{len(pending)} 个")


# ---------------------------------------------------------------- 9. 字体子集
def check_fonts_in_sync():
    print("\n9. 字体子集跟得上模板（缺字会静静回退系统黑体）")
    try:
        import fontTools  # noqa: F401
    except ImportError:
        warn(False, "本机没装 fontTools，跳过字体检查",
             "pip install fonttools brotli 后跑 python scripts/check_fonts.py")
        return
    r = subprocess.run([sys.executable, "scripts/check_fonts.py"],
                       cwd=REPO, capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    check(r.returncode == 0, "check_fonts.py 通过",
          "" if r.returncode == 0 else "跑 python scripts/check_fonts.py --list 看缺哪些字")


# ---------------------------------------------------------------- 只能人工确认
MANUAL = [
    "服务器上 /opt/heuesta/.env 已按 ops/env.example 填好（尤其 DJANGO_SECRET_KEY "
    "是长随机值、EMAIL_HOST_USER 配了真邮箱 —— 不配的话验证码只打进 docker 日志）",
    "本次改了 ops/nginx/heuesta.cn.conf（gzip_types / Cache-Control / "
    "X-Frame-Options 三处），deploy.sh 会 cp 过去并 nginx -t，**部署后确认 "
    "`curl -I https://heuesta.cn/static/css/core.<hash>.css` 只有一条 Cache-Control**",
    "部署后抽查 `curl -sI -H 'Accept-Encoding: gzip' https://heuesta.cn/static/js/"
    "motion-core.<hash>.js | grep -i content-encoding` 确认 JS 真的压缩了",
    "部署后抽查 `curl -I https://heuesta.cn/ | grep -i x-frame-options` 应为 SAMEORIGIN",
    "先备份数据库再部署：ops/backup.sh（deploy.sh 不含备份）",
    "本机没有 Docker，镜像构建只能在服务器上验；构建就在 2 核 1.6G 上做，留出时间",
    "站务在 /dashboard/media/ 补图后再对外宣传（现在多数位置是空焊盘占位）",
]


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    print("上线前地面检查（不碰生产、不改任何东西）")
    check_git()
    check_migrations()
    check_deploy_settings()
    check_static()
    check_requirements()
    check_env_example()
    check_deploy_files()
    check_tracked_assets()
    check_fonts_in_sync()

    print("\n只能人工确认的（这里不假装检查过）：")
    for i, item in enumerate(MANUAL, 1):
        print(f"  {i}. {item}")

    print()
    if warnings:
        print(f"{len(warnings)} 条提醒：" + "、".join(warnings))
    if failures:
        print(f"{len(failures)} 项会挡住上线：")
        for f in failures:
            print(f"  · {f}")
        return 1
    print("地面检查全部通过 —— 可以按 docs/2026改版计划.md 的上线步骤走")
    return 0


if __name__ == "__main__":
    sys.exit(main())
