from django.core.management.base import BaseCommand

from tunisovereign_core.agent_trigger import DEFAULT_MAX_RUNS, trigger_agent_on_critical
from tunisovereign_core.ml_anomaly import (
    ML_MODEL_VERSION,
    OVERLOAD_THRESHOLD,
    TunisianTelemetryAnomalyEngine,
    load_feeder_loads,
)
from tunisovereign_core.models import AnomalyAndForecastEvent

Event = AnomalyAndForecastEvent


class Command(BaseCommand):
    help = (
        "Détecte les surcharges de feeders (règle) et les anomalies de nœud (IsolationForest) "
        "et les enregistre comme événements (idempotent)."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--clear", action="store_true",
            help="supprime tous les événements avant de détecter",
        )
        parser.add_argument(
            "--skip-ml", action="store_true",
            help="ne lance que la règle de surcharge feeder (sans IsolationForest)",
        )
        parser.add_argument(
            "--no-agent", action="store_true",
            help="ne déclenche pas l'agent sur les anomalies CRITICAL",
        )
        parser.add_argument(
            "--max-agent-runs", type=int, default=DEFAULT_MAX_RUNS,
            help=f"nombre maximal d'exécutions de l'agent par lancement (défaut {DEFAULT_MAX_RUNS})",
        )

    def handle(self, *args, **options):
        if options["clear"]:
            print("Événements supprimés :", Event.objects.all().delete())

        self._detect_feeder_overloads()
        if not options["skip_ml"]:
            self._detect_node_anomalies()

        total = Event.objects.count()
        overloads = Event.objects.filter(anomaly_type=Event.AnomalyType.FEEDER_OVERLOAD).count()
        self.stdout.write(self.style.SUCCESS(
            f"Total : {total} événement(s) en base, dont {overloads} surcharge(s) feeder."
        ))

        # Déclenchement automatique de l'agent (Rôle 4) sur les incidents CRITICAL
        if not options["no_agent"]:
            trigger_agent_on_critical(
                max_runs=options["max_agent_runs"], log=self.stdout.write
            )

    # ------------------------------------------------------------------ règle feeder
    def _detect_feeder_overloads(self):
        load, _truth, capacity = load_feeder_loads()  # la vérité terrain n'est pas utilisée ici

        detected = created = 0
        for (feeder_id, ts), total in sorted(load.items()):
            if total / capacity[feeder_id] <= OVERLOAD_THRESHOLD:
                continue
            detected += 1
            _event, was_created = Event.objects.update_or_create(
                feeder_id=feeder_id,
                reading_timestamp=ts,
                anomaly_type=Event.AnomalyType.FEEDER_OVERLOAD,
                defaults={
                    "severity": Event.Severity.CRITICAL,
                    "isolation_forest_score": None,  # règle de seuil : pas de score ML
                    "model_version": "rule-overload-v1",
                },
            )
            created += was_created
        self.stdout.write(self.style.SUCCESS(
            f"Surcharges feeder : {detected} détectée(s), {created} nouvelle(s)."
        ))

    # ------------------------------------------------------------------ IsolationForest
    def _detect_node_anomalies(self):
        found = TunisianTelemetryAnomalyEngine().detect_node_anomalies_from_db()

        created = 0
        by_type, by_severity = {}, {}
        for item in found:
            anomaly_type = getattr(Event.AnomalyType, item["anomaly_type"])
            severity = getattr(Event.Severity, item["severity"])
            # Anomalie rattachée au nœud (le feeder reste réservé aux surcharges de niveau feeder)
            _event, was_created = Event.objects.update_or_create(
                node_id=item["node_id"],
                reading_timestamp=item["timestamp"],
                anomaly_type=anomaly_type,
                defaults={
                    "severity": severity,
                    "isolation_forest_score": item["score"],
                    "model_version": ML_MODEL_VERSION,
                },
            )
            created += was_created
            by_type[item["anomaly_type"]] = by_type.get(item["anomaly_type"], 0) + 1
            by_severity[item["severity"]] = by_severity.get(item["severity"], 0) + 1

        self.stdout.write(self.style.SUCCESS(
            f"Anomalies de nœud (IsolationForest) : {len(found)} détectée(s), {created} nouvelle(s)."
        ))
        self.stdout.write(f"  par type     : {by_type}")
        self.stdout.write(f"  par sévérité : {by_severity}")