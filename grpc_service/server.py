"""
Serveur gRPC d'ingestion de télémétrie (SolarSouk-STEG, Track 7).
Implémente TelemetryIngestService (protos/tunisovereign.proto) :
  - StreamTelemetry     : écrit les paquets dans TelemetryReading ;
  - TriggerUrgentAudit  : lance l'agent (run_agent, Rôle 4) sur la dernière anomalie CRITICAL du nœud.
Lancement depuis la racine du dépôt : python grpc_service/server.py
"""
import os
import sys
import time
import traceback
from concurrent import futures
from datetime import datetime, timezone
from pathlib import Path

import django
import grpc

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT / "backend"))  # pour importer config et tunisovereign_core
sys.path.insert(0, str(HERE))              # pour importer les stubs tunisovereign_pb2*
sys.path.append(str(ROOT))                 # pour importer le package "agent" (Rôle 4)
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from django.db import close_old_connections  # noqa: E402
from django.db.models import F, Q  # noqa: E402

import tunisovereign_pb2 as pb2  # noqa: E402
import tunisovereign_pb2_grpc as pb2_grpc  # noqa: E402
from tunisovereign_core.models import (  # noqa: E402
    AgentLoopExecution,
    AnomalyAndForecastEvent,
    OnChainZKReceipt,
    ResourceNodePlot,
    TelemetryReading,
)

BATCH_SIZE = 200
VALID_METRICS = set(TelemetryReading.MetricType.values)


def parse_timestamp(raw: str) -> datetime:
    ts = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return ts


def launch_agent(anomaly_id: int):
    """Appelle run_agent(anomaly_id) du Rôle 4 (contrat : docs/contrats_interfaces.md, section 2.5).

    Retourne l'id de l'AgentLoopExecution, ou None tant que l'agent n'est pas disponible.
    """
    try:
        from agent.langgraph_agent import run_agent
    except ImportError:
        return None
    return run_agent(anomaly_id)


class TelemetryIngestServicer(pb2_grpc.TelemetryIngestServiceServicer):
    def StreamTelemetry(self, request_iterator, context):
        nodes = dict(ResourceNodePlot.objects.values_list("node_code", "id"))
        batch, accepted, rejected = [], 0, 0
        try:
            for packet in request_iterator:
                node_id = nodes.get(packet.node_code)
                if node_id is None or packet.metric_type not in VALID_METRICS:
                    rejected += 1
                    continue
                try:
                    ts = parse_timestamp(packet.iso_timestamp)
                except ValueError:
                    rejected += 1
                    continue
                batch.append(
                    TelemetryReading(
                        node_id=node_id,
                        timestamp=ts,
                        metric_type=packet.metric_type,
                        value=packet.value,
                        ingestion_protocol=TelemetryReading.Protocol.GRPC,
                        is_injected_anomaly=packet.is_injected_anomaly,
                    )
                )
                accepted += 1
                if len(batch) >= BATCH_SIZE:
                    TelemetryReading.objects.bulk_create(batch)
                    batch = []
            if batch:
                TelemetryReading.objects.bulk_create(batch)
        finally:
            close_old_connections()

        if rejected:
            print(f"[gRPC] {rejected} paquet(s) rejeté(s) (nœud, métrique ou horodatage invalide)")
        # La détection en temps réel sur le flux sera branchée dans un incrément suivant.
        return pb2.IngestAck(accepted_count=accepted, anomaly_triggered=False, agent_thread_id="")

    def TriggerUrgentAudit(self, request, context):
        try:
            return self._urgent_audit(request)
        except Exception:  # un agent en panne ne doit pas faire tomber le serveur
            traceback.print_exc()
            return pb2.AuditResponse(status="AGENT_ERROR", tx_hash="")
        finally:
            close_old_connections()

    def _urgent_audit(self, request):
        node = ResourceNodePlot.objects.select_related("feeder").filter(
            node_code=request.node_code
        ).first()
        if node is None:
            return pb2.AuditResponse(status="UNKNOWN_NODE", tx_hash="")

        anomaly = (
            AnomalyAndForecastEvent.objects.filter(
                Q(node=node) | Q(feeder=node.feeder),
                severity=AnomalyAndForecastEvent.Severity.CRITICAL,
            )
            .order_by(F("reading_timestamp").desc(nulls_last=True), "-id")
            .first()
        )
        if anomaly is None:
            return pb2.AuditResponse(status="NO_CRITICAL_ANOMALY", tx_hash="")

        execution_id = launch_agent(anomaly.id)
        if execution_id is None:
            return pb2.AuditResponse(status="AGENT_NOT_CONNECTED", tx_hash="")

        status = AgentLoopExecution.objects.get(pk=execution_id).status
        tx_hash = (
            OnChainZKReceipt.objects.filter(agent_execution_id=execution_id)
            .values_list("tx_hash", flat=True)
            .first()
            or ""
        )
        return pb2.AuditResponse(status=status, tx_hash=tx_hash)


def serve(port: int = 50051):
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=8))
    pb2_grpc.add_TelemetryIngestServiceServicer_to_server(TelemetryIngestServicer(), server)
    server.add_insecure_port(f"[::]:{port}")
    server.start()
    print(f"[SolarSouk-STEG gRPC] En écoute sur le port {port}")
    try:
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        server.stop(0)


if __name__ == "__main__":
    serve()