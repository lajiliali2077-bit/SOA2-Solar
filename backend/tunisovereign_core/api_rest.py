"""
API REST de SolarSouk-STEG (Rôle 2).

Authentification JWT :
  POST /api/auth/register/  -> créer un compte (toujours COOP_MEMBER)
  POST /api/auth/login/     -> obtenir un jeton d'accès (access) et un jeton de rafraîchissement (refresh)
  POST /api/auth/refresh/   -> obtenir un nouveau jeton d'accès à partir du refresh

Données (préfixe /api/v1/), filtrées selon le rôle (voir permissions.py) :
  GET  /api/v1/nodes/         et /api/v1/nodes/<id>/
  GET  /api/v1/cooperatives/  et /api/v1/cooperatives/<id>/
  GET  /api/v1/anomalies/     et /api/v1/anomalies/<id>/
  POST /api/v1/anomalies/     (AGENT_SERVICE et NATIONAL_ADMIN seulement)
"""
from django.contrib.auth.password_validation import validate_password
from rest_framework import generics, mixins, permissions, routers, serializers, viewsets
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from rest_framework_simplejwt.views import TokenObtainPairView

from .models import AnomalyAndForecastEvent, CooperativeUnit, ResourceNodePlot, StakeholderUser
from .permissions import (
    ALL_ROLES,
    FULL_ACCESS_ROLES,
    InScopePermission,
    Role,
    RoleBasedPermission,
    anomalies_visible_to,
    cooperatives_visible_to,
    nodes_visible_to,
)


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


# ---------------------------------------------------------------------------
# 3. Serializers : on choisit explicitement les champs exposés
# ---------------------------------------------------------------------------
class NodeSerializer(serializers.ModelSerializer):
    class Meta:
        model = ResourceNodePlot
        fields = [
            "id", "node_code", "coop", "owner", "feeder", "site_type",
            "installed_kwp", "battery_capacity_kwh", "has_pump",
            "pump_rated_kw", "is_pump_dispatch_active",
        ]


class CooperativeSerializer(serializers.ModelSerializer):
    class Meta:
        model = CooperativeUnit
        fields = ["id", "name", "governorate", "track_domain", "daily_quota_limit", "contract_address"]


class AnomalySerializer(serializers.ModelSerializer):
    class Meta:
        model = AnomalyAndForecastEvent
        fields = "__all__"
        read_only_fields = ["id", "detected_at"]

    def validate(self, attrs):
        # La base exige au moins un nœud ou un feeder : on répond proprement (400) au lieu de planter.
        if not attrs.get("node") and not attrs.get("feeder"):
            raise serializers.ValidationError("Il faut au moins un nœud (node) ou un feeder.")
        return attrs


# ---------------------------------------------------------------------------
# 4. Vues : même squelette pour toutes les ressources
# ---------------------------------------------------------------------------
class RoleScopedViewSet(viewsets.GenericViewSet):
    """
    - read_roles / write_roles : rôles autorisés à lire / écrire (sinon 403)
    - visible_to(user) : ce que la personne a le droit de voir
      * dans une liste : on ne montre que ces objets
      * pour un objet précis : hors de ce périmètre -> 403
    """

    permission_classes = [RoleBasedPermission, InScopePermission]
    read_roles = ALL_ROLES
    write_roles = ()

    def visible_to(self, user):
        raise NotImplementedError

    def get_queryset(self):
        queryset = self.queryset.all()
        if self.action == "list":
            queryset = queryset.filter(pk__in=self.visible_to(self.request.user).values("pk"))
        return queryset


class NodeViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, RoleScopedViewSet):
    queryset = ResourceNodePlot.objects.order_by("node_code")
    serializer_class = NodeSerializer

    def visible_to(self, user):
        return nodes_visible_to(user)


class CooperativeViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, RoleScopedViewSet):
    queryset = CooperativeUnit.objects.order_by("name")
    serializer_class = CooperativeSerializer

    def visible_to(self, user):
        return cooperatives_visible_to(user)


class AnomalyViewSet(
    mixins.ListModelMixin, mixins.RetrieveModelMixin, mixins.CreateModelMixin, RoleScopedViewSet
):
    queryset = AnomalyAndForecastEvent.objects.order_by("-detected_at")
    serializer_class = AnomalySerializer
    read_roles = (Role.REGIONAL_AUDITOR, Role.NATIONAL_ADMIN, Role.AGENT_SERVICE)
    write_roles = FULL_ACCESS_ROLES

    def visible_to(self, user):
        return anomalies_visible_to(user)


router = routers.DefaultRouter()
router.register("nodes", NodeViewSet, basename="node")
router.register("cooperatives", CooperativeViewSet, basename="cooperative")
router.register("anomalies", AnomalyViewSet, basename="anomaly")