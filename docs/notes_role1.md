# Notes du Rôle 1 (Ali) : données, ML, infra et documentation

Journal de travail pour les slides et la défense orale individuelle.
**À mettre à jour à chaque push** : ajouter une entrée en haut de « Journal », cocher la liste d'avancement, et commiter ce fichier avec le reste du travail.

## Comment mettre à jour ce fichier (30 secondes)

1. Copier le modèle d'entrée ci-dessous en tête de la section « Journal ».
2. Le remplir : ce qui a été fait, pourquoi ce choix, ce qui n'est pas vérifié.
3. Cocher l'objectif concerné dans « Avancement ».
4. Ajouter dans « Pour la défense » une question probable et sa réponse en une phrase, si l'incrément en suggère une.
5. Commiter ce fichier avec le reste (même commit, même push).

### Modèle d'entrée

```
### Incrément N : titre court (AAAA-MM-JJ, branche xxx)
- Fait : ...
- Pourquoi : ...
```

## Avancement des objectifs du Rôle 1

- [x] 1a. Spec de la migration 0002 dans `docs/models.md`
- [x] 1b. `models.py` et migration 0002 (appliquée et testée en local)
- [x] 2a. Stub de `forecast_peak_load` (contrat d'interface respecté, tests automatisés)
- [ ] 2b. Vrai modèle de prévision (profil horaire moyen des jours précédents + ajustement)
- [ ] 3. Anomalies de nœud (IsolationForest) : type, sévérité, enregistrement dans `detect_anomalies`
- [ ] 4. gRPC : `run_agent` sur anomalie CRITICAL, branchement de `TriggerUrgentAudit`
- [ ] 5. Docker : Dockerfile en Python 3.14, `.dockerignore`, service de l'application, README (facteur d'émission sourcé, tarifs signalés non officiels)
- [ ] 6. UML de classes (Mermaid), diagramme de séquence, schéma d'architecture, assemblage des slides et de la vidéo, fusion dans `main`

## Journal (le plus récent en haut)

### Incrément 3 : stub de forecast_peak_load (2026-11-14, branche role1-data)
- Fait : création de `agent/skills/irradiance_forecaster.py` avec la signature du contrat d'interface, et de ses 8 tests unittest. Le stub ne lit pas la base : il renvoie un profil déterministe sur 24 h (production solaire en cloche, pic de consommation en soirée à 96 % d'une capacité supposée de 100 kW).
- Pourquoi : les Rôles 2 et 4 attendent la signature pour brancher le serveur MCP et l'agent, et un stub sans accès à la base ne les bloque pas. Le pic à 96 % donne à l'agent une surcharge à corriger pour exercer sa boucle d'auto-correction. `load_kw` est la charge nette (somme des `GRID_NET_KW`) parce que c'est celle comparée au seuil de 92 % ; `forecasted_deficit_24h_kwh` est l'énergie au-dessus de ce seuil, ce que l'optimiseur doit déplacer.

### Incrément 2 : `models.py` et migration 0002 (2026-11-14, branche role1-data)
- Fait : ajout de `PumpSchedule`, `NetMeteringSettlement` et `CarbonCredit` dans `models.py`. `isolation_forest_score` devient nullable et `is_verified_on_chain` passe à `False` par défaut. Migration générée : `0002_pumpschedule_settlement_carboncredit`.
- Pourquoi ce choix :
  - Une seule migration pour tous les changements, afin que les autres n'aient à refaire leur base qu'une fois.
  - Les règles d'intégrité sont dans la base (contraintes), pas seulement dans le code Python : elles protègent aussi contre une écriture directe en SQL.
  - Un règlement est unique par (nœud, période) pour que l'agent puisse réessayer sans créer de doublon.
  - `CarbonCredit` copie le facteur d'émission utilisé, ce qui rend le calcul reproductible même si `.env` change.
  - Règlements en PROTECT sur le nœud pour ne pas perdre d'historique financier.
- Testé : `python manage.py check` sans erreur, `makemigrations` (fichier conforme à la spec), `migrate`. Essais volontairement invalides, annulés ensuite par une transaction : règlement incohérent refusé, fin avant début refusée, facteur d'émission nul refusé, planning avec puissance négative refusé, score ML vide accepté, défaut `is_verified_on_chain = False` confirmé.
- Non vérifié / limite : le test d'unicité (nœud, période) a échoué à cause d'une erreur de saisie dans la console, il est à refaire et à confirmer ici. Un passage d'agent produit au plus un reçu, car `OnChainZKReceipt.agent_execution` est un OneToOne : régler plusieurs nœuds demande plusieurs passages. Le point « qui écrit les lignes de règlement et de crédit en base » reste à confirmer avec le groupe.
- Impact sur les autres rôles : les Rôles 2, 3, 4 et 5 peuvent coder contre les nouveaux modèles après `git pull` puis `python manage.py migrate` dans `backend`.

### Incrément 1 : spec de la migration 0002 dans `docs/models.md` (2026-11-14, branche role1-data)
- Fait : spécification des trois nouveaux modèles, des deux champs modifiés, du diagramme Mermaid mis à jour, et d'une table de correspondance entre les dictionnaires des contrats d'interface et les champs de la base.
- Pourquoi ce choix : le `.md` est poussé avant le code, comme l'exige la règle d'équipe, pour que les autres puissent coder contre les noms de champs avant la migration. Aucun nouveau type d'anomalie n'était nécessaire : `AnomalyType` contenait déjà les types de nœud.
- Testé : relecture du diff (seules les lignes prévues changent). Le rendu du diagramme Mermaid n'a pas été vérifié sur mermaid.live.
- Non vérifié / limite : le point « qui crée quoi » (règlement, crédit carbone, reçu) est marqué « à confirmer par le groupe » dans le fichier.
- Impact sur les autres rôles : ils ont reçu le message de prévenance avant le code de `models.py`.

## Décisions de conception à pouvoir expliquer

- **Argent en millimes entiers** : pas d'erreurs d'arrondi sur les montants. Les kWh restent en nombres à virgule.
- **Horodatages en UTC** : une seule référence de temps pour la télémétrie, les plannings et les règlements. La conversion en heure de Tunis se fait à l'affichage.
- **Charge d'un feeder = somme des `GRID_NET_KW` de ses nœuds** : positif = import, négatif = export. Elle n'est pas stockée, elle se calcule à la demande.
- **Le ML ne lit jamais `is_injected_anomaly`** : cette étiquette sert uniquement à calculer précision, rappel et F1.
- **Un seul propriétaire par fichier** : évite les conflits de fusion. Les modèles et migrations ne passent que par le Rôle 1.

## Pour la défense : questions probables et réponses courtes

- Pourquoi des contraintes en base et pas seulement des validateurs Django ?
  Les validateurs ne s'exécutent que si on passe par les formulaires ou `full_clean()`. Les contraintes de la base protègent aussi contre une insertion directe ou un bug d'un autre module.
- Pourquoi stocker le facteur d'émission dans `CarbonCredit` ?
  Pour qu'un crédit calculé hier reste vérifiable même si la variable d'environnement change demain.
- Pourquoi `isolation_forest_score` peut-il être vide ?
  Parce que la surcharge de feeder (> 92 %) est détectée par une règle déterministe, qui ne produit pas de score ML.
- Que se passe-t-il si l'agent réessaie un règlement ?
  La contrainte d'unicité (nœud, période) refuse le doublon : l'agent doit mettre à jour la ligne existante.

## Points ouverts

- Qui écrit les lignes `NetMeteringSettlement` et `CarbonCredit` ? Proposition : Rôle 4 (agent), avec le calcul du règlement fourni par le Rôle 2 et le calcul du CO2 par le Rôle 5. À confirmer.
- Tarifs de seed : illustratifs, à signaler comme non officiels dans le README.
- Facteur d'émission du réseau tunisien : à sourcer dans le README.