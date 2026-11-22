"""
Détection d'anomalies SolarSouk-STEG (Track 7).

IsolationForest sur la télémétrie stockée en base. Une ligne du jeu de données = un nœud
à un instant (ses 5 métriques regroupées). Évaluation : Précision, Rappel, F1.

RÈGLE : is_injected_anomaly sert UNIQUEMENT à évaluer. Il n'est jamais une entrée du modèle.

Depuis le dossier backend :
    python -m tunisovereign_core.ml_anomaly
"""
import math
import os

import numpy as np
from sklearn.ensemble import IsolationForest
from sklearn.metrics import confusion_matrix, f1_score, precision_score, recall_score

UTC_OFFSET_H = 1  # Tunisie : UTC+1 toute l'année (la base stocke en UTC)
REQUIRED_METRICS = ("GENERATION_KW", "PUMP_LOAD_KW", "VOLTAGE_V", "GRID_NET_KW")
FEATURE_NAMES = ["gen_ratio", "soc_pct", "pump_ratio", "voltage_v", "net_ratio", "hour_sin", "hour_cos"]
ML_MODEL_VERSION = "isoforest-v1"  # valeur par défaut de AnomalyAndForecastEvent.model_version
CRITICAL_SHARE = 0.10  # parmi les anomalies détectées : 10 % les plus extrêmes -> CRITICAL
MEDIUM_SHARE = 0.30    # les 30 % suivants -> MEDIUM, le reste -> LOW
VOLTAGE_MIN, VOLTAGE_MAX = 220 * 0.94, 220 * 1.06  # 220 V ± 6 %
SOLAR_WINDOW = (10, 15)  # heures locales : fenêtre solaire de pompage (10h-15h)
SOC_MIN_PCT = 10.0       # le simulateur ne descend jamais sous 10 % : en dessous = incohérent
# Pour le repli (aucune règle ne s'applique) : colonne de X la plus atypique -> type d'anomalie
FALLBACK_TYPE_BY_FEATURE = {
    0: "INVERTER_FAILURE",     # production anormale
    1: "SOC_INCONSISTENT",     # batterie
    2: "PUMP_MISALIGNED",      # pompe
    3: "VOLTAGE_OUT_OF_RANGE", # tension
    4: "INVERTER_FAILURE",     # puissance réseau anormale
}


def load_dataset():
    """Lit la télémétrie en base. Retourne (lignes regroupées par (nœud, instant), nœuds par id)."""
    from tunisovereign_core.models import ResourceNodePlot, TelemetryReading

    nodes = {n.id: n for n in ResourceNodePlot.objects.all()}
    rows = {}
    qs = TelemetryReading.objects.values_list(
        "node_id", "timestamp", "metric_type", "value", "is_injected_anomaly"
    ).iterator(chunk_size=5000)
    for node_id, ts, metric, value, injected in qs:
        row = rows.setdefault((node_id, ts), {"v": {}, "y": 0})
        row["v"][metric] = value
        if injected:
            row["y"] = 1  # une ligne est « anormale » si une de ses métriques l'est
    return rows, nodes


def build_matrix(rows, nodes):
    """Construit X (caractéristiques), y (vérité terrain, pour l'évaluation seulement), keys."""
    X, y, keys = [], [], []
    for key in sorted(rows):
        node_id, ts = key
        v = rows[key]["v"]
        if any(m not in v for m in REQUIRED_METRICS):
            continue  # ligne incomplète
        n = nodes[node_id]
        hour = (ts.hour + ts.minute / 60 + UTC_OFFSET_H) % 24
        angle = 2 * math.pi * hour / 24
        kwp = max(n.installed_kwp, 1e-6)
        pump_ratio = v["PUMP_LOAD_KW"] / n.pump_rated_kw if n.pump_rated_kw > 0 else 0.0
        X.append([
            v["GENERATION_KW"] / kwp,     # production rapportée à la puissance installée
            v.get("BATTERY_SOC", 0.0),    # état de charge (%)
            pump_ratio,                   # charge de la pompe rapportée à sa puissance nominale
            v["VOLTAGE_V"],
            v["GRID_NET_KW"] / kwp,       # puissance réseau rapportée à la puissance installée
            math.sin(angle),              # heure locale en cercle : 23h50 est proche de 0h
            math.cos(angle),
        ])
        y.append(rows[key]["y"])
        keys.append(key)
    return np.array(X), np.array(y), keys

OVERLOAD_THRESHOLD = 0.92  # surcharge critique : charge du feeder > 92 % de capacity_kw


def load_feeder_loads():
    """Charge d'un feeder à chaque instant = somme des GRID_NET_KW de ses nœuds."""
    from tunisovereign_core.models import Feeder, ResourceNodePlot, TelemetryReading

    capacity = {f.id: f.capacity_kw for f in Feeder.objects.all()}
    feeder_of = dict(ResourceNodePlot.objects.values_list("id", "feeder_id"))
    load, truth = {}, {}
    qs = TelemetryReading.objects.filter(metric_type="GRID_NET_KW").values_list(
        "node_id", "timestamp", "value", "is_injected_anomaly"
    ).iterator(chunk_size=5000)
    for node_id, ts, value, injected in qs:
        key = (feeder_of[node_id], ts)
        load[key] = load.get(key, 0.0) + value
        truth[key] = truth.get(key, False) or injected
    return load, truth, capacity


def evaluate_feeder_overload_rule(load, truth, capacity, threshold=OVERLOAD_THRESHOLD):
    """Règle de seuil au niveau feeder, évaluée contre la vérité terrain."""
    tp = fp = fn = 0
    for key, total in load.items():
        flagged = total / capacity[key[0]] > threshold
        if flagged and truth[key]:
            tp += 1
        elif flagged:
            fp += 1
        elif truth[key]:
            fn += 1
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {
        "feeder_instants": len(load),
        "overload_instants": sum(1 for t in truth.values() if t),
        "tp": tp, "fp": fp, "fn": fn,
        "precision": round(precision, 4), "recall": round(recall, 4), "f1_score": round(f1, 4),
    }

class TunisianTelemetryAnomalyEngine:
    """Détecteur IsolationForest + banc d'évaluation Précision / Rappel / F1 sur la base."""

    def __init__(self, contamination: float = 0.03, random_state: int = 42):
        # contamination = proportion d'anomalies attendue (hypothèse de départ, à ajuster).
        self.model = IsolationForest(
            n_estimators=200, contamination=contamination, random_state=random_state
        )

    def fit_and_evaluate_from_db(self) -> dict:
        rows, nodes = load_dataset()
        X, y, _keys = build_matrix(rows, nodes)
        if len(y) == 0:
            raise ValueError("Aucune télémétrie complète en base : lancez le simulateur d'abord.")

        y_pred = (self.model.fit_predict(X) == -1).astype(int)  # y n'entre jamais dans fit
        tn, fp, fn, tp = confusion_matrix(y, y_pred, labels=[0, 1]).ravel()
        return {
            "rows": int(len(y)),
            "injected_anomalies": int(y.sum()),
            "flagged": int(y_pred.sum()),
            "tp": int(tp), "fp": int(fp), "fn": int(fn), "tn": int(tn),
            "precision": round(float(precision_score(y, y_pred, zero_division=0)), 4),
            "recall": round(float(recall_score(y, y_pred, zero_division=0)), 4),
            "f1_score": round(float(f1_score(y, y_pred, zero_division=0)), 4),
        }

    def detect_node_anomalies_from_db(self) -> list:
        """Détecte les mesures de nœud inhabituelles (sans utiliser la vérité terrain).

        Retourne une liste de dictionnaires, triée par instant :
          node_id, timestamp, score (plus négatif = plus anormal),
          anomaly_type (nom d'un AnomalyType), severity (LOW / MEDIUM / CRITICAL)
        """
        rows, nodes = load_dataset()
        X, _y, keys = build_matrix(rows, nodes)  # _y ignoré : jamais utilisé pour détecter
        if len(keys) == 0:
            raise ValueError("Aucune télémétrie complète en base : lancez le simulateur d'abord.")

        flags = self.model.fit_predict(X)          # -1 = anomalie
        scores = self.model.score_samples(X)       # plus petit = plus anormal
        flagged = [i for i in range(len(keys)) if flags[i] == -1]
        if not flagged:
            return []

        # Gravité par rang : les plus extrêmes sont CRITICAL, puis MEDIUM, puis LOW
        flagged.sort(key=lambda i: scores[i])
        n_critical = max(1, round(len(flagged) * CRITICAL_SHARE))
        n_medium = round(len(flagged) * MEDIUM_SHARE)

        mean, std = X.mean(axis=0), X.std(axis=0) + 1e-9
        results = []
        for rank, i in enumerate(flagged):
            node_id, ts = keys[i]
            if rank < n_critical:
                severity = "CRITICAL"
            elif rank < n_critical + n_medium:
                severity = "MEDIUM"
            else:
                severity = "LOW"
            results.append({
                "node_id": node_id,
                "timestamp": ts,
                "score": float(scores[i]),
                "anomaly_type": classify_node_anomaly(
                    rows[keys[i]]["v"], nodes[node_id], ts, (X[i] - mean) / std
                ),
                "severity": severity,
            })
        results.sort(key=lambda r: (r["timestamp"], r["node_id"]))
        return results


def classify_node_anomaly(values, node, ts, zscores):
    """Donne un type d'anomalie à une mesure déjà jugée atypique (règles lisibles d'abord).

    Retourne le NOM d'un AnomalyType (ex. "VOLTAGE_OUT_OF_RANGE").
    """
    hour = (ts.hour + ts.minute / 60 + UTC_OFFSET_H) % 24
    in_solar_window = SOLAR_WINDOW[0] <= hour < SOLAR_WINDOW[1]

    if not VOLTAGE_MIN <= values["VOLTAGE_V"] <= VOLTAGE_MAX:
        return "VOLTAGE_OUT_OF_RANGE"
    soc = values.get("BATTERY_SOC")
    if soc is not None and not SOC_MIN_PCT <= soc <= 100:
        return "SOC_INCONSISTENT"
    if in_solar_window and node.installed_kwp > 0 and values["GENERATION_KW"] / node.installed_kwp < 0.05:
        return "INVERTER_FAILURE"  # pas de production en plein soleil
    if node.pump_rated_kw > 0 and values["PUMP_LOAD_KW"] / node.pump_rated_kw > 0.1 and not in_solar_window:
        return "PUMP_MISALIGNED"   # pompe en marche hors fenêtre solaire

    # Repli : la caractéristique la plus éloignée de la normale décide du type
    worst = int(np.argmax(np.abs(zscores[:5])))
    return FALLBACK_TYPE_BY_FEATURE[worst]


if __name__ == "__main__":
    import django

    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    django.setup()

    metrics = TunisianTelemetryAnomalyEngine().fit_and_evaluate_from_db()
    print("Évaluation ML (IsolationForest, une ligne = un nœud à un instant) :")
    for name, value in metrics.items():
        print(f"  {name:<20} {value}")

    feeder_metrics = evaluate_feeder_overload_rule(*load_feeder_loads())
    print(f"\nRègle de surcharge feeder (> {OVERLOAD_THRESHOLD:.0%} de capacity_kw) :")
    for name, value in feeder_metrics.items():
        print(f"  {name:<20} {value}")