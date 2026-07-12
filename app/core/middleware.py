class DynamicPagesNoCacheMiddleware:
    """给未显式声明缓存策略的动态响应加上 private, no-cache。

    站点前置了 CDN（腾讯 EdgeOne）：静态资源走 /static/（长缓存），
    而 Django 渲染的页面可能包含登录态，绝不能被 CDN 缓存后串给其他访客。
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if not response.has_header("Cache-Control"):
            response["Cache-Control"] = "private, no-cache"
        return response
