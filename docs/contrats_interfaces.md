# Contrats d'interface et démarrage (SolarSouk-STEG, Track 7)

Référence pour tous les rôles. Mainteneur : Rôle 1.
Règle : on modifie ce fichier d'abord, on prévient le groupe, puis on modifie le code.
Les modèles de données sont décrits dans `docs/models.md`.

## 1. Conventions de données

- Argent en **millimes** (entiers). Horodatages en **UTC** (`USE_TZ = True`). Heure locale tunisienne : UTC+1 toute l'année.
- `GRID_NET_KW` : positif = import depuis le réseau, négatif = export.
- **Charge d'un feeder = somme des `GRID_NET_KW` de ses nœuds**, à chaque instant. Elle n'est pas stockée.
- Surcharge critique : charge du feeder > 92 % de `Feeder.capacity_kw`.
- Fenêtre solaire des pompes : 10h à 15h (heure locale).
- Le ML ne lit **jamais** `TelemetryReading.is_injected_anomaly`, qui sert uniquement à calculer Précision, Rappel et F1.
- Aucun secret en dur : tout passe par `.env` (jamais commité).

## 2. Contrats entre rôles

| Fonction | Propriétaire | Fichier | Statut |
|---|---|---|---|
| `forecast_peak_load` | Rôle 1 | `agent/skills/irradiance_forecaster.py` | stub dans `main` |
| `optimize_pump_schedule` | Rôle 4 | `agent/skills/pump_optimizer.py` | à pousser (stub d'abord) |
| `prove_green_origin` | Rôle 5 | `agent/skills/zk_origin_prover.py` | à pousser (stub d'abord) |
| `settle_on_chain` | Rôle 5 | `contracts/web3_zk_client.py` | à pousser (stub d'abord) |
| `run_agent` | Rôle 4 | `agent/langgraph_agent.py` | à pousser (stub d'abord) |

Chaque propriétaire met la colonne « Statut » à jour (« stub », puis « réel »). **La signature ne change pas** quand le stub est remplacé par la vraie version.

### 2.1 `forecast_peak_load(feeder_id: int, horizon_hours: int = 24) -> dict`

```python
{
  "feeder_id": 1,
  "horizon_hours": 24,
  "hourly": [{"hour": "2026-11-16T19:00:00+00:00", "load_kw": 41.2, "generation_kw": 0.0}],
  "peak_kw": 44.1,
  "peak_pct": 98.0,                    # pic rapporté à Feeder.capacity_kw, en %
  "forecasted_deficit_24h_kwh": 3.4,   # kWh au-dessus de 92 % de la capacité (définition à confirmer avec les Rôles 2 et 4)
}
```
`load_kw` est la charge nette du feeder (somme des `GRID_NET_KW`). Un stub doit rester plausible : au-dessus de 92 % pour `Feeder-TOZ-01`, sous 92 % pour les autres feeders. Sinon l'agent n'a rien à corriger.

### 2.2 `optimize_pump_schedule(feeder_id: int, forecast: dict) -> dict`

```python
{
  "feasible": True,
  "peak_pct_before": 98.0,
  "peak_pct_after": 71.5,
  "schedules": [{"node_code": "TOZ-001", "start": "2026-11-16T10:00:00+00:00", "end": "2026-11-16T14:00:00+00:00", "planned_kw": 15.0}],
}
```

### 2.3 `prove_green_origin(node_code: str, period_start: str, period_end: str, green_kwh: float, quota_kwh: float) -> dict`

```python
{"commitment_hash": "0x" + 64 hex, "public_inputs": {...}}   # hash de 66 caractères au total
```

### 2.4 `settle_on_chain(commitment_hash: str, public_inputs: dict) -> dict`

```python
{"tx_hash": "0x...", "block_number": 12345, "network_name": "Foundry-Anvil-Local", "is_verified": True}
```
Contient tout ce qu'il faut pour créer un `OnChainZKReceipt` (le Rôle 4 l'écrit en base).

### 2.5 `run_agent(anomaly_id: int) -> int`

Retourne l'`id` de l'`AgentLoopExecution`. Cette fonction crée l'exécution en `RUNNING`, la met à jour (`status`, `retry_count`, `mcp_tools_invoked`, `skills_executed`, `confidence_score`, `final_recommendation`) et crée l'`OnChainZKReceipt`. Statuts : `RUNNING`, `COMPLETED`, `ESCALATED`, `FAILED`.

## 3. Données de référence

- 4 feeders : `Feeder-TOZ-01` (45 kW), `Feeder-KEB-01` (47 kW), `Feeder-TAT-01` (29 kW), `Feeder-SFX-01` (36 kW).
- 10 nœuds (`TOZ-001`, `TOZ-002`, `TOZ-003`, `KEB-001`...`SFX-002`), 4 coopératives, 3 tarifs, 7 utilisateurs de test.
- Télémétrie : un pas de 15 minutes, 5 métriques par nœud. 7 jours = 33 600 mesures, dont 308 étiquetées anomalie.
- Chaque jour, `Feeder-TOZ-01` dépasse 92 % entre 19h00 et 20h15 (environ 97 à 99 %). Les autres feeders restent sous environ 73 %. Après `detect_anomalies --clear` : 42 événements `FEEDER_OVERLOAD` de gravité `CRITICAL`.

| Compte | Rôle | Gouvernorat |
|---|---|---|
| `coop_tozeur`, `coop_kebili`, `coop_tataouine`, `coop_sfax` | `COOP_MEMBER` | celui du nom |
| `auditeur_tozeur` | `REGIONAL_AUDITOR` | Tozeur |
| `admin_national` | `NATIONAL_ADMIN` | Tozeur |
| `agent_service` | `AGENT_SERVICE` | Tozeur |

Mot de passe de développement : variable `SEED_USER_PASSWORD` du `.env`, sinon la valeur par défaut de `seed_solarsouk.py`. Il ne sert qu'en local.

## 4. Démarrer le projet

### Mode développement (chacun, dans son `.venv`)

```powershell
cd C:\SOA2-Solar
docker compose up -d db
cd backend
python manage.py migrate
python manage.py seed_solarsouk
```
Puis, pour charger des données :
- Terminal 1, racine : `python grpc_service\server.py`
- Terminal 2, racine : `python simulator\tunisian_simulator.py --days 7 --clear`, puis `cd backend` et `python manage.py detect_anomalies --clear`

### Mode démo (tout dans Docker, une seule machine)

```powershell
cd C:\SOA2-Solar
docker compose up -d --build web grpc
docker compose run --rm simulate
```
La première commande construit l'image, applique les migrations et le seed (service `init`), puis démarre l'application et le serveur gRPC. La seconde simule 7 jours de télémétrie et détecte les anomalies.

## 5. Services et adresses

| Service | Depuis votre `.venv` | Depuis un conteneur |
|---|---|---|
| PostgreSQL | `localhost:5432` | `db:5432` |
| Application Django | `http://localhost:8000` | `http://web:8000` |
| Serveur gRPC | `localhost:50051` | `grpc:50051` |
| Anvil (blockchain) | `http://localhost:8545` | `http://anvil-blockchain:8545` |
| Dashboard Streamlit | `http://localhost:8501` | `dashboard:8501` |
| n8n | `http://localhost:5678` | `http://n8n-boundary:5678` |
| Redis | `localhost:6379` | `redis:6379` |

Dans un conteneur, `localhost` désigne le conteneur lui-même. `docker-compose.yml` remplace donc les adresses du `.env` (`DATABASE_URL`, `POSTGRES_HOST`, `REDIS_URL`, `WEB3_RPC_URL`, `OLLAMA_BASE_URL`) par celles de la colonne de droite. Le `.env` garde les adresses `localhost`, pour le mode développement.

## 6. Règles d'équipe

- Un seul propriétaire par fichier (voir les fiches de rôle).
- Personne sauf le Rôle 1 ne modifie `models.py` ni `migrations/`.
- Une branche par personne. Récupérer `main` avant de pousser. Ne jamais commiter `.env`, `.venv`, `db.sqlite3`, `__pycache__`.
- Ne jamais coller la sortie de `docker compose config` dans un chat ou un dépôt : elle affiche les valeurs du `.env`.