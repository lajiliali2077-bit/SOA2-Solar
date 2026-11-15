# Outils MCP : SolarGridMCP (Rôle 2)

Serveur : `mcp_server/solargrid_mcp.py`. SDK `mcp` 2.3.0 (classe `MCPServer`, qui remplace `FastMCP` de la version 1), transport **stdio**.

## Lancer et appeler

- Le client lance le serveur lui-même en sous-processus. Exemple complet : `mcp_server/client_example.py`.
- Test manuel depuis la racine, `.venv` actif et base lancée (`docker compose up -d db`) : `python mcp_server\client_example.py`
- Le serveur lit la base avec le `.env` de la racine (`DATABASE_URL`).
- **Jamais de `print()` dans le serveur** : stdout est le canal du protocole. Les messages passent par `logging` (stderr).

## Les 6 outils

| Outil | Entrées | Sortie | Source | Statut |
|---|---|---|---|---|
| `get_feeder_status` | `feeder_id: int` | `feeder_id`, `name`, `governorate`, `capacity_kw`, `node_count`, `load_kw`, `load_pct`, `is_overloaded` (> 92 %), `as_of` | base de données : dernière mesure `GRID_NET_KW` de chaque nœud | réel |
| `get_cooperative_quota` | `coop_id: str` (UUID) | `coop_id`, `name`, `governorate`, `daily_quota_limit_kwh`, `node_codes` | base de données | réel |
| `forecast_peak_load` | `feeder_id: int`, `horizon_hours: int = 24` | contrat 2.1 de `docs/contrats_interfaces.md` | `agent/skills/irradiance_forecaster.py` (Rôle 1) | réel |
| `optimize_pump_schedule` | `feeder_id: int`, `forecast: dict` | contrat 2.2 | `agent/skills/pump_optimizer.py` (Rôle 4) | stub |
| `prove_green_origin` | `node_code`, `period_start`, `period_end`, `green_kwh`, `quota_kwh` | contrat 2.3 | `agent/skills/zk_origin_prover.py` (Rôle 5) | stub |
| `settle_on_chain` | `commitment_hash: str`, `public_inputs: dict` | contrat 2.4 | `contracts/web3_zk_client.py` (Rôle 5) | stub |

Notes :
- `get_feeder_status` donne la charge **actuelle** (dernière mesure), pas le pic. Le pic vient de `forecast_peak_load`.
- `get_cooperative_quota` donne le plafond, pas encore l'énergie déjà consommée dans la journée.

## Stubs

Si le fichier d'un coéquipier n'existe pas encore, l'outil répond avec une fausse réponse plausible, au même format que le contrat, avec en plus `"stub": true`. Un avertissement `STUB utilisé` est écrit sur stderr.
- Le stub de `settle_on_chain` renvoie `network_name = "STUB-no-chain"` : un reçu portant ce nom n'a jamais touché une blockchain.
- Ne jamais présenter un résultat de stub comme réel en démonstration.
- Dès que le vrai fichier est poussé, le serveur l'utilise sans modification (la signature ne change pas).

## Erreurs

- Erreurs prévues (feeder ou coopérative introuvable, `coop_id` invalide, `green_kwh > quota_kwh`) : le client reçoit `is_error = True` avec un message clair.
- Plantage imprévu : le client reçoit seulement `Error executing tool <nom>` ; le détail est dans les logs du serveur (stderr).

## Appeler le serveur depuis l'agent (Rôle 4)

```python
import sys
from mcp import Client, StdioServerParameters

parametres = StdioServerParameters(command=sys.executable, args=["mcp_server/solargrid_mcp.py"])
async with Client(parametres) as client:
    resultat = await client.call_tool("forecast_peak_load", {"feeder_id": 1})
    donnees = resultat.structured_content   # un dict ; resultat.is_error vaut True en cas d'erreur
```

## Tests

Vérification de bout en bout avec `client_example.py` (7 jours de télémétrie simulée : `Feeder-TOZ-01` donne `peak_pct` d'environ 98 %). Tests automatiques des outils : à ajouter.