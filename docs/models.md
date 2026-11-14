# Contrat des modèles : SolarSouk-STEG (Track 7)

Référence unique, alignée sur `backend/tunisovereign_core/models.py`.
**Règle : on modifie ce fichier d'abord, on prévient le groupe, puis on modifie `models.py`.**

## Conventions

- **Une seule app Django** : `tunisovereign_core`. Toutes les classes sont dans `models.py`.
- `AUTH_USER_MODEL = "tunisovereign_core.StakeholderUser"`.
- Noms en anglais, `snake_case`. Les noms de classes du sujet sont conservés pour que l'UML corresponde au code.
- Chaque énumération est un `TextChoices`. Chaque modèle a un `__str__`.
- Argent en **millimes** (entiers). Horodatages en **UTC** (`USE_TZ = True`).
- Unités de télémétrie : kW, %, V.
- Une ligne de `TelemetryReading` = une mesure, comme un paquet du `.proto` (`node_code`, `metric_type`, `value`, `iso_timestamp`).

## Énumération partagée

`Governorate` : `TOZEUR`, `KEBILI`, `TATAOUINE`, `SFAX`.

## Modèles

### Utilisateurs

| Modèle | Champs |
|---|---|
| `StakeholderUser` (hérite d'`AbstractUser`) | `role` (`Role`, défaut `COOP_MEMBER`), `governorate` (`Governorate`, index), `wallet_address` (Char 42, null), `preferred_dialect` (Char 16, défaut `ar-TN`) |

`Role` : `COOP_MEMBER` (ferme ou PME productrice), `REGIONAL_AUDITOR` (auditeur énergie régional), `NATIONAL_ADMIN`, `AGENT_SERVICE` (agent IA et compte MCP).

### Réseau

| Modèle | Champs | Contraintes |
|---|---|---|
| `Feeder` | `name` (unique), `governorate`, `capacity_kw`, `created_at` | `capacity_kw > 0` |
| `CooperativeUnit` | `id` (UUID, pk), `name`, `governorate`, `track_domain` (Char 64, défaut `Track_07_SolarSouk_STEG`), `daily_quota_limit` (kWh/jour), `contract_address` (Char 42, blank), `created_at` | |
| `ResourceNodePlot` (site solaire) | `coop` (FK, `related_name="nodes"`), `owner` (FK utilisateur, `related_name="owned_nodes"`), `feeder` (FK, PROTECT, `related_name="nodes"`), `node_code` (unique, ex. `TOZ-001`), `site_type` (`FARM` ou `SME`), `installed_kwp`, `battery_capacity_kwh`, `has_pump`, `pump_rated_kw`, `is_pump_dispatch_active`, `created_at` | `pump_rated_kw = 0` si `has_pump = False` |
| `Tariff` | `name`, `time_band` (`OFFPEAK`, `DAY`, `PEAK`), `start_hour` (0-23), `end_hour` (0-24), `buy_price_millimes_kwh`, `sell_price_millimes_kwh`, `valid_from`, `valid_to` (null), `created_at` | `valid_to >= valid_from` |

Une tranche horaire peut passer minuit (`OFFPEAK` : 22 à 6). Le calcul de facture doit gérer ce cas.

### Télémétrie

| Modèle | Champs | Index |
|---|---|---|
| `TelemetryReading` | `node` (FK, `related_name="readings"`), `timestamp` (UTC, index), `metric_type`, `value` (Float), `ingestion_protocol` (`REST`, `GRPC`, `GRAPHQL`, défaut `GRPC`), `is_injected_anomaly` (Bool, défaut False) | `(node, metric_type, -timestamp)` et `(timestamp, metric_type)` |

`metric_type` :

| Valeur | Sens |
|---|---|
| `GENERATION_KW` | Production solaire (kW) |
| `BATTERY_SOC` | État de charge de la batterie (%) |
| `PUMP_LOAD_KW` | Charge de la pompe (kW) |
| `VOLTAGE_V` | Tension de l'onduleur (V) |
| `GRID_NET_KW` | Puissance réseau : **positif = import, négatif = export** |

La **charge d'un feeder** n'est pas stockée : on la calcule en sommant la charge des nœuds rattachés (consommation moins production, par instant).

`is_injected_anomaly` est la vérité terrain du simulateur. Elle sert uniquement à calculer Précision, Rappel et F1. **Le modèle ML ne doit jamais la lire comme variable d'entrée.**

### ML, agent et blockchain

| Modèle | Champs | Contraintes et index |
|---|---|---|
| `AnomalyAndForecastEvent` | `node` (FK, null), `feeder` (FK, null), `reading_timestamp` (null), `detected_at` (auto), `anomaly_type`, `severity`, `isolation_forest_score`, `forecasted_deficit_24h` (kWh), `model_version` (défaut `isoforest-v1`) | au moins un de `node` ou `feeder` ; index `(severity, -detected_at)` |
| `AgentLoopExecution` | `thread_id` (index), `trigger_source`, `anomaly` (FK, null, SET_NULL), `status`, `retry_count`, `darja_transcript`, `parsed_intent_json`, `mcp_tools_invoked` (liste JSON), `skills_executed` (liste JSON), `final_recommendation`, `confidence_score` (0 à 1), `created_at` | |
| `OnChainZKReceipt` | `agent_execution` (OneToOne, `related_name="zk_receipt"`), `zk_commitment_hash` (unique, 66), `public_inputs_json`, `tx_hash` (unique, 66), `block_number`, `network_name` (défaut `Foundry-Anvil-Local`), `is_verified_on_chain`, `created_at` | |

- `Severity` : `LOW`, `MEDIUM`, `CRITICAL`.
- `AnomalyType` : `FEEDER_OVERLOAD`, `VOLTAGE_OUT_OF_RANGE`, `INVERTER_FAILURE`, `PUMP_MISALIGNED`, `SOC_INCONSISTENT`.
- `Status` (agent) : `RUNNING`, `COMPLETED`, `ESCALATED`, `FAILED`.
- La surcharge d'un feeder est une anomalie **de niveau feeder** : on renseigne `feeder`, `node` reste vide.
- `AgentLoopExecution` est créé en `RUNNING` au début d'un passage, puis complété. C'est pourquoi `final_recommendation` accepte d'être vide.

## Diagramme de classes (Mermaid)

```mermaid
classDiagram
    class StakeholderUser {
        role
        governorate
        wallet_address
        preferred_dialect
    }
    class Feeder {
        name
        governorate
        capacity_kw
    }
    class CooperativeUnit {
        id UUID
        name
        governorate
        track_domain
        daily_quota_limit
        contract_address
    }
    class ResourceNodePlot {
        node_code
        site_type
        installed_kwp
        battery_capacity_kwh
        has_pump
        pump_rated_kw
        is_pump_dispatch_active
    }
    class Tariff {
        time_band
        start_hour
        end_hour
        buy_price_millimes_kwh
        sell_price_millimes_kwh
        valid_from
        valid_to
    }
    class TelemetryReading {
        timestamp
        metric_type
        value
        ingestion_protocol
        is_injected_anomaly
    }
    class AnomalyAndForecastEvent {
        anomaly_type
        severity
        isolation_forest_score
        forecasted_deficit_24h
        reading_timestamp
        model_version
    }
    class AgentLoopExecution {
        thread_id
        trigger_source
        status
        retry_count
        mcp_tools_invoked
        skills_executed
        final_recommendation
        confidence_score
    }
    class OnChainZKReceipt {
        zk_commitment_hash
        tx_hash
        block_number
        network_name
        is_verified_on_chain
    }

    StakeholderUser "1" --> "*" ResourceNodePlot : owner
    CooperativeUnit "1" --> "*" ResourceNodePlot : nodes
    Feeder "1" --> "*" ResourceNodePlot : nodes
    ResourceNodePlot "1" --> "*" TelemetryReading : readings
    ResourceNodePlot "1" --> "*" AnomalyAndForecastEvent : anomalies
    Feeder "1" --> "*" AnomalyAndForecastEvent : anomalies
    AnomalyAndForecastEvent "1" --> "*" AgentLoopExecution : agent_runs
    AgentLoopExecution "1" --> "0..1" OnChainZKReceipt : zk_receipt
```

`Tariff` n'a pas de relation : il est consulté par le calcul de facture selon l'heure et la date.

## Seuils du Track 7 (simulateur et ML)

- Tension normale : **220 V ± 6 %**, soit 206,8 à 233,2 V.
- Pompes alignées sur le pic solaire : **10h à 15h**.
- Anomalie critique : charge du feeder **> 92 %** de `capacity_kw`, en soirée à faible irradiation.

## Données de seed (hypothèses à valider par les Membres 1 et 4)

- 4 feeders, un par gouvernorat. Leur capacité doit être calibrée de façon qu'un démarrage simultané des pompes en soirée dépasse 92 %, sinon l'anomalie principale n'apparaîtra jamais.
- 1 coopérative par gouvernorat, environ 10 nœuds au total, 2 à 3 par feeder, `node_code` de la forme `TOZ-001`, `KEB-001`, `TAT-001`, `SFX-001`.
- 3 tarifs **illustratifs** (millimes/kWh). Ce ne sont pas des tarifs STEG officiels : à remplacer par des valeurs sourcées dans le README.

| Tranche | Heures | Achat | Rachat |
|---|---|---|---|
| `OFFPEAK` | 22 à 6 | 150 | 100 |
| `DAY` | 6 à 18 | 200 | 130 |
| `PEAK` | 18 à 22 | 300 | 160 |

- Le facteur d'émission du réseau tunisien (pour les crédits carbone) est une variable d'environnement, avec sa source citée dans le README.

## Modèles ajoutés plus tard

`PumpSchedule`, `NetMeteringSettlement`, `CarbonCredit` : ils seront ajoutés dans une **nouvelle migration** (`0002`), en référençant `ResourceNodePlot`. Ne renommez pas les modèles existants, pour ne pas obliger l'équipe à recréer sa base.

## Anciens noms du starter (Track 1) vers le Track 7

| Ancien | Nouveau |
|---|---|
| `MetricType` : `MOISTURE`, `FLOW`, `TEMP`, `STOCK` | `GENERATION_KW`, `BATTERY_SOC`, `PUMP_LOAD_KW`, `VOLTAGE_V`, `GRID_NET_KW` |
| `crop_or_sector_type` | `site_type` (`FARM` ou `SME`) |
| `allocated_share_pct` | supprimé |
| `is_valve_or_dispatch_active` | `is_pump_dispatch_active` |
| `governorate` (texte libre) | `Governorate` (`TextChoices`) |
| `ingestion_protocol = "gRPC"` | `GRPC` (`TextChoices`) |
| `AnomalyAndForecastEvent.node` obligatoire | `node` ou `feeder` (au moins un) |
| `CooperativeUnit.track_domain` = `Track_01_Water_Agri` | conservé, défaut `Track_07_SolarSouk_STEG` |
| `Feeder`, `Tariff` | nouveaux modèles |