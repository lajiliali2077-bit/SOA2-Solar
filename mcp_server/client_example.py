"""
Exemple de client MCP : lance le serveur SolarGridMCP en sous-processus,
liste ses outils et en appelle quelques-uns.

Lancer depuis la racine du projet (.venv activé) :
    python mcp_server\\client_example.py

Sert de modèle au Rôle 4 : l'agent peut appeler les outils exactement comme ici.
"""
import asyncio
import json
import sys
from pathlib import Path

from mcp import Client, StdioServerParameters

SERVEUR = Path(__file__).resolve().parent / "solargrid_mcp.py"


async def appeler(client, nom, arguments):
    resultat = await client.call_tool(nom, arguments)
    print(f"\n--- {nom}({arguments}) ---")
    if resultat.is_error:
        print("ERREUR :", resultat.content[0].text)
        return None
    donnees = resultat.structured_content
    print(json.dumps(donnees, indent=2, ensure_ascii=False)[:700])
    return donnees


async def main():
    parametres = StdioServerParameters(command=sys.executable, args=[str(SERVEUR)])
    async with Client(parametres) as client:
        outils = await client.list_tools()
        print("Outils disponibles :", [o.name for o in outils.tools])

        prevision = await appeler(client, "forecast_peak_load", {"feeder_id": 1, "horizon_hours": 24})
        await appeler(client, "get_feeder_status", {"feeder_id": 1})
        if prevision:
            await appeler(client, "optimize_pump_schedule", {"feeder_id": 1, "forecast": prevision})
        preuve = await appeler(
            client,
            "prove_green_origin",
            {"node_code": "TOZ-001", "period_start": "2026-11-01T00:00:00Z", "period_end": "2026-11-02T00:00:00Z", "green_kwh": 40.0, "quota_kwh": 120.0},
        )
        if preuve:
            await appeler(client, "settle_on_chain", {"commitment_hash": preuve["commitment_hash"], "public_inputs": preuve["public_inputs"]})
        await appeler(client, "get_feeder_status", {"feeder_id": 99999})


if __name__ == "__main__":
    asyncio.run(main())