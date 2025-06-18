from rest_framework.authentication import BaseAuthentication
from rest_framework import exceptions
import jwt
from django.conf import settings
from django.contrib.auth.models import AnonymousUser

class SupabaseJWTUser:
    def __init__(self, id, email=None):
        self.id = id
        self.email = email
        self.is_authenticated = True

class SupabaseJWTAuthentication(BaseAuthentication):
    def authenticate(self, request):
        auth = request.headers.get('Authorization')
        if not auth or not auth.startswith('Bearer '):
            return None  # No authentication, move on to next authentication class

        token = auth[7:]
        try:
            payload = jwt.decode(token, settings.SUPABASE_JWT_SECRET, algorithms=["HS256"])
            user_id = payload.get('sub') or payload.get('id')
            user_email = payload.get('email')
            user = SupabaseJWTUser(user_id, user_email)
            return (user, None)
        except Exception:
            raise exceptions.AuthenticationFailed('Invalid token')

        return None