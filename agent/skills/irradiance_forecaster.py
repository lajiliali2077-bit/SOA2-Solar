"""
IrradianceAndLoadForecasterSkill : prévision de charge et de production d'un feeder.

STUB (incrément 3) : renvoie des données plausibles et déterministes, SANS lire la base,
pour que les Rôles 2 (serveur MCP) et 4 (agent) puissent intégrer la signature du contrat.
La vraie prévision (profil horaire moyen des jours précédents + ajustement) la remplacera
sans changer la signature ni les clés du dictionnaire.

Contrat d'interface :
    forecast_peak_load(feeder_id, horizon_hours=24) -> {
        "feeder_id", "horizon_hours",
        "hourly": [{"hour": ISO UTC, "load_kw", "generation_kw"}],
        "peak_kw", "peak_pct", "forecasted_deficit_24h_kwh"
    }

Sens des valeurs :
    load_kw                      charge NETTE du feeder (somme des GRID_NET_KW, positif = import)
    generation_kw                production solaire du feeder (somme des GENERATION_KW), informatif
    peak_kw                      maximum de load_kw sur l'horizon
    peak_pct                     peak_kw / capacity_kw * 100, à comparer au seuil de 92 %
    forecasted_deficit_24h_kwh   énergie (kWh) de charge nette au-dessus de 92 % de capacity_kw
"""
import math
from datetime import datetime, timedelta, timezone

IS_STUB = True
STUB_CAPACITY_KW = 100.0  # capacité supposée par le stub (la vraie version lira Feeder.capacity_kw)
OVERLOAD_THRESHOLD_PCT = 92.0


def _solar_generation_kw(hour_utc: int) -> float:
    """Courbe solaire en cloche entre 05h et 17h UTC, maximum 60 kW vers 11h UTC."""
    if 5 <= hour_utc <= 17:
        return 60.0 * math.sin(math.pi * (hour_utc - 5) / 12)
    return 0.0


def _consumption_kw(hour_utc: int) -> float:
    """Consommation : base de 38 kW plus un pic de soirée de 58 kW centré sur 18h UTC."""
    evening_peak = 58.0 * math.exp(-(((hour_utc - 18) / 2.0) ** 2))
    return 38.0 + evening_peak


def forecast_peak_load(feeder_id: int, horizon_hours: int = 24) -> dict:
    if not 1 <= horizon_hours <= 168:
        raise ValueError("horizon_hours doit être compris entre 1 et 168")

    start = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    hourly = []
    for i in range(horizon_hours):
        hour = start + timedelta(hours=i)
        generation = _solar_generation_kw(hour.hour)
        load = _consumption_kw(hour.hour) - generation
        hourly.append(
            {
                "hour": hour.isoformat(),
                "load_kw": round(load, 2),
                "generation_kw": round(generation, 2),
            }
        )

    peak_kw = max(point["load_kw"] for point in hourly)
    limit_kw = STUB_CAPACITY_KW * OVERLOAD_THRESHOLD_PCT / 100.0
    deficit_kwh = sum(max(0.0, point["load_kw"] - limit_kw) for point in hourly)  # 1 point = 1 h

    return {
        "feeder_id": feeder_id,
        "horizon_hours": horizon_hours,
        "hourly": hourly,
        "peak_kw": peak_kw,
        "peak_pct": round(peak_kw / STUB_CAPACITY_KW * 100.0, 1),
        "forecasted_deficit_24h_kwh": round(deficit_kwh, 2),
    }