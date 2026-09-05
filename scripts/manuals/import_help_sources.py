"""One-time conversion of the reviewed v1 manuals to task-oriented sources.

Existing task files are never overwritten. After conversion, edit only the
Markdown in app/helpcenter/content; exporters consume those same files.
"""
import json
import re
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEST = ROOT / "app/helpcenter"
BOOKS = {
    "recruit": ("招新注册手册", [
        ("prepare", "/recruitment/", "准备邮箱与真实身份资料，确认本次招新开放。"),
        ("channel", "/accounts/register/", "新同学选自动激活通道，曾入会的成员选身份恢复。"),
        ("identity", "/accounts/register/new/", "用固定学院和入学年份，完成第一步身份信息。"),
        ("contact", "/accounts/register/new/", "选择擅长方向，并填写长期可用的联系方式。"),
        ("verify", "/accounts/register/new/", "获取邮箱验证码、设置密码并确认隐私说明。"),
        ("registered", "/recruitment/", "确认已自动登录；接下来还需要提交招新报名。"),
        ("group", "/recruitment/", "找到官方招新群 1081376858，核对后加入。"),
        ("direction", "/recruitment/apply/", "选择意向部门与兴趣领域，不确定也可如实表达。"),
        ("application", "/recruitment/apply/", "填写个人情况、自我介绍与经历，完成报名答卷。"),
        ("submit", "/recruitment/apply/", "核对完整答卷后提交，看到已报名才算完成。"),
        ("progress", "/accounts/profile/", "查看申请状态，理解一面、二面与会员等级变化。"),
        ("notifications", "/notify/", "找到面试通知，核对时间、地点与最新安排。"),
        ("account", "/accounts/login/", "登录、修改资料和找回密码，维护自己的账号。"),
        ("troubleshooting", "/recruitment/", "按提示定位验证码、重复身份和权限问题。"),
    ]),
    "member": ("老会员使用手册", [
        ("channel", "/accounts/register/", "有账号先登录；没有账号再申请恢复老会员身份。"),
        ("prepare", "/accounts/register/returning/", "准备可核验的原身份、实际入学年份和联系方式。"),
        ("register", "/accounts/register/returning/", "逐步填写身份申报，完成邮箱验证并提交。"),
        ("review", "/accounts/login/", "待审核账号暂不能登录，核验通过后按邮件提示进入。"),
        ("login", "/accounts/login/", "首次登录、改密与退出，建立可靠的账号使用习惯。"),
        ("profile", "/accounts/profile/", "维护私有档案，查看会员等级、任职与勋章。"),
        ("permissions", "/notify/", "理解会员权限变化，并查看站内通知。"),
        ("resources", "/resources/", "找到可访问的公告、教材和资料下载入口。"),
        ("activities", "/events/", "查看活动报名与签到，浏览项目和公开作品。"),
        ("forum", "https://bbs.heuesta.cn/", "通过官网账号进入论坛，理解公共邮箱可见范围。"),
        ("showcase", "/accounts/showcase/", "从一张成员卡片开始，选模板、背景与公开内容。"),
        ("publish", "/accounts/showcase/?section=publish", "预览后确认公开范围，随时保留草稿或撤回。"),
        ("troubleshooting", "/feedback/", "找到审核、登录、图片和论坛问题的处理方法。"),
    ]),
    "admin": ("网站管理手册", [
        ("permissions", "/accounts/profile/", "确认站务、系统管理员与论坛管理员的职责边界。"),
        ("login", "/dashboard/", "进入管理驾驶舱，找到任务并安全退出。"),
        ("overview", "/dashboard/", "从统计发现待办，回到原始记录核实变化。"),
        ("members", "/dashboard/members/", "按姓名、用户名和学号查人，核对等级与积分。"),
        ("review", "/dashboard/members/", "核验老会员申报，批准、拒绝或重新审核。"),
        ("recruitment", "/dashboard/recruitment/", "管理批次和答卷，记录面试并更新录取状态。"),
        ("news", "/dashboard/news/", "编辑并预览公告，检查发布状态和可见等级。"),
        ("events", "/dashboard/events/", "设置活动时间和名额，管理报名、签到与导出。"),
        ("resources", "/dashboard/resources/", "维护分级资料和项目，核对公开作品范围。"),
        ("media", "/dashboard/media/", "维护荣誉与图片素材，检查构图和授权。"),
        ("showcase", "/showcase/moderation/", "处理展示违规与解除限制，保留成员自主发布权。"),
        ("positions", "/dashboard/positions/", "搜索候选人，区分现任与历史任职，管理勋章。"),
        ("feedback", "/dashboard/feedbacks/", "回复问题反馈，核对通知并完成工单。"),
        ("forum", "https://bbs.heuesta.cn/", "检查论坛账号互通和邮件同步，按权限升级异常。"),
        ("settings", "/dashboard/site/", "维护关键配置前记录原值，修改后验证访问结果。"),
        ("handover", "/dashboard/", "照清单完成日常检查，记录复现条件并交接。"),
    ]),
}


def main():
    (DEST / "assets").mkdir(parents=True, exist_ok=True)
    for audience, (book, tasks) in BOOKS.items():
        original = (ROOT / "docs/manuals" / f"{book}.md").read_text(encoding="utf-8")
        chunks = re.split(r"^## (\d+)\. ([^\n]+)\n", original, flags=re.M)
        directory = DEST / "content" / audience
        directory.mkdir(parents=True, exist_ok=True)
        for number, title, body in zip(chunks[1::3], chunks[2::3], chunks[3::3]):
            index = int(number)
            slug, route, summary = tasks[index - 1]
            path = directory / f"{slug}.md"
            if path.exists():
                continue
            body = re.split(r"^## [^\n]+\n", body, maxsplit=1, flags=re.M)[0]
            body = re.sub(r"### 操作目标\n.*?(?=### )", "", body, flags=re.S)
            body = body.replace("### 具体步骤", "## 按步骤操作").replace("### 完成结果", "## 你应该看到").replace("### 常见错误", "## 遇到问题").replace("### ", "## ")
            shots = []
            def picture(match):
                alt, relative = match.groups()
                source = ROOT / "docs/manuals" / relative
                name = source.parent.name + "-" + source.name
                shutil.copyfile(source, DEST / "assets" / name)
                shots.append(name)
                return f"![{alt}](asset:{name})"
            body = re.sub(r"!\[([^\]]*)\]\((assets/[^)]+)\)", picture, body)
            # Resolve public site links to the current deployment.
            body = body.replace("https://heuesta.cn/", "/")
            body = re.sub(r"<(/[^>]+)>", r"[打开页面](\1)", body)
            if audience == "admin" and slug == "members":
                body = body.replace('5. “设为站务管理”和“设为系统管理员”仅系统管理员可用；必须有明确授权理由。', '5. 需要更改站务或系统权限时，交由系统管理员处理，并提供授权依据。')
            if audience == "admin" and slug == "handover":
                body = body.replace('先备份、使用演示数据、最小化变更并保留回退方案。', '正式站只做只读检查；失败恢复与权限变更测试在隔离环境完成。')
            access = "admin" if audience == "admin" and slug in {"settings", "positions"} else "officer" if audience == "admin" else "public"
            meta = dict(title=title.strip(), summary=summary, access=access, order=index,
                        minutes=max(2, min(8, len(body) // 650 + 1)), routes=[route],
                        checkpoints=["已找到正确的操作页面并核对账号身份", "已按步骤完成本次任务", "结果与本页说明一致；如有差异已记录问题"],
                        screenshots=shots, verified="2026-09-04", version="9c9b9e8")
            path.write_text("---\n" + json.dumps(meta, ensure_ascii=False, indent=2) + "\n---\n\n" + body.strip() + "\n", encoding="utf-8")
            print(f"Imported {audience}/{slug}")


if __name__ == "__main__":
    main()
