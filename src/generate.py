"""
generate.py — ÉTAPE 2. Produit le JSON du jour (le « contrat ») via inférence.

Ne PAS brancher tant que render.py n'est pas validé sur plusieurs jours écrits
à la main. Ici on remplace l'humain qui écrit le JSON par le LLM — le template,
lui, ne change plus.

Principe : ROUTER PAR TÂCHE, pas par habitude.
  - extraction/classification légère → petit modèle gratuit (Workers AI)
  - rédaction qui porte la voix (analogie, geste, notes) → modèle capable
Le tout via l'AI Gateway (endpoint OpenAI-compatible) : changer de modèle = une
chaîne de caractères, sans toucher au reste du pipeline.

Secrets attendus (repository secrets GitHub, jamais dans le code) :
  CF_ACCOUNT_ID, CF_GATEWAY, CF_API_TOKEN
"""

from __future__ import annotations
import json
import os
import re
from pathlib import Path
from typing import Any

import requests

from refs import recuperer, texte_segond  # type: ignore
from liturgie import depuis_aelf  # type: ignore

RACINE = Path(__file__).resolve().parent.parent
DATA_JOURS = RACINE / "data" / "jours"

# --- Routage des modèles (édite ces deux lignes pour changer de moteur) ---
MODELE_REDACTION = "@cf/moonshotai/kimi-k2.6"      # voix, analogies, notes
MODELE_LEGER = "@cf/meta/llama-3.1-8b-instruct"    # extraction, tags

# Endpoint AI Gateway compatible OpenAI : un seul chemin, modèle interchangeable.
# https://gateway.ai.cloudflare.com/v1/{account}/{gateway}/compat/chat/completions
GATEWAY_URL = (
    "https://gateway.ai.cloudflare.com/v1/"
    "{account}/{gateway}/compat/chat/completions"
)


def _appel(modele: str, systeme: str, user: str,
           json_mode: bool = True, max_tokens: int = 1500) -> str:
    url = GATEWAY_URL.format(
        account=os.environ["CF_ACCOUNT_ID"],
        gateway=os.environ["CF_GATEWAY"],
    )
    payload: dict[str, Any] = {
        "model": modele,
        "messages": [
            {"role": "system", "content": systeme},
            {"role": "user", "content": user},
        ],
        "max_tokens": max_tokens,
        "temperature": 0.7,
    }
    if json_mode:
        payload["response_format"] = {"type": "json_object"}
    r = requests.post(
        url,
        headers={"Authorization": f"Bearer {os.environ['CF_API_TOKEN']}"},
        json=payload, timeout=90,
    )
    r.raise_for_status()
    return r.json()["choices"][0]["message"]["content"]


def _json_propre(txt: str) -> dict:
    """Retire d'éventuelles clôtures ```json … ``` avant de parser."""
    txt = re.sub(r"^```(?:json)?|```$", "", txt.strip(), flags=re.MULTILINE)
    return json.loads(txt.strip())


# --------- Le prompt système : c'est ICI que vit la VOIX du projet ---------
# La qualité ne vient pas du modèle mais de ce cadrage. C'est le garde-fou
# herméneutique + le ton (Chrysostome vulgarisateur, pas eiségèse actu).
VOIX = """Tu écris une page quotidienne d'étude biblique, tradition protestante \
(ÉPUdF), sur le lectionnaire romain. Public : tout âge, surtout jeunes, souvent \
peu familiers du texte. Objectif : rendre l'Écriture vivante et digeste SANS la \
diluer, et inviter à se laisser rejoindre par le Christ, jamais de façon \
moralisatrice.

Règles absolues :
- Rigueur exégétique : structure texte → sens → application (modèle de \
l'homélie patristique). Jamais plaquer l'actualité sur le texte (pas d'eiségèse).
- Chaque affirmation interprétative doit rester traçable (verset parallèle, \
Père de l'Église nommé, note historique). Si tu n'es pas sûr, tu n'affirmes pas.
- Analogies contemporaines qui PORTENT, concrètes, jamais gadget.
- Ton : sobre, chaleureux, une image centrale par jour. Style écrit, pas \
« assistant IA » : pas de listes à puces, pas de formules creuses, pas d'emphase \
automatique. Prose française soignée.
- Sources : domaine public uniquement (Segond 1910, Calvin, Chrysostome, Pères).
- Tu ne choisis AUCUNE couleur : la teinte de la page vient du calendrier
liturgique, jamais d'une intuition esthétique. On ne te demande pas de palette.
Tu réponds STRICTEMENT en JSON valide, sans texte autour."""


def construire_json(date_iso: str) -> dict:
    jour = recuperer(date_iso)

    # 1) Texte biblique : Segond, jamais le LLM (fiabilité) ----------------
    lectures_ctx = []
    for lec in jour.lectures:
        versets = texte_segond(lec.reference_courte)
        lectures_ctx.append({
            "type": lec.type, "reference": lec.reference,
            "reference_courte": lec.reference_courte,
            "texte_segond": " ".join(versets) if versets else "(à charger)",
        })

    # 2) Rédaction des 7 slots : un seul appel cadré par la VOIX ----------
    #    (Le RAG patristique — Calvin/Chrysostome via Vectorize — s'injecte
    #     ici dans le user prompt : récupère les passages pertinents et
    #     colle-les sous « SOURCES » avant d'appeler. Laissé en TODO.)
    # 2) Rédaction des 7 slots. Un seul appel, cadré par la VOIX.
    #    Le RAG patristique (Calvin/Chrysostome via Vectorize) s'injecte ici :
    #    récupère les passages pertinents et colle-les sous « SOURCES » dans la
    #    demande avant l'appel.  TODO.
    demande = {
        "date_humaine": jour.informations.get("jour", date_iso),
        "lectures": lectures_ctx,
        "consigne": (
            "Produis le JSON du jour avec EXACTEMENT ces clés : "
            "titre (un seul mot ou syntagme court), "
            "titre_html (le titre, avec la 2e moitié dans <span class=\"it\"> "
            "pour l'italique), "
            "sous_titre, "
            "suite_hier (une phrase reliant au texte de la veille, ou null), "
            "gravure_alt (description du bois gravé à dessiner), "
            "lectures (liste, une par lecture reçue, {etiquette, reference, "
            "traduction, classe: ''|'psaume'|'evangile', corps_html avec les "
            "sigles de verset <span class=\"s\">N</span> et les mots glosables "
            "en <button class=\"mot\" data-g=\"g-xxx\">…</button>, "
            "gloses: [{id: 'g-xxx', lemme: court, html: la glose}]}), "
            "contexte (liste de 2 {titre, corps_html}), "
            "analogie {titre, paragraphes[]}, "
            "invitation {intro, geste, note}, "
            "question (une seule, ouverte), "
            "racines (liste de 3 {titre, corps_html, attribution}). "
            "Pour analogie.paragraphes, propose 3 variantes distinctes : "
            "l'humain choisira. "
            "N'invente ni couleur, ni SVG : ce n'est pas ton ressort."
        ),
    }
    brut = _appel(MODELE_REDACTION, VOIX, json.dumps(demande, ensure_ascii=False))
    contenu = _json_propre(brut)

    # 3) Assemblage du contrat. Ce qui est DÉTERMINISTE ne passe pas par le LLM :
    #    la couleur vient du calendrier, les références de l'API, le texte de
    #    Segond. Le LLM ne fournit que la langue.
    contrat = {
        "date": date_iso,
        "date_humaine": jour.informations.get("jour", date_iso),
        "semaine": jour.informations.get("semaine", ""),
        "ferie": jour.informations.get("degre", "férie"),
        "liturgie": depuis_aelf(jour.informations).as_dict(),
        "deuterocanonique": jour.deuterocanonique,
        "references_brutes": jour.references_brutes,
        "traduction_globale": "Louis Segond 1910",
        # Le bois gravé n'est PAS généré (sous-problème ouvert). S'il manque, on
        # met un SVG vide plutôt que de faire tomber le cron : la page paraît
        # sans image, ce qui est dégradé mais lisible. Le message d'avertissement
        # signale qu'un geste humain est attendu.
        "gravure_svg": contenu.pop("gravure_svg", "") or _GRAVURE_ABSENTE,
        **contenu,
    }

    manquantes = _cles_manquantes(contrat)
    if manquantes:
        raise ValueError(
            f"Contrat incomplet, le rendu échouerait : {', '.join(manquantes)}. "
            f"Le modèle n'a pas respecté la consigne — relancer ou corriger à la main."
        )
    if contrat["gravure_svg"] is _GRAVURE_ABSENTE:
        print("⚠  Pas de bois gravé pour ce jour : la page paraîtra sans image. "
              "Ajoute 'gravure_svg' à la main dans le JSON.")
    return contrat


# Le template exige ces clés. On échoue ICI, avec un message clair, plutôt que
# de produire une page cassée à 4 h du matin.
# Marqueur : le bois gravé manque. Un SVG vide, pas un plantage.
_GRAVURE_ABSENTE = '<svg viewBox="0 0 340 8" aria-hidden="true"></svg>'

CLES_REQUISES = {
    "gravure_svg",
    "date_humaine", "semaine", "ferie", "liturgie", "titre", "titre_html",
    "sous_titre", "gravure_alt", "lectures", "contexte", "analogie",
    "invitation", "question", "racines", "references_brutes",
    "traduction_globale",
}


def _cles_manquantes(contrat: dict) -> list[str]:
    return sorted(CLES_REQUISES - set(contrat))


if __name__ == "__main__":
    import sys
    d = sys.argv[1] if len(sys.argv) > 1 else "2026-07-08"
    contrat = construire_json(d)
    sortie = DATA_JOURS / f"{d}.json"
    sortie.write_text(json.dumps(contrat, ensure_ascii=False, indent=2),
                      encoding="utf-8")
    print(f"✓ {sortie.relative_to(RACINE)} généré. "
          f"Relis-le, choisis l'analogie, puis : python src/render.py {d}")
