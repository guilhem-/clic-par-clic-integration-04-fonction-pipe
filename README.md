# Le studio comme un modèle — fonction Pipe Open WebUI, déroulé fixé par le code

Code et configuration de la démonstration du module 4 de la série « Clic par clic » **Intégrations IA**
(Open WebUI relié au studio 3D de l'organisation).

Vidéo : {{video}}

## But

Aux modules 1 à 3, le studio était un **outil** : le modèle de l'assistant décidait de l'appeler, ou
non. Ici, le studio devient lui-même un **modèle**, « Studio 3D », à choisir dans le sélecteur d'Open
WebUI. C'est une **fonction Pipe** : à chaque message, son code fixe le déroulé.

```
message ─▶ Pipe ─GET /api/assets─▶ studio            (la bibliothèque, ajoutée aux consignes)
           Pipe ─generate_chat_completion─▶ modèle de langage de l'instance ─▶ titre + script
           Pipe : verifier(script)  ── refusé ──▶ l'erreur repart au modèle, qui corrige
           Pipe ─POST /api/soumettre─▶ studio        (au nom de l'utilisateur)
           Pipe ─GET /api/etat/<n> toutes les 2 s─▶ studio ─▶ événements « status » dans la conversation
           Pipe ─▶ réponse : image, objet 3D (artefact), scène Blender, assets, marquage
```

Contenu, à l'état montré en fin de vidéo :

| Fichier | Rôle |
|---|---|
| `open-webui/studio_pipe.py` | La fonction Pipe (gardée sous la forme reformatée par Open WebUI à l'enregistrement) : vannes (adresse interne du studio, jeton en champ masqué, modèle qui écrit le code, essais), `pipes()` (le modèle `studio_3d.studio` du sélecteur), consignes (pièges connus et bibliothèque d'assets), boucle des essais (`ecrire` → `generate_chat_completion`, `decouper`, `verifier`, `corriger`), soumission et suivi (`suivre`, événements `status`), réponse finale (`reponse`). Les tâches d'Open WebUI (titre, suggestions) vont directement au modèle de langage, sans rendu |
| `studio/integrations.py` | Côté studio, routes internes protégées par le jeton du studio et l'adresse de l'utilisateur : `/api/assets` (bibliothèque : nom, libellé, dimensions), `/api/soumettre` (même file que l'outil MCP, scène Blender prévue), `/api/etat/<n>` (état de sa demande seulement : position, worker, puis image, objet 3D, scène, assets, marquage). Les routes `/s/` et `/api/suivi` servent au module 3 |
| `installer.py` | La fonction, ses vannes, son activation et l'accès au modèle (groupe), par l'API d'Open WebUI (`--retirer` pour tout retirer) |

## Prérequis

- Le studio 3D dans sa dernière version, déployé dans le même cluster qu'Open WebUI : dépôt
  [clic-par-clic-studio3d-06-stockage-s3](https://github.com/guilhem-/clic-par-clic-studio3d-06-stockage-s3)
  (image `studio3d:5`, Redis, workers, bibliothèque d'assets, stockage S3).
- Open WebUI 0.11 (tourné sur 0.11.3), un compte **administrateur** et son jeton ; un groupe
  d'utilisateurs (« Graphistes » dans la vidéo) ; un modèle de l'instance pour écrire le code.
- Python 3.10 ou plus récent (bibliothèque standard seulement) pour `installer.py`.

## Installation pas à pas

### 1. Les routes du studio

`integrations.py` s'ajoute à l'image du studio : `api.py` le charge s'il est présent. Dans le dépôt du
module 6 de la série Studio 3D :

```bash
cp studio/integrations.py ../clic-par-clic-studio3d-06-stockage-s3/studio/
# Dockerfile : COPY commun.py api.py travailleur.py … integrations.py ./
docker build -t studio3d:5 ../clic-par-clic-studio3d-06-stockage-s3/studio
k3d image import studio3d:5 -c <votre cluster>     # avec k3d ; sinon, poussez l'image dans votre registre
kubectl rollout restart deployment/studio-api -n studio3d
```

Ces routes restent internes au cluster : aucun Ingress ne les publie.

### 2. À la main, comme dans la vidéo

1. **Panneau d'administration › Fonctions › Créer** : nom « Studio 3D » (l'identifiant `studio_3d` s'en
   déduit) ; collez le contenu de `open-webui/studio_pipe.py` dans l'éditeur ; **Enregistrer & Créer**,
   puis **Confirmer** (une fonction exécute du code sur le serveur).
2. Dans la liste des fonctions, activez « Studio 3D », puis ouvrez ses **Vannes** : l'adresse interne du
   studio est proposée par défaut ; collez le jeton du studio (champ masqué) ; indiquez l'identifiant du
   modèle qui écrit le code ; **Enregistrer**.
3. **Réglages › Modèles** : cherchez « Studio 3D » (« Privé » : administrateurs seuls) ; **Modifier** ›
   **Accès** › ajoutez le groupe ; **Enregistrer & Mettre à jour**.

### 3. Ou par le script

```bash
cp .env.example .env          # OWUI_URL, OWUI_JETON, STUDIO_URL, STUDIO_JETON, MODELE_CODE, GROUPE
python installer.py           # fonction, vannes, activation, accès au modèle
python installer.py --retirer # retire le modèle et la fonction
```

## Essai

Avec le compte d'un membre du groupe, choisissez « Studio 3D » dans le sélecteur de modèles, puis :
« Le bureau métallique de la bibliothèque, avec la lampe de bureau posée dessus et une tasse rouge à
côté, sous l'éclairage studio doux. » Sous le nom du modèle, l'état défile : lecture de la bibliothèque,
écriture du code, file d'attente, calcul sur un worker. Puis la réponse : l'image, l'objet 3D en
artefact, le lien « Télécharger la scène Blender », les assets utilisés et le marquage.

La vérification se lit aussi à la main :

```python
import sys; sys.path.insert(0, "open-webui")
from studio_pipe import verifier
verifier('charger_asset("canape")', {"bureau_metal", "lampe_bureau"})
# 'Assets absents de la bibliothèque : canape'
```

## Outil ou modèle Pipe ?

| | Outil MCP (modules 1 à 3) | Modèle Pipe (ce module) |
|---|---|---|
| Qui décide du déroulé | le modèle de l'assistant | le code de la fonction |
| Plusieurs services dans la même conversation | oui | non : chaque message part au studio |
| Erreurs de code | à la charge du modèle | vérifiées, renvoyées au modèle, corrigées |
| Suivi | widget (module 3) ou message direct (module 2) | événements `status`, poussés par le Pipe |

## Sécurité

- Le jeton du studio reste dans les vannes de la fonction, sur le serveur d'Open WebUI (champ masqué).
- Le Pipe appelle le studio au nom de l'utilisateur connecté (`X-Utilisateur-Email`) ; `/api/etat` ne
  renvoie que ses propres demandes.
- Le modèle de langage est appelé par `generate_chat_completion`, avec les droits de l'utilisateur.
- Aucun secret dans ce dépôt (`.env` est ignoré par git).

## Série

- Module précédent : **Un widget de suivi dans la conversation** —
  [clic-par-clic-integration-03-widget-suivi](https://github.com/guilhem-/clic-par-clic-integration-03-widget-suivi).
- Module suivant : **Un bouton sous chaque réponse : une fonction Action** —
  [clic-par-clic-integration-05-fonction-action](https://github.com/guilhem-/clic-par-clic-integration-05-fonction-action).
- Construire le studio : série « Créer un service d'IA compatible agentique : le studio 3D »
  (dépôts `clic-par-clic-studio3d-01` à `06`).

## Licence

MIT (voir `LICENSE`).
