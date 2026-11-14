"""
API REST de SolarSouk-STEG (Rôle 2).

Incrément 1 : authentification JWT.
  POST /api/auth/register/  -> créer un compte (toujours COOP_MEMBER)
  POST /api/auth/login/     -> obtenir un jeton d'accès (access) et un jeton de rafraîchissement (refresh)
  POST /api/auth/refresh/   -> obtenir un nouveau jeton d'accès à partir du refresh
"""
from django.contrib.auth.password_validation import validate_password
from rest_framework import generics, permissions, serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from rest_framework_simplejwt.views import TokenObtainPairView

from .models import StakeholderUser


# ---------------------------------------------------------------------------
# 1. Connexion : le jeton contient le rôle et le gouvernorat de la personne
# ---------------------------------------------------------------------------
class SolarTokenObtainPairSerializer(TokenObtainPairSerializer):
    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)
        token["role"] = user.role
        token["governorate"] = user.governorate
        return token


class LoginView(TokenObtainPairView):
    serializer_class = SolarTokenObtainPairSerializer


# ---------------------------------------------------------------------------
# 2. Inscription : ouverte à tous, mais le rôle est TOUJOURS COOP_MEMBER
# ---------------------------------------------------------------------------
class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, validators=[validate_password])

    class Meta:
        model = StakeholderUser
        fields = ["id", "username", "email", "password", "governorate", "role"]
        read_only_fields = ["id", "role"]  # le client ne peut pas choisir son rôle

    def create(self, validated_data):
        # create_user chiffre le mot de passe (on ne le stocke jamais en clair)
        return StakeholderUser.objects.create_user(
            role=StakeholderUser.Role.COOP_MEMBER, **validated_data
        )


class RegisterView(generics.CreateAPIView):
    queryset = StakeholderUser.objects.all()
    serializer_class = RegisterSerializer
    authentication_classes = []  # route publique : on ignore tout jeton envoyé (même périmé)
    permission_classes = [permissions.AllowAny]