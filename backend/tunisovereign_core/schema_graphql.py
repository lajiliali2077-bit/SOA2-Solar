from typing import List, Optional

import strawberry
import strawberry_django
from django.db.models import Q, Sum
from rest_framework_simplejwt.authentication import JWTAuthentication
from strawberry import auto
from strawberry.types import Info

from tunisovereign_core import models

Role = models.StakeholderUser.Role
FULL_ACCESS_ROLES = (Role.NATIONAL_ADMIN, Role.AGENT_SERVICE)
MAX_LIMIT = 1000


# ---------------------------------------------------------------------------
# Utilisateur courant et règles de visibilité par rôle
# ---------------------------------------------------------------------------
def current_user(info: Info):
    """Session Django d'abord (GraphiQL après connexion à /admin/), sinon jeton JWT."""
    request = info.context.request
    user = getattr(request, "user", None)
    if user is not None and user.is_authenticated:
        return user
    try:
        result = JWTAuthentication().authenticate(request)
    except Exception:
        return None
    return result[0] if result else None


def visible_feeders(user):
    qs = models.Feeder.objects.all()
    if user is None:
        return qs.none()
    if user.role in FULL_ACCESS_ROLES:
        return qs
    if user.role == Role.REGIONAL_AUDITOR:
        return qs.filter(governorate=user.governorate)
    if user.role == Role.COOP_MEMBER:
        return qs.filter(nodes__owner=user).distinct()
    return qs.none()


def visible_nodes(user):
    qs = models.ResourceNodePlot.objects.all()
    if user is None:
        return qs.none()
    if user.role in FULL_ACCESS_ROLES:
        return qs
    if user.role == Role.REGIONAL_AUDITOR:
        return qs.filter(feeder__governorate=user.governorate)
    if user.role == Role.COOP_MEMBER:
        return qs.filter(owner=user)
    return qs.none()


def visible_readings(user):
    return models.TelemetryReading.objects.filter(node__in=visible_nodes(user))


def visible_anomalies(user):
    qs = models.AnomalyAndForecastEvent.objects.all()
    if user is None:
        return qs.none()
    if user.role in FULL_ACCESS_ROLES:
        return qs
    if user.role == Role.REGIONAL_AUDITOR:
        return qs.filter(
            Q(node__in=visible_nodes(user)) | Q(feeder__in=visible_feeders(user))
        )
    if user.role == Role.COOP_MEMBER:
        return qs.filter(node__in=visible_nodes(user))
    return qs.none()


# ---------------------------------------------------------------------------
# Types GraphQL
# ---------------------------------------------------------------------------
@strawberry_django.type(models.ResourceNodePlot)
class NodeType:
    id: auto
    node_code: auto
    site_type: auto
    installed_kwp: auto
    battery_capacity_kwh: auto
    has_pump: auto
    pump_rated_kw: auto
    is_pump_dispatch_active: auto


@strawberry_django.type(models.Feeder)
class FeederType:
    id: auto
    name: auto
    governorate: auto
    capacity_kw: auto
    created_at: auto

    @strawberry_django.field
    def nodes(self, info: Info) -> List[NodeType]:
        # Seuls les nœuds visibles par l'utilisateur connecté
        return list(visible_nodes(current_user(info)).filter(feeder=self))


@strawberry_django.type(models.TelemetryReading)
class TelemetryReadingType:
    id: auto
    timestamp: auto
    metric_type: auto
    value: auto
    ingestion_protocol: auto
    # le champ de vérité terrain du simulateur n'est volontairement pas exposé (ML)


@strawberry_django.type(models.AnomalyAndForecastEvent)
class AnomalyType:
    id: auto
    reading_timestamp: auto
    detected_at: auto
    anomaly_type: auto
    severity: auto
    isolation_forest_score: auto
    forecasted_deficit_24h: auto
    model_version: auto


@strawberry.type
class LoadPointType:
    timestamp: str
    total_kw: float
    percentage_capacity: float


@strawberry.type
class FeederLoadGraphType:
    feeder_id: int
    feeder_name: str
    capacity_kw: float
    points: List[LoadPointType]


# ---------------------------------------------------------------------------
# Requêtes
# ---------------------------------------------------------------------------
@strawberry.type
class Query:
    @strawberry.field
    def resource_node_plots(self, info: Info) -> List[NodeType]:
        return list(visible_nodes(current_user(info)))

    @strawberry.field
    def feeders(self, info: Info) -> List[FeederType]:
        return list(visible_feeders(current_user(info)))

    @strawberry.field
    def feeder(self, info: Info, id: int) -> Optional[FeederType]:
        return visible_feeders(current_user(info)).filter(pk=id).first()

    @strawberry.field
    def telemetry_readings(
        self, info: Info, metric_type: Optional[str] = None, limit: int = 100
    ) -> List[TelemetryReadingType]:
        qs = visible_readings(current_user(info))
        if metric_type:
            qs = qs.filter(metric_type=metric_type)
        limit = max(1, min(limit, MAX_LIMIT))
        return list(qs.order_by("-timestamp")[:limit])

    @strawberry.field
    def anomalies(
        self, info: Info, severity: Optional[str] = None, limit: int = 200
    ) -> List[AnomalyType]:
        qs = visible_anomalies(current_user(info))
        if severity:
            qs = qs.filter(severity=severity)
        limit = max(1, min(limit, MAX_LIMIT))
        return list(qs.order_by("-detected_at")[:limit])

    @strawberry.field
    def feeder_load_graph(self, info: Info, feeder_id: int) -> Optional[FeederLoadGraphType]:
        user = current_user(info)
        # La charge agrégée d'un feeder n'est pas montrée aux membres de coopérative
        if user is None or user.role == Role.COOP_MEMBER:
            return None
        feeder = visible_feeders(user).filter(pk=feeder_id).first()
        if feeder is None:
            return None

        rows = (
            models.TelemetryReading.objects
            .filter(node__feeder_id=feeder.id, metric_type="GRID_NET_KW")
            .values("timestamp")
            .annotate(total_kw=Sum("value"))
            .order_by("timestamp")
        )

        points = []
        for row in rows:
            total_kw = row["total_kw"] or 0.0
            pct = total_kw / feeder.capacity_kw * 100 if feeder.capacity_kw else 0.0
            points.append(
                LoadPointType(
                    timestamp=row["timestamp"].isoformat(),
                    total_kw=float(total_kw),
                    percentage_capacity=float(pct),
                )
            )

        return FeederLoadGraphType(
            feeder_id=feeder.id,
            feeder_name=feeder.name,
            capacity_kw=feeder.capacity_kw,
            points=points,
        )


schema = strawberry.Schema(query=Query)
