"""Le studio comme un modèle : la fonction Pipe « Studio 3D » d'Open WebUI.

Fait ce que le module 4 de la série « Intégrations IA » montre à l'écran :
  1. la fonction « Studio 3D » (open-webui/studio_pipe.py), identifiant studio_3d ;
  2. ses vannes : adresse interne du studio, jeton du studio (lu dans .env, jamais affiché),
     modèle de l'instance qui écrit le script de la scène ;
  3. la fonction activée ;
  4. son modèle, studio_3d.studio, réservé au groupe d'utilisateurs (« Graphistes »).

Côté studio, les routes /api/assets, /api/soumettre et /api/etat/<n> sont dans
studio/integrations.py (voir README.md).

Usage :
  python installer.py              # installe (ou met à jour)
  python installer.py --retirer    # retire le modèle et la fonction

Réglages : fichier .env (voir .env.example) ; les variables d'environnement l'emportent.
Aucune dépendance : Python 3.10 ou plus récent, bibliothèque standard seulement.
"""
import json
import os
import pathlib
import sys
import urllib.error
import urllib.request

ICI = pathlib.Path(__file__).resolve().parent
FONCTION = {"id": "studio_3d", "nom": "Studio 3D"}
MODELE = f"{FONCTION['id']}.studio"  # identifiant de la fonction + identifiant renvoyé par pipes()


def reglages() -> dict:
    """Lit .env (clé=valeur), puis l'environnement, qui l'emporte."""
    r = {"STUDIO_URL": "http://studio.studio3d.svc.cluster.local:8000", "GROUPE": "Graphistes", "ESSAIS": "3"}
    env = ICI / ".env"
    if env.exists():
        for ligne in env.read_text(encoding="utf-8").splitlines():
            ligne = ligne.strip()
            if ligne and not ligne.startswith("#") and "=" in ligne:
                cle, valeur = ligne.split("=", 1)
                r[cle.strip()] = valeur.strip()
    for cle in ("OWUI_URL", "OWUI_JETON", "STUDIO_URL", "STUDIO_JETON", "MODELE_CODE", "GROUPE", "ESSAIS"):
        if os.environ.get(cle):
            r[cle] = os.environ[cle]
    return r


R = reglages()


def api(methode: str, chemin: str, corps=None, ok404: bool = False):
    """Appel de l'API d'Open WebUI avec le jeton administrateur."""
    req = urllib.request.Request(R["OWUI_URL"].rstrip("/") + chemin, method=methode,
                                 data=None if corps is None else json.dumps(corps).encode(),
                                 headers={"Content-Type": "application/json", "Authorization": f"Bearer {R['OWUI_JETON']}"})
    try:
        with urllib.request.urlopen(req, timeout=60) as rep:
            texte = rep.read().decode()
    except urllib.error.HTTPError as e:
        if ok404 and e.code in (400, 401, 404):
            return None
        sys.exit(f"{methode} {chemin} : {e.code} {e.read().decode()[:300]}")
    return json.loads(texte) if texte else None


def groupe() -> str:
    for g in api("GET", "/api/v1/groups/") or []:
        if g["name"] == R["GROUPE"]:
            return g["id"]
    sys.exit(f"groupe « {R['GROUPE']} » absent : créez-le (Panneau d'administration › Utilisateurs › Groupes)")


# ---------------------------------------------------------------- 1 à 3. La fonction, ses vannes, son activation

def fonction() -> None:
    corps = {"id": FONCTION["id"], "name": FONCTION["nom"],
             "content": (ICI / "open-webui" / "studio_pipe.py").read_text(encoding="utf-8"),
             "meta": {"description": "Le studio 3D comme un modèle", "manifest": {}}}
    if api("GET", f"/api/v1/functions/id/{FONCTION['id']}", ok404=True):
        api("POST", f"/api/v1/functions/id/{FONCTION['id']}/update", corps)
        print(f"fonction « {FONCTION['nom']} » mise à jour")
    else:
        api("POST", "/api/v1/functions/create", corps)
        print(f"fonction « {FONCTION['nom']} » créée")
    api("POST", f"/api/v1/functions/id/{FONCTION['id']}/valves/update",
        {"studio_url": R["STUDIO_URL"], "jeton": R["STUDIO_JETON"], "modele_code": R["MODELE_CODE"], "essais": int(R["ESSAIS"])})
    print("vannes enregistrées (adresse du studio, jeton, modèle qui écrit le code, essais)")
    if not api("GET", f"/api/v1/functions/id/{FONCTION['id']}")["is_active"]:
        api("POST", f"/api/v1/functions/id/{FONCTION['id']}/toggle")
    print("fonction activée")


# ---------------------------------------------------------------- 4. Le modèle, réservé au groupe

def modele() -> None:
    acces = [{"principal_type": "group", "principal_id": groupe(), "permission": "read"}]
    m = api("GET", f"/api/v1/models/model?id={MODELE}", ok404=True)
    if m:
        m["access_grants"] = acces
        api("POST", "/api/v1/models/model/update", m)
    else:
        api("POST", "/api/v1/models/create", {"id": MODELE, "name": FONCTION["nom"], "base_model_id": None,
                                              "meta": {"description": ""}, "params": {}, "access_grants": acces,
                                              "is_active": True})
    print(f"modèle {MODELE} réservé au groupe {R['GROUPE']}")


def retirer() -> None:
    api("POST", "/api/v1/models/model/delete", {"id": MODELE}, ok404=True)
    api("DELETE", f"/api/v1/functions/id/{FONCTION['id']}/delete", ok404=True)
    print(f"modèle et fonction « {FONCTION['nom']} » retirés")


if __name__ == "__main__":
    requis = ("OWUI_URL", "OWUI_JETON") + (() if "--retirer" in sys.argv else ("STUDIO_JETON", "MODELE_CODE"))
    for cle in requis:
        if not R.get(cle):
            sys.exit(f"réglage manquant : {cle} (voir .env.example)")
    if "--retirer" in sys.argv:
        retirer()
    else:
        fonction()
        modele()
