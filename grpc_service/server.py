"""
Serveur gRPC d'ingestion de télémétrie (SolarSouk-STEG, Track 7).
Implémente TelemetryIngestService (protos/tunisovereign.proto) et écrit dans TelemetryReading.
Lancement depuis la racine du dépôt : python grpc_service/server.py
"""
import os
import sys
import time
from concurrent import futures
from datetime import datetime, timezone
from pathlib import Path

import django
import grpc

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "backend"))  # pour importer config et tunisovereign_core
sys.path.insert(0, str(HERE))                     # pour importer les stubs tunisovereign_pb2*
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from django.db import close_old_connections  # noqa: E402

import tunisovereign_pb2 as pb2  # noqa: E402
import tunisovereign_pb2_grpc as pb2_grpc  # noqa: E402
from tunisovereign_core.models import ResourceNodePlot, TelemetryReading  # noqa: E402

BATCH_SIZE = 200
VALID_METRICS = set(TelemetryReading.MetricType.values)


def parse_timestamp(raw: str) -> datetime:
    ts = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return ts


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
        # La détection d'anomalie (ML) et l'agent seront branchés plus tard.
        return pb2.IngestAck(accepted_count=accepted, anomaly_triggered=False, agent_thread_id="")

    def TriggerUrgentAudit(self, request, context):
        # Provisoire : l'agent LangGraph n'est pas encore adapté au Track 7.
        return pb2.AuditResponse(status="AGENT_NOT_CONNECTED", tx_hash="")


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