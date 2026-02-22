from django.contrib.auth.backends import ModelBackend
from django.contrib.auth import get_user_model

User = get_user_model()

class EmailAuthBackend(ModelBackend):
    def authenticate(self, request, email=None, password=None, **kwargs):
        try:
            user = User.objects.get(email__iexact=email)
        except User.DoesNotExist:
            return None
        if user.check_password(password) and user.actif:
            return user
        return None
    def get_user(self, user_id):
        try:
            return User.objectifs.get(pk=user_id)
        except User.DoesNotExist:
            return None
