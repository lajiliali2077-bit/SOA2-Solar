"""
Agent LangGraph du Rôle 4 : point d'entrée `run_agent`.

STUB (incrément 2) : respecte le contrat `run_agent(anomaly_id) -> int` pour débloquer
agent_trigger.py (Ali) et le serveur gRPC. Il crée l'exécution liée à l'anomalie
(statut RUNNING), puis la termine (COMPLETED) sans rien décider. La vraie version
(graphe LangGraph : prévision -> optimisation -> vérification -> preuve ZK) remplacera
le corps de `run_agent` sans changer sa signature.

Important : l'exécution est liée à l'anomalie (champ `anomaly`). Sans ce lien,
agent_trigger.py relancerait l'agent en boucle sur le même incident.
"""
import uuid

IS_STUB = True


def run_agent(anomaly_id: int) -> int:
    """Lance l'agent sur une anomalie et renvoie l'id de l'AgentLoopExecution."""
    # Imports tardifs : Django doit être prêt (même convention que pump_optimizer.py).
    from tunisovereign_core.models import AgentLoopExecution, AnomalyAndForecastEvent

    if not AnomalyAndForecastEvent.objects.filter(pk=anomaly_id).exists():
        raise ValueError(f"Anomalie introuvable : {anomaly_id}")

    execution = AgentLoopExecution.objects.create(
        thread_id=f"anomaly-{anomaly_id}-{uuid.uuid4().hex[:8]}",   # <= 64 caractères
        trigger_source="agent_trigger",
        anomaly_id=anomaly_id,
        status="RUNNING",
    )

    # STUB : aucune décision réelle pour l'instant.
    execution.status = "COMPLETED"
    execution.final_recommendation = "[STUB] Agent non implémenté : aucune action décidée."
    execution.save(update_fields=["status", "final_recommendation"])
    return execution.id