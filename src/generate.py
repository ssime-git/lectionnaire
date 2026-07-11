"""
generate.py — ÉTAPE 2. Produit le JSON du jour (le « contrat ») via inférence.

Ne PAS brancher tant que render.py n'est pas validé sur plusieurs jours écrits
à la main. Ici on remplace l'humain qui écrit le JSON par le LLM — le template,
lui, ne change plus.

Principe : ce qui est déterministe reste local ; Workers AI ne rédige que les
champs éditoriaux du contrat.

Secrets attendus (repository secrets GitHub, jamais dans le code) :
  CLOUDFLARE_ACCOUNT_ID, CLOUDFLARE_AI_API_TOKEN
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

# Le modèle reste configurable dans le code, mais l'appel ne passe par aucun
# Gateway payant : il utilise directement le quota quotidien Workers AI.
# Kimi K2.6 (1T, classe frontière) : ~2 000 neurons par page, soit ~5
# générations par jour dans le quota gratuit de 10 000 neurons.
MODELE_REDACTION = "@cf/moonshotai/kimi-k2.6"
WORKERS_AI_URL = "https://api.cloudflare.com/client/v4/accounts/{account}/ai/run/{model}"


def _appel(systeme: str, user: str, max_tokens: int = 12000) -> str:
    """Appelle Workers AI et retourne uniquement la réponse textuelle du modèle."""
    account = os.environ.get("CLOUDFLARE_ACCOUNT_ID")
    token = os.environ.get("CLOUDFLARE_AI_API_TOKEN")
    if not account:
        raise RuntimeError("CLOUDFLARE_ACCOUNT_ID manquant")
    if not token:
        raise RuntimeError("CLOUDFLARE_AI_API_TOKEN manquant")

    url = WORKERS_AI_URL.format(account=account, model=MODELE_REDACTION)
    payload: dict[str, Any] = {
        "messages": [
            {"role": "system", "content": systeme},
            {"role": "user", "content": user},
        ],
        "max_tokens": max_tokens,
        "temperature": 0.7,
        "response_format": {"type": "json_object"},
        # Sans ceci, Kimi « pense » en reasoning_content et épuise le budget
        # de tokens avant d'écrire le JSON final (run 29159734572).
        "chat_template_kwargs": {"thinking": False},
        # Un modèle de classe frontière met plusieurs minutes à rédiger une
        # page : sans streaming, la passerelle Cloudflare coupe en 408. En
        # SSE, la connexion reste vivante tant que des tokens arrivent.
        "stream": True,
    }
    derniere_erreur: Exception | None = None
    for tentative in range(2):
        try:
            r = requests.post(
                url,
                headers={"Authorization": f"Bearer {token}"},
                json=payload,
                timeout=300,
                stream=True,
            )
            r.raise_for_status()
            texte, echantillon = _lire_flux(r)
            if texte.strip():
                return texte
            raise RuntimeError(
                "Workers AI n'a renvoyé aucun token dans le flux SSE. "
                f"Premières lignes reçues : {echantillon!r}"
            )
        except requests.Timeout as exc:
            derniere_erreur = exc
            print(f"⚠  Timeout Workers AI (tentative {tentative + 1}/2)")
        except requests.RequestException as exc:
            raise RuntimeError(f"Échec de l'appel Workers AI : {exc}") from exc
    raise RuntimeError(
        f"Échec de l'appel Workers AI : {derniere_erreur}"
    ) from derniere_erreur


def _lire_flux(r: Any) -> tuple[str, list[str]]:
    """Accumule un flux SSE Workers AI et garde un échantillon brut pour le
    diagnostic. Deux dialectes selon le modèle : {"response": "delta"} (Meta)
    ou {"choices": [{"delta": {"content": …}}]} (format OpenAI — Kimi,
    gpt-oss…)."""
    morceaux: list[str] = []
    echantillon: list[str] = []
    for ligne in r.iter_lines(decode_unicode=True):
        if len(echantillon) < 10 and ligne:
            echantillon.append(ligne[:300])
        if not ligne or not ligne.startswith("data:"):
            continue
        donnee = ligne[len("data:"):].strip()
        if donnee == "[DONE]":
            break
        try:
            paquet = json.loads(donnee)
        except json.JSONDecodeError:
            continue
        delta = paquet.get("response")
        if not isinstance(delta, str):
            choices = paquet.get("choices")
            if isinstance(choices, list) and choices and isinstance(choices[0], dict):
                contenu = (choices[0].get("delta") or {}).get("content")
                delta = contenu if isinstance(contenu, str) else None
        if delta:
            morceaux.append(delta)
    return "".join(morceaux), echantillon


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
- Profondeur exigée partout : une glose ou un encart qui se contente d'une \
définition de dictionnaire est un ÉCHEC. Chaque glose part du mot original \
(hébreu ou grec translittéré, balisé <span class=\"gr\">…</span>), dit ce que \
Segond a choisi de traduire et pourquoi c'est discutable ou éclairant, et \
cite la réception (un Père nommé, Calvin, les rabbins) quand elle existe. \
Deux à quatre phrases pleines par glose, jamais une seule.
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
            "analogie {titre, variantes: [3 paragraphes distincts], choisi: 0}, "
            "invitation {intro, geste, note}, "
            "question (une seule, ouverte), "
            "racines (liste de 3 {titre, corps_html, attribution}). "
            "analogie.variantes doit contenir exactement 3 variantes distinctes ; "
            "mets choisi à 0, l'humain pourra changer ce choix. "
            "N'invente ni couleur, ni SVG : ce n'est pas ton ressort."
        ),
        "exigences_de_profondeur": (
            "Gloses : 2 à 4 phrases chacune, partant du mot hébreu/grec, "
            "discutant le choix de Segond, citant la réception quand elle "
            "existe. Contexte et racines : paragraphes nourris (300 à 450 "
            "caractères), avec sources nommées (Chrysostome, Calvin, note "
            "historique datée) — jamais de généralités. Analogie : chaque "
            "variante est une vraie scène concrète développée, pas un résumé. "
            "Question : ouverte, qui travaille le lecteur, pas une question "
            "de contrôle de lecture."
        ),
        "exemple_de_glose_attendue": {
            "id": "g-schilo",
            "lemme": "Schilo",
            "html": (
                "Le mot le plus discuté de la Genèse. Segond le laisse tel "
                "quel, faute de certitude. On y a lu « celui à qui appartient "
                "le sceptre », ou « celui qui apporte la paix ». Les rabbins "
                "comme les Pères y ont vu l'annonce du Messie — c'est ce "
                "niveau de précision et d'honnêteté qui est attendu."
            ),
        },
    }
    brut = _appel(VOIX, json.dumps(demande, ensure_ascii=False))
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
