from django.conf import settings
from django.shortcuts import redirect
from django.urls import NoReverseMatch, reverse


class CheckUserLoggedInMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response
        self._public_paths = None
        self._public_prefixes = None

    def __call__(self, request):
        if request.user.is_authenticated:
            return self.get_response(request)

        path = request.path
        if path in self.public_paths:
            return self.get_response(request)

        for prefix in self.public_prefixes:
            if prefix and path.startswith(prefix):
                return self.get_response(request)

        return redirect("login")

    @property
    def public_paths(self):
        if self._public_paths is not None:
            return self._public_paths

        paths = {"/", "/admin/login/"}
        for name in ("login", "logout", "verify-2fa"):
            try:
                paths.add(reverse(name))
            except NoReverseMatch:
                continue
        self._public_paths = paths
        return self._public_paths

    @property
    def public_prefixes(self):
        if self._public_prefixes is not None:
            return self._public_prefixes

        prefixes = {"/static/", "/media/", "/favicon.ico"}
        static_url = getattr(settings, "STATIC_URL", None)
        if static_url:
            prefixes.add(static_url if static_url.endswith("/") else f"{static_url}/")
        media_url = getattr(settings, "MEDIA_URL", None)
        if media_url:
            prefixes.add(media_url if media_url.endswith("/") else f"{media_url}/")

        self._public_prefixes = tuple(prefixes)
        return self._public_prefixes
