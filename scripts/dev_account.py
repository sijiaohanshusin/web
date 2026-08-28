# -*- coding: utf-8 -*-
"""在开发数据库里准备一个站务账号，供截图与浏览器契约脚本登录用。

为什么需要它：驾驶舱的页面都要登录才能看，而截图工具没法凭空变出会话。
与其在每个检查脚本里各写一遍建号逻辑，不如统一到这里。

幂等：已存在就只把等级补齐。**拒绝在 DEBUG=False 下运行** —— 这个账号密码是
写死的，绝对不能出现在生产库里。

    python scripts/dev_account.py                 # 创建/修复默认站务账号
    python scripts/dev_account.py --admin         # 提到管理员级（能进站点设置）
    python scripts/dev_account.py --level 1       # 招新成员，用来看报名表那一态

默认账号：shootbot / shootbot-dev-only。等级不同看到的页面完全不同（招新落地页
就有四个分支），所以 --level 是必需的：站务级永远看到「你已经是科协会员」，
根本截不到报名表。
"""
import argparse
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "app"))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.dev")

USERNAME = "shootbot"
PASSWORD = "shootbot-dev-only"
# 注册链路的检查脚本要一个「确实已注册」的邮箱来验「该邮箱已注册」这条服务端提示。
# .invalid 是 RFC 2606 保留后缀，永远不会真的发出邮件。
EMAIL = "shootbot@heuesta.invalid"


def ensure(admin: bool = False, level: int | None = None) -> tuple[str, str]:
    import django

    django.setup()

    from django.conf import settings

    if not settings.DEBUG:
        raise SystemExit("拒绝执行：这个账号只能存在于开发库里（当前 DEBUG=False）。")

    from django.contrib.auth import get_user_model

    from accounts import roles

    User = get_user_model()
    user, created = User.objects.get_or_create(
        username=USERNAME, defaults={"is_active": True},
    )
    user.set_password(PASSWORD)
    user.is_active = True
    user.email = EMAIL
    if level is None:
        level = roles.LEVEL_ADMIN if admin else roles.LEVEL_OFFICER
    if hasattr(user, "set_level"):
        user.set_level(level)
    else:
        user.member_level = level
    user.save()
    roles.sync_user_groups(user)
    print(f"{'创建' if created else '更新'}开发账号 {USERNAME} "
          f"（{roles.LEVEL_LABELS[level]}）")
    return USERNAME, PASSWORD


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser()
    ap.add_argument("--admin", action="store_true", help="提到管理员级")
    ap.add_argument("--level", type=int, choices=range(0, 6),
                    help="直接指定会员等级 0~5（0 待审核 / 1 招新成员 / 2 预备 / "
                         "3 科协会员 / 4 站务 / 5 管理员）")
    args = ap.parse_args()
    user, password = ensure(args.admin, args.level)
    print(f"截图时用：python scripts/shoot.py --url /dashboard/media/ --login {user}:{password}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
