"""
邮箱验证码：生成、发送、校验，带限流与防爆破。

- 60 秒重发冷却
- 单邮箱每日发码上限（settings.VERIFICATION_DAILY_LIMIT）
- 单条验证码 5 次错误即作废
- 有效期 settings.VERIFICATION_CODE_TTL 秒
"""
import datetime
import secrets

from django.conf import settings
from django.core.mail import send_mail
from django.utils import timezone

from .models import VerificationCode

MAX_ATTEMPTS = 5

PURPOSE_SUBJECT = {
    "register": "【HEU ESTA】注册验证码",
    "reset": "【HEU ESTA】找回密码验证码",
    "login": "【HEU ESTA】登录验证码",
}


class CodeError(Exception):
    """用于向视图返回可读的中文错误。"""


def _now():
    return timezone.now()


def can_send(email: str) -> tuple[bool, str]:
    """检查冷却与每日额度。返回 (是否可发, 错误信息)。"""
    since_cooldown = _now() - datetime.timedelta(seconds=settings.VERIFICATION_RESEND_COOLDOWN)
    if VerificationCode.objects.filter(email=email, created_at__gte=since_cooldown).exists():
        return False, f"发送太频繁，请 {settings.VERIFICATION_RESEND_COOLDOWN} 秒后再试。"

    day_start = _now() - datetime.timedelta(days=1)
    if VerificationCode.objects.filter(email=email, created_at__gte=day_start).count() >= settings.VERIFICATION_DAILY_LIMIT:
        return False, "今日验证码发送次数已达上限，请明天再试或联系管理员。"
    return True, ""


def issue(email: str, purpose: str) -> VerificationCode:
    """生成并发送验证码。调用前应先 can_send 校验。"""
    email = email.strip().lower()
    # 作废该邮箱同用途的旧码
    VerificationCode.objects.filter(email=email, purpose=purpose, used=False).update(used=True)

    code = f"{secrets.randbelow(1000000):06d}"
    record = VerificationCode.objects.create(email=email, code=code, purpose=purpose)

    minutes = settings.VERIFICATION_CODE_TTL // 60
    subject = PURPOSE_SUBJECT.get(purpose, "【HEU ESTA】验证码")
    body = (
        f"你的验证码是：{code}\n\n"
        f"有效期 {minutes} 分钟，请勿泄露给他人。\n"
        f"如果这不是你本人的操作，请忽略本邮件。\n\n"
        f"—— 哈尔滨工程大学电子科技协会"
    )
    send_mail(subject, body, settings.DEFAULT_FROM_EMAIL, [email], fail_silently=False)
    return record


def verify(email: str, purpose: str, code: str) -> None:
    """校验验证码；失败抛 CodeError，成功则标记已使用。"""
    email = (email or "").strip().lower()
    code = (code or "").strip()
    record = (
        VerificationCode.objects.filter(email=email, purpose=purpose, used=False)
        .order_by("-created_at")
        .first()
    )
    if not record:
        raise CodeError("请先获取验证码。")

    expire_at = record.created_at + datetime.timedelta(seconds=settings.VERIFICATION_CODE_TTL)
    if _now() > expire_at:
        record.used = True
        record.save(update_fields=["used"])
        raise CodeError("验证码已过期，请重新获取。")

    if record.attempts >= MAX_ATTEMPTS:
        record.used = True
        record.save(update_fields=["used"])
        raise CodeError("验证码错误次数过多，请重新获取。")

    if record.code != code:
        record.attempts += 1
        record.save(update_fields=["attempts"])
        raise CodeError("验证码不正确。")

    record.used = True
    record.save(update_fields=["used"])
