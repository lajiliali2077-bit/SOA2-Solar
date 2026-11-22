# Notes Rôle 3 : GraphQL, dashboard, n8n

## Semaine 1 : GraphQL
- GraphQL (strawberry-django) expose feeders, nœuds, mesures et anomalies, plus un graphe de charge d'un feeder (somme de GRID_NET_KW des nœuds, en pourcentage de capacity_kw). Intérêt : une seule requête au lieu de plusieurs appels REST.
- Chaque requête est filtrée selon le rôle de l'utilisateur (session Django ou jeton JWT) : admin et agent voient tout, l'auditeur son gouvernorat, un membre de coopérative ses seuls nœuds. Sans jeton, les listes sont vides.
- is_injected_anomaly n'est pas exposé : c'est la vérité terrain du simulateur, que le ML ne doit pas lire.
- Les listes sont plafonnées (limit max 1000) pour ne pas renvoyer des dizaines de milliers de mesures.
- La route /graphql/ est exemptée de CSRF pour permettre les appels par jeton JWT (Streamlit). Le schéma n'a que des lectures. L'authentification par session reste possible pour tester dans GraphiQL ; si des mutations sont ajoutées, ce choix devra être réexaminé.
- Test : Feeder-TOZ-01 atteint un pic de 98,8 % de sa capacité (45 kW), au-dessus du seuil de 92 %.