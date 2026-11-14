# Contrat des modèles : SolarSouk-STEG (Track 7)

Référence unique. On modifie ce fichier d'abord, puis on prévient le groupe.

## Conventions
- Noms en anglais, snake_case. Noms de classes du sujet conservés.
- Chaque enum est un `TextChoices`. Chaque modèle a un `__str__` lisible.
- `created_at` (auto_now_add) partout, sauf `TelemetryReading` (gros volume).
- Argent en millimes (entiers). Horodatages en UTC (`USE_TZ = True`).
- Unités de télémétrie : kW, %, V. Pas de mesure toutes les 15 min.

## accounts
**Governorate** (TextChoices, défini dans accounts/models.py, importé par les autres apps) : TOZEUR, KEBILI, TATAOUINE, SFAX

| Modèle | Champs |
|---|---|
| `StakeholderUser` (AbstractUser) | `role` (Role : COOP_MEMBER, REGIONAL_AUDITOR, NATIONAL_ADMIN, AGENT_SERVICE ; défaut COOP_MEMBER), `governorate` (Governorate, db_index), `wallet_address` (Char 42, null, blank), `preferred_dialect` (Char 16, défaut "ar-TN") |

## grid
| Modèle | Champs |
|---|---|
| `Feeder` | `name`, `governorate`, `capacity_kw` (Float > 0), `created_at` |
| `CooperativeUnit` | `id` (UUID pk), `name`, `governorate`, `daily_quota_limit` (Float, kWh/jour d'import réseau max, sert à la preuve ZK), `contract_address` (Char 42, blank), `created_at` |
| `ResourceNodePlot` (= site solaire) | `coop` (FK CooperativeUnit, related_name="nodes"), `owner` (FK StakeholderUser, related_name="owned_nodes"), `feeder` (FK Feeder, PROTECT), `node_code` (unique), `site_type` (FARM, SME), `installed_kwp`, `battery_capacity_kwh`, `has_pump` (Bool), `pump_rated_kw` (Float, défaut 0), `is_pump_dispatch_active` (Bool, défaut False), `created_at` |
| `Tariff` | `name`, `time_band` (OFFPEAK, DAY, PEAK), `start_hour`, `end_hour`, `buy_price_millimes_kwh` (PositiveInt), `sell_price_millimes_kwh` (PositiveInt), `valid_from`, `valid_to` (null), `created_at` |

## telemetry
| Modèle | Champs |
|---|---|
| `TelemetryReading` | `node` (FK ResourceNodePlot, related_name="readings"), `timestamp` (db_index), `metric_type` (GENERATION_KW, BATTERY_SOC, PUMP_LOAD_KW, VOLTAGE_V, GRID_NET_KW), `value` (Float), `ingestion_protocol` (REST, GRPC, GRAPHQL ; défaut GRPC), `is_injected_anomaly` (Bool, défaut False) |

Meta : `Index(fields=["node", "metric_type", "-timestamp"])`

## Seuils Track 7 (simulateur et ML)
- Tension normale : 220 V ± 6 % (206,8 à 233,2 V)
- Pompes alignées sur le pic solaire : 10h à 15h
- Anomalie critique : charge du feeder > 92 % de `capacity_kw` en soirée (faible irradiation)

## Modèles futurs (noms figés, champs : sujet §4.1)
`AnomalyAndForecastEvent`, `AgentLoopExecution`, `OnChainZKReceipt`.
Ajouts prévus aux incréments 3 et 4 : `PumpSchedule`, `NetMeteringSettlement`, `CarbonCredit` (référencent `ResourceNodePlot`).