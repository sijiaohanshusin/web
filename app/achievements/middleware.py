class AchievementPrivacyMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if request.path.startswith(('/achievements/', '/honors/', '/media/honors/member/')):
            response['Cache-Control'] = 'private, no-store, max-age=0'
            response['CDN-Cache-Control'] = 'no-store'
            if request.path != '/honors/':
                response['X-Robots-Tag'] = 'noindex, nofollow'
        return response
