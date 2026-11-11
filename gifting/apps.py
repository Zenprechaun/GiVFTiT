from django.apps import AppConfig


class GiftingConfig(AppConfig):
    name = "gifting"

    def ready(self):
        from . import signals  # noqa: F401
