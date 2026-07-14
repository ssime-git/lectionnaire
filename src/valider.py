#!/usr/bin/env python3
"""
valider.py — refuse un JSON du jour bancal avant qu'il n'atteigne le rendu.

Autonome : aucune dépendance hors bibliothèque standard. Sortie 0 si valide,
1 sinon, avec la liste précise des fautes.

    python scripts/valider.py data/jours/2026-12-17.json

Le validateur n'est pas une formalité. Il encode les fautes qui ont réellement
cassé le site : une palette sans variante sombre (titre noir sur noir), une
glose sans bouton (lien mort), un SVG avec des couleurs en dur (dessin figé en
vert un jour de carême).
"""

from __future__ import annotations
import json
import re
import sys
from pathlib import Path

CLES_REQUISES = {
    "date", "date_humaine", "semaine", "ferie", "liturgie", "deuterocanonique",
    "titre", "titre_html", "sous_titre", "traduction_globale",
    "references_brutes", "gravure_alt", "gravure_svg", "lectures", "contexte",
    "analogie", "invitation", "question", "racines",
}

CLASSES_CONNUES = {"", "psaume", "evangile", "genealogie"}
TRAITS_AUTORISES = {"trait-encre", "trait-liturgie", "trait-rubrique"}
SOURCES_INTERDITES = re.compile(
    r"\b(TOB|Bible de Jérusalem|Segond 21|traduction liturgique)\b", re.I)


def valider(chemin: Path) -> list[str]:
    try:
        d = json.loads(chemin.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        return [f"JSON invalide : {e}"]
    return valider_contrat(d)


def valider_contrat(d: dict) -> list[str]:
    """Même contrôle que `valider`, mais sur un dict déjà chargé — pour que
    generate.py puisse refuser (et faire réparer) un contrat avant de l'écrire."""
    fautes: list[str] = []

    # 1. Clés du contrat
    for k in sorted(CLES_REQUISES - set(d)):
        fautes.append(f"clé manquante : {k}")

    # 2. Couleur liturgique — le mode sombre casse sans hex_sombre
    lit = d.get("liturgie") or {}
    if not {"nom", "hex", "hex_sombre"} <= set(lit):
        fautes.append("liturgie : il faut nom, hex ET hex_sombre "
                      "(sinon le mode sombre est illisible). "
                      "Utiliser scripts/liturgie.py, ne pas écrire à la main.")

    # 3. Bois gravé — aucune couleur en dur, uniquement des classes de trait
    svg = d.get("gravure_svg", "")
    if svg:
        for hexa in set(re.findall(r"#[0-9A-Fa-f]{6}", svg)):
            fautes.append(f"gravure_svg : couleur en dur {hexa}. "
                          f"Utiliser les classes {sorted(TRAITS_AUTORISES)}.")
        for cls in set(re.findall(r'class="([^"]+)"', svg)):
            if cls not in TRAITS_AUTORISES:
                fautes.append(f"gravure_svg : classe inconnue {cls!r}")
        if not re.search(r"<svg[^>]*viewBox=", svg):
            fautes.append("gravure_svg : viewBox manquant")

    # 4. Lectures : classes connues, gloses appariées, lettrine bien placée
    for i, lec in enumerate(d.get("lectures", [])):
        ref = lec.get("reference", f"lecture {i}")
        classe = lec.get("classe", "")
        if classe not in CLASSES_CONNUES:
            fautes.append(f"{ref} : classe inconnue {classe!r}. "
                          f"Si le texte ne rentre pas, proposer une variante "
                          f"plutôt que de le forcer.")
        corps = lec.get("corps_html", "")
        boutons = set(re.findall(r'data-g="([^"]+)"', corps))
        gloses = {g.get("id") for g in lec.get("gloses", [])}
        for orph in sorted(gloses - boutons):
            fautes.append(f"{ref} : glose {orph!r} sans bouton correspondant")
        for mort in sorted(boutons - gloses):
            fautes.append(f"{ref} : bouton {mort!r} sans glose — lien mort")
        for g in lec.get("gloses", []):
            lemme = g.get("lemme", "")
            if lemme and len(lemme.split()) > 6:
                fautes.append(f"{ref} : lemme trop long ({lemme[:30]}…), "
                              f"2 à 5 mots")
        if classe == "genealogie" and "<ul" in corps and corps.strip().startswith("<p>") is False:
            pass  # la structure exacte est libre, le rendu l'enveloppe dans un div
        if classe == "psaume" and 'class="init"' in corps:
            fautes.append(f"{ref} : un psaume ne porte pas de lettrine")

    # 5. Analogie : trois variantes distinctes, un index choisi
    a = d.get("analogie") or {}
    variantes = a.get("variantes") or a.get("paragraphes", [])
    if len(variantes) < 3:
        fautes.append(f"analogie : {len(variantes)} variante(s), il en faut 3 "
                      f"distinctes (clé 'variantes') — un humain choisira.")
    if "variantes" in a:
        i = a.get("choisi")
        if not isinstance(i, int) or not (0 <= i < len(variantes)):
            fautes.append(f"analogie.choisi = {i!r} : index hors bornes. "
                          f"Indiquer la variante à publier (0 à {len(variantes)-1}).")

    # 6. Contexte et racines : les comptes attendus par le template
    if len(d.get("contexte", [])) != 2:
        fautes.append(f"contexte : {len(d.get('contexte', []))} entrées, 2 attendues")
    if len(d.get("racines", [])) != 3:
        fautes.append(f"racines : {len(d.get('racines', []))} entrées, 3 attendues")

    # 7. Sources sous droits
    texte_entier = json.dumps(d, ensure_ascii=False)
    for m in set(SOURCES_INTERDITES.findall(texte_entier)):
        fautes.append(f"source sous droits citée : {m!r}. "
                      f"Domaine public uniquement (Segond 1910, Calvin, Pères).")

    # 8. Traçabilité des racines
    for r in d.get("racines", []):
        if not r.get("attribution"):
            fautes.append(f"racine {r.get('titre', '?')!r} : attribution manquante. "
                          f"Le site est anonyme : son autorité vient de ses sources.")

    return fautes


def main() -> int:
    if len(sys.argv) < 2:
        print("usage : python scripts/valider.py data/jours/AAAA-MM-JJ.json")
        return 2
    chemin = Path(sys.argv[1])
    if not chemin.exists():
        print(f"✗ fichier introuvable : {chemin}")
        return 1

    fautes = valider(chemin)
    if not fautes:
        print(f"✓ {chemin.name} — contrat valide")
        return 0
    print(f"✗ {chemin.name} — {len(fautes)} faute(s) :")
    for f in fautes:
        print(f"   · {f}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
