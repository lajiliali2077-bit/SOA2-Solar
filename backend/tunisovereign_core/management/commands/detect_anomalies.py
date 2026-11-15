from django.core.management.base import BaseCommand

from tunisovereign_core.ml_anomaly import OVERLOAD_THRESHOLD, load_feeder_loads
from tunisovereign_core.models import AnomalyAndForecastEvent

Event = AnomalyAndForecastEvent


class Command(BaseCommand):
    help = "Détecte les surcharges de feeders et les enregistre comme événements (idempotent)."
    def add_arguments(self, parser):
        parser.add_argument(
            "--clear", action="store_true",
            help="supprime tous les événements avant de détecter",
        )
    def handle(self, *args, **options):
        if options["clear"]:
            print("Événements supprimés :", Event.objects.all().delete())
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
                    "isolation_forest_score": 0.0,  # règle de seuil : pas de score ML
                    "model_version": "rule-overload-v1",
                },
            )
            created += was_created

        self.stdout.write(self.style.SUCCESS(
            f"Surcharges feeder : {detected} détectée(s), {created} nouvelle(s), "
            f"{Event.objects.count()} événement(s) en base."
        ))