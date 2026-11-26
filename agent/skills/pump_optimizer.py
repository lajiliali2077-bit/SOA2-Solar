"""
PumpPeakShavingOptimizerSkill : optimisation du planning des pompes (Rôle 4).

STUB (incrément 1) : respecte la signature du contrat d'interface et renvoie des
données plausibles, pour débloquer le serveur MCP (Rôle 2) et l'agent. Il n'optimise
rien : il place simplement chaque pompe du feeder dans la fenêtre solaire, en
décalant les démarrages de 30 minutes. La vraie version (algorithme + tests)
remplacera `_stub_plan` sans changer la signature de `optimize_pump_schedule`.

Contrat (voir CONTEXTE_COMMUN) :
    optimize_pump_schedule(feeder_id: int, forecast: dict) -> dict
    {"feasible": bool, "peak_pct_before": float, "peak_pct_after": float,
     "schedules": [{"node_code": str, "start": ISO UTC, "end": ISO UTC, "planned_kw": float}]}

Convention : horodatages en UTC. La Tunisie est à UTC+1 : la fenêtre solaire
10h-15h (heure locale) correspond à 09h-14h UTC.
"""
from datetime import datetime, time, timedelta, timezone

IS_STUB = True              # passer à False avec la vraie version (même convention que irradiance_forecaster.py)
PEAK_LIMIT_PCT = 92.0        # seuil de surcharge du feeder (énoncé, Track 7)
SOLAR_START_UTC_HOUR = 9     # 10h Tunis = 09h UTC
PUMP_RUN_HOURS = 2           # durée d'un arrosage dans le stub
STAGGER_MINUTES = 30         # décalage entre deux démarrages de pompes
MAX_STAGGER_SLOTS = 6        # reste dans la fenêtre : 09h + 5 x 30 min + 2 h <= 14h


def optimize_pump_schedule(feeder_id: int, forecast: dict) -> dict:
    """Point d'entrée du contrat : lit les pompes du feeder en base, puis planifie."""
    return _stub_plan(_pump_nodes(feeder_id), forecast)


def _pump_nodes(feeder_id: int) -> list:
    """[(node_code, pump_rated_kw)] des nœuds équipés d'une pompe sur ce feeder."""
    from tunisovereign_core.models import ResourceNodePlot  # import tardif : Django doit être prêt

    return list(
        ResourceNodePlot.objects.filter(feeder_id=feeder_id, has_pump=True)
        .order_by("node_code")
        .values_list("node_code", "pump_rated_kw")
    )


def _first_window_start(forecast: dict, now: datetime = None) -> datetime:
    """Prochain début de fenêtre solaire (09h UTC) après le début de la prévision."""
    hourly = forecast.get("hourly") or []
    if hourly:
        base = datetime.fromisoformat(str(hourly[0]["hour"]).replace("Z", "+00:00"))
    else:
        base = now or datetime.now(timezone.utc)
    if base.tzinfo is None:
        base = base.replace(tzinfo=timezone.utc)
    start = datetime.combine(base.date(), time(SOLAR_START_UTC_HOUR), tzinfo=timezone.utc)
    return start if base < start else start + timedelta(days=1)


def _stub_plan(pumps: list, forecast: dict, now: datetime = None) -> dict:
    before = float(forecast.get("peak_pct", 0.0))
    # Stub : on suppose que décaler les pompes ramène la pointe sous le seuil.
    after = min(before, PEAK_LIMIT_PCT - 4.0) if before > PEAK_LIMIT_PCT else before

    window_start = _first_window_start(forecast, now)
    schedules = []
    for i, (node_code, pump_kw) in enumerate(pumps):
        start = window_start + timedelta(minutes=STAGGER_MINUTES * (i % MAX_STAGGER_SLOTS))
        schedules.append({
            "node_code": node_code,
            "start": start.isoformat(),
            "end": (start + timedelta(hours=PUMP_RUN_HOURS)).isoformat(),
            "planned_kw": float(pump_kw),
        })

    return {
        "feasible": after <= PEAK_LIMIT_PCT,
        "peak_pct_before": round(before, 1),
        "peak_pct_after": round(after, 1),
        "schedules": schedules,
        "stub": True,   # même clé que les stubs du serveur MCP ; à retirer avec la vraie version
    }