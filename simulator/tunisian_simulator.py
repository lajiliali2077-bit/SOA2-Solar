"""
Simulateur de télémétrie SolarSouk-STEG (Track 7).

Lit les nœuds en base, simule pour chacun production solaire, batterie, pompe, tension
et puissance réseau par pas de 15 minutes, injecte 5 anomalies étiquetées
(is_injected_anomaly), puis envoie le tout au serveur gRPC.

Depuis la racine du dépôt :
    python simulator/tunisian_simulator.py --dry-run
"""
import argparse
import math
import os
import random
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import django
import grpc

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT / "grpc_service"))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

import tunisovereign_pb2 as pb2  # noqa: E402
import tunisovereign_pb2_grpc as pb2_grpc  # noqa: E402
from tunisovereign_core.models import ResourceNodePlot, TelemetryReading  # noqa: E402

LOCAL_TZ = timezone(timedelta(hours=1))  # Tunisie : UTC+1 toute l'année (stockage en UTC)
STEP_H = 0.25                            # un pas = 15 minutes
BASE_LOAD_PER_KWP = 0.20                 # charge de base (kW par kWp installé)
EVENING_FACTOR = 1.4                     # charge de base x1,4 entre 18h et 22h
PUMP_START, PUMP_END = 10, 15            # fenêtre solaire des pompes (heure locale)
SOC_MIN_PCT = 10.0                       # la batterie ne descend pas sous 10 %

# Une anomalie par type du contrat (docs/models.md). Heures locales.
ANOMALIES = [
    {"kind": "FEEDER_OVERLOAD", "feeder": "Feeder-TOZ-01", "start": 19.0, "end": 20.5},
    {"kind": "VOLTAGE_OUT_OF_RANGE", "node": "KEB-001", "start": 13.0, "end": 13.5},
    {"kind": "INVERTER_FAILURE", "node": "SFX-002", "start": 11.0, "end": 12.0},
    {"kind": "PUMP_MISALIGNED", "node": "TAT-001", "start": 21.0, "end": 22.0},
    {"kind": "SOC_INCONSISTENT", "node": "SFX-001", "start": 14.0, "end": 15.0},
]


def irradiance(hour):
    """Courbe solaire en cloche entre 6h et 18h (0 la nuit, 1 à midi)."""
    return math.sin(math.pi * (hour - 6) / 12) if 6 <= hour <= 18 else 0.0


def active_kinds(node, hour):
    kinds = set()
    for a in ANOMALIES:
        if a["start"] <= hour < a["end"] and (
            a.get("node") == node.node_code or a.get("feeder") == node.feeder.name
        ):
            kinds.add(a["kind"])
    return kinds


def simulate(nodes, day_start, rng, soc):
    """Mesures d'une journée : tuples (node_code, governorate, ts_utc, metric, value, injected)."""
    for i in range(int(24 / STEP_H)):
        hour = i * STEP_H
        ts = (day_start + timedelta(hours=hour)).astimezone(timezone.utc)
        for n in nodes:
            kinds = active_kinds(n, hour)
            flagged = set()  # métriques réellement altérées par une anomalie

            gen = n.installed_kwp * 0.85 * irradiance(hour) * rng.uniform(0.93, 1.0)
            evening = EVENING_FACTOR if 18 <= hour < 22 else 1.0
            base = n.installed_kwp * BASE_LOAD_PER_KWP * evening * rng.uniform(0.97, 1.03)
            pump = 0.0
            if n.has_pump and PUMP_START <= hour < PUMP_END:
                pump = n.pump_rated_kw * rng.uniform(0.95, 1.0)
            battery_on = True

            if "FEEDER_OVERLOAD" in kinds:  # démarrage simultané des pompes, batteries indisponibles
                battery_on = False
                flagged.add("GRID_NET_KW")
                if n.has_pump:
                    pump = n.pump_rated_kw * rng.uniform(0.98, 1.0)
                    flagged.add("PUMP_LOAD_KW")
            if "PUMP_MISALIGNED" in kinds and n.has_pump:  # pompe hors fenêtre solaire
                pump = n.pump_rated_kw * rng.uniform(0.95, 1.0)
                flagged.add("PUMP_LOAD_KW")
            if "INVERTER_FAILURE" in kinds:  # production nulle en plein soleil
                gen = 0.0
                flagged.add("GENERATION_KW")

            net = base + pump - gen  # > 0 : déficit à couvrir (import)
            cap = n.battery_capacity_kwh
            if cap > 0 and battery_on:
                energy = soc[n.node_code]
                if net > 0:  # la batterie se décharge
                    power = min(net, max(0.0, energy - cap * SOC_MIN_PCT / 100) / STEP_H)
                    net -= power
                    energy -= power * STEP_H
                else:  # la batterie se charge avec le surplus
                    power = min(-net, (cap - energy) / STEP_H)
                    net += power
                    energy += power * STEP_H
                soc[n.node_code] = energy

            volt = 220.0 + rng.gauss(0, 1.5) - 0.05 * net
            if "VOLTAGE_OUT_OF_RANGE" in kinds:
                volt = rng.uniform(240.0, 250.0)
                flagged.add("VOLTAGE_V")

            metrics = {
                "GENERATION_KW": gen,
                "PUMP_LOAD_KW": pump,
                "VOLTAGE_V": volt,
                "GRID_NET_KW": net,
            }
            if cap > 0:
                soc_pct = 100.0 * soc[n.node_code] / cap
                if "SOC_INCONSISTENT" in kinds:
                    soc_pct = rng.uniform(1.0, 4.0)
                    flagged.add("BATTERY_SOC")
                metrics["BATTERY_SOC"] = soc_pct

            for metric, value in metrics.items():
                yield (n.node_code, n.feeder.governorate, ts, metric, round(value, 3), metric in flagged)


def packets(rows):
    for code, gov, ts, metric, value, injected in rows:
        yield pb2.TelemetryPacket(
            node_code=code,
            governorate=gov,
            metric_type=metric,
            value=value,
            iso_timestamp=ts.isoformat(),
            is_injected_anomaly=injected,
        )


def report_feeders(nodes, rows):
    """Charge d'un feeder = somme des GRID_NET_KW de ses nœuds (voir docs/models.md)."""
    feeder_of = {n.node_code: n.feeder for n in nodes}
    load, flag = {}, {}
    for code, _gov, ts, metric, value, injected in rows:
        if metric != "GRID_NET_KW":
            continue
        key = (feeder_of[code].name, ts)
        load[key] = load.get(key, 0.0) + value
        flag[key] = flag.get(key, False) or injected

    print("Charge des feeders (en % de capacity_kw) :")
    for f in sorted({n.feeder for n in nodes}, key=lambda f: f.name):
        normal = [v for (name, _), v in load.items() if name == f.name and not flag[(name, _)]]
        anom = [v for (name, _), v in load.items() if name == f.name and flag[(name, _)]]
        pn = 100 * max(normal) / f.capacity_kw
        pa = f"{100 * max(anom) / f.capacity_kw:5.1f} %" if anom else "   —"
        print(f"  {f.name:<14} cap {f.capacity_kw:>5.1f} kW | pic normal {pn:5.1f} % | pic anomalie {pa}")


def main():
    p = argparse.ArgumentParser(description="Simulateur de télémétrie SolarSouk-STEG")
    p.add_argument("--days", type=int, default=1, help="nombre de jours simulés (se terminant hier)")
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--dry-run", action="store_true", help="simule et affiche les stats, sans envoyer")
    p.add_argument("--clear", action="store_true", help="supprime toute la télémétrie avant l'envoi")
    p.add_argument("--target", default="localhost:50051", help="adresse du serveur gRPC")
    args = p.parse_args()

    nodes = list(ResourceNodePlot.objects.select_related("feeder").order_by("node_code"))
    if not nodes:
        sys.exit("Aucun nœud en base : lancez d'abord python manage.py seed_solarsouk")

    rng = random.Random(args.seed)
    soc = {n.node_code: 0.5 * n.battery_capacity_kwh for n in nodes}  # batteries à 50 % au départ
    today = datetime.now(LOCAL_TZ).replace(hour=0, minute=0, second=0, microsecond=0)

    rows = []
    for d in range(args.days, 0, -1):
        rows.extend(simulate(nodes, today - timedelta(days=d), rng, soc))

    total = len(rows)
    injected = sum(1 for r in rows if r[5])
    print(f"{total} mesures simulées sur {args.days} jour(s), dont {injected} étiquetées anomalie "
          f"({100 * injected / total:.2f} %)")
    report_feeders(nodes, rows)

    if args.dry_run:
        print("Mode --dry-run : rien n'a été envoyé.")
        return
    if args.clear:
        print("Suppression de la télémétrie existante :", TelemetryReading.objects.all().delete())
    with grpc.insecure_channel(args.target) as channel:
        ack = pb2_grpc.TelemetryIngestServiceStub(channel).StreamTelemetry(packets(rows))
    print(f"Envoyé : accepted_count = {ack.accepted_count} / {total}")


if __name__ == "__main__":
    main()