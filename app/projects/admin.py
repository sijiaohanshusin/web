from django.contrib import admin

from .models import Project, ProjectFile, ProjectFolder, ProjectMember


class ProjectMemberInline(admin.TabularInline):
    model = ProjectMember
    extra = 0
    raw_id_fields = ("user",)


@admin.register(Project)
class ProjectAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "department", "status", "created_by", "updated_at")
    list_filter = ("department", "status")
    search_fields = ("name", "summary")
    inlines = [ProjectMemberInline]


@admin.register(ProjectFolder)
class ProjectFolderAdmin(admin.ModelAdmin):
    list_display = ("id", "project", "name", "parent", "created_at")
    search_fields = ("name",)
    raw_id_fields = ("project", "parent")


@admin.register(ProjectFile)
class ProjectFileAdmin(admin.ModelAdmin):
    list_display = ("id", "project", "name", "folder", "uploader", "size", "created_at")
    search_fields = ("name",)
    raw_id_fields = ("project", "folder", "uploader")
