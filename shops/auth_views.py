from django.conf import settings
from django.contrib.auth.views import LoginView

from . import audit, throttle


class ThrottledLoginView(LoginView):
    """Ketma-ket xato urinishlardan keyin vaqtincha bloklaydi (IP+login va umumiy IP bo'yicha)."""

    def _keys(self, request):
        ip = throttle.client_ip(request)
        username = (request.POST.get("username") or "").strip().lower()[:150]
        return f"login-ip:{ip}", f"login-ipuser:{ip}:{username}"

    def post(self, request, *args, **kwargs):
        ip_key, pair_key = self._keys(request)
        if (
            throttle.count(ip_key) >= settings.LOGIN_IP_MAX_ATTEMPTS
            or throttle.count(pair_key) >= settings.LOGIN_MAX_ATTEMPTS
        ):
            form = self.get_form()
            audit.record(request, "login_blocked", username=(request.POST.get("username") or "")[:150])
            form.add_error(None, "Juda ko'p muvaffaqiyatsiz urinish. 15 daqiqadan keyin qayta urinib ko'ring.")
            return self.render_to_response(self.get_context_data(form=form), status=429)
        return super().post(request, *args, **kwargs)

    def form_invalid(self, form):
        ip_key, pair_key = self._keys(self.request)
        throttle.hit(ip_key, settings.LOGIN_LOCK_SECONDS)
        throttle.hit(pair_key, settings.LOGIN_LOCK_SECONDS)
        return super().form_invalid(form)

    def form_valid(self, form):
        _, pair_key = self._keys(self.request)
        throttle.reset(pair_key)
        return super().form_valid(form)
