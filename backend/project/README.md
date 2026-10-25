# Backend — Plateforme intelligente de régulation des télécommunications (Madagascar)

API REST Django / DRF pour ARTEC, YAS, AIRTEL et ORANGE. Elle se connecte au frontend React/TypeScript situé à la racine du projet.

> Si votre dossier contient un ancien `db.sqlite3` issu de `startproject`, il n'est plus utilisé (PostgreSQL est la base du projet) ; vous pouvez le supprimer.

**Principes appliqués** : le rôle et l'organisation sont toujours lus en base (jamais depuis le client) ; les querysets sont filtrés par organisation (un opérateur qui connaît l'identifiant d'une ressource concurrente reçoit **404**) ; aucune prédiction ne déclenche de décision ; aucun seuil ni aucune liste administrative « officielle » n'est livré.

## 1. Installation

Structure : `backend/.venv` (votre environnement virtuel), `backend/project/` (projet Django : `manage.py`, package `project/`, applications dans `apps/`).

### Windows (PowerShell)
```powershell
cd backend
.venv\Scripts\Activate.ps1            # votre environnement existant
cd project
pip install -r requirements.txt        # ajoute Celery, pandas, scikit-learn, etc.
copy .env.example .env                 # puis éditer les valeurs
```

### Linux / macOS
```bash
cd backend && python3 -m venv .venv && source .venv/bin/activate
cd project && pip install -r requirements.txt && cp .env.example .env
```

### PostgreSQL (obligatoire)
```sql
CREATE USER telecom_user WITH PASSWORD 'mot-de-passe-fort';
CREATE DATABASE telecom_regulation OWNER telecom_user ENCODING 'UTF8';
```
Renseignez `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_HOST`, `DB_PORT` dans `.env`. Générez `DJANGO_SECRET_KEY` avec :
`python -c "from django.core.management.utils import get_random_secret_key as g; print(g())"`

### Initialisation
```bash
python manage.py migrate
python manage.py setup_platform              # organisations + régions d'exemple + comptes initiaux
```
`setup_platform` enchaîne `init_organizations` (ARTEC, YAS, AIRTEL, ORANGE), `load_regions` (**jeu d'exemple non officiel**, option `--regions-file referentiel.json`, ou `--skip-regions`) et `init_accounts`.

**Comptes créés par `init_accounts`** (domaine modifiable : `--domain` ou `INITIAL_ACCOUNTS_DOMAIN`) :

| Email | Rôle | Espace |
|---|---|---|
| `yas@plateforme.local` | OPERATOR_USER (YAS) | Opérateur |
| `airtel@plateforme.local` | OPERATOR_USER (AIRTEL) | Opérateur |
| `orange@plateforme.local` | OPERATOR_USER (ORANGE) | Opérateur |
| `artec.regulation@plateforme.local` | ARTEC_REGULATOR | ARTEC Régulation et Prédiction |
| `artec.publications@plateforme.local` | ARTEC_PUBLISHER | ARTEC Publications |
| `admin@plateforme.local` | SYSTEM_ADMIN | Administration technique |

Aucun mot de passe n'est écrit dans le code. Si `INITIAL_ACCOUNTS_PASSWORD` (ou `--password`) n'est pas fourni, un mot de passe aléatoire est généré pour chaque compte et **affiché une seule fois** : notez-le. La commande est idempotente (un compte existant n'est pas modifié ; `--reset-passwords` régénère les mots de passe). Changez ensuite les mots de passe via `POST /api/v1/auth/change-password/`.

```bash
python manage.py createsuperuser             # facultatif : accès à /admin/
```
Format du référentiel région/ville : `{"Région": ["Ville1", "Ville2"]}`.

### Lancement
```bash
python manage.py runserver                   # http://localhost:8000
# Swagger : http://localhost:8000/api/docs/      Schéma : /api/schema/   (copie : docs/openapi.yml)
celery -A project worker -l info              # scraping, entraînement, prédictions
celery -A project beat -l info                # publications planifiées, scraping, échéances
```
Sous Windows : `celery -A project worker -l info --pool=solo`. Redis est requis (`REDIS_URL`, `CELERY_BROKER_URL`).

**Redis** : si `REDIS_URL` n'est pas défini dans `.env`, le mode développement exécute les tâches Celery de façon synchrone (pas de worker nécessaire). Pour un vrai worker, définissez `REDIS_URL`, `CELERY_BROKER_URL` et `CELERY_RESULT_BACKEND`.

### Tests
```bash
pytest                                  # 156 tests, SQLite en mémoire (rapide)
TEST_ON_POSTGRES=true pytest            # mêmes tests sur PostgreSQL (utilise DB_* ; crée « test_<DB_NAME> », l'utilisateur doit avoir CREATEDB)
# Windows PowerShell : $env:TEST_ON_POSTGRES="true"; pytest
```
Migrations, tests et un scénario complet (sondage, datasets, supervision, obligations, alertes, dossiers) ont été exécutés avec succès sur PostgreSQL 16 lors de la préparation de cette livraison.

### Frontend
Dossier `frontend/` : copiez `.env.example` en `.env` (`VITE_API_URL=http://localhost:8000/api/v1`), puis `npm install --legacy-peer-deps` et `npm run dev` (http://localhost:5173). Ajoutez l'origine du frontend à `CORS_ALLOWED_ORIGINS`.

## 2. Rôles et séparation des pouvoirs

| Rôle | Peut | Ne peut pas |
|---|---|---|
| `ARTEC_REGULATOR` — administrateur réglementaire | examiner les soumissions ; seuils QoS ; entraîner/exécuter les prédictions ; obligations, alertes, dossiers, décisions motivées, avertissements, demandes de correction, félicitations ; **créer et publier des sondages réglementaires** ; **publier rapports, consultations et le baromètre public** ; valider les sondages d'opérateurs ; **gérer les comptes des opérateurs** (création, désactivation, réinitialisation) ; traiter réclamations et contestations | gérer des comptes ARTEC ou administrateur ; publier des communications générales (réservées à ARTEC Publications) |
| `ARTEC_PUBLISHER` | publications et sondages ARTEC, validation des sondages d'opérateurs, modération | datasets, prédictions, dossiers, décisions |
| `OPERATOR_USER` (YAS/AIRTEL/ORANGE) | consulter ses données, créer des sondages (validés par l'ARTEC), importer des datasets et lancer des collectes, soumettre à l'ARTEC, déposer contestations et réponses, suivre ses engagements, avertissements et plans correctifs | voir ou modifier les ressources d'un concurrent ; examiner, décider |
| `SYSTEM_ADMIN` | gérer tous les comptes (y compris ARTEC) | toute compétence réglementaire ou éditoriale |
| Public (sans compte) | répondre aux sondages ouverts (limitation des abus), commenter, signaler un problème, consulter résultats publics, rapports et baromètre publié | — |

## 3. Endpoints (préfixe `/api/v1/`)

| Domaine | Points d'entrée principaux |
|---|---|
| `auth/` | `login/`, `refresh/`, `logout/`, `me/`, `change-password/`, `users/` (administrateur système : tous ; ARTEC Régulation : opérateurs) |
| `organizations/` | `/`, `regions/`, `cities/` (référentiel public) |
| `publications/` | `overview/`, CRUD, `{id}/publish/`, `schedule/`, `archive/`, `attachments/` ; public : `public/`, `public/{slug}/` |
| `comments/` | `POST /` (public, modéré), `GET ?publication=`, `{id}/approve|reject|hide|report/` |
| `surveys/` | CRUD, `publish/`, `approve/`, `reject/`, `close/`, `participation-token/`, `POST {id}/responses/`, `{id}/results/` |
| `datasets/` | CRUD, `{id}/versions/` (upload), `versions/{id}/validate|submit|download|preview/` |
| `submissions/` | liste, `{id}/start-review|request-correction|accept|reject/` |
| `qos/` | `measurements/`, `measurements/dashboard/` (supervision comparée), `measurements/summary/`, `measurements/metrics/`, `thresholds/`, `public/` (baromètre public), `public/settings/` (publier / retirer, ARTEC Régulation) |
| `predictions/` | `risk-types/`, `training-sets/build/`, `models/train/`, `models/compare/`, `forecast/`, `runs/`, `runs/{id}/results|export/` |
| `regulation/` | `cases/` (+ `request-explanation`, `respond`, `evidence`, `decide`, `corrective-actions`, `close`, `timeline`, `note`), `decisions/{id}/amend/`, `corrective-actions/` (+ `schedule-check`, `verify`, `update-progress`), `obligations/` (+ `evaluate`, `evaluate-all`, `evaluations`), `alerts/` (+ `acknowledge`, `dismiss`, `escalate`), `checks/` (+ `complete`), `operator-files/` et `operator-files/{code|me}/`, `overview/` |
| `complaints/` | `public/`, `public/track/`, CRUD authentifié, `messages/`, `process/`, `attachments/` |
| `scraping/` | `status/`, `sources/`, `jobs/` (+ `run/`), `records/` (+ `validate/`, `reject/`) |
| `notifications/` | liste, `{id}/read/`, `read-all/`, `unread-count/` |
| `audit/` | lecture seule |
| `realtime/` | `events/?after=<curseur>` (journal d'événements, repli et rattrapage) ; WebSocket `ws/realtime/` |

Erreurs uniformes : `{"error": {"code": "...", "message": "...", "details": ...}}`.

### Exemples
```bash
# Connexion
curl -X POST :8000/api/v1/auth/login/ -H 'Content-Type: application/json' -d '{"email":"yas@operateur.demo","password":"…"}'
# Import d'un dataset (opérateur)
curl -X POST :8000/api/v1/datasets/ -H "Authorization: Bearer $T" -H 'Content-Type: application/json' -d '{"name":"Mesures 4G sept.","data_type":"QOS_MEASUREMENT"}'
curl -X POST :8000/api/v1/datasets/1/versions/ -H "Authorization: Bearer $T" -F file=@mesures.csv
curl -X POST :8000/api/v1/datasets/versions/1/submit/ -H "Authorization: Bearer $T"
# Examen (ARTEC Régulation)
curl -X POST :8000/api/v1/submissions/1/start-review/ -H "Authorization: Bearer $R"
curl -X POST :8000/api/v1/submissions/1/accept/ -H "Authorization: Bearer $R" -H 'Content-Type: application/json' -d '{"comment":"Conforme"}'
# Participation publique à un sondage (sans compte)
curl :8000/api/v1/surveys/1/participation-token/
curl -X POST :8000/api/v1/surveys/1/responses/ -H 'Content-Type: application/json' \
  -d '{"region":1,"city":1,"location_context":"USAGE","participation_token":"…","answers":[{"question":1,"value":4}]}'
# Entraînement puis prédiction
curl -X POST :8000/api/v1/predictions/models/train/ -H "Authorization: Bearer $R" -H 'Content-Type: application/json' -d '{"name":"qos-softmax","training_dataset_version":3}'
curl -X POST :8000/api/v1/predictions/runs/ -H "Authorization: Bearer $R" -H 'Content-Type: application/json' -d '{"model_version":1,"input_dataset_version":4}'
```

## 4. Les trois grandes fonctions

### 4.1 Supervision de la QoS
`GET /qos/measurements/dashboard/?date_from=&date_to=&region=&technology=&sources=` compare les opérateurs sur : disponibilité, débits descendant et montant, latence, gigue, perte de paquets, taux de réussite des appels et des connexions, taux d'échec et de coupure.
* Par défaut, **seules les mesures techniques validées** sont utilisées ; déclarations, sondages et scraping sont comptés à part (`coverage`) et comparés aux mesures (`declared_vs_measured`).
* Aucune moyenne n'est faite entre méthodes de mesure ou unités différentes (kbps converti en Mbps à l'import) ; `comparable=false` si moins de deux opérateurs ont des mesures avec la même méthode.
* Les statuts GOOD/MEDIUM/POOR viennent des seuils configurés (`/qos/thresholds/`, origine obligatoire) ; sans seuil : « seuil non configuré ».
* Un opérateur ne voit que ses propres chiffres.
* À l'import d'un dataset, l'opérateur indique la **nature** des données : `TECHNICAL` (sondes, drive tests, speed tests, avec méthode documentée) ou `DECLARED`. L'ARTEC vérifie avant acceptation ; seules les mesures techniques servent à évaluer les engagements.
* Les questions de sondage numériques ou de satisfaction peuvent alimenter un indicateur (`qos_metric`) : les réponses deviennent des mesures de source `SURVEY` (perception), rattachées à l'opérateur évalué.

### 4.2 Prédiction anticipée des problèmes
1. `POST /predictions/training-sets/build/` {`risk_type`, `granularity`, `sources`} construit un jeu « variables de la période t → classe de la période t+1 », étiqueté par les seuils : `GENERAL_QUALITY`, `THROUGHPUT_DEGRADATION`, `AVAILABILITY_DROP`, `CONGESTION` (indicateur **indirect** : latence, gigue, perte de paquets), `THRESHOLD_BREACH`.
2. `POST /predictions/models/train/` entraîne le modèle Softmax (évaluation temporelle, avec une période d'écart pour éviter les fuites). Statut `NOT_READY` si l'historique est insuffisant.
3. `POST /predictions/forecast/` applique un modèle prêt à la dernière période de chaque opérateur × région × technologie.
Chaque résultat contient : classe prédite (`risk_label` : risque faible / modéré / élevé), probabilités des trois classes, **score de confiance** (`needs_review` sous `ML_REVIEW_CONFIDENCE`) et **facteurs explicatifs** (`top_factors` : contribution de chaque variable au logit Softmax de la classe prédite ; importance globale dans `metrics.feature_importance`).

### 4.3 Obligations réglementaires
* `Obligation` : engagement d'un opérateur (indicateur, condition ≥ / ≤, cible, **méthode de mesure de référence**, base juridique obligatoire). Aucune obligation n'est livrée : l'ARTEC les saisit.
* Évaluation (`evaluate`, `evaluate-all`, tâche Celery toutes les 6 h) sur les mesures techniques validées de la fenêtre ; sous `min_samples` : « données insuffisantes ».
* Un écart crée une **alerte algorithmique** (`ComplianceAlert`), interne à l'ARTEC Régulation, **sans valeur de décision**. Un agent peut la prendre en compte, la classer sans suite (motif obligatoire) ou l'**escalader** en dossier réglementaire. Aucune décision, aucun avertissement ni sanction n'est créé automatiquement (testé).
* Décisions formelles (avertissement, demande de correction, recommandation, félicitations officielles, absence de manquement, clôture) : motivées, datées, signées, immuables (modification motivée = nouvelle décision qui remplace l'ancienne). Un avertissement exige une demande d'explication préalable et une preuve.
* `operator-files/{code}` : dossier de suivi d'un opérateur (engagements, résultats, écarts, décisions, actions correctives, contrôles de suivi). L'opérateur consulte le sien sans voir les alertes internes.

### 4.4 Site en temps réel
Toute écriture importante (soumission, décision, alerte, sondage, publication, commentaire, mesure acceptée, notification…) publie un **événement** ciblé : thème + public concerné (`public`, `org:<id>`, `role:<RÔLE>`, `user:<id>`). Les événements **ne contiennent aucune donnée métier** : le navigateur recharge ensuite les données par l'API, qui applique les permissions habituelles.
* **WebSocket** `ws://hôte/ws/realtime/` : le client s'identifie par un premier message `{"type":"auth","token":"<jeton d'accès>"}` (le jeton n'est jamais dans l'URL) ; sans jeton, seul le public « public » est servi ; à l'expiration du jeton le canal retombe en public et le client se ré-authentifie. Les origines sont contrôlées (`CORS_ALLOWED_ORIGINS`).
* **Repli et rattrapage** : `GET /realtime/events/?after=<curseur>` renvoie les événements manqués (coupure réseau, serveur sans WebSocket, événements émis par un worker Celery). Le frontend interroge ce journal toutes les 5 s si le WebSocket est indisponible, et toutes les 30 s par sécurité s'il est connecté.
* **Lancement** : `python manage.py runserver` sert aussi les WebSockets (Daphne est dans `INSTALLED_APPS`). En production : `daphne -b 0.0.0.0 -p 8000 project.asgi:application` (ou uvicorn). Le proxy inverse doit transmettre l'en-tête `Upgrade` (nginx : `proxy_set_header Upgrade $http_upgrade; proxy_set_header Connection "upgrade";`).
* **Redis** : sans `REDIS_URL`, la diffusion WebSocket est en mémoire (un seul processus). Avec plusieurs processus ou des workers Celery qui émettent des événements, définissez `REDIS_URL` (couche `channels_redis`). Le journal HTTP rattrape de toute façon les événements non diffusés.
* Le journal est purgé automatiquement (24 h).

## 5. Formats de données attendus
* **QOS_MEASUREMENT** (CSV/XLSX/JSON) : `region, city, service_type, technology, metric_name, metric_value, unit, measurement_method, measured_at`. Indicateurs et unités admis : `apps/qos/rules.py`. À l'acceptation par l'ARTEC, les lignes valides (région/ville connues, unité cohérente) deviennent des `QoSMeasurement` validées ; les autres sont écartées.
* **LABELED_TRAINING** : `quality_class` (`GOOD|MEDIUM|POOR`), `campaign_id` (évite les fuites train/test), colonnes numériques explicatives, `observation_id` facultatif.

## 6. Prédiction Softmax : garde-fous
* Classification **multiclasse** `GOOD / MEDIUM / POOR` par régression logistique multinomiale (solveur `lbfgs`) : les probabilités des trois classes sont obtenues par la fonction **Softmax** (`predict_proba`) et leur somme vaut 1.
* Régression logistique multinomiale + `StandardScaler`, découpage `GroupShuffleSplit` par `campaign_id`.
* `NOT_READY` (avec motif) si moins de `ML_MIN_TRAINING_ROWS` lignes, une classe sous `ML_MIN_ROWS_PER_CLASS`, ou moins de `ML_MIN_GROUPS` campagnes. `LOW_QUALITY` si F1 macro < `ML_MIN_MACRO_F1`. Seul `READY` peut être exécuté.
* Métriques : accuracy, précision/rappel/F1 par classe, matrice de confusion, calibration (ECE, Brier, fiabilité par classes de confiance).
* Chaque exécution enregistre modèle, version, dataset, statut ; l'artefact est vérifié par checksum au chargement.
* Seuls les datasets **acceptés** par l'ARTEC (ou propres à l'ARTEC et valides) sont analysables.
* Les seuils du `.env` sont des garde-fous techniques à ajuster avec les experts métier, pas des valeurs réglementaires.

## 7. Sécurité : en place / à votre charge
En place : JWT courte durée (15 min), rotation et liste noire du refresh ; révocation à la modification du mot de passe ; verrouillage après 5 échecs (15 min) + limitation de débit ; mots de passe de 12 caractères minimum ; CORS restreint ; HTTPS/HSTS/cookies sécurisés dans `prod.py` ; fichiers importés stockés hors URL publique, jamais exécutés, contrôle d'extension **et** de contenu ; empreinte anonyme salée (HMAC) pour les sondages, sans IP stockée ; honeypot + jeton signé temporisé ; audit immuable avec masquage des secrets.

À votre charge / limites connues :
* **Scraping** : la résolution DNS est vérifiée avant chaque requête mais pas « épinglée » ; exécutez le worker dans un réseau sans accès aux ressources internes. `SCRAPING_ALLOWED_DOMAINS` vide = scraping désactivé (état explicite). Vérifiez les conditions d'utilisation de chaque source.
* Le jeton de renouvellement est conservé côté frontend en `sessionStorage` (pas de cookie) ; adaptez si votre politique exige des cookies `HttpOnly`.
* Pas d'antivirus sur les pièces jointes ; pas de CAPTCHA (à ajouter si les sondages sont attaqués).
* Sauvegarde : `pg_dump -Fc telecom_regulation > backup.dump` ; restauration : `pg_restore -d telecom_regulation --clean backup.dump` ; sauvegardez aussi `PRIVATE_MEDIA_ROOT`.
* Planifiez `python manage.py deactivate_inactive_users --days 180`.
* Les connexions de nombreux utilisateurs derrière une même adresse (réseaux mobiles à adresse partagée) comptent dans les limitations par IP : ajustez les débits dans `REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"]` selon votre trafic.
* Un opérateur connecté qui consulte `/surveys/` voit ses propres sondages (vue de gestion) ; l'espace public appelle l'API sans jeton.
