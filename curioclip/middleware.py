import jwt
from django.conf import settings
from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed
from api.constants import SUPABASE_JWT_SECRET, SUPBASE_ISSUER


ALGORITHM = "HS256"
AUDIENCE  = "authenticated"        # Supabase default
class SupabaseUser:
    def __init__(self, sub, email=None):
        self.id = sub
        self.email = email
        self.is_authenticated = True

class SupabaseJWTAuthentication(BaseAuthentication):
    """
    Validate Supabase access / refresh / service-role tokens.

    Expected header:  Authorization: Bearer <token>
    """
    def authenticate(self, request):
        auth = request.headers.get("Authorization", "")
        if not auth.startswith("Bearer "):
            return None        # let other authenticators run

        token = auth.split(" ", 1)[1]
        try:
            payload = jwt.decode(
                token,
                SUPABASE_JWT_SECRET,  # HS256 shared secret
                algorithms=[ALGORITHM],
                audience=AUDIENCE,             
                issuer=SUPBASE_ISSUER,        
            )
        except jwt.PyJWTError as exc:
            raise AuthenticationFailed(f"Invalid Supabase token: {exc}")

        user = SupabaseUser(payload["sub"], payload.get("email"))
        return (user, None)