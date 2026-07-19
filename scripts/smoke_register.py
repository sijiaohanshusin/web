"""
注册流程端到端冒烟测试：走公网真实路径（含 CDN）。

流程：注册页拿 CSRF → 请求邮箱验证码 → IMAP 收码 → 提交注册 → 验证登录态。
用法：
    python smoke_register.py --imap-pass <noreply密码> [--base https://heuesta.cn] [--keep]

默认用 noreply@heuesta.cn 作为收码邮箱（发件即收件，自发自收）。
测试完请用 --cleanup-cmd 输出的命令在服务器上删除测试账号（或加 --keep 保留观察）。
"""
import argparse
import email as email_lib
import imaplib
import re
import secrets
import sys
import time
from email.header import decode_header

import requests

UA = {"User-Agent": "HEUESTA-SmokeTest/1.0"}


def log(step, msg):
    print(f"[{step}] {msg}", flush=True)


def get_csrf(session, base):
    r = session.get(f"{base}/accounts/register/", headers=UA, timeout=20)
    r.raise_for_status()
    m = re.search(r'name="csrfmiddlewaretoken" value="([^"]+)"', r.text)
    if not m:
        raise RuntimeError("注册页未找到 CSRF token")
    return m.group(1)


def send_code(session, base, csrf, mail_addr):
    r = session.post(
        f"{base}/accounts/send-code/",
        data={"email": mail_addr, "purpose": "register"},
        headers={**UA, "Referer": f"{base}/accounts/register/", "X-CSRFToken": csrf},
        timeout=20,
    )
    data = r.json()
    if not data.get("ok"):
        raise RuntimeError(f"发码失败: {data.get('msg')}")
    return data["msg"]


def fetch_code_via_imap(host, user, password, known_ids, tries=12, wait=5):
    """轮询 IMAP：只看 known_ids 之外的新邮件，取最新一封注册验证码邮件的 6 位码。

    注：不用 Date 头做过滤——Django 发信 Date 为 -0000，Python 解析成
    naive datetime 后 .timestamp() 会按本地时区偏移 8 小时，之前因此误杀新邮件。
    """
    for attempt in range(tries):
        time.sleep(wait)
        m = imaplib.IMAP4_SSL(host, 993)
        try:
            m.login(user, password)
            m.select("INBOX")
            typ, data = m.search(None, "ALL")
            ids = [i for i in data[0].split() if i not in known_ids]
            for mid in reversed(ids):
                typ, md = m.fetch(mid, "(RFC822)")
                msg = email_lib.message_from_bytes(md[0][1])
                subj = ""
                for part, enc in decode_header(msg.get("Subject", "")):
                    subj += part.decode(enc or "utf-8") if isinstance(part, bytes) else part
                if "注册验证码" not in subj:
                    continue
                body = ""
                if msg.is_multipart():
                    for p in msg.walk():
                        if p.get_content_type() == "text/plain":
                            body = p.get_payload(decode=True).decode(p.get_content_charset() or "utf-8")
                            break
                else:
                    body = msg.get_payload(decode=True).decode(msg.get_content_charset() or "utf-8")
                found = re.search(r"验证码是：(\d{6})", body)
                if found:
                    return found.group(1)
        finally:
            try:
                m.logout()
            except Exception:
                pass
        log("IMAP", f"第 {attempt + 1} 次未找到新验证码邮件，{wait} 秒后重试…")
    raise RuntimeError("超时未收到验证码邮件")


def snapshot_inbox_ids(host, user, password) -> set:
    """记录发码前收件箱已有的邮件 id，之后只找新增的。"""
    m = imaplib.IMAP4_SSL(host, 993)
    try:
        m.login(user, password)
        m.select("INBOX")
        typ, data = m.search(None, "ALL")
        return set(data[0].split())
    finally:
        try:
            m.logout()
        except Exception:
            pass


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default="https://heuesta.cn")
    parser.add_argument("--mail", default="noreply@heuesta.cn")
    parser.add_argument("--imap-host", default="imap.qiye.aliyun.com")
    parser.add_argument("--imap-pass", required=True)
    parser.add_argument("--keep", action="store_true", help="保留测试账号")
    args = parser.parse_args()

    suffix = secrets.token_hex(3)
    username = f"smoke_{suffix}"
    password = f"Smoke!{secrets.token_hex(6)}"

    s = requests.Session()

    log("1/5", f"打开注册页拿 CSRF（{args.base}）")
    csrf = get_csrf(s, args.base)

    log("2/5", f"请求发送验证码到 {args.mail}")
    known = snapshot_inbox_ids(args.imap_host, args.mail, args.imap_pass)
    t0 = time.time()
    msg = send_code(s, args.base, csrf, args.mail)
    log("2/5", f"接口返回：{msg}")

    log("3/5", "IMAP 轮询收码…")
    code = fetch_code_via_imap(args.imap_host, args.mail, args.imap_pass, known)
    elapsed = time.time() - t0
    log("3/5", f"收到验证码 {code}（耗时 {elapsed:.0f} 秒）")

    log("4/5", f"提交注册 username={username}")
    csrf = get_csrf(s, args.base)
    r = s.post(
        f"{args.base}/accounts/register/",
        data={
            "username": username,
            "real_name": "冒烟测试",
            "student_id": f"9999{suffix}",
            "college": "信通学院",
            "grade": "2025",
            "email": args.mail,
            "phone": f"139{secrets.randbelow(10**8):08d}",
            "qq": "",
            "code": code,
            "password1": password,
            "password2": password,
        },
        headers={**UA, "Referer": f"{args.base}/accounts/register/", "X-CSRFToken": csrf},
        timeout=20,
        allow_redirects=False,
    )
    if r.status_code != 302:
        err = re.findall(r'class="form-error">([^<]+)<', r.text)
        raise RuntimeError(f"注册未通过（HTTP {r.status_code}）：{err or '未知错误'}")
    log("4/5", "注册成功并自动登录（302 跳转首页）")

    log("5/5", "验证登录态与内测权限…")
    r = s.get(f"{args.base}/accounts/profile/", headers=UA, timeout=20)
    assert r.status_code == 200, f"个人中心打不开：{r.status_code}"
    assert "干事" in r.text, "内测模式下新用户应为干事级"
    assert "冒烟测试" in r.text, "个人中心未显示姓名"
    log("5/5", "通过：自动登录成功，等级=干事，个人中心正常")

    print()
    print("=" * 52)
    print("注册全流程冒烟测试 PASS")
    print(f"  验证码送达耗时：{elapsed:.0f} 秒")
    print(f"  测试账号：{username}（邮箱 {args.mail}）")
    if not args.keep:
        print("  清理命令（在服务器上执行）：")
        print(
            "  docker compose -f ops/docker-compose.yml --env-file /opt/heuesta/.env "
            f"exec -T app python manage.py shell -c \"from accounts.models import User, VerificationCode; "
            f"User.objects.filter(username='{username}').delete(); "
            f"VerificationCode.objects.filter(email='{args.mail}').delete()\""
        )
    print("=" * 52)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"\nFAIL: {e}", file=sys.stderr)
        sys.exit(1)
