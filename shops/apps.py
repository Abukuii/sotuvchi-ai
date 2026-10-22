from django.apps import AppConfig


class ShopsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "shops"
    verbose_name = "Do'konlar"

    def ready(self):
        from . import audit  # noqa: F401  (kirish/chiqish signallarini ulaydi)
