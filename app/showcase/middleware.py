class ShowcasePrivacyMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if request.path.startswith(("/team/", "/accounts/showcase/", "/showcase/", "/media/showcase/")):
            response["Cache-Control"] = "private, no-store, max-age=0"
            response["CDN-Cache-Control"] = "no-store"
            response["Expires"] = "0"
            response["Referrer-Policy"] = "no-referrer"
            if request.path != "/team/":
                response["X-Robots-Tag"] = "noindex, nofollow, noarchive"
        return response
