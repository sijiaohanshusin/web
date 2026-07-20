from urllib.parse import quote

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import redirect_to_login
from django.http import FileResponse, HttpResponse, HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from accounts.roles import is_member, is_officer

from . import permissions
from .models import Project, ProjectFile, ProjectFolder, ProjectMember

User = get_user_model()


def project_list(request):
    if not request.user.is_authenticated:
        return redirect_to_login(request.get_full_path())
    if not permissions.can_view_list(request.user):
        return HttpResponseForbidden("项目档案库仅对会员开放。")

    projects = Project.objects.select_related("created_by").prefetch_related("members")
    dept = request.GET.get("dept", "")
    if dept in Project.Department.values:
        projects = projects.filter(department=dept)
    status = request.GET.get("status", "active")
    if status in Project.Status.values:
        projects = projects.filter(status=status)

    my_ids = set(
        ProjectMember.objects.filter(user=request.user).values_list("project_id", flat=True)
    )
    context = {
        "projects": projects,
        "dept": dept,
        "status": status,
        "departments": Project.Department.choices,
        "my_project_ids": my_ids,
        "is_officer": is_officer(request.user),
    }
    return render(request, "projects/list.html", context)


def _folder_context(request, project, folder):
    subfolders = project.folders.filter(parent=folder).select_related("created_by")
    files = project.files.filter(folder=folder).select_related("uploader")
    return {
        "project": project,
        "folder": folder,
        "breadcrumb": folder.breadcrumb if folder else [],
        "subfolders": subfolders,
        "files": files,
        "members": project.members.select_related("user", "user__position"),
        "can_edit": permissions.can_edit(request.user, project),
        "can_manage": permissions.can_manage(request.user, project),
    }


def project_detail(request, pk: int, folder_pk: int | None = None):
    project = get_object_or_404(Project, pk=pk)
    if not request.user.is_authenticated:
        return redirect_to_login(request.get_full_path())
    if not permissions.can_view_files(request.user, project):
        return HttpResponseForbidden("你不是该项目成员，无法查看项目文件。")

    folder = None
    if folder_pk is not None:
        folder = get_object_or_404(ProjectFolder, pk=folder_pk, project=project)

    return render(request, "projects/detail.html", _folder_context(request, project, folder))


@login_required
@require_POST
def create_folder(request, pk: int):
    project = get_object_or_404(Project, pk=pk)
    if not permissions.can_edit(request.user, project):
        return HttpResponseForbidden("无权在此项目建目录。")

    name = (request.POST.get("name") or "").strip()
    parent = None
    parent_pk = request.POST.get("parent")
    if parent_pk and parent_pk.isdigit():
        parent = get_object_or_404(ProjectFolder, pk=int(parent_pk), project=project)

    if not name:
        messages.error(request, "目录名不能为空。")
    elif "/" in name or "\\" in name:
        messages.error(request, "目录名不能包含斜杠。")
    elif ProjectFolder.objects.filter(project=project, parent=parent, name=name).exists():
        messages.error(request, f"目录「{name}」已存在。")
    else:
        ProjectFolder.objects.create(project=project, parent=parent, name=name, created_by=request.user)
        messages.success(request, f"已新建目录「{name}」。")

    return redirect(_back(project, parent))


@login_required
@require_POST
def upload_file(request, pk: int):
    project = get_object_or_404(Project, pk=pk)
    if not permissions.can_edit(request.user, project):
        return HttpResponseForbidden("无权在此项目上传文件。")

    folder = None
    folder_pk = request.POST.get("folder")
    if folder_pk and folder_pk.isdigit():
        folder = get_object_or_404(ProjectFolder, pk=int(folder_pk), project=project)

    uploaded = request.FILES.getlist("files") or ([request.FILES["file"]] if "file" in request.FILES else [])
    if not uploaded:
        messages.error(request, "没有选择文件。")
        return redirect(_back(project, folder))

    for f in uploaded:
        ProjectFile.objects.create(project=project, folder=folder, file=f, uploader=request.user)
    messages.success(request, f"已上传 {len(uploaded)} 个文件。")
    return redirect(_back(project, folder))


@login_required
@require_POST
def delete_file(request, pk: int, file_pk: int):
    project = get_object_or_404(Project, pk=pk)
    if not permissions.can_edit(request.user, project):
        return HttpResponseForbidden("无权删除该项目的文件。")
    f = get_object_or_404(ProjectFile, pk=file_pk, project=project)
    folder = f.folder
    f.file.delete(save=False)
    f.delete()
    messages.success(request, "文件已删除。")
    return redirect(_back(project, folder))


@login_required
@require_POST
def delete_folder(request, pk: int, folder_pk: int):
    project = get_object_or_404(Project, pk=pk)
    if not permissions.can_edit(request.user, project):
        return HttpResponseForbidden("无权删除该项目的目录。")
    folder = get_object_or_404(ProjectFolder, pk=folder_pk, project=project)
    parent = folder.parent
    # 删除目录内所有文件的物理文件（数据库记录随级联删除）
    for f in ProjectFile.objects.filter(folder__in=_descendant_ids(folder) + [folder.pk]):
        f.file.delete(save=False)
    folder.delete()
    messages.success(request, f"已删除目录「{folder.name}」及其内容。")
    return redirect(_back(project, parent))


def project_file_download(request, pk: int, file_pk: int):
    project = get_object_or_404(Project, pk=pk)
    if not request.user.is_authenticated:
        return redirect_to_login(request.get_full_path())
    if not permissions.can_view_files(request.user, project):
        return HttpResponseForbidden("你不是该项目成员，无法下载项目文件。")

    f = get_object_or_404(ProjectFile, pk=file_pk, project=project)
    if settings.DEBUG:
        return FileResponse(f.file.open("rb"), as_attachment=True, filename=f.filename)

    # 生产：Django 鉴权后交给 nginx 传输（不占应用内存）
    response = HttpResponse()
    response["Content-Type"] = "application/octet-stream"
    response["X-Accel-Redirect"] = f"/protected/{quote(f.file.name)}"
    response["Content-Disposition"] = f"attachment; filename*=UTF-8''{quote(f.filename)}"
    return response


@login_required
@require_POST
def manage_members(request, pk: int):
    project = get_object_or_404(Project, pk=pk)
    if not permissions.can_manage(request.user, project):
        return HttpResponseForbidden("只有项目负责人或干事可以管理成员。")

    action = request.POST.get("action", "")
    if action == "add":
        username = (request.POST.get("username") or "").strip()
        role = request.POST.get("role", ProjectMember.Role.MEMBER)
        if role not in ProjectMember.Role.values:
            role = ProjectMember.Role.MEMBER
        user = User.objects.filter(username=username).first() or \
            User.objects.filter(student_id=username).first()
        if user is None:
            messages.error(request, f"没找到用户「{username}」（可用用户名或学号）。")
        elif not is_member(user):
            messages.error(request, "该用户还不是会员，无法加入项目。")
        else:
            _, created = ProjectMember.objects.get_or_create(
                project=project, user=user, defaults={"role": role},
            )
            messages.success(request, f"已把 {user.display_name} 加入项目。" if created else "该用户已在项目中。")
    elif action == "remove":
        m = get_object_or_404(ProjectMember, pk=request.POST.get("member_id"), project=project)
        name = m.user.display_name
        m.delete()
        messages.success(request, f"已移除成员 {name}。")
    return redirect("projects:detail", pk=project.pk)


def _descendant_ids(folder) -> list[int]:
    """收集某目录下所有子孙目录的 id（用于删除时清理文件）。"""
    ids, stack = [], list(folder.children.all())
    while stack:
        node = stack.pop()
        ids.append(node.pk)
        stack.extend(node.children.all())
    return ids


def _back(project, folder):
    if folder is not None:
        return redirect("projects:folder", pk=project.pk, folder_pk=folder.pk).url
    return redirect("projects:detail", pk=project.pk).url
