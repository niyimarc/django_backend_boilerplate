from django.apps import AppConfig


class UserAuthKeyConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'user_auth_key'

    def ready(self):
        import user_auth_key.signals