from django.apps import AppConfig


class NossopainelConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "nossopainel"

    def ready(self):
        import nossopainel.signals, nossopainel.utils
