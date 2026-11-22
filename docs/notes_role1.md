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
- [x] 2b. Vrai modèle de prévision (profil horaire moyen des jours précédents + ajustement)
- [x] 3. Anomalies de nœud (IsolationForest) : type, sévérité, enregistrement dans `detect_anomalies` (Semaine 2)
- [x] 4. gRPC : `run_agent` sur anomalie CRITICAL, branchement de `TriggerUrgentAudit`
- [x] 4b. Déclenchement automatique de l'agent sur les incidents CRITICAL après la détection, `agent_trigger.py` (Semaine 2)
- [x] 5. Docker (Dockerfile, compose, démarrage vérifié) et README (facteur d'émission sourcé, tarifs signalés non officiels) (Semaine 2)
- [x] 5b. Évaluation du ML documentée : précision 0,88, rappel 0,79, F1 0,83 ; règle feeder F1 1,0 (Semaine 2)
- [x] 5c. Rapport et README présentés par semaine (Semaine 2 en tête) (Semaine 2)
- [ ] 6a. UML de classes (Mermaid, à partir de `docs/models.md`)
- [ ] 6b. Diagramme de séquence de la chaîne complète
- [ ] 6c. Schéma d'architecture
- [ ] 6d. Assemblage des slides (`.pptx` et `.pdf`) et de la vidéo
- [ ] 6e. Fusion des branches dans `testmain` puis `main`
- [ ] 7. Test de bout en bout avec l'agent du Rôle 4 (`run_agent`, `TriggerUrgentAudit`)
- [ ] 8. Démarrage en une commande `docker compose up` (critère 6.2 de l'énoncé)

## Prochaines étapes

### Semaine 3 (Rôle 1)

- [ ] **Diagrammes** : UML de classes (6a), séquence (6b : simulateur → gRPC → détection → agent → optimiseur → preuve ZK → règlement), architecture (6c).
- [ ] **Test de bout en bout avec l'agent de Mouin** (7) : relancer `detect_anomalies`, vérifier qu'une `AgentLoopExecution` est créée par incident, puis tester `TriggerUrgentAudit` avec un petit client gRPC.
- [ ] **Vérifier le contrat gRPC de l'énoncé** : flux client `StreamTelemetry` et champ de signature HMAC (signalés « à vérifier » dans l'annexe D du README).
- [ ] **Tests automatisés** pour `detect_anomalies` et `agent_trigger.py` (aujourd'hui vérifiés à la main seulement).
- [ ] **Trancher le point ouvert** « qui écrit `NetMeteringSettlement` et `CarbonCredit` » avec le groupe.
- [ ] **Valider le facteur d'émission** avec l'équipe, le revérifier à la source IEA, puis le communiquer au Rôle 5.
- [ ] **Intégration** : fusionner les branches dans `testmain`, résoudre les conflits, relancer l'installation de zéro sur une machine propre.
- [ ] *(Optionnel, avec le Rôle 3)* Météo réelle via n8n et Open-Meteo pour la prévision (§ 4.11 du README).

### Semaine 4 (Rôle 1)

- [ ] **`docker compose up` en une commande** (8) : lever la règle provisoire « toujours nommer les services ».
- [ ] **README final** : compléter avec les parties des Rôles 2 à 5, mettre à jour l'annexe D et les tableaux de la Semaine 4.
- [ ] **Slides** (`.pptx` et `.pdf`) : UML de classes et de séquence, schéma d'architecture, matrices de comparaison des protocoles et de l'architecture, captures d'écran, tableau des métriques (précision, rappel, F1).
- [ ] **Vidéo** (`.mp4`, 5 à 10 minutes) : flux gRPC en direct, détection d'anomalie, boucle de l'agent, règlement on-chain, tableau de bord.
- [ ] **Remise** : archive unique (`.zip` ou `.rar`), objet du message `[DS22026-2027-Track#7]SolarSouk-STEG-[Section]-[GroupNumber&Members]`.
- [ ] **Préparation de la défense orale** : relire ce journal, répéter les réponses de « Pour la défense ».

## Journal (le plus récent en haut)

### Semaine 2 — Objectif 5c : rapport et README par semaine (2026-11-22)
- Fait : le README est reconstruit à partir de l'ancienne version, avec une section « Avancement de la Semaine 2 » en tête (tableau par rôle, détail, résultats, barème, décisions) ; ajout du § 4.12, des compléments du § 4.7, de l'étape 4 de l'annexe C et de questions de défense. Le rapport (version 3) a la même forme : Partie A (Semaine 2) puis Partie B (rapport complet, Semaine 1 conservée).
- Pourquoi : l'équipe doit présenter son avancement semaine par semaine. Les tableaux de la Semaine 1 gardent leur état d'origine, avec une note qui renvoie vers la Semaine 2, pour que chaque semaine reste lisible séparément.
- Recherches : facteur d'émission proposé 0,468 kgCO₂/kWh (moyenne IEA citée par le rapport EPIC Deploy sur la Tunisie, 2026) ; alternative 0,483 (Electricity Maps 2025, citée par le rapport carbone 2025 du groupe Qair). Aucune norme externe ne fixe le seuil de 92 % : il vient de l'énoncé.
- Corrigé au passage : la pointe de Tozeur est à 19 h–20 h 15 **heure de Tunis** (le simulateur travaille en heure locale), soit 18 h–19 h 15 UTC ; l'ancien README disait « UTC ».
- Non vérifié / limite : la page IEA d'origine n'a pas pu être ouverte, le facteur d'émission est à revérifier à la source. Les lignes des Rôles 2 à 5 restent à compléter par leurs auteurs. Le message réel de l'agent (S2.4) est à coller après exécution.

### Semaine 2 — Objectif 4b : déclenchement automatique de l'agent (2026-11-22)
- Fait : nouveau module `agent_trigger.py` dans `tunisovereign_core`, appelé en dernière étape de `detect_anomalies`. Il lance `run_agent(anomaly_id)` sur les incidents CRITICAL. `server.py` est inchangé : `TriggerUrgentAudit` continue de fonctionner à la demande.
- Pourquoi ce choix :
  - Un **incident** = les anomalies CRITICAL d'un même nœud (ou feeder) le même jour ; l'agent est lancé une fois par incident, sur sa première anomalie. 62 anomalies CRITICAL (42 surcharges feeder et 20 anomalies de nœud) ne donnent donc pas 62 exécutions.
  - **Idempotent** : un incident dont une anomalie a déjà une `AgentLoopExecution` n'est jamais relancé.
  - **Borné** : 5 exécutions par lancement, les plus récentes d'abord (`--max-agent-runs`) ; `--no-agent` désactive le déclenchement.
  - **Sans plantage** : si `agent.langgraph_agent.run_agent` n'existe pas (`ImportError`), un message indique le nombre d'incidents en attente. Pas d'exécution factice, comme pour `TriggerUrgentAudit` (même raison : ne pas polluer le tableau de bord).
  - Logique placée dans un module à part plutôt que dans `server.py`, pour la réutiliser depuis la commande sans importer le serveur gRPC.
- Testé : la commande `detect_anomalies --clear` s'exécute sans erreur (après correction de l'emplacement du fichier : `agent_trigger.py` va dans `tunisovereign_core/`, pas dans `management/commands/`).
- Non vérifié / limite : aucun appel réel de `run_agent` (l'agent n'existe pas encore) ; pas de test automatisé. L'idempotence suppose que l'agent enregistre l'anomalie dans `AgentLoopExecution.anomaly` : sinon l'incident serait relancé à chaque exécution.
- Impact sur les autres rôles : **Rôle 4 (Mouin)** : `run_agent(anomaly_id)` doit retourner l'identifiant de l'`AgentLoopExecution` créée et renseigner son champ `anomaly`.

### Semaine 2 — Objectif 3 : anomalies de nœud en base (2026-11-22)
- Fait : dans `ml_anomaly.py`, nouvelle méthode `detect_node_anomalies_from_db` et fonction `classify_node_anomaly` ; dans `detect_anomalies.py`, enregistrement des anomalies de nœud (score, version `isoforest-v1`) et options `--skip-ml`, `--no-agent`, `--max-agent-runs`. Résultat : 202 anomalies de nœud, plus 42 surcharges feeder, soit **244 événements**.
- Pourquoi ce choix :
  - **Type par règles** : l'IsolationForest dit qu'une mesure est inhabituelle, pas pourquoi. Le type vient de règles lisibles : tension hors 220 V ± 6 % (`VOLTAGE_OUT_OF_RANGE`), batterie sous 10 % (`SOC_INCONSISTENT`), production quasi nulle entre 10 h et 15 h (`INVERTER_FAILURE`), pompe hors fenêtre 10 h–15 h (`PUMP_MISALIGNED`), sinon la mesure la plus atypique décide.
  - **Sévérité par rang** : le score d'un IsolationForest n'a pas d'échelle absolue. Les 10 % les plus extrêmes sont CRITICAL, les 30 % suivants MEDIUM, le reste LOW.
  - **Rattachée au nœud, feeder vide** : le feeder reste réservé aux surcharges de niveau feeder.
  - **Idempotent** : `update_or_create` sur (nœud, horodatage, type) ; relancer la commande ne crée pas de doublons.
  - Seuil de batterie corrigé après lecture du simulateur : l'anomalie injectée met la batterie à 1–4 % (et non hors de 0–100 %) ; la règle teste donc « sous 10 % ».
- Testé : exécution locale de `detect_anomalies --clear` : 42 surcharges, 202 anomalies de nœud, 244 au total. Évaluation : IsolationForest précision 0,88, rappel 0,79, F1 0,83 (224 anomalies injectées, 202 signalées, 177 correctes, 25 fausses alertes, 47 manquées) ; règle feeder précision 1,0, rappel 1,0. Répartition par type : `PUMP_MISALIGNED` 130, `INVERTER_FAILURE` 29, `SOC_INCONSISTENT` 28, `VOLTAGE_OUT_OF_RANGE` 15 ; par sévérité : LOW 121, MEDIUM 61, CRITICAL 20.
- Non vérifié / limite : les règles de type sont écrites d'après ce que le simulateur injecte, le F1 mesure la détection et non l'exactitude du type. `PUMP_MISALIGNED` domine car les pompes de Tozeur tournent le soir pendant la surcharge. Pas de test automatisé de la commande. Le F1 mesuré est 0,83 ; l'estimation de la Semaine 1 (≈ 0,85) est abandonnée.
- Impact sur les autres rôles : la base contient désormais 244 événements et non plus 42. **Rôle 3 (Adem)** : le contrôle « 42 anomalies attendues » doit filtrer `anomaly_type = FEEDER_OVERLOAD` ; les graphes et la carte peuvent exploiter les 202 anomalies de nœud (types et sévérités). **Rôle 2 (Mohamed)** : `/api/v1/anomalies` renvoie aussi ces événements.

### Objectif 4 : gRPC et déclenchement de l'agent à la demande (Semaine 1)
- Fait : TriggerUrgentAudit appelle run_agent avec un repli propre.
- Pourquoi pas d’exécution factice en repli : on évite de polluer le tableau de bord avec de fausses exécutions.

### Objectif 2b : vrai modèle de prévision (Semaine 1)
- Fait : prévision par profil médian au pas de 15 minutes, avec 12 tests sans base de données.
- Pourquoi la médiane : elle résiste aux valeurs aberrantes. Pourquoi le pas de 15 minutes : la moyenne horaire noie le pic de Tozeur.
- Limite connue : pas d’ajustement de tendance, et pas de test sur la lecture de la base (feeder inconnu, nœud sans mesures).

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
- **Type d'anomalie par règles, sévérité par rang** : le ML signale l'inhabituel, des règles lisibles le nomment, et le rang du score fixe la gravité (10 % CRITICAL, 30 % MEDIUM, 60 % LOW).
- **Un incident = un nœud (ou feeder) et un jour** : l'agent est lancé une fois par incident, jamais deux fois pour le même, et au plus 5 fois par lancement.
- **Détection idempotente** : relancer `detect_anomalies` donne le même résultat, sans doublons.

## Pour la défense : questions probables et réponses courtes

- Pourquoi des contraintes en base et pas seulement des validateurs Django ?
  Les validateurs ne s'exécutent que si on passe par les formulaires ou `full_clean()`. Les contraintes de la base protègent aussi contre une insertion directe ou un bug d'un autre module.
- Pourquoi stocker le facteur d'émission dans `CarbonCredit` ?
  Pour qu'un crédit calculé hier reste vérifiable même si la variable d'environnement change demain.
- Pourquoi `isolation_forest_score` peut-il être vide ?
  Parce que la surcharge de feeder (> 92 %) est détectée par une règle déterministe, qui ne produit pas de score ML.
- Que se passe-t-il si l'agent réessaie un règlement ?
  La contrainte d'unicité (nœud, période) refuse le doublon : l'agent doit mettre à jour la ligne existante.
- Comment le type et la sévérité d'une anomalie de nœud sont-ils décidés ?
  Le type vient de règles lisibles (tension, production, pompe, batterie) appliquées aux mesures que l'IsolationForest a jugées inhabituelles ; la sévérité vient du rang du score : 10 % CRITICAL, 30 % MEDIUM, le reste LOW.
- Pourquoi le F1 de l'IsolationForest est-il de 0,83 et pas 1 ?
  Sur 224 anomalies injectées, il en retrouve 177 (rappel 0,79) et fait 25 fausses alertes (précision 0,88) : le taux d'anomalies attendu (3 %) est une hypothèse de départ.
- Pourquoi la règle de surcharge a-t-elle un F1 de 1,0 ?
  Le simulateur injecte une surcharge nette au-dessus du seuil de 92 % ; la règle la retrouve exactement (42 sur 42). C'est le résultat sur données simulées, pas sur un vrai réseau.
- Pourquoi autant d'événements `PUMP_MISALIGNED` ?
  Pendant la surcharge de Tozeur, les pompes tournent le soir, hors de la fenêtre solaire 10 h–15 h : la règle les étiquette ainsi, ce n'est pas une erreur.
- Pourquoi lancer l'agent une seule fois par incident ?
  62 anomalies CRITICAL décrivent peu d'incidents distincts ; on regroupe par nœud ou feeder et par jour pour ne pas lancer l'agent 62 fois, et on ne relance jamais un incident déjà traité.
- Que veut dire « idempotent » ?
  Relancer la commande donne le même résultat sans créer de doublons : c'est ce qui rend les démonstrations reproductibles.

## Points ouverts

- Qui écrit les lignes `NetMeteringSettlement` et `CarbonCredit` ? Proposition : Rôle 4 (agent), avec le calcul du règlement fourni par le Rôle 2 et le calcul du CO2 par le Rôle 5. À confirmer.
- ~~Tarifs de seed : illustratifs, à signaler comme non officiels dans le README.~~ Résolu (Semaine 2) : signalé dans le README et le rapport.
- Facteur d'émission du réseau tunisien : valeur proposée 0,468 kgCO₂/kWh (IEA, via le rapport EPIC Deploy 2026), alternative 0,483 (Electricity Maps 2025). **À valider par l'équipe**, à revérifier à la source IEA, puis à communiquer au Rôle 5 (lecture dans `.env`).
- `run_agent` (Rôle 4) doit retourner l'identifiant de l'`AgentLoopExecution` et renseigner son champ `anomaly`, sinon l'idempotence de `agent_trigger.py` ne fonctionne pas. À confirmer avec Mouin.
- Contrat gRPC de l'énoncé : flux client `StreamTelemetry` et champ de signature HMAC à vérifier.
- Types d'anomalie de nœud : règles écrites d'après le simulateur ; à revoir si le simulateur change.