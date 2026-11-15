"""
Qui a le droit de faire quoi ? (Rôle 2)

Deux sortes de règles dans ce fichier :

1. Les fonctions "xxx_visible_to(user)" : elles répondent à la question
   "quelles données cette personne a-t-elle le droit de VOIR ?".
   Elles sont réutilisables par GraphQL (Rôle 3) :
       from tunisovereign_core.permissions import feeders_visible_to

2. Les classes de permission DRF : elles répondent "ce rôle a-t-il le droit
   d'utiliser cette adresse (lecture / écriture) ?". Sinon : erreur 403.

Résumé des rôles :
  COOP_MEMBER      -> seulement ses propres nœuds, et leur coopérative / feeder
  REGIONAL_AUDITOR -> tout ce qui est dans son gouvernorat
  NATIONAL_ADMIN   -> tout
  AGENT_SERVICE    -> tout (il doit tout lire pour travailler, et il écrit les événements)
"""
from django.db.models import Q
from rest_framework.permissions import SAFE_METHODS, BasePermission

from .models import (
    AnomalyAndForecastEvent,
    CooperativeUnit,
    Feeder,
    ResourceNodePlot,
    StakeholderUser,
    TelemetryReading,
)

Role = StakeholderUser.Role

ALL_ROLES = (
    Role.COOP_MEMBER,
    Role.REGIONAL_AUDITOR,
    Role.NATIONAL_ADMIN,
    Role.AGENT_SERVICE,
)
FULL_ACCESS_ROLES = (Role.NATIONAL_ADMIN, Role.AGENT_SERVICE)


def _role(user):
    """Rôle de la personne, ou None si elle n'est pas connectée."""
    if user is None or not user.is_authenticated:
        return None
    return user.role


# ---------------------------------------------------------------------------
# 1. Ce que chaque personne a le droit de VOIR
# ---------------------------------------------------------------------------
def nodes_visible_to(user):
    role = _role(user)
    nodes = ResourceNodePlot.objects.all()
    if role in FULL_ACCESS_ROLES:
        return nodes
    if role == Role.REGIONAL_AUDITOR:
        return nodes.filter(feeder__governorate=user.governorate)
    if role == Role.COOP_MEMBER:
        return nodes.filter(owner=user)
    return nodes.none()


def feeders_visible_to(user):
    role = _role(user)
    feeders = Feeder.objects.all()
    if role in FULL_ACCESS_ROLES:
        return feeders
    if role == Role.REGIONAL_AUDITOR:
        return feeders.filter(governorate=user.governorate)
    if role == Role.COOP_MEMBER:
        return feeders.filter(nodes__owner=user).distinct()
    return feeders.none()


def cooperatives_visible_to(user):
    role = _role(user)
    coops = CooperativeUnit.objects.all()
    if role in FULL_ACCESS_ROLES:
        return coops
    if role == Role.REGIONAL_AUDITOR:
        return coops.filter(governorate=user.governorate)
    if role == Role.COOP_MEMBER:
        # pas de lien direct utilisateur -> coopérative : on passe par ses nœuds
        return coops.filter(nodes__owner=user).distinct()
    return coops.none()


def readings_visible_to(user):
    """Mesures de compteur : celles des nœuds que la personne peut voir."""
    return TelemetryReading.objects.filter(node__in=nodes_visible_to(user))


def anomalies_visible_to(user):
    role = _role(user)
    events = AnomalyAndForecastEvent.objects.all()
    if role in FULL_ACCESS_ROLES:
        return events
    if role == Role.REGIONAL_AUDITOR:
        gov = user.governorate
        return events.filter(Q(feeder__governorate=gov) | Q(node__feeder__governorate=gov))
    return events.none()  # un membre de coopérative ne consulte pas les anomalies


# ---------------------------------------------------------------------------
# 2. Classes de permission DRF
# ---------------------------------------------------------------------------
class RoleBasedPermission(BasePermission):
    """
    Refuse (403) les rôles qui n'ont pas le droit d'utiliser l'adresse.
    Chaque vue déclare read_roles (lecture) et write_roles (écriture).
    """

    def has_permission(self, request, view):
        role = _role(request.user)
        if role is None:
            return False  # pas connecté : DRF répond 401
        allowed = view.read_roles if request.method in SAFE_METHODS else view.write_roles
        return role in allowed


class InScopePermission(BasePermission):
    """
    Pour la lecture d'un objet précis : refuse (403) si l'objet n'est pas dans
    ce que la personne a le droit de voir (ex. le nœud d'un autre membre).
    """

    def has_object_permission(self, request, view, obj):
        return view.visible_to(request.user).filter(pk=obj.pk).exists()