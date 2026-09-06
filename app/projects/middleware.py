import re


class WorksPrivacyMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if request.path.startswith(('/works/', '/media/projects/member-works/')):
            response['Cache-Control'] = 'private, no-store, max-age=0'
            response['CDN-Cache-Control'] = 'no-store'
            if not re.fullmatch(r'/works/(\d+/)?', request.path):
                response['X-Robots-Tag'] = 'noindex, nofollow'
        return response
