"""
IrradianceAndLoadForecasterSkill : prévision de charge et de production d'un feeder.

Version réelle (remplace le stub) : profil journalier MÉDIAN de l'historique, au pas de 15 minutes,
projeté sur l'horizon demandé. Même signature et mêmes clés que le contrat d'interface.

    forecast_peak_load(feeder_id, horizon_hours=24) -> {
        "feeder_id", "horizon_hours",
        "hourly": [{"hour": ISO UTC, "load_kw", "generation_kw"}],
        "peak_kw", "peak_pct", "forecasted_deficit_24h_kwh"
    }

Sens des valeurs :
    load_kw                      pic de charge NETTE de l'heure (max des 4 pas de 15 min ; charge nette =
                                 somme des GRID_NET_KW du feeder, positif = import)
    generation_kw                production solaire moyenne de l'heure (somme des GENERATION_KW)
    peak_kw                      maximum de load_kw sur l'horizon
    peak_pct                     peak_kw / Feeder.capacity_kw * 100, à comparer au seuil de 92 %
    forecasted_deficit_24h_kwh   énergie (kWh) de charge nette au-dessus de 92 % de capacity_kw,
                                 calculée sur les pas de 15 minutes (un pas = 0,25 h)

Méthode : pour chaque pas de 15 min de la journée (96 créneaux, en UTC), médiane de la charge nette
des HISTORY_DAYS derniers jours de données. La médiane résiste aux valeurs ponctuelles aberrantes.
L'historique se termine à la dernière mesure en base (et non à « maintenant »), pour fonctionner
aussi avec des données plus anciennes. Un créneau n'est retenu que si tous les nœuds du feeder
ont mesuré à cet instant. is_injected_anomaly n'est JAMAIS lu.
"""
import os
import statistics
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

IS_STUB = False
OVERLOAD_THRESHOLD_PCT = 92.0
HISTORY_DAYS = 14
SLOTS_PER_DAY = 96  # pas de 15 minutes
SLOT_HOURS = 0.25


def _ensure_django():
    """Permet d'appeler la skill depuis l'agent ou le serveur MCP (hors du dossier backend)."""
    import django
    from django.apps import apps

    if apps.ready:
        return
    backend = Path(__file__).resolve().parents[2] / "backend"
    if str(backend) not in sys.path:
        sys.path.insert(0, str(backend))
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    django.setup()


def _load_history(feeder_id: int):
    """Retourne (capacité kW, charge nette par instant, production par instant) pour un feeder."""
    _ensure_django()
    from tunisovereign_core.models import Feeder, ResourceNodePlot, TelemetryReading

    try:
        feeder = Feeder.objects.get(pk=feeder_id)
    except Feeder.DoesNotExist:
        raise ValueError(f"Feeder {feeder_id} introuvable") from None
    n_nodes = ResourceNodePlot.objects.filter(feeder_id=feeder_id).count()
    if n_nodes == 0:
        raise ValueError(f"Le feeder {feeder_id} n'a aucun nœud rattaché")

    readings = TelemetryReading.objects.filter(
        node__feeder_id=feeder_id, metric_type__in=("GRID_NET_KW", "GENERATION_KW")
    )
    latest = readings.order_by("-timestamp").values_list("timestamp", flat=True).first()
    if latest is None:
        raise ValueError(f"Aucune télémétrie pour le feeder {feeder_id} : lancez le simulateur")
    since = latest - timedelta(days=HISTORY_DAYS)

    sums = {"GRID_NET_KW": {}, "GENERATION_KW": {}}
    rows = readings.filter(timestamp__gt=since).values_list("timestamp", "metric_type", "value")
    for ts, metric, value in rows.iterator(chunk_size=5000):
        acc = sums[metric].setdefault(ts, [0.0, 0])
        acc[0] += value
        acc[1] += 1

    def complete(metric):  # instants où tous les nœuds du feeder ont mesuré
        return {ts: total for ts, (total, count) in sums[metric].items() if count == n_nodes}

    return feeder.capacity_kw, complete("GRID_NET_KW"), complete("GENERATION_KW")


def _median_profile(series: dict) -> dict:
    """Médiane par créneau de 15 minutes (0 à 95, en UTC) d'une série {horodatage: valeur}."""
    by_slot = {}
    for ts, value in series.items():
        ts = ts.astimezone(timezone.utc)
        by_slot.setdefault(ts.hour * 4 + ts.minute // 15, []).append(value)
    return {slot: statistics.median(values) for slot, values in by_slot.items()}


def _forecast_from_history(feeder_id, capacity_kw, horizon_hours, start, net, gen) -> dict:
    net_profile = _median_profile(net)
    gen_profile = _median_profile(gen)
    if len(net_profile) < SLOTS_PER_DAY:
        raise ValueError(
            f"Historique incomplet : {len(net_profile)} créneaux de 15 min sur {SLOTS_PER_DAY}"
        )

    limit_kw = capacity_kw * OVERLOAD_THRESHOLD_PCT / 100.0
    hourly, deficit_kwh = [], 0.0
    for i in range(horizon_hours):
        hour = start + timedelta(hours=i)
        slots = [hour.hour * 4 + q for q in range(4)]
        loads = [net_profile[s] for s in slots]
        gens = [gen_profile.get(s, 0.0) for s in slots]
        deficit_kwh += sum(max(0.0, load - limit_kw) for load in loads) * SLOT_HOURS
        hourly.append(
            {
                "hour": hour.isoformat(),
                "load_kw": round(max(loads), 2),
                "generation_kw": round(sum(gens) / len(gens), 2),
            }
        )

    peak_kw = max(point["load_kw"] for point in hourly)
    return {
        "feeder_id": feeder_id,
        "horizon_hours": horizon_hours,
        "hourly": hourly,
        "peak_kw": peak_kw,
        "peak_pct": round(peak_kw / capacity_kw * 100.0, 1),
        "forecasted_deficit_24h_kwh": round(deficit_kwh, 2),
    }


def forecast_peak_load(feeder_id: int, horizon_hours: int = 24) -> dict:
    if not 1 <= horizon_hours <= 168:
        raise ValueError("horizon_hours doit être compris entre 1 et 168")
    capacity_kw, net, gen = _load_history(feeder_id)
    start = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    return _forecast_from_history(feeder_id, capacity_kw, horizon_hours, start, net, gen)