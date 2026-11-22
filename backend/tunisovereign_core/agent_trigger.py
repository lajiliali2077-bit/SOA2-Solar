"""
Déclenchement automatique de l'agent (run_agent, Rôle 4) sur les anomalies CRITICAL.

Contrat : run_agent(anomaly_id) -> id de l'AgentLoopExecution (docs/contrats_interfaces.md).

Règles :
  - un INCIDENT = les anomalies CRITICAL d'un même nœud (ou feeder) le même jour.
    L'agent n'est lancé qu'une fois par incident (sur sa première anomalie), pas 62 fois ;
  - un incident déjà traité (une AgentLoopExecution existe) n'est jamais relancé : idempotent ;
  - les incidents les plus récents passent en premier, dans la limite de max_runs ;
  - si l'agent n'existe pas encore, rien ne plante : un message l'indique.
"""
import sys
from pathlib import Path

from tunisovereign_core.models import AgentLoopExecution, AnomalyAndForecastEvent

Event = AnomalyAndForecastEvent
ROOT = Path(__file__).resolve().parents[2]  # racine du dépôt (contient le dossier "agent")
DEFAULT_MAX_RUNS = 5


def pending_critical_incidents():
    """Première anomalie CRITICAL de chaque incident non encore traité, du plus récent au plus ancien."""
    handled_ids = set(
        AgentLoopExecution.objects.filter(anomaly__isnull=False).values_list("anomaly_id", flat=True)
    )
    events = (
        Event.objects.filter(severity=Event.Severity.CRITICAL, reading_timestamp__isnull=False)
        .order_by("reading_timestamp", "id")
    )
    incidents = {}
    for event in events:
        entity = ("node", event.node_id) if event.node_id else ("feeder", event.feeder_id)
        key = entity + (event.reading_timestamp.date(),)
        incident = incidents.setdefault(key, {"first": event, "handled": False})
        if event.id in handled_ids:
            incident["handled"] = True
    pending = [i["first"] for i in incidents.values() if not i["handled"]]
    pending.sort(key=lambda e: (e.reading_timestamp, e.id), reverse=True)
    return pending


def trigger_agent_on_critical(max_runs=DEFAULT_MAX_RUNS, log=print):
    """Lance run_agent sur les incidents CRITICAL en attente. Retourne le nombre d'exécutions lancées."""
    incidents = pending_critical_incidents()
    if not incidents:
        log("Agent : aucun incident CRITICAL en attente.")
        return 0

    if str(ROOT) not in sys.path:
        sys.path.append(str(ROOT))
    try:
        from agent.langgraph_agent import run_agent
    except ImportError as exc:
        log(
            f"Agent non connecté (Rôle 4) : {len(incidents)} incident(s) CRITICAL en attente. "
            f"Ils seront traités quand l'agent existera. (détail : {exc})"
        )
        return 0

    started = 0
    for event in incidents[:max_runs]:
        try:
            execution_id = run_agent(event.id)
        except Exception as exc:  # un agent en panne ne doit pas arrêter la détection
            log(f"  Anomalie {event.id} : l'agent a échoué ({exc})")
            continue
        started += 1
        log(f"  Anomalie {event.id} ({event.anomaly_type}, {event.reading_timestamp:%Y-%m-%d %H:%M} UTC) "
            f"-> exécution de l'agent {execution_id}")

    remaining = len(incidents) - started
    log(f"Agent : {started} exécution(s) lancée(s), {remaining} incident(s) restant(s) "
        f"(limite {max_runs} par lancement).")
    return started