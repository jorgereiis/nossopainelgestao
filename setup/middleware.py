from django.shortcuts import redirect

class CheckUserLoggedInMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if not request.user.is_authenticated and request.path != '/' and request.path != '/reset-senha/':
            return redirect("login")

        return self.get_response(request)
