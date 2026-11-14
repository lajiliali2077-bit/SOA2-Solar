"""Client de test : envoie 7 paquets au serveur gRPC (6 valides, 1 avec un nœud inconnu)."""
import sys
from datetime import datetime, timezone
from pathlib import Path

import grpc

sys.path.insert(0, str(Path(__file__).resolve().parent))
import tunisovereign_pb2 as pb2  # noqa: E402
import tunisovereign_pb2_grpc as pb2_grpc  # noqa: E402


def make_packets():
    now = datetime.now(timezone.utc).isoformat()
    valid = [
        ("GENERATION_KW", 12.5, False),
        ("BATTERY_SOC", 80.0, False),
        ("PUMP_LOAD_KW", 0.0, False),
        ("VOLTAGE_V", 221.3, False),
        ("GRID_NET_KW", -4.2, False),
        ("VOLTAGE_V", 250.0, True),  # anomalie injectée (hors 220 V ± 6 %)
    ]
    for metric, value, injected in valid:
        yield pb2.TelemetryPacket(
            node_code="TOZ-001", governorate="TOZEUR", metric_type=metric,
            value=value, iso_timestamp=now, is_injected_anomaly=injected,
        )
    # Paquet invalide : ce nœud n'existe pas, le serveur doit le rejeter.
    yield pb2.TelemetryPacket(
        node_code="XXX-999", governorate="TOZEUR", metric_type="GENERATION_KW",
        value=1.0, iso_timestamp=now,
    )


if __name__ == "__main__":
    with grpc.insecure_channel("localhost:50051") as channel:
        stub = pb2_grpc.TelemetryIngestServiceStub(channel)
        ack = stub.StreamTelemetry(make_packets())
        print(f"accepted_count = {ack.accepted_count}")