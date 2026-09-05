"""Versioned task articles shared by HTML and document exporters."""
import json
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from accounts import roles

ROOT = Path(__file__).parent
AUDIENCES = {
    "recruit": {"title": "招新注册手册", "label": "准备加入协会", "summary": "从创建账号到提交报名，一次完成一个小目标。", "tag": "START HERE", "action": "/accounts/register/new/"},
    "member": {"title": "老会员使用手册", "label": "我是协会成员", "summary": "恢复身份、参加活动，让你的作品与故事被看见。", "tag": "MEMBER GUIDE", "action": "/accounts/profile/"},
    "admin": {"title": "网站管理手册", "label": "我来维护网站", "summary": "按任务检查权限、执行操作、核对结果。内部使用。", "tag": "OPERATIONS", "action": "/dashboard/"},
}


@dataclass(frozen=True)
class Article:
    slug: str
    audience: str
    title: str
    summary: str
    access: str
    order: int
    minutes: int
    routes: tuple
    checkpoints: tuple
    screenshots: tuple
    verified: str
    version: str
    body: str

    @property
    def url(self):
        return f"/help/{self.audience}/{self.slug}/"

    @property
    def key(self):
        return f"{self.audience}/{self.slug}"

    @property
    def action_url(self):
        return self.routes[0] if self.routes else AUDIENCES[self.audience]["action"]


def allowed(user, access):
    if access == "public":
        return True
    if not getattr(user, "is_authenticated", False) or not getattr(user, "is_active", False):
        return False
    return roles.is_admin(user) if access == "admin" else roles.is_officer(user)


@lru_cache(maxsize=1)
def articles():
    result = []
    for path in sorted((ROOT / "content").glob("*/*.md")):
        raw = path.read_text(encoding="utf-8")
        _, header, body = raw.split("---", 2)
        meta = json.loads(header)
        audience, slug = path.parent.name, path.stem
        if audience not in AUDIENCES or not re.fullmatch(r"[a-z0-9-]+", slug):
            raise ValueError(f"Invalid help article: {path.name}")
        access = meta["access"]
        if access not in {"public", "officer", "admin"} or (audience == "admin") != (access != "public"):
            raise ValueError(f"Invalid help access: {path.name}")
        result.append(Article(slug=slug, audience=audience, body=body.strip(), **{
            **meta, "routes": tuple(meta["routes"]), "checkpoints": tuple(meta["checkpoints"]),
            "screenshots": tuple(meta["screenshots"]),
        }))
    return tuple(sorted(result, key=lambda article: (article.audience, article.order)))


def visible(user, audience=None):
    return [a for a in articles() if (audience is None or a.audience == audience) and allowed(user, a.access)]


def find(user, audience, slug):
    return next((a for a in visible(user, audience) if a.slug == slug), None)


def search(user, query):
    tokens = query.casefold().split()[:8]
    if not tokens:
        return []
    results = []
    for article in visible(user):
        text = (article.title + " " + article.summary + " " + article.body).casefold()
        if all(token in text for token in tokens):
            score = sum(5 * article.title.casefold().count(token) + article.summary.casefold().count(token) for token in tokens)
            results.append((score, article))
    return [a for _, a in sorted(results, key=lambda item: (-item[0], item[1].order))][:40]
