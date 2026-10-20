"""Xavfsizlik sarlavhalari: CSP (admin tashqarisida), Permissions-Policy, shaxsiy sahifalarni keshlamaslik."""

CSP = (
    "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; "
    "font-src 'self'; connect-src 'self'; object-src 'none'; frame-ancestors 'none'; "
    "base-uri 'self'; form-action 'self'"
)


class SecurityHeadersMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if not request.path.startswith("/admin/"):  # Django admin o'z inline skriptlaridan foydalanadi
            response.headers.setdefault("Content-Security-Policy", CSP)
        response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=(), payment=()")
        if getattr(request, "user", None) is not None and request.user.is_authenticated:
            response.headers["Cache-Control"] = "no-store"
        return response
