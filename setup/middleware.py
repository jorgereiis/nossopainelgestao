from django.shortcuts import redirect

class CheckUserLoggedInMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Libera o webhook sem autenticação
        #if request.path.startswith('/webhook/'):
        #    return self.get_response(request)

        if not request.user.is_authenticated and request.path != '/':
            return redirect("login")

        return self.get_response(request)