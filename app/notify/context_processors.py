def unread(request):
    """导航栏铃铛的未读数（仅登录用户，单条索引 COUNT）。"""
    if not request.user.is_authenticated:
        return {}
    return {
        "unread_notifications": request.user.notifications.filter(read_at__isnull=True).count(),
    }
