"""
Modèles de domaine : SolarSouk-STEG (Track 7).

Une seule app Django : tunisovereign_core.
Référence : docs/models.md. Règle : on modifie le .md d'abord, puis ce fichier.
Réglage requis dans settings.py : AUTH_USER_MODEL = "tunisovereign_core.StakeholderUser"
"""
import uuid

from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import F, Q


# ---------------------------------------------------------------------------
# Énumération partagée
# ---------------------------------------------------------------------------
class Governorate(models.TextChoices):
    TOZEUR = "TOZEUR", "Tozeur"
    KEBILI = "KEBILI", "Kébili"
    TATAOUINE = "TATAOUINE", "Tataouine"
    SFAX = "SFAX", "Sfax"


# ---------------------------------------------------------------------------
# 1. Utilisateurs et rôles (4 rôles imposés par le sujet)
# ---------------------------------------------------------------------------
class StakeholderUser(AbstractUser):
    class Role(models.TextChoices):
        COOP_MEMBER = "COOP_MEMBER", "Ferme / PME productrice (prosumer)"
        REGIONAL_AUDITOR = "REGIONAL_AUDITOR", "Auditeur énergie régional"
        NATIONAL_ADMIN = "NATIONAL_ADMIN", "Administrateur national"
        AGENT_SERVICE = "AGENT_SERVICE", "Agent IA et compte de service MCP"

    role = models.CharField(max_length=24, choices=Role.choices, default=Role.COOP_MEMBER)
    governorate = models.CharField(
        max_length=16, choices=Governorate.choices, default=Governorate.TOZEUR, db_index=True
    )
    wallet_address = models.CharField(max_length=42, blank=True, null=True)
    preferred_dialect = models.CharField(max_length=16, default="ar-TN")

    def __str__(self):
        return f"{self.username} ({self.role})"


# ---------------------------------------------------------------------------
# 2. Réseau : feeders, coopératives, sites, tarifs
# ---------------------------------------------------------------------------
class Feeder(models.Model):
    """Départ moyenne tension alimentant plusieurs sites. Sa charge = somme des nœuds rattachés."""

    name = models.CharField(max_length=80, unique=True)
    governorate = models.CharField(max_length=16, choices=Governorate.choices, db_index=True)
    capacity_kw = models.FloatField(validators=[MinValueValidator(0.1)])
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.CheckConstraint(condition=Q(capacity_kw__gt=0), name="feeder_capacity_positive"),
        ]

    def __str__(self):
        return f"{self.name} ({self.capacity_kw} kW)"


class CooperativeUnit(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=120)
    governorate = models.CharField(max_length=16, choices=Governorate.choices, db_index=True)
    track_domain = models.CharField(max_length=64, default="Track_07_SolarSouk_STEG")
    daily_quota_limit = models.FloatField(
        validators=[MinValueValidator(0)],
        help_text="Plafond quotidien d'énergie réseau (kWh/jour). Sert de borne à la preuve ZK.",
    )
    contract_address = models.CharField(max_length=42, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.name} ({self.governorate})"


class ResourceNodePlot(models.Model):
    """Un site solaire (ferme ou PME) avec onduleur, batterie et éventuellement une pompe."""

    class SiteType(models.TextChoices):
        FARM = "FARM", "Exploitation agricole"
        SME = "SME", "PME"

    coop = models.ForeignKey(CooperativeUnit, on_delete=models.CASCADE, related_name="nodes")
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="owned_nodes"
    )
    feeder = models.ForeignKey(Feeder, on_delete=models.PROTECT, related_name="nodes")
    node_code = models.CharField(max_length=32, unique=True)  # ex. TOZ-001
    site_type = models.CharField(max_length=8, choices=SiteType.choices, default=SiteType.FARM)
    installed_kwp = models.FloatField(validators=[MinValueValidator(0)])
    battery_capacity_kwh = models.FloatField(default=0.0, validators=[MinValueValidator(0)])
    has_pump = models.BooleanField(default=False)
    pump_rated_kw = models.FloatField(default=0.0, validators=[MinValueValidator(0)])
    is_pump_dispatch_active = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=Q(has_pump=True) | Q(pump_rated_kw=0),
                name="node_pump_power_requires_pump",
            ),
        ]

    def __str__(self):
        return self.node_code


class Tariff(models.Model):
    """Tarif d'achat et de rachat par tranche horaire. Montants en millimes, jamais en float."""

    class TimeBand(models.TextChoices):
        OFFPEAK = "OFFPEAK", "Heures creuses"
        DAY = "DAY", "Jour"
        PEAK = "PEAK", "Pointe"

    name = models.CharField(max_length=80)
    time_band = models.CharField(max_length=8, choices=TimeBand.choices)
    start_hour = models.PositiveSmallIntegerField(
        validators=[MaxValueValidator(23)],
        help_text="Heure de début (0 à 23). Une tranche peut passer minuit (ex. 22 à 6).",
    )
    end_hour = models.PositiveSmallIntegerField(validators=[MaxValueValidator(24)])
    buy_price_millimes_kwh = models.PositiveIntegerField(help_text="Prix d'achat au réseau")
    sell_price_millimes_kwh = models.PositiveIntegerField(help_text="Prix de rachat (net-metering)")
    valid_from = models.DateField()
    valid_to = models.DateField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=Q(valid_to__isnull=True) | Q(valid_to__gte=F("valid_from")),
                name="tariff_valid_range",
            ),
        ]

    def __str__(self):
        return f"{self.name} [{self.time_band}]"


# ---------------------------------------------------------------------------
# 3. Télémétrie : une ligne par mesure (même forme que le paquet gRPC)
# ---------------------------------------------------------------------------
class TelemetryReading(models.Model):
    class MetricType(models.TextChoices):
        GENERATION_KW = "GENERATION_KW", "Production solaire (kW)"
        BATTERY_SOC = "BATTERY_SOC", "État de charge batterie (%)"
        PUMP_LOAD_KW = "PUMP_LOAD_KW", "Charge de la pompe (kW)"
        VOLTAGE_V = "VOLTAGE_V", "Tension onduleur (V)"
        GRID_NET_KW = "GRID_NET_KW", "Puissance réseau (kW, positif = import, négatif = export)"

    class Protocol(models.TextChoices):
        REST = "REST", "REST"
        GRPC = "GRPC", "gRPC"
        GRAPHQL = "GRAPHQL", "GraphQL"

    node = models.ForeignKey(ResourceNodePlot, on_delete=models.CASCADE, related_name="readings")
    timestamp = models.DateTimeField(db_index=True)  # UTC
    metric_type = models.CharField(max_length=16, choices=MetricType.choices)
    value = models.FloatField()
    ingestion_protocol = models.CharField(
        max_length=16, choices=Protocol.choices, default=Protocol.GRPC
    )
    is_injected_anomaly = models.BooleanField(
        default=False,
        help_text="Étiquette de vérité terrain pour Précision/Rappel/F1. Ne JAMAIS l'utiliser comme variable du modèle ML.",
    )

    class Meta:
        indexes = [
            models.Index(fields=["node", "metric_type", "-timestamp"], name="tele_node_metric_ts_idx"),
            models.Index(fields=["timestamp", "metric_type"], name="tele_ts_metric_idx"),
        ]

    def __str__(self):
        return f"{self.node_id} {self.metric_type}={self.value} @ {self.timestamp:%Y-%m-%d %H:%M}"


# ---------------------------------------------------------------------------
# 4. ML : anomalies et prévisions
# ---------------------------------------------------------------------------
class AnomalyAndForecastEvent(models.Model):
    class Severity(models.TextChoices):
        LOW = "LOW", "Faible"
        MEDIUM = "MEDIUM", "Moyenne"
        CRITICAL = "CRITICAL", "Critique (surcharge / panne)"

    class AnomalyType(models.TextChoices):
        FEEDER_OVERLOAD = "FEEDER_OVERLOAD", "Surcharge du feeder (> 92 %)"
        VOLTAGE_OUT_OF_RANGE = "VOLTAGE_OUT_OF_RANGE", "Tension hors 220 V ± 6 %"
        INVERTER_FAILURE = "INVERTER_FAILURE", "Panne d'onduleur"
        PUMP_MISALIGNED = "PUMP_MISALIGNED", "Pompe hors fenêtre solaire (10h-15h)"
        SOC_INCONSISTENT = "SOC_INCONSISTENT", "État de charge incohérent"

    # Une anomalie concerne un nœud, un feeder, ou les deux (surcharge = niveau feeder).
    node = models.ForeignKey(
        ResourceNodePlot, on_delete=models.CASCADE, related_name="anomalies", null=True, blank=True
    )
    feeder = models.ForeignKey(
        Feeder, on_delete=models.CASCADE, related_name="anomalies", null=True, blank=True
    )
    reading_timestamp = models.DateTimeField(
        null=True, blank=True, help_text="Horodatage de la mesure détectée (sert au calcul F1)"
    )
    detected_at = models.DateTimeField(auto_now_add=True)
    anomaly_type = models.CharField(max_length=64, choices=AnomalyType.choices)
    severity = models.CharField(max_length=16, choices=Severity.choices)
    isolation_forest_score = models.FloatField(
        null=True,
        blank=True,
        help_text="Vide pour les anomalies détectées par règle (ex. FEEDER_OVERLOAD > 92 %)",
    )
    forecasted_deficit_24h = models.FloatField(default=0.0, help_text="kWh")
    model_version = models.CharField(max_length=32, default="isoforest-v1")

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=Q(node__isnull=False) | Q(feeder__isnull=False),
                name="anomaly_has_node_or_feeder",
            ),
        ]
        indexes = [
            models.Index(fields=["severity", "-detected_at"], name="anom_sev_detected_idx"),
        ]

    def __str__(self):
        return f"{self.anomaly_type} [{self.severity}]"


# ---------------------------------------------------------------------------
# 5. Agent LangGraph et preuve on-chain
# ---------------------------------------------------------------------------
class AgentLoopExecution(models.Model):
    class Status(models.TextChoices):
        RUNNING = "RUNNING", "En cours"
        COMPLETED = "COMPLETED", "Terminé"
        ESCALATED = "ESCALATED", "Escaladé à l'auditeur"
        FAILED = "FAILED", "Échec"

    thread_id = models.CharField(max_length=64, db_index=True)
    trigger_source = models.CharField(max_length=64)  # gRPC_Anomaly, Scheduled_Audit, Darja_Voice
    anomaly = models.ForeignKey(
        AnomalyAndForecastEvent,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="agent_runs",
    )
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.RUNNING)
    retry_count = models.PositiveSmallIntegerField(default=0, help_text="Tours de la boucle d'auto-correction")
    darja_transcript = models.TextField(blank=True)
    parsed_intent_json = models.JSONField(default=dict)
    mcp_tools_invoked = models.JSONField(default=list)
    skills_executed = models.JSONField(default=list)
    final_recommendation = models.TextField(blank=True)
    confidence_score = models.FloatField(
        default=0.0, validators=[MinValueValidator(0.0), MaxValueValidator(1.0)]
    )
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.thread_id} [{self.status}]"


class OnChainZKReceipt(models.Model):
    agent_execution = models.OneToOneField(
        AgentLoopExecution, on_delete=models.CASCADE, related_name="zk_receipt"
    )
    zk_commitment_hash = models.CharField(max_length=66, unique=True)
    public_inputs_json = models.JSONField(default=dict)
    tx_hash = models.CharField(max_length=66, unique=True)
    block_number = models.PositiveIntegerField()
    network_name = models.CharField(max_length=32, default="Foundry-Anvil-Local")
    is_verified_on_chain = models.BooleanField(
        default=False,
        help_text="Passe à True seulement après confirmation par le contrat",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.tx_hash[:12]}… (bloc {self.block_number})"

    


# ---------------------------------------------------------------------------
# 6. Migration 0002 : planning des pompes, règlement net-metering, crédit carbone
# ---------------------------------------------------------------------------
class PumpSchedule(models.Model):
    """Planning de démarrage d'une pompe, proposé par l'agent (PumpPeakShavingOptimizerSkill)."""

    class Status(models.TextChoices):
        PROPOSED = "PROPOSED", "Proposé"
        APPLIED = "APPLIED", "Appliqué"
        CANCELLED = "CANCELLED", "Annulé"

    node = models.ForeignKey(ResourceNodePlot, on_delete=models.CASCADE, related_name="pump_schedules")
    agent_execution = models.ForeignKey(
        AgentLoopExecution,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="pump_schedules",
    )
    start = models.DateTimeField()  # UTC
    end = models.DateTimeField()  # UTC
    planned_kw = models.FloatField(validators=[MinValueValidator(0)])
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PROPOSED)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.CheckConstraint(condition=Q(end__gt=F("start")), name="pump_schedule_end_after_start"),
            models.CheckConstraint(condition=Q(planned_kw__gte=0), name="pump_schedule_kw_non_negative"),
        ]
        indexes = [
            models.Index(fields=["node", "start"], name="pump_node_start_idx"),
        ]

    def __str__(self):
        return f"{self.node_id} {self.start:%Y-%m-%d %H:%M} -> {self.end:%H:%M} ({self.planned_kw} kW)"


class NetMeteringSettlement(models.Model):
    """Règlement net-metering d'un nœud sur une période. Montants en millimes (entiers)."""

    class Status(models.TextChoices):
        PENDING = "PENDING", "En attente"
        SETTLED = "SETTLED", "Réglé"
        FAILED = "FAILED", "Échec"

    node = models.ForeignKey(ResourceNodePlot, on_delete=models.PROTECT, related_name="settlements")
    period_start = models.DateTimeField()  # UTC
    period_end = models.DateTimeField()  # UTC
    imported_kwh = models.FloatField(validators=[MinValueValidator(0)])
    exported_kwh = models.FloatField(validators=[MinValueValidator(0)])
    import_cost_millimes = models.PositiveBigIntegerField()
    export_credit_millimes = models.PositiveBigIntegerField()
    net_amount_millimes = models.BigIntegerField(
        help_text="Positif : le nœud paie. Négatif : le réseau paie le nœud."
    )
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING)
    zk_receipt = models.OneToOneField(
        OnChainZKReceipt,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="settlement",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=Q(period_end__gt=F("period_start")), name="settlement_end_after_start"
            ),
            models.UniqueConstraint(
                fields=["node", "period_start", "period_end"], name="settlement_unique_node_period"
            ),
            models.CheckConstraint(
                condition=Q(net_amount_millimes=F("import_cost_millimes") - F("export_credit_millimes")),
                name="settlement_net_is_import_minus_export",
            ),
        ]

    def __str__(self):
        return f"{self.node_id} {self.period_start:%Y-%m-%d} net={self.net_amount_millimes} millimes"


class CarbonCredit(models.Model):
    """Crédit carbone associé à un règlement. Le facteur d'émission utilisé est conservé."""

    settlement = models.OneToOneField(
        NetMeteringSettlement, on_delete=models.PROTECT, related_name="carbon_credit"
    )
    green_kwh = models.FloatField(validators=[MinValueValidator(0)])
    co2_avoided_kg = models.FloatField(validators=[MinValueValidator(0)])
    emission_factor_kg_per_kwh = models.FloatField(help_text="Facteur utilisé pour ce calcul (kg CO2/kWh)")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=Q(emission_factor_kg_per_kwh__gt=0), name="carbon_factor_positive"
            ),
        ]

    def __str__(self):
        return f"{self.co2_avoided_kg:.1f} kg CO2 (règlement {self.settlement_id})"