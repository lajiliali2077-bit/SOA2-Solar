"""Client de test de TriggerUrgentAudit : 3 cas (surcharge, nœud sans anomalie, nœud inconnu)."""
import sys
from pathlib import Path

import grpc

sys.path.insert(0, str(Path(__file__).resolve().parent))
import tunisovereign_pb2 as pb2  # noqa: E402
import tunisovereign_pb2_grpc as pb2_grpc  # noqa: E402

CASES = [
    ("TOZ-001", "Surcharge du feeder de Tozeur"),
    ("KEB-001", "Nœud sans anomalie critique"),
    ("XXX-999", "Nœud inconnu"),
]

if __name__ == "__main__":
    with grpc.insecure_channel("localhost:50051") as channel:
        stub = pb2_grpc.TelemetryIngestServiceStub(channel)
        for node_code, reason in CASES:
            reply = stub.TriggerUrgentAudit(pb2.AuditRequest(node_code=node_code, reason=reason))
            print(f"{node_code}: status={reply.status} tx_hash={reply.tx_hash!r}")