"""
refs.py — récupère les RÉFÉRENCES liturgiques du jour via l'API AELF,
détecte les livres deutérocanoniques, et prépare la récupération du texte
biblique en Segond 1910 (domaine public).

Pourquoi cette séparation :
- AELF fournit gratuitement les RÉFÉRENCES (Os 10, 1-3.7-8.12 ; Mt 10, 1-7).
- La TRADUCTION liturgique AELF est sous droits → on ne l'utilise pas.
- Le corps du texte vient de Segond 1910 (libre), chargé depuis data/segond1910/.

⚠️ La forme exacte du JSON renvoyé par l'API AELF doit être vérifiée contre une
réponse réelle (le parsing ci-dessous est défensif et isolé dans _parse_aelf).
Endpoint documenté : https://api.aelf.org  (voir la page « API » du site AELF).
"""

from __future__ import annotations
import json
import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import requests

RACINE = Path(__file__).resolve().parent.parent
SEGOND_DIR = RACINE / "data" / "segond1910"

AELF_URL = "https://api.aelf.org/v1/messes/{date}/{zone}"

# Sigles AELF des livres deutérocanoniques (hors canon Segond/protestant).
# Quand l'un d'eux apparaît, on lève le drapeau pour afficher le badge
# pédagogique « livre deutérocanonique » (option B décidée en amont).
DEUTEROCANONIQUES = {
    "Tb",   # Tobie
    "Jdt",  # Judith
    "Sg",   # Sagesse
    "Si",   # Siracide / Ecclésiastique
    "Ba",   # Baruch (et Lettre de Jérémie)
    "1M", "2M",  # Maccabées
    # Ajouts grecs à Daniel et Esther : cas partiels, à affiner si besoin.
}

# Mapping sigle AELF → clé de fichier Segond (data/segond1910/<clé>.json).
# À compléter avec l'ensemble des livres ; extrait représentatif ici.
SIGLE_VERS_LIVRE = {
    "Gn": "genese", "Ex": "exode", "Ps": "psaumes",
    "Os": "osee", "Jl": "joel", "Am": "amos",
    "Mt": "matthieu", "Mc": "marc", "Lc": "luc", "Jn": "jean",
    "Ac": "actes", "Rm": "romains",
}

# Deutérocanoniques : absents de Segond, présents dans la Crampon 1923
# (domaine public). data/crampon1923/<clé>.json.
SIGLE_VERS_DEUTERO = {
    "Tb": "tobie", "Jdt": "judith", "Sg": "sagesse", "Si": "siracide",
    "Ba": "baruch", "1M": "maccabees1", "2M": "maccabees2",
}


def source_du_livre(sigle: str) -> tuple[str, str] | tuple[None, None]:
    """Retourne (dossier, clé_fichier) pour un sigle, ou (None, None).
    Aiguille vers Segond (canonique) ou Crampon (deutérocanonique)."""
    if sigle in SIGLE_VERS_LIVRE:
        return "segond1910", SIGLE_VERS_LIVRE[sigle]
    if sigle in SIGLE_VERS_DEUTERO:
        return "crampon1923", SIGLE_VERS_DEUTERO[sigle]
    return None, None


@dataclass
class Lecture:
    type: str                 # "lecture_1" | "psaume" | "evangile" | ...
    sigle: str                # "Os", "Mt", "Ps"…
    reference: str            # "Osée 10, 1-3.7-8.12"
    reference_courte: str     # "Os 10, 1-3.7-8.12"
    versets: list[str] = field(default_factory=list)  # texte Segond, si trouvé
    deuterocanonique: bool = False


@dataclass
class JourLiturgique:
    date: str
    informations: dict
    lectures: list[Lecture]

    @property
    def deuterocanonique(self) -> bool:
        return any(l.deuterocanonique for l in self.lectures)

    @property
    def references_brutes(self) -> str:
        return " ; ".join(l.reference_courte for l in self.lectures
                          if l.type != "psaume") or \
               " ; ".join(l.reference_courte for l in self.lectures)


def recuperer(date_iso: str, zone: str = "romain") -> JourLiturgique:
    """Appelle l'API AELF pour une date (AAAA-MM-JJ) et une zone."""
    url = AELF_URL.format(date=date_iso, zone=zone)
    r = requests.get(url, timeout=15, headers={"Accept": "application/json"})
    r.raise_for_status()
    return _parse_aelf(date_iso, r.json())


def _parse_aelf(date_iso: str, data: dict) -> JourLiturgique:
    """Parsing ISOLÉ et défensif de la réponse AELF.
    ⚠️ Vérifier les clés exactes contre une réponse réelle avant prod."""
    informations = data.get("informations", {})
    messes = data.get("messes", [])
    lectures_brutes = messes[0].get("lectures", []) if messes else []

    lectures: list[Lecture] = []
    for lb in lectures_brutes:
        ref_longue = (lb.get("ref") or lb.get("reference") or "").strip()
        type_ = lb.get("type", "")
        sigle = _sigle_depuis_reference(ref_longue)
        ref_courte = _reference_courte(ref_longue, sigle)
        lectures.append(Lecture(
            type=type_,
            sigle=sigle,
            reference=ref_longue,
            reference_courte=ref_courte,
            deuterocanonique=sigle in DEUTEROCANONIQUES,
        ))
    return JourLiturgique(date=date_iso, informations=informations,
                          lectures=lectures)


def _sigle_depuis_reference(ref: str) -> str:
    """« Osée 10, 1-3 » → « Os ». Heuristique : premier token alphabétique.
    On mappe quelques noms complets fréquents ; sinon on garde le token brut."""
    noms = {
        "osée": "Os", "osee": "Os", "matthieu": "Mt", "marc": "Mc",
        "luc": "Lc", "jean": "Jn", "psaume": "Ps", "genèse": "Gn",
        "actes": "Ac", "romains": "Rm", "joël": "Jl", "amos": "Am",
        "sagesse": "Sg", "siracide": "Si", "tobie": "Tb", "judith": "Jdt",
        "baruch": "Ba", "maccabées": "1M",
    }
    m = re.match(r"\s*([\wéèêàâîôûç]+)", ref, re.IGNORECASE)
    if not m:
        return ""
    tok = m.group(1)
    return noms.get(_sans_accents(tok).lower(), tok)


def _reference_courte(ref: str, sigle: str) -> str:
    """« Osée 10, 1-3.7-8.12 » → « Os 10, 1-3.7-8.12 »."""
    reste = re.sub(r"^\s*[\wéèêàâîôûç]+\s*", "", ref)
    return f"{sigle} {reste}".strip()


def _sans_accents(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", s)
                   if unicodedata.category(c) != "Mn")


# --------- Récupération du texte Segond 1910 (domaine public) ----------

def parser_versets(reference_courte: str) -> tuple[Optional[str], Optional[int], list[int]]:
    """« Os 10, 1-3.7-8.12 » → ("Os", 10, [1,2,3,7,8,12]).
    Gère les plages (1-3), les listes (.), les versets seuls."""
    m = re.match(r"\s*([\dA-Za-z]+)\s+(\d+)\s*,\s*(.+)", reference_courte)
    if not m:
        return None, None, []
    sigle, chap, plage = m.group(1), int(m.group(2)), m.group(3)
    versets: list[int] = []
    for bloc in re.split(r"[.\s]+", plage):
        bloc = bloc.strip().rstrip(".")
        if not bloc:
            continue
        if "-" in bloc:
            a, b = bloc.split("-")[:2]
            a = re.sub(r"\D", "", a)
            b = re.sub(r"\D", "", b)
            if a and b:
                versets.extend(range(int(a), int(b) + 1))
        else:
            n = re.sub(r"\D", "", bloc)
            if n:
                versets.append(int(n))
    return sigle, chap, versets


def texte_lecture(reference_courte: str) -> tuple[list[str], str]:
    """Retourne (versets, nom_traduction) pour une référence.
    Aiguille automatiquement Segond (canonique) / Crampon (deutérocanonique).
    Traduction vide et liste vide si le livre n'est pas dans le corpus."""
    sigle, chap, versets = parser_versets(reference_courte)
    if not sigle or not chap:
        return [], ""
    dossier, cle = source_du_livre(sigle)
    if not cle:
        return [], ""
    chemin = RACINE / "data" / dossier / f"{cle}.json"
    if not chemin.exists():
        return [], ""
    livre = json.loads(chemin.read_text(encoding="utf-8"))
    chap_data = livre.get(str(chap), {})
    sortie = [chap_data[str(v)] for v in versets if str(v) in chap_data]
    traduction = "Crampon 1923" if dossier == "crampon1923" else "Louis Segond 1910"
    return sortie, traduction


def texte_segond(reference_courte: str) -> list[str]:
    """Compat : renvoie seulement les versets (Segond ou Crampon selon le livre)."""
    versets, _ = texte_lecture(reference_courte)
    return versets


if __name__ == "__main__":
    import sys
    d = sys.argv[1] if len(sys.argv) > 1 else "2026-07-08"
    try:
        jour = recuperer(d)
        print(f"{jour.date} — deutérocanonique: {jour.deuterocanonique}")
        for l in jour.lectures:
            print(f"  [{l.type}] {l.reference_courte}"
                  f"{'  ⚑ deutéro' if l.deuterocanonique else ''}")
        print("références:", jour.references_brutes)
    except Exception as e:
        print(f"Échec (API AELF ou parsing à vérifier) : {e}")
