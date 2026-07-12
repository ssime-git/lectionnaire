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
import subprocess
import time
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


# Moteur de secours : Claude Code en mode headless, couvert par l'abonnement
# Claude Pro (voie officiellement supportée : `claude setup-token` +
# CLAUDE_CODE_OAUTH_TOKEN). Sélection par LECTIONNAIRE_MOTEUR=claude.
# Sonnet 5 : excellent en prose française, économe en limites d'abonnement.
MODELE_CLAUDE = "claude-sonnet-5"


def _appel(systeme: str, user: str, max_tokens: int = 12000) -> str:
    """Route l'appel vers le moteur choisi et retourne le texte du modèle."""
    if os.environ.get("LECTIONNAIRE_MOTEUR") == "claude":
        return _appel_claude(systeme, user)
    return _appel_workers_ai(systeme, user, max_tokens)


def _appel_claude(systeme: str, user: str) -> str:
    """Appelle Claude Code en mode headless (`claude -p`), sans outils :
    le prompt entre par stdin, le JSON ressort par stdout."""
    cmd = [
        "claude", "-p",
        "--model", MODELE_CLAUDE,
        "--system-prompt", systeme,
    ]
    try:
        r = subprocess.run(
            cmd, input=user, capture_output=True, text=True, timeout=900,
        )
    except FileNotFoundError as exc:
        raise RuntimeError(
            "CLI `claude` introuvable — installer @anthropic-ai/claude-code."
        ) from exc
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError("Claude Code n'a pas répondu en 15 minutes.") from exc
    if r.returncode != 0:
        raise RuntimeError(
            f"Échec de Claude Code (code {r.returncode}) : {r.stderr.strip()[:400]}"
        )
    if not r.stdout.strip():
        raise RuntimeError("Claude Code n'a renvoyé aucun texte.")
    return r.stdout


def _appel_workers_ai(systeme: str, user: str, max_tokens: int = 12000) -> str:
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
    for tentative in range(4):
        try:
            r = requests.post(
                url,
                headers={"Authorization": f"Bearer {token}"},
                json=payload,
                timeout=300,
                stream=True,
            )
            r.raise_for_status()
            # Le flux SSE arrive sans charset déclaré : sans ceci, requests
            # décode en latin-1 et chaque accent devient du mojibake (Ã©…).
            r.encoding = "utf-8"
            texte, echantillon = _lire_flux(r)
            if texte.strip():
                return texte
            raise RuntimeError(
                "Workers AI n'a renvoyé aucun token dans le flux SSE. "
                f"Premières lignes reçues : {echantillon!r}"
            )
        except requests.Timeout as exc:
            derniere_erreur = exc
            print(f"⚠  Timeout Workers AI (tentative {tentative + 1}/4)")
        except requests.RequestException as exc:
            reponse_http = getattr(exc, "response", None)
            if reponse_http is not None and reponse_http.status_code == 429:
                # Un 429 est ambigu : quota quotidien épuisé, OU modèle
                # momentanément saturé. Le corps de la réponse tranche ; on
                # réessaie avec attente croissante avant d'abandonner.
                detail = (reponse_http.text or "")[:400]
                derniere_erreur = RuntimeError(
                    "Workers AI renvoie 429 après plusieurs tentatives. "
                    "Si le détail parle de quota : 10 000 neurons gratuits "
                    "par jour, retour à zéro à 00:00 UTC. Détail : " + detail
                )
                attente = 30 * (tentative + 1)
                print(f"⚠  429 Workers AI (tentative {tentative + 1}/4), "
                      f"nouvel essai dans {attente} s. Détail : {detail}")
                time.sleep(attente)
                continue
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


# --------- La gravure : un second appel, plus court, dédié au dessin -------
GRAVEUR = """Tu graves des bois pour un lectionnaire : des illustrations SVG \
minimales, dans l'esprit des gravures sur bois protestantes — quelques traits, \
une image forte, aucune couleur (les classes CSS colorent selon la liturgie).

Contraintes STRICTES :
- SVG racine : viewBox="0 0 340 150", xmlns, fill="none", stroke-width="1.3",
  stroke-linecap="round", stroke-linejoin="round".
- Uniquement des <g> et des <path>. Pas de texte, pas d'image, pas de script.
- Les <g> portent class="trait-encre" (traits principaux), et si utile
  class="trait-rubrique" ou class="trait-liturgie" pour UN élément à teinter.
- Sobriété : 5 à 20 chemins, lignes épurées, pas de détail réaliste.
Tu réponds STRICTEMENT en JSON valide : {"gravure_svg": "<svg …>…</svg>"}."""

GRAVURE_EXEMPLE = (
    '<svg viewBox="0 0 340 150" xmlns="http://www.w3.org/2000/svg" fill="none" '
    'stroke-width="1.3" stroke-linecap="round" stroke-linejoin="round">'
    '<g class="trait-encre"><path d="M6 120 h328"/><path d="M170 20 v40"/>'
    '<path d="M157 33 h26"/></g>'
    '<g class="trait-rubrique"><path d="M90.0 120 q-11 -17 -1 -31 q-3 13 6 15 '
    'q7 -19 -3 -43 q14 22 3 43 q9 -6 6 -17 q8 19 -11 34"/></g>'
    '<g class="trait-liturgie"><path d="M242.0 80 q0 18 13 20 q13 -2 13 -20 z"/>'
    '<path d="M255.0 100 v14"/><path d="M244.0 120 h22"/></g></svg>'
)


def _gravure_sure(svg: str) -> bool:
    """N'accepte qu'un SVG épuré : viewBox attendu, seulement g/path/svg,
    aucun attribut événement ni lien."""
    import xml.etree.ElementTree as ET

    if not isinstance(svg, str) or 'viewBox="0 0 340 150"' not in svg:
        return False
    try:
        racine = ET.fromstring(svg)
    except ET.ParseError:
        return False
    for element in racine.iter():
        balise = element.tag.split("}")[-1]
        if balise not in {"svg", "g", "path"}:
            return False
        for attribut in element.attrib:
            nom = attribut.split("}")[-1].lower()
            if nom.startswith("on") or "href" in nom:
                return False
    return True


def _generer_gravure(alt: str) -> str:
    """Demande le bois gravé au modèle ; placeholder si le SVG est douteux."""
    demande = json.dumps(
        {
            "sujet": alt,
            "exemple_du_style_attendu": GRAVURE_EXEMPLE,
            "consigne": (
                "Grave ce sujet dans le style exact de l'exemple : mêmes "
                "attributs racine, mêmes classes, même sobriété."
            ),
        },
        ensure_ascii=False,
    )
    try:
        contenu = _json_propre(_appel(GRAVEUR, demande, max_tokens=3000))
        svg = contenu.get("gravure_svg", "")
    except (RuntimeError, json.JSONDecodeError) as exc:
        print(f"⚠  Gravure non générée ({exc}) : placeholder utilisé.")
        return _GRAVURE_ABSENTE
    if _gravure_sure(svg):
        return svg
    print("⚠  Gravure refusée par la validation : placeholder utilisé.")
    return _GRAVURE_ABSENTE


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
- Analogies : jamais de saynètes anecdotiques (la friche réhabilitée, la \
salle de classe…) qui restent dans l'imagerie du texte et le paraphrasent. \
Chaque analogie part d'une expérience spirituelle intérieure que le lecteur \
reconnaît (prier sans rien ressentir, une parole qui remonte des années \
après, servir sans voir de fruit) et le conduit devant Dieu — concrète sans \
être anecdotique, spirituelle sans être abstraite.
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
            "variante part d'une expérience spirituelle intérieure du lecteur "
            "(adressée au « tu ») et l'amène à la promesse du texte du jour — "
            "PAS une petite scène illustrative vue de l'extérieur qui rejoue "
            "la parabole. Le lecteur doit finir devant Dieu, pas devant une "
            "anecdote. "
            "Question : ouverte, qui travaille le lecteur, pas une question "
            "de contrôle de lecture."
        ),
        "exemple_de_variante_d_analogie_attendue": (
            "Un verset appris par cœur dans l'enfance, récité sans le "
            "comprendre ou lu en hâte un matin sans qu'il te touche, peut "
            "rester enfoui vingt ou trente ans sans que tu y penses jamais. "
            "Puis un jour de deuil, ou de décision qu'il faut prendre seul, "
            "il remonte intact, avec les mots exacts que tu croyais avoir "
            "oubliés, et il porte alors ce qu'il ne portait pas au moment où "
            "tu l'as reçu. Tu n'as rien fait pour le garder vivant — c'est "
            "ce niveau d'intériorité et d'adresse au lecteur qui est attendu."
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
    # Si le modèle rédacteur a produit un SVG malgré la consigne, on l'écarte :
    # la gravure vient du second appel dédié, jamais de celui-ci.
    contenu.pop("gravure_svg", None)

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
        # Le bois gravé sort d'un second appel dédié, cadré par un exemple réel
        # et validé strictement (g/path seulement). En cas d'échec : SVG vide,
        # la page paraît sans image — dégradé mais lisible, jamais bloquant.
        "gravure_svg": _generer_gravure(contenu.get("gravure_alt", "")),
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
