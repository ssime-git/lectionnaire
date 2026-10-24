#!/usr/bin/env python3
"""
corpus.py — les Pères et Réformateurs, rangés par référence biblique.

Les commentaires anciens suivent le texte biblique : pour savoir ce que
Chrysostome dit de Mt 22, 34-40, il suffit de trouver l'homélie qui commente
ce passage. Pas de recherche « par le sens », donc pas de Vectorize : chaque
extrait cité est recopié tel quel, avec sa source.

    python src/corpus.py        # importe les commentaires de Chrysostome

Source : Wikisource, Œuvres complètes de saint Jean Chrysostome, trad. Jeannin
(1864-1867), domaine public. Une homélie dont la référence n'est pas lisible
n'est jamais devinée : elle reste hors index et figure dans le rapport.
"""

from __future__ import annotations
import json
import re
import time
import unicodedata
from pathlib import Path
from typing import Any

import requests

RACINE = Path(__file__).resolve().parent.parent
TEXTES = RACINE / "data" / "tradition" / "textes" / "chrysostome"
CACHE = RACINE / ".cache" / "wikisource"
API = "https://fr.wikisource.org/w/api.php"
ENTETES = {"User-Agent": "LectionnaireCorpus/0.1 (https://github.com/ssime-git/lectionnaire; corpus domaine public)"}
PAUSE = 6  # secondes entre deux requêtes Wikisource
MAX_PASSAGES = 2

# sigle AELF → (nom affiché, pages Wikisource qui, ensemble, couvrent le livre)
PAGES: dict[str, tuple[str, list[str]]] = {
    "Mt": ("Matthieu", [
        "Jean Chrysostome/Commentaire sur l’Évangile selon saint Matthieu/Homélie I",
        "Jean Chrysostome/Commentaire sur l’Évangile selon saint Matthieu/Homélie XL",
        "Jean Chrysostome/Commentaire sur l’Évangile selon saint Matthieu/Homélie LXXVIII",
    ]),
    "Jn": ("Jean", [
        "Jean Chrysostome/Commentaire sur l’Évangile selon saint Jean/Homélie I à Homélie XLIX",
        "Jean Chrysostome/Commentaire sur l’Évangile selon saint Jean/Homélie L à Homélie LXXXVIII",
    ]),
    "Rm": ("l'Épître aux Romains", ["Commentaire sur l’Épître de saint Paul aux Romains"]),
    "Ep": ("l'Épître aux Éphésiens", ["Commentaire sur l’Épître de saint Paul aux Éphésiens"]),
    "1Th": ("la première Épître aux Thessaloniciens",
            ["Commentaire sur la première Épître de saint Paul aux Thessaloniciens"]),
}

NB_CHAPITRES = {"Mt": 28, "Jn": 21, "Rm": 16, "Ep": 6, "1Th": 5}

_ROMAINS = {"I": 1, "V": 5, "X": 10, "L": 50, "C": 100}


def _romain(s: str) -> int:
    total = 0
    for i, c in enumerate(s):
        v = _ROMAINS[c]
        total += -v if i + 1 < len(s) and _ROMAINS[s[i + 1]] > v else v
    return total


def _nombre(s: str) -> int:
    return int(s) if s.isdigit() else _romain(s)


_CHAP = r"(?:CHAP(?:ITRE)?\.?\s*([IVXLC]+|\d+)|\b([IVXLC]+)\b(?=\s*,))"


def _chapitres(s: str) -> list[tuple[int, int]]:
    """(position, numéro) de chaque chapitre annoncé : « CHAP. 12 » ou un
    chiffre romain suivi d'une virgule. Un nombre nu n'est jamais un chapitre."""
    return [(m.start(), _nombre(m[1] or m[2])) for m in re.finditer(_CHAP, s)]


def parser_reference(txt: str, chapitre_precedent: int | None, verset_suivant: int = 1
                     ) -> tuple[tuple[int, int], tuple[int, int], bool] | None:
    """« (CHAP. I, VERS. 1, 2 JUSQU’À 7) » → ((1, 1), (1, 7), False).
    Sans chapitre explicite, celui de l'homélie précédente est repris (et
    signalé). 999 vaut « jusqu'à la fin du chapitre ». None si illisible."""
    s = txt.upper().replace("’", "'").strip().strip("()").strip()
    coupe = re.search(r"JUSQU'(?:AU|À|A)\b", s)
    debut_txt, fin_txt = (s[: coupe.start()], s[coupe.end():]) if coupe else (s, "")

    chap_debut = _chapitres(debut_txt)
    herite = not chap_debut
    if herite:
        if chapitre_precedent is None:
            return None
        chapitre = chapitre_precedent
        versets_debut = [int(n) for n in re.findall(r"\d+", debut_txt)]
    else:
        pos, chapitre = chap_debut[0]
        apres = re.sub(_CHAP, " ", debut_txt[pos:], count=1)
        versets_debut = [int(n) for n in re.findall(r"\d+", apres)]
    dernier_chapitre = chap_debut[-1][1] if chap_debut else chapitre

    if re.search(r"FIN DU CHAP", fin_txt or s):
        debut_v = versets_debut[0] if versets_debut else 1
        return ((chapitre, debut_v), (dernier_chapitre, 999), herite)
    if not versets_debut and not fin_txt:
        return None
    if not versets_debut:
        # « (JUSQU’AU VERSET 9) » : l'homélie reprend où la précédente s'est arrêtée.
        versets_debut = [verset_suivant if herite else 1]

    if fin_txt:
        chap_fin = _chapitres(fin_txt)
        du_chap = re.search(r"DU\s+CHAP(?:ITRE)?\.?\s*([IVXLC]+|\d+)", fin_txt)
        nombres_fin = [int(n) for n in re.findall(r"\d+", re.sub(_CHAP, " ", fin_txt))]
        if not nombres_fin:
            return None
        if du_chap:
            fin = (_nombre(du_chap[1]), nombres_fin[0])
        elif chap_fin:
            fin = (chap_fin[-1][1], nombres_fin[-1])
        else:
            fin = (dernier_chapitre, nombres_fin[-1])
    else:
        fin = (dernier_chapitre, versets_debut[-1])
    debut_v = versets_debut[0]
    if herite and fin[0] == chapitre:
        debut_v = min(debut_v, fin[1])
    return ((chapitre, debut_v), fin, herite)


def _propre(texte: str) -> str:
    texte = re.sub(r"\[\s*modifier\s*\]", " ", texte.replace("\xa0", " "))
    return re.sub(r"\s+", " ", texte).strip()


def decouper_homelies(texte: str, sigle: str, url: str,
                      nb_chapitres: int | None = None,
                      precedentes: list[dict] | None = None) -> tuple[list[dict], list[str]]:
    """Découpe un commentaire en homélies indexées par référence biblique.
    Renvoie (unités indexées, numéros des homélies ignorées)."""
    texte = _propre(texte)
    reperes = list(re.finditer(r"HOMÉLIE ([IVXLC]+)\b\.?", texte))
    # Un commentaire suivi commence au chapitre 1 : « (VERSET 1) » en tête
    # de livre vaut donc 1, 1.
    unites, ignorees, chapitre = [], [], 1
    # Un livre peut s'étendre sur plusieurs pages Wikisource qui se
    # chevauchent : on reprend l'état de la page précédente.
    deja = {u["homelie"] for u in precedentes or []}
    rompue = False  # après une homélie écartée, le chapitre n'est plus sûr
    if precedentes:
        dernier = precedentes[-1]["fin"]
        chapitre = dernier[0] if dernier[1] != 999 else dernier[0] + 1
    for i, m in enumerate(reperes):
        if m[1] in deja:
            continue  # homélie déjà lue sur la page précédente
        bloc = texte[m.end(): reperes[i + 1].start() if i + 1 < len(reperes) else len(texte)].strip()
        analyse_m = re.search(r"\bANALYSE\b\.?", bloc, re.I)
        entete = bloc[: analyse_m.start()] if analyse_m else bloc[:1200]
        ref_m = next((r for r in re.finditer(r"\(([^()]{1,120})\)", entete) if re.search(r"\d|FIN DU CHAP", r[1], re.I)), None)
        if not ref_m:  # parenthèse ouvrante oubliée par la transcription
            ref_m = re.search(r"\b(?:CHAP\.|VERS(?:ET)?\.?)\s*[^()]{0,100}?\d[^()]{0,60}?(?:\)|$)", entete)
        precedente = (unites or precedentes or [None])[-1]
        suivant = (precedente["fin"][1] + 1 if precedente and precedente["fin"][0] == chapitre
                   and precedente["fin"][1] != 999 else 1)
        ref = parser_reference(ref_m[0], chapitre, suivant) if ref_m else None
        if not ref or (rompue and ref[2]):
            ignorees.append(m[1])
            # En tête de livre (rien d'indexé encore), le chapitre 1 reste sûr.
            rompue = bool(unites or precedentes)
            continue
        debut, fin, herite = ref
        cle = lambda cv: cv[0] * 1000 + cv[1]  # noqa: E731
        hors_livre = nb_chapitres is not None and max(debut[0], fin[0]) > nb_chapitres
        reference = (unites or precedentes or [None])[-1]
        recule = reference is not None and cle(debut) < cle(tuple(reference["debut"]))
        if hors_livre or cle(debut) > cle(fin) or recule:
            ignorees.append(m[1])  # référence incohérente : jamais devinée
            rompue = True
            continue
        rompue = False
        chapitre = fin[0] if fin[1] != 999 else fin[0] + 1
        analyse, corps = "", bloc[ref_m.end():]
        if analyse_m:
            apres = bloc[analyse_m.end():].strip()
            # L'analyse liste « 1. … 2. … » ou « 1 et 2. … » ; le corps commence
            # au « 1. » qui suit la liste.
            premiers = [x.start() for x in re.finditer(r"(?:^|\s)1\.\s", apres)]
            analyse_numerotee = bool(re.match(r"1\.\s", apres))
            coupe = (premiers[1] if analyse_numerotee and len(premiers) > 1
                     else premiers[0] if premiers and not analyse_numerotee else 0)
            analyse, corps = apres[:coupe].strip(), apres[coupe:]
        unites.append({
            "id": f"chrysostome-{sigle}-{m[1]}",
            "livre": sigle,
            "homelie": m[1],
            "debut": list(debut),
            "fin": list(fin),
            "chapitre_herite": herite,
            "lemme": entete[: ref_m.start()].strip().strip("«» ").strip(),
            "analyse": analyse,
            "texte": corps.strip(),
            "source_url": url,
        })
    return unites, ignorees


def appliquer_corrections(unites: list[dict], corrections: dict[str, dict]) -> None:
    """Corrige les références fautives de l'édition, chacune motivée."""
    for u in unites:
        c = corrections.get(u["homelie"])
        if c:
            u["debut"], u["fin"], u["correction"] = list(c["debut"]), list(c["fin"]), c["motif"]


def _sans_accents(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")


def etendue(reference_courte: str) -> tuple[str, tuple[int, int], tuple[int, int]] | None:
    """« 1 Th 1, 5c-10 » → ("1Th", (1, 5), (1, 10)). Les psaumes à double
    numérotation et les références illisibles renvoient None."""
    if "(" in reference_courte:
        return None
    m = re.match(r"\s*(\d?)\s*([A-Za-zÀ-ÿ]+)\s+(\d+)\s*,\s*(.+)$", reference_courte)
    if not m:
        return None
    sigle, chapitre, plage = f"{m[1]}{m[2]}", int(m[3]), m[4]
    croise = re.search(r"[-–]\s*(\d+)\s*,\s*(\d+)[a-z]?\s*$", plage)
    nombres = [int(n) for n in re.findall(r"\d+", plage[: croise.start()] if croise else plage)]
    if not nombres:
        return None
    fin = (int(croise[1]), int(croise[2])) if croise else (chapitre, max(nombres))
    return sigle, (chapitre, min(nombres)), fin


def passages_pour(reference_courte: str, unites: dict[str, list[dict]]) -> list[dict]:
    """Les homélies qui commentent une lecture, meilleur recouvrement d'abord."""
    e = etendue(reference_courte)
    if not e or e[0] not in unites:
        return []
    cle = lambda cv: cv[0] * 1000 + cv[1]  # noqa: E731
    d, f = cle(e[1]), cle(e[2])
    notes = []
    for u in unites[e[0]]:
        recouvre = min(f, cle(u["fin"])) - max(d, cle(u["debut"])) + 1
        if recouvre > 0:
            notes.append((recouvre, u))
    notes.sort(key=lambda x: -x[0])
    return [u for _, u in notes[:MAX_PASSAGES]]


# --------- Import depuis Wikisource (réseau, avec cache) ---------

def _nom_cache(page: str) -> str:
    return re.sub(r"[^\w]+", "_", _sans_accents(page)).strip("_") + ".html"


def _html_de_la_page(page: str, cache: Path) -> str:
    """Rendu HTML d'une page Wikisource (texte transclus compris), mis en
    cache : on ne sollicite Wikisource qu'une fois par page."""
    fichier = cache / _nom_cache(page)
    if fichier.exists():
        return fichier.read_text(encoding="utf-8")
    for essai in range(4):
        r = requests.get(API, params={"action": "parse", "prop": "text", "format": "json",
                                      "maxlag": 5, "page": page}, headers=ENTETES, timeout=120)
        if r.ok:
            d = r.json()
            if "error" in d:
                raise RuntimeError(f"Wikisource : {page} — {d['error'].get('info')}")
            html = d["parse"]["text"]["*"]
            cache.mkdir(parents=True, exist_ok=True)
            fichier.write_text(html, encoding="utf-8")
            time.sleep(PAUSE)
            return html
        time.sleep(PAUSE * (essai + 2))
    raise RuntimeError(f"Wikisource indisponible pour {page} (HTTP {r.status_code}).")


def _texte_de_html(html: str) -> str:
    sans = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", html, flags=re.S)
    sans = re.sub(r"<sup[^>]*class=\"reference\"[^>]*>.*?</sup>", " ", sans, flags=re.S)
    sans = re.sub(r"<[^>]+>", " ", sans)
    import html as html_lib
    return html_lib.unescape(sans)


def importer(sigle: str, sortie: Path = TEXTES, cache: Path = CACHE) -> dict[str, Any]:
    """Importe les homélies d'un livre. Tout est lu avant d'écrire : une
    panne réseau ne laisse jamais de fichier à moitié rempli."""
    nom, pages = PAGES[sigle]
    unites, ignorees = [], []
    for page in pages:
        url = "https://fr.wikisource.org/wiki/" + page.replace(" ", "_")
        u, ig = decouper_homelies(_texte_de_html(_html_de_la_page(page, cache)), sigle, url,
                                  nb_chapitres=NB_CHAPITRES.get(sigle), precedentes=unites)
        unites += u
        ignorees += ig
    fichier_corr = TEXTES / "corrections.json"
    if fichier_corr.exists():
        appliquer_corrections(unites, json.loads(fichier_corr.read_text(encoding="utf-8")).get(sigle, {}))
    sortie.mkdir(parents=True, exist_ok=True)
    (sortie / f"{sigle}.json").write_text(json.dumps({
        "oeuvre": "chrysostome-homelies",
        "livre": sigle,
        "titre": f"Homélies sur {nom}",
        "unites": unites,
    }, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return {"indexees": len(unites), "ignorees": ignorees}


def charger_unites(dossier: Path = TEXTES) -> dict[str, list[dict]]:
    """Toutes les homélies indexées, par sigle de livre."""
    if not dossier.exists():
        return {}
    return {f.stem: json.loads(f.read_text(encoding="utf-8"))["unites"]
            for f in sorted(dossier.glob("*.json")) if f.stem != "corrections"}


if __name__ == "__main__":
    lignes = ["# Couverture du corpus Chrysostome", "",
              "Homélies indexées par référence biblique ; les ignorées ont une "
              "référence illisible et ne sont jamais devinées.", ""]
    for s in PAGES:
        b = importer(s)
        lignes.append(f"- **{s}** ({PAGES[s][0]}) : {b['indexees']} indexées"
                      + (f", ignorées : {', '.join(b['ignorees'])}" if b["ignorees"] else ""))
        print(lignes[-1])
    (TEXTES / "RAPPORT.md").write_text("\n".join(lignes) + "\n", encoding="utf-8")
