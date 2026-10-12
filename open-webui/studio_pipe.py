"""
title: Studio 3D
description: Le studio 3D comme un modèle : décrivez une scène, le studio la calcule et vous tient informé en direct.
version: 2.0
"""

# Fonction « Pipe » d'Open WebUI (Panneau d'administration › Fonctions). Elle apparaît dans le
# sélecteur de modèles. À chaque message, le déroulé est fixé par ce code : un modèle de langage
# écrit le script Blender de la scène, le Pipe le vérifie, le soumet au studio, puis publie
# lui-même l'avancement dans la conversation (événements « status ») jusqu'à l'image, l'objet 3D
# et la scène Blender. Code refusé ou rendu en échec : l'erreur repart au modèle, qui corrige.

import asyncio
import json
import re

import aiohttp
from pydantic import BaseModel, Field

CONSIGNE = """Tu écris un script Python pour Blender 5.2 (module bpy) qui construit la scène demandée, dans une scène vide.
Script court et à plat : un sol nommé « Decor sol », les objets demandés, rien d'autre sauf demande.
Dès qu'un objet ou un éclairage figure dans la bibliothèque ci-dessous, utilise-le : charger_asset("nom", position=(x, y, z)) et environnement("nom"), sans import, chaque appel au début de sa ligne, sans indentation.
position est celle de la base de l'objet : z = 0 au sol ; posé sur un autre objet, z = hauteur de celui-ci (dimensions en mètres : largeur × profondeur × hauteur).
Donne un nom commençant par « Decor » à tout ce qui n'est pas le sujet. Couleurs : entrée « Base Color » du nœud Principled BSDF.
Caméra facultative, sans profondeur de champ. Ne règle pas le moteur, n'enregistre rien.
Réponds par une ligne « Titre : » de quatre mots au plus, puis un seul bloc de code python.
Bibliothèque du studio :
"""


class Pipe:
    class Valves(BaseModel):
        studio_url: str = Field(
            "http://studio.studio3d.svc.cluster.local:8000",
            description="Adresse interne du studio",
        )
        jeton: str = Field(
            "",
            description="Jeton du studio",
            json_schema_extra={"input": {"type": "password"}},
        )
        modele_code: str = Field("", description="Modèle qui écrit le code de la scène")
        essais: int = Field(3, description="Essais : code refusé, rendu en échec")

    def __init__(self):
        self.valves = self.Valves()

    def pipes(self):
        # Une entrée par « modèle » proposé dans le sélecteur : studio_3d.studio
        return [{"id": "studio", "name": "Studio 3D"}]

    async def pipe(
        self, body, __user__, __request__, __event_emitter__=None, __task__=None
    ):
        async def etat(texte: str, fini: bool = False):
            if __event_emitter__:
                await __event_emitter__(
                    {"type": "status", "data": {"description": texte, "done": fini}}
                )

        v = self.valves
        if __task__:  # tâche d'Open WebUI (titre, suggestions…) : pas de rendu
            return await ecrire(__request__, __user__, v.modele_code, body["messages"])
        entetes = {
            "Authorization": f"Bearer {v.jeton}",
            "X-Utilisateur-Email": __user__["email"],
        }
        async with aiohttp.ClientSession(v.studio_url, headers=entetes) as studio:
            # 1. La bibliothèque du studio, ajoutée aux consignes du modèle.
            await etat("Lecture de la bibliothèque du studio…")
            async with studio.get("/api/assets") as r:
                assets = await r.json()
            consigne = CONSIGNE + "\n".join(f"- {bibliotheque(a)}" for a in assets)
            messages = [{"role": "system", "content": consigne}] + [
                m for m in body["messages"] if m["role"] != "system"
            ]

            for essai in range(1, v.essais + 1):
                # 2. Le modèle de langage écrit (ou corrige) le script de la scène.
                if essai == 1:
                    await etat("Le modèle écrit le code de la scène…")
                else:
                    await etat(f"Le modèle corrige le code (essai {essai})…")
                texte = await ecrire(__request__, __user__, v.modele_code, messages)
                messages.append({"role": "assistant", "content": texte})
                titre, code = decouper(texte)

                # 3. Vérification, avant de mobiliser un worker.
                erreur = verifier(code, {a["nom"] for a in assets})
                if erreur:
                    await etat(f"Code refusé : {erreur}")
                    messages.append(corriger(erreur))
                    continue

                # 4. Soumission au studio, au nom de l'utilisateur ; 5. suivi en direct.
                demande = {"titre": titre, "code": code}
                async with studio.post("/api/soumettre", json=demande) as r:
                    numero = (await r.json())["numero"]
                e = await suivre(studio, numero, titre, etat)
                if e["statut"] == "termine":
                    await etat(
                        f"Rendu n° {numero} prêt en {e['duree_secondes']} s, calculé par {e['travailleur']}",
                        fini=True,
                    )
                    return reponse(e)
                messages.append(corriger(f"Le rendu a échoué : {e.get('erreur', '')}"))

        await etat("Le rendu a échoué", fini=True)
        return f"Le rendu a échoué après {v.essais} essais. Reformulez la demande."


async def ecrire(request, user: dict, modele: str, messages: list) -> str:
    """Appelle un modèle de l'instance, comme une conversation, et renvoie son texte."""
    from open_webui.models.users import Users
    from open_webui.utils.chat import generate_chat_completion

    utilisateur = Users.get_user_by_id(user["id"])
    if asyncio.iscoroutine(utilisateur):
        utilisateur = await utilisateur
    reponse = await generate_chat_completion(
        request, {"model": modele, "stream": False, "messages": messages}, utilisateur
    )
    if hasattr(reponse, "body"):  # réponse HTTP plutôt que dictionnaire
        reponse = json.loads(reponse.body)
    return reponse["choices"][0]["message"]["content"]


def decouper(texte: str) -> tuple[str, str]:
    """Titre (ligne « Titre : ») et code (premier bloc python) d'une réponse du modèle."""
    t = re.search(r"Titre\s*:\s*\**([^\n*]+)", texte)
    bloc = re.search(r"```(?:python)?[^\n]*\n(.*?)(?:```|$)", texte, re.S)
    titre = t.group(1).strip()[:60] if t else "Scène"
    return titre, bloc.group(1) if bloc else texte


def bibliotheque(a: dict) -> str:
    """Une ligne de la bibliothèque, pour les consignes : nom, libellé, genre, dimensions."""
    taille = " × ".join(f"{x:g}" for x in a["dimensions_m"] or [])
    return f"{a['nom']} : {a['libelle']} ({a['genre']}{', ' + taille + ' m' if taille else ''})"


def corriger(probleme: str) -> dict:
    """Message renvoyé au modèle de langage : le problème, et ce qu'on attend de lui."""
    return {
        "role": "user",
        "content": f"{probleme}. Renvoie le script complet corrigé.",
    }


def verifier(code: str, noms: set) -> str | None:
    """Ce qui ferait échouer le rendu, ou None : le message renvoyé au modèle pour correction."""
    try:
        compile(code, "scene.py", "exec")
    except SyntaxError as err:
        return f"Ton code ne compile pas, ligne {err.lineno} : {err.msg}"
    appels = re.findall(r"(?:charger_asset|environnement)\(\s*[\"']([^\"']+)", code)
    inconnus = sorted(set(appels) - noms)
    if inconnus:
        return f"Assets absents de la bibliothèque : {', '.join(inconnus)}"
    if re.search(r"use_dof\s*=\s*True", code):
        return "Pas de profondeur de champ (use_dof)"
    return None


async def suivre(studio, numero: int, titre: str, etat) -> dict:
    """Lit l'état de la demande toutes les deux secondes et le publie ; renvoie l'état final."""
    while True:
        async with studio.get(f"/api/etat/{numero}") as r:
            e = await r.json()
        if e["statut"] == "en_attente":
            position = e["position"]
            await etat(
                f"Demande n° {numero} « {titre} » : dans la file, position {position}"
            )
        elif e["statut"] == "en_cours":
            worker, depuis = e["travailleur"], e["depuis_secondes"]
            await etat(f"Demande n° {numero} : calcul sur {worker} depuis {depuis} s")
        else:
            return e
        await asyncio.sleep(2)


def reponse(e: dict) -> str:
    """Réponse finale : image, objet 3D (artefact), scène Blender, assets utilisés, marquage."""
    visionneuse = (
        "```html\n"
        '<script type="module" src="https://cdn.jsdelivr.net/npm/@google/model-viewer@4.0.0/dist/model-viewer.min.js"></script>\n'
        f'<model-viewer src="{e["glb"]}" poster="{e["png"]}" camera-controls auto-rotate '
        'shadow-intensity="1" style="width:100%;height:480px;background:#f4f4f5"></model-viewer>\n'
        "```"
    )
    lignes = [
        f"Voici **{e['titre']}** (demande n° {e['numero']}).",
        f"![{e['titre']}]({e['png']})",
        visionneuse,
    ]
    if str(e.get("scene", "")).startswith("http"):
        lignes.append(f"[Télécharger la scène Blender]({e['scene']})")
    elif e.get("scene"):
        lignes.append("La scène Blender n'a pas pu être enregistrée.")
    if e.get("assets"):
        noms = ", ".join(f"{a['libelle']} ({a['licence']})" for a in e["assets"])
        lignes.append(f"Assets de la bibliothèque : {noms}")
    if e.get("marquage_visible"):
        lignes.append("Marquage : bandeau visible, et métadonnées du fichier.")
    else:
        lignes.append("Marquage : invisible, dans les métadonnées du fichier.")
    return "\n\n".join(lignes)
