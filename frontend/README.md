# Frontend — Plateforme de régulation des télécommunications

React 19 + TypeScript + Vite, React Router, Recharts, Tailwind CSS 4. Toutes les pages lisent l'API du backend (`backend/project`).

## Démarrage
```bash
cp .env.example .env            # VITE_API_URL=http://localhost:8000/api/v1
npm install --legacy-peer-deps
npm run dev                     # http://localhost:5173
npm run build                   # tsc -b && vite build
npm run lint
```
Le backend doit tourner sur le port 8000 et l'origine du frontend doit figurer dans `CORS_ALLOWED_ORIGINS`.

## Espaces
* **Public** : accueil (chiffres réels), sondages (formulaire dynamique) et leurs résultats publics, publications et commentaires, baromètre de qualité (si publié par l'ARTEC), rapports, signalement d'un problème et suivi, pages d'information.
* **ARTEC Régulation** (`/regulation`) : comptes des opérateurs, sondages réglementaires, rapports et publication du baromètre, supervision QoS comparée, prédictions anticipées avec facteurs explicatifs, obligations et alertes algorithmiques, dossiers par opérateur, dossiers réglementaires (décisions, plans correctifs, contrôles de suivi), soumissions, mesures, seuils, réclamations, historique.
* **Opérateur** (`/operateur`) : sa qualité mesurée, sa conformité, datasets et soumissions, sondages, publications, scraping, dossiers (réponses aux demandes d'explication), contestations.
* **Administration système** (`/administration`) : tous les comptes, historique.
* **ARTEC Publications** (`/publications-admin`) : publications, sondages (validation de ceux des opérateurs), modération.

Les listes d'opérateurs, régions et indicateurs viennent de l'API : un nouvel opérateur n'exige aucune modification du code. Les rôles affichés viennent de `/auth/me/` ; les permissions réelles sont appliquées par le serveur.

## Temps réel
Les pages se mettent à jour d'elles-mêmes dès qu'une donnée change : `src/lib/realtime.ts` ouvre un WebSocket (`/ws/realtime/`), reçoit des événements « thème modifié » et recharge les ressources concernées (`useFetch`, listes, pages publiques). Si le WebSocket est indisponible, le journal d'événements est interrogé toutes les 5 s. Un badge « En direct » / « Actualisation périodique » est affiché dans l'en-tête, et les nouvelles notifications apparaissent en bulle.

## Organisation
* `src/lib/` : client API (`api.ts`), session (`auth-context.ts`, `AuthProvider.tsx`, `RequireSpace.tsx`), `useFetch.ts`, `format.ts`
* `src/components/` : mises en page (`AppLayout`, `PublicLayout`), composants de base (`ui.tsx`) et kit des espaces (`kit.tsx`)
* `src/pages/` : `Supervision`, `Predictions`, `Compliance`, `Cases`, `Surveys`, `Thresholds`, `Homes`, `Workspace` (listes), `PublicPages`, `PublicLive`
