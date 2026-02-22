from django.apps import AppConfig


class IaConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'ia'
    def ready(self):
        import courriers.signals

