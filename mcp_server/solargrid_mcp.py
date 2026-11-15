"""
Serveur MCP SolarGridMCP (Rôle 2).

C'est la "boîte à outils" que l'agent IA (Rôle 4) ouvre pour travailler.
Chaque outil est une fonction que l'agent peut appeler par son nom.

Lancement (depuis la racine du projet, .venv activé) :
    python mcp_server\\solargrid_mcp.py
Le serveur parle sur stdin/stdout (transport "stdio") : en général c'est le
client MCP (l'agent) qui le lance lui-même. Voir client_example.py.

RÈGLE D'OR du transport stdio : ne JAMAIS faire print() dans ce fichier.
stdout est le canal de communication ; un print casserait le protocole.
Les messages de suivi passent par logging, qui écrit sur stderr.

Outils : get_feeder_status, get_cooperative_quota, forecast_peak_load,
optimize_pump_schedule, prove_green_origin, settle_on_chain.
Tant qu'un coéquipier n'a pas poussé sa fonction, l'outil utilise un STUB
(fausse réponse plausible, marquée "stub": True). Voir docs/mcp_tools.md.
"""
import hashlib
import importlib
import logging
import os
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

# --- Démarrer Django (pour lire la base) -----------------------------------
RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))  # pour importer agent.skills...
sys.path.insert(0, str(RACINE / "backend"))  # pour importer config et tunisovereign_core
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

import django  # noqa: E402

django.setup()

from mcp.server.mcpserver import MCPServer  # noqa: E402
from mcp.server.mcpserver.exceptions import ToolError  # noqa: E402

from tunisovereign_core.models import CooperativeUnit, Feeder, TelemetryReading  # noqa: E402

logging.basicConfig(stream=sys.stderr, level=logging.INFO, format="[SolarGridMCP] %(message)s")
log = logging.getLogger("solargrid")

OVERLOAD_PCT = 92.0  # seuil de surcharge d'un feeder (règle d'équipe)

mcp = MCPServer("SolarGridMCP")


# ---------------------------------------------------------------------------
# Brancher les fonctions des coéquipiers, avec un STUB de secours
# ---------------------------------------------------------------------------
def _skill(module, function, stub):
    """Renvoie la vraie fonction si le fichier du coéquipier existe, sinon le stub."""
    try:
        return getattr(importlib.import_module(module), function)
    except (ImportError, AttributeError):
        log.warning("%s.%s introuvable : STUB utilisé", module, function)
        return stub


def _stub_forecast(feeder_id, horizon_hours=24):
    feeder = Feeder.objects.get(pk=feeder_id)
    debut = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    horaire = []
    for h in range(horizon_hours):
        instant = debut + timedelta(hours=h)
        soleil = max(0.0, 1 - abs(instant.hour - 12) / 6)  # courbe en cloche autour de midi
        horaire.append(
            {
                "hour": instant.isoformat(),
                "load_kw": round(feeder.capacity_kw * (0.55 + 0.35 * (instant.hour >= 18)), 1),
                "generation_kw": round(feeder.capacity_kw * 0.4 * soleil, 1),
            }
        )
    pic = max(p["load_kw"] for p in horaire)
    return {
        "feeder_id": feeder_id,
        "horizon_hours": horizon_hours,
        "hourly": horaire,
        "peak_kw": pic,
        "peak_pct": round(100 * pic / feeder.capacity_kw, 1),
        "forecasted_deficit_24h_kwh": 0.0,
        "stub": True,
    }


def _stub_optimize(feeder_id, forecast):
    demain_10h = datetime.now(timezone.utc).replace(hour=10, minute=0, second=0, microsecond=0) + timedelta(days=1)
    pompes = Feeder.objects.get(pk=feeder_id).nodes.filter(has_pump=True).order_by("node_code")
    plannings = [
        {
            "node_code": n.node_code,
            "start": (demain_10h + timedelta(minutes=30 * i)).isoformat(),
            "end": (demain_10h + timedelta(minutes=30 * i, hours=2)).isoformat(),
            "planned_kw": n.pump_rated_kw,
        }
        for i, n in enumerate(pompes)
    ]
    avant = float(forecast.get("peak_pct", 0.0))
    return {"feasible": True, "peak_pct_before": avant, "peak_pct_after": min(avant, 85.0), "schedules": plannings, "stub": True}


def _stub_prove(node_code, period_start, period_end, green_kwh, quota_kwh):
    if green_kwh > quota_kwh:
        raise ToolError("green_kwh dépasse quota_kwh : preuve impossible")
    empreinte = hashlib.sha256(f"{node_code}|{period_start}|{period_end}|{green_kwh}".encode()).hexdigest()
    return {
        "commitment_hash": "0x" + empreinte,
        "public_inputs": {  # green_kwh reste privé : il n'apparaît pas ici
            "node_code": node_code,
            "period_start": period_start,
            "period_end": period_end,
            "quota_kwh": quota_kwh,
            "bound_ok": True,
        },
        "stub": True,
    }


def _stub_settle(commitment_hash, public_inputs):
    return {
        "tx_hash": "0x" + hashlib.sha256(f"tx|{commitment_hash}".encode()).hexdigest(),
        "block_number": 1,
        "network_name": "STUB-no-chain",
        "is_verified": True,
        "stub": True,
    }


# ---------------------------------------------------------------------------
# Les 6 outils
# ---------------------------------------------------------------------------
@mcp.tool()
def get_feeder_status(feeder_id: int) -> dict[str, Any]:
    """État d'un feeder : capacité, charge actuelle (somme des GRID_NET_KW de ses nœuds), % de charge et surcharge (> 92 %)."""
    feeder = Feeder.objects.filter(pk=feeder_id).first()
    if feeder is None:
        raise ToolError(f"Feeder {feeder_id} introuvable")
    nodes = list(feeder.nodes.all())
    charge_kw, a_la_date = 0.0, None
    for node in nodes:  # dernière mesure de chaque nœud
        derniere = (
            TelemetryReading.objects.filter(node=node, metric_type=TelemetryReading.MetricType.GRID_NET_KW)
            .order_by("-timestamp")
            .first()
        )
        if derniere:
            charge_kw += derniere.value
            a_la_date = derniere.timestamp if a_la_date is None else max(a_la_date, derniere.timestamp)
    charge_pct = round(100 * charge_kw / feeder.capacity_kw, 1)
    return {
        "feeder_id": feeder.pk,
        "name": feeder.name,
        "governorate": feeder.governorate,
        "capacity_kw": feeder.capacity_kw,
        "node_count": len(nodes),
        "load_kw": round(charge_kw, 1),
        "load_pct": charge_pct,
        "is_overloaded": charge_pct > OVERLOAD_PCT,
        "as_of": a_la_date.isoformat() if a_la_date else None,
    }


@mcp.tool()
def get_cooperative_quota(coop_id: str) -> dict[str, Any]:
    """Quota quotidien d'énergie réseau (kWh/jour) d'une coopérative, et la liste de ses nœuds. coop_id = identifiant UUID."""
    try:
        identifiant = uuid.UUID(coop_id)
    except ValueError:
        raise ToolError(f"coop_id doit être un UUID, reçu : {coop_id!r}") from None
    coop = CooperativeUnit.objects.filter(pk=identifiant).first()
    if coop is None:
        raise ToolError(f"Coopérative {coop_id} introuvable")
    return {
        "coop_id": str(coop.pk),
        "name": coop.name,
        "governorate": coop.governorate,
        "daily_quota_limit_kwh": coop.daily_quota_limit,
        "node_codes": list(coop.nodes.order_by("node_code").values_list("node_code", flat=True)),
    }


@mcp.tool()
def forecast_peak_load(feeder_id: int, horizon_hours: int = 24) -> dict[str, Any]:
    """Prévision horaire de charge et de production d'un feeder, pic attendu et déficit sur 24 h (fonction du Rôle 1)."""
    fonction = _skill("agent.skills.irradiance_forecaster", "forecast_peak_load", _stub_forecast)
    return fonction(feeder_id, horizon_hours)


@mcp.tool()
def optimize_pump_schedule(feeder_id: int, forecast: dict[str, Any]) -> dict[str, Any]:
    """Planning des pompes déplacé vers la fenêtre solaire 10h-15h pour garder le feeder sous 92 % (fonction du Rôle 4). 'forecast' = résultat de forecast_peak_load."""
    fonction = _skill("agent.skills.pump_optimizer", "optimize_pump_schedule", _stub_optimize)
    return fonction(feeder_id, forecast)


@mcp.tool()
def prove_green_origin(node_code: str, period_start: str, period_end: str, green_kwh: float, quota_kwh: float) -> dict[str, Any]:
    """Engagement (commitment) prouvant que green_kwh <= quota_kwh sans révéler green_kwh (fonction du Rôle 5)."""
    fonction = _skill("agent.skills.zk_origin_prover", "prove_green_origin", _stub_prove)
    return fonction(node_code, period_start, period_end, green_kwh, quota_kwh)


@mcp.tool()
def settle_on_chain(commitment_hash: str, public_inputs: dict[str, Any]) -> dict[str, Any]:
    """Enregistre le commitment sur la blockchain pour le règlement net-metering et le token carbone (fonction du Rôle 5)."""
    fonction = _skill("contracts.web3_zk_client", "settle_on_chain", _stub_settle)
    return fonction(commitment_hash, public_inputs)


if __name__ == "__main__":
    mcp.run(transport="stdio")