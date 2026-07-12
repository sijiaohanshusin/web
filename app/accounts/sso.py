"""
论坛账号互通：给已登录用户下发签名 JWT Cookie（heuesta_sso）。

NodeBB 的 nodebb-plugin-session-sharing 插件会读取该 Cookie（域 .heuesta.cn），
验签通过即自动登录 / 首次自动建号；用户在主站登出时 Cookie 被清除，论坛同步登出。

未配置 NODEBB_JWT_SECRET 时本中间件完全不生效，主站行为不受影响。
"""
import time

import jwt
from django.conf import settings


class SsoCookieMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)

        secret = getattr(settings, "NODEBB_JWT_SECRET", "")
        if not secret:
            return response

        cookie_name = settings.SSO_COOKIE_NAME
        cookie_domain = settings.SSO_COOKIE_DOMAIN
        user = getattr(request, "user", None)

        if user is not None and user.is_authenticated and user.is_active:
            if not self._token_valid(request.COOKIES.get(cookie_name), user, secret):
                now = int(time.time())
                payload = {
                    "id": user.pk,
                    "username": user.username,
                    "fullname": user.display_name or user.username,
                    "groups": self._role_groups(user),
                    "iat": now,
                    "exp": now + settings.SESSION_COOKIE_AGE,
                }
                if user.email:
                    payload["email"] = user.email
                token = jwt.encode(payload, secret, algorithm="HS256")
                response.set_cookie(
                    cookie_name,
                    token,
                    max_age=settings.SESSION_COOKIE_AGE,
                    domain=cookie_domain,
                    secure=not settings.DEBUG,
                    httponly=True,
                    samesite="Lax",
                )
        elif cookie_name in request.COOKIES:
            response.delete_cookie(cookie_name, domain=cookie_domain)

        return response

    @staticmethod
    def _role_groups(user) -> list[str]:
        """映射主站角色 -> 论坛用户组（论坛端 join-only 同步，显示彩色头衔）。"""
        names = set(user.groups.filter(name__in=["会员", "干事", "管理员"]).values_list("name", flat=True))
        if user.is_staff or user.is_superuser:
            names.add("管理员")
        return sorted(names)

    @staticmethod
    def _token_valid(token: str | None, user, secret: str) -> bool:
        """现有 Cookie 仍然有效且属于当前用户时不重复签发。"""
        if not token:
            return False
        try:
            data = jwt.decode(token, secret, algorithms=["HS256"])
        except jwt.InvalidTokenError:
            return False
        return data.get("id") == user.pk
