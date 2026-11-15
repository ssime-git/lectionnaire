"""
render.py — JSON du jour + template Jinja2 → page HTML statique.

C'est le cœur de l'étape 1 : il ne dépend d'AUCUN LLM.
Tu écris (ou génères) un JSON dans data/jours/AAAA-MM-JJ.json, tu lances :

    python src/render.py 2026-07-08

et tu obtiens docs/2026-07-08.html + la mise à jour de docs/index.html.

Tant que ce script produit une page parfaite sur plusieurs jours écrits à la
main, le template est validé. Ensuite seulement on branche generate.py.
"""

from __future__ import annotations
import html as html_lib
import json
import re
import sys
from datetime import date, datetime
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from refs import parser_versets
from videos import CHAINE, charger_catalogue, telecharger_vignette
from valider import charger_oeuvres
from corpus import AUTEURS, MAX_PAR_AUTEUR, charger_passages, passages_pour
from scene import FILTRES, composition, fond_ouverture

RACINE = Path(__file__).resolve().parent.parent
DATA_JOURS = RACINE / "data" / "jours"
TEMPLATE_DIR = RACINE / "template"
DOCS = RACINE / "docs"
ECLAIRAGES = RACINE / "data" / "eclairages.json"
METEO = RACINE / "data" / "meteo.json"


# La date affichée se compose ici, en français et sans locale système :
# le `date_humaine` d'AELF est parfois tronqué (« mardi » tout court), ce qui
# laissait le lecteur deviner de quel jour parlait la page.
JOURS_FR = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]
MOIS_FR = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet",
           "août", "septembre", "octobre", "novembre", "décembre"]


def _date_complete(jour_iso: str) -> str:
    try:
        d = datetime.strptime(jour_iso, "%Y-%m-%d").date()
    except ValueError:
        return jour_iso
    return f"{JOURS_FR[d.weekday()]} {d.day} {MOIS_FR[d.month - 1]} {d.year}"


def charger_jour(jour: str) -> dict:
    chemin = DATA_JOURS / f"{jour}.json"
    if not chemin.exists():
        raise FileNotFoundError(
            f"Pas de JSON pour {jour} ({chemin}). "
            f"Écris-le à la main (étape 1) ou lance generate.py (étape 2)."
        )
    donnees = json.loads(chemin.read_text(encoding="utf-8"))
    donnees["date_complete"] = _date_complete(donnees.get("date", jour))
    _resoudre_analogie(donnees)
    _valider(donnees, chemin)
    _preparer_videos(donnees, charger_catalogue(), DOCS / "vignettes")
    donnees.setdefault("carnet", [])
    donnees["oeuvres"] = charger_oeuvres()
    donnees["meteo"] = json.loads(METEO.read_text()) if METEO.exists() else {}
    donnees["eclairages"] = _eclairages(donnees)
    donnees["peres"] = _tradition(donnees)  # sources du fil du jour
    _preparer_scenes(donnees, jour)
    return donnees


def _preparer_scenes(d: dict, jour: str) -> None:
    """Scènes colorées du jour, déterministes (même date, même image).
    Les pauses viennent du JSON (« pauses », facultatif) ; la question finale
    a toujours sa scène."""
    graine = d.get("date", jour)
    d["filtres_svg"] = FILTRES
    d["scene_fond"] = fond_ouverture(graine)
    d["scene_question"] = composition(graine + ":question")
    d["pauses"] = [
        {"question": p["question"], "suite": p.get("suite", ""), "svg": composition(f"{graine}:pause:{i}")}
        for i, p in enumerate(d.get("pauses") or []) if p.get("question")
    ][:1]


def _preparer_videos(d: dict, catalogue: dict[str, str], dossier: Path) -> None:
    """Complète les vidéos choisies : titre du catalogue (jamais celui du
    modèle), vignette locale, études de mots avant panoramas de livres."""
    preparees = []
    for groupe in ("mot", "livre"):
        for v in d.get("videos") or []:
            if v.get("groupe") != groupe:
                continue
            fichier = telecharger_vignette(v["id"], dossier)
            preparees.append({
                "id": v["id"],
                "titre": catalogue.get(v["id"], v["id"]),
                "raison": v.get("raison", ""),
                "groupe": groupe,
                "vignette": f"vignettes/{fichier.name}" if fichier else None,
            })
    d["videos"] = preparees
    d["chaine"] = CHAINE


def _resoudre_analogie(d: dict) -> None:
    """Le JSON de travail porte plusieurs variantes d'analogie (le choix
    éditorial). La page n'en rend qu'UNE. On résout ici :
    analogie.variantes + analogie.choisi → analogie.paragraphes (rendu).

    Rétrocompatible : si 'paragraphes' existe déjà sans 'variantes', on ne
    touche à rien."""
    a = d.get("analogie") or {}
    variantes = a.get("variantes")
    if not variantes:
        return
    i = a.get("choisi", 0)
    if not isinstance(i, int) or not (0 <= i < len(variantes)):
        raise ValueError(
            f"analogie.choisi = {i!r} hors de [0, {len(variantes) - 1}]. "
            f"Indiquer quelle variante publier."
        )
    a["paragraphes"] = [variantes[i]]


# Le template exige ces clés. Mieux vaut échouer ici, avec un message clair,
# que rendre une page où la couleur liturgique ou les racines manquent.
CLES_REQUISES = {
    "date_humaine", "semaine", "ferie", "liturgie", "titre", "titre_html",
    "sous_titre", "gravure_alt", "gravure_svg", "lectures", "contexte",
    "analogie", "invitation", "question", "racines", "references_brutes",
    "traduction_globale",
}


def _valider(d: dict, chemin: Path) -> None:
    manquantes = sorted(CLES_REQUISES - set(d))
    if manquantes:
        raise ValueError(
            f"{chemin.name} : contrat incomplet, clés manquantes → "
            f"{', '.join(manquantes)}"
        )
    lit = d.get("liturgie") or {}
    if not {"nom", "hex", "hex_sombre"} <= set(lit):
        raise ValueError(
            f"{chemin.name} : 'liturgie' doit porter nom, hex et hex_sombre "
            f"(le mode sombre casserait sans hex_sombre). Utilise "
            f"src/liturgie.py : depuis_cle('vert').as_dict()"
        )
    for i, lec in enumerate(d.get("lectures", [])):
        for g in lec.get("gloses", []):
            if f'data-g="{g["id"]}"' not in lec.get("corps_html", ""):
                raise ValueError(
                    f"{chemin.name} : lecture {i}, la glose '{g['id']}' n'a "
                    f"aucun bouton correspondant dans corps_html."
                )


def _texte(fragment: str) -> str:
    """HTML → texte brut, espaces normalisés."""
    blocs = re.sub(r"</(p|div|li|h\d)>|<br\s*/?>", " ", fragment or "")
    sans = re.sub(r"<[^>]+>", "", blocs)  # balises en ligne : aucun espace ajouté
    return re.sub(r"\s+", " ", html_lib.unescape(sans)).strip()


MAX_TRADITION = 4


def _tradition(d: dict) -> list[dict]:
    """Les passages des Pères qui commentent les lectures du jour — plusieurs
    auteurs peuvent se croiser —, recopiés tels quels avec leur source : le
    carnet libre ne cite que cela. Aucun accès réseau ici (le corpus se
    complète la nuit). Si le brouillon a confirmé ses passages
    (« passages_tradition »), eux seuls font foi."""
    confirmes = d.get("passages_tradition")
    extraits: list[dict] = []
    for cle, auteur in AUTEURS.items():
        stock, pris = charger_passages(cle), 0
        # L'évangile d'abord (dernière lecture), puis on remonte ; un passage
        # par lecture et par auteur, le plus proche du texte.
        for lec in reversed(d.get("lectures", [])):
            for u in passages_pour(lec.get("reference", ""), stock)[:1]:
                if pris >= MAX_PAR_AUTEUR or len(extraits) >= MAX_TRADITION \
                        or any(e["id"] == u["id"] for e in extraits):
                    continue
                if confirmes is not None and u["id"] not in confirmes:
                    continue
                texte = u.get("texte", "")
                pris += 1
                extraits.append({
                    "id": u["id"],
                    "titre": f"{auteur.nom}, {u['titre']}",
                    "lecture": lec.get("reference", ""),
                    "analyse": u.get("analyse", ""),
                    "extrait": texte[:1500],
                    "url": u.get("source_url", ""),
                    "credit": auteur.credit,
                })
    return extraits


def contexte_du_jour(d: dict) -> dict:
    """Ce que le carnet libre sait du jour : le contenu de la page, en texte.
    Publié en statique, lu côté serveur — jamais envoyé par le navigateur."""
    return {
        "date": d.get("date", ""),
        "titre": d.get("titre", ""),
        "references": d.get("references_brutes", ""),
        "lectures": [{"etiquette": l.get("etiquette", ""), "reference": l.get("reference", ""),
                      "texte": _texte(l.get("corps_html", ""))} for l in d.get("lectures", [])],
        "gloses": [{"lemme": g.get("lemme", ""), "texte": _texte(g.get("html", ""))}
                   for l in d.get("lectures", []) for g in l.get("gloses", [])],
        "contexte": [{"titre": c.get("titre", ""), "texte": _texte(c.get("corps_html", ""))}
                     for c in d.get("contexte", [])],
        "carnet": [{"question": q.get("question", ""), "reponse": _texte(q.get("reponse_html", ""))}
                   for q in d.get("carnet") or []],
        "tradition": _tradition(d),
    }


# Les lectures du jour arrivent parfois avec le nom du livre en toutes lettres.
SIGLES = {
    "Matthieu": "Mt", "Marc": "Mc", "Luc": "Lc", "Jean": "Jn", "Romains": "Rm",
    "Galates": "Ga", "Éphésiens": "Ep", "Ép": "Ep", "Philippiens": "Ph",
    "Psaume": "Ps", "Psaumes": "Ps", "Ézéchiel": "Ez", "Daniel": "Dn", "Siracide": "Si",
    "Deutéronome": "Dt", "Michée": "Mi", "Genèse": "Gn", "Isaïe": "Is", "Jérémie": "Jr",
    "Apocalypse": "Ap", "Exode": "Ex", "Job": "Jb", "Proverbes": "Pr", "Qohèleth": "Qo",
}


def _passage(reference: str) -> tuple[str | None, int | None, list[int]]:
    """« Ps 22 (23), 1-6 » → ("Ps", 23, [1..6]) : pour les psaumes, la
    numérotation hébraïque (entre parenthèses, celle de Segond) fait foi."""
    m = re.match(r"\s*(\S+)\s+(\d+)\s*\((\d+)\)\s*,\s*(.+)", reference)
    if m:
        reference = f"{m.group(1)} {m.group(3)}, {m.group(4)}"
    tete = re.match(r"\s*\S+\s+(\d+)\s*,(.*)", reference)
    if not tete:
        return None, None, []
    chapitre_lu, suite = int(tete.group(1)), tete.group(2)
    # « Mt 21, 33-22, 14 » change de chapitre : pas pris en charge. Mais
    # « Ps 33 (34), 2-3, 4-5 » n'est qu'une suite de versets du même psaume.
    for a, b in re.findall(r"(\d+)[a-z]*\s*-\s*(\d+)\s*,", suite):
        if int(b) == chapitre_lu + 1 and int(b) < int(a):
            return None, None, []
    reference = reference[:tete.start(2)] + suite.replace(",", ".")
    livre, chapitre, versets = parser_versets(reference)
    return SIGLES.get(livre, livre), chapitre, versets


def _ancre(a: list) -> tuple[str, int, set[int]]:
    """[livre, chapitre, verset] ou [livre, chapitre, début, fin]."""
    fin = a[3] if len(a) > 3 else a[2]
    return a[0], a[1], set(range(a[2], fin + 1))


MAX_ECLAIRAGES = 2


def _eclairages(d: dict) -> list[dict]:
    """Corpus relu, apparié à un verset effectivement présent dans les lectures.

    Aucun appel au modèle : on ne lui demande pas d'inventer une attribution.
    L'évangile passe en premier ; deux auteurs différents au plus.
    """
    corpus = json.loads(ECLAIRAGES.read_text(encoding="utf-8"))
    resultat, auteurs = [], set()
    for lecture in reversed(d.get("lectures", [])):
        reference = lecture.get("reference", "")
        livre, chapitre, versets = _passage(reference)
        if not livre:
            continue
        for e in corpus:
            if e["auteur"] in auteurs or any(r["id"] == e["id"] for r in resultat):
                continue
            if any(l == livre and c == chapitre and v & set(versets)
                   for l, c, v in map(_ancre, e["ancrages"])):
                resultat.append({**e, "lecture": reference})
                auteurs.add(e["auteur"])
    return resultat[:MAX_ECLAIRAGES]


def rendre_html(donnees: dict) -> str:
    """Rend la page d'un jour déjà chargé, sans rien écrire."""
    env = Environment(
        loader=FileSystemLoader(str(TEMPLATE_DIR)),
        # autoescape désactivé : le contenu porte du HTML volontaire (| safe).
        # C'est acceptable car la source est TON JSON, pas une entrée externe.
        # Si un jour le contenu vient d'ailleurs, réactive-le et assainis.
        autoescape=select_autoescape(enabled_extensions=(), default=False),
        trim_blocks=True,
        lstrip_blocks=True,
        # Le template est truffé de CSS : `{#carte{...}}` fait croire à Jinja
        # qu'un commentaire {# ... #} commence. On déplace les délimiteurs de
        # commentaire vers des tokens absents du CSS. (Variables {{ }} et blocs
        # {% %} ne collisionnent pas avec du CSS valide.)
        comment_start_string="{##",
        comment_end_string="##}",
    )
    return env.get_template("jour.html.j2").render(**donnees)


def rendre(jour: str) -> Path:
    donnees = charger_jour(jour)
    html = rendre_html(donnees)
    (DOCS / "contexte").mkdir(parents=True, exist_ok=True)
    (DOCS / "contexte" / f"{jour}.json").write_text(
        json.dumps(contexte_du_jour(donnees), ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8")

    DOCS.mkdir(exist_ok=True)
    sortie = DOCS / f"{jour}.html"
    sortie.write_text(html, encoding="utf-8")
    print(f"✓ {sortie.relative_to(RACINE)}  ({len(html) // 1024} Ko)")

    reconstruire_index()
    return sortie


def reconstruire_index() -> None:
    """Reconstruit docs/index.html : l'archive navigable, gratuite car chaque
    jour est un fichier figé. Google indexe une page par jour."""
    jours = sorted(
        (p.stem for p in DOCS.glob("20*.html") if p.stem != "index"),
        reverse=True,
    )
    liens = []
    for j in jours:
        titre = ""
        jp = DATA_JOURS / f"{j}.json"
        if jp.exists():
            d = json.loads(jp.read_text(encoding="utf-8"))
            titre = d.get("titre", "")
        try:
            libelle = datetime.strptime(j, "%Y-%m-%d").strftime("%d/%m/%Y")
        except ValueError:
            libelle = j
        liens.append(
            f'<li><a href="./{j}.html"><span class="d">{libelle}</span>'
            f'<span class="t">{titre}</span></a></li>'
        )

    index = _INDEX_AVANT + "\n".join(liens) + _INDEX_APRES
    (DOCS / "index.html").write_text(index, encoding="utf-8")
    # Liste des jours publiés : le fil du jour y trouve la veille et le
    # lendemain sans re-rendre les pages voisines à chaque publication.
    (DOCS / "jours.json").write_text(json.dumps(sorted(jours)), encoding="utf-8")
    print(f"✓ docs/index.html  ({len(jours)} jour·s)")


# Chaînes brutes (pas d'f-string) : le CSS et le JS regorgent d'accolades.
_INDEX_AVANT = """<!DOCTYPE html>
<html lang="fr"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Lectionnaire — archive</title>
<script>(function(){var t=localStorage.getItem('theme');if(t)document.documentElement.setAttribute('data-theme',t)})()</script>
<link href="https://fonts.googleapis.com/css2?family=EB+Garamond:wght@400;500&family=Archivo:wght@500;600&display=swap" rel="stylesheet">
<style>
:root{color-scheme:light dark;
  --papier:#F7EEDF;--ink:#3C3028;--muet:#796451;--filet:#D9C5AC;--accent:#886026;--rubrique:#9B5039}
@media (prefers-color-scheme: dark){:root:not([data-theme="light"]){
  --papier:#261E1A;--ink:#F2E5D1;--muet:#C7B09A;--filet:#594738;--accent:#E5BE83;--rubrique:#E3AC8F}}
:root[data-theme="dark"]{
  --papier:#261E1A;--ink:#F2E5D1;--muet:#C7B09A;--filet:#594738;--accent:#E5BE83;--rubrique:#E3AC8F}
:root[data-theme="dark"]{color-scheme:dark}
:root[data-theme="light"]{color-scheme:light}
body{font-family:'EB Garamond',serif;background:var(--papier);color:var(--ink);max-width:640px;margin:0 auto;padding:3rem 1.5rem}
h1{font-weight:500;font-size:2.2rem;margin-bottom:.3rem}
p.sous{color:var(--muet);margin-bottom:1.2rem}
nav.pages{margin-bottom:2.5rem;font-variant:small-caps;letter-spacing:.08em;font-size:.95rem}
nav.pages a{color:var(--accent);text-decoration:none;margin-right:1.4rem}
nav.pages a:hover{text-decoration:underline}
ul{list-style:none;padding:0}
li a{display:flex;gap:1rem;align-items:baseline;padding:.9rem 0;border-bottom:1px solid var(--filet);text-decoration:none;color:inherit}
li a:hover .t{color:var(--accent)}
.d{font-family:'Archivo',sans-serif;font-size:.8rem;color:var(--muet);min-width:5.5rem}
.t{font-size:1.25rem;transition:color .2s}
.auj{font-family:'Archivo',sans-serif;font-size:.68rem;letter-spacing:.08em;text-transform:uppercase;color:var(--rubrique);border:1px solid var(--rubrique);border-radius:1px;padding:.05rem .45rem;margin-left:auto}
#basculer-theme{position:fixed;top:1rem;right:1rem;width:36px;height:36px;border:1px solid var(--filet);border-radius:50%;background:var(--papier);color:var(--ink);font-size:1rem;cursor:pointer}
#basculer-theme:hover{border-color:var(--accent)}
</style></head><body>
<button id="basculer-theme" aria-label="Basculer entre thème clair et sombre"></button>
<h1>Lectionnaire</h1>
<p class="sous">Une invitation quotidienne à la découverte des Écritures.</p>
<nav class="pages"><a href="./guide.html">Comment lire une page</a><a href="./calendrier.html">L'année liturgique</a></nav>
<ul>
"""

_INDEX_APRES = """
</ul>
<script>
(function(){
  var b=document.getElementById('basculer-theme');
  function courant(){return document.documentElement.getAttribute('data-theme')||(matchMedia('(prefers-color-scheme: dark)').matches?'dark':'light')}
  function icone(){b.textContent=courant()==='dark'?'\\u2600':'\\u263E'}
  b.addEventListener('click',function(){var t=courant()==='dark'?'light':'dark';document.documentElement.setAttribute('data-theme',t);localStorage.setItem('theme',t);icone()});
  icone();
  var d=new Date();
  var iso=d.getFullYear()+'-'+String(d.getMonth()+1).padStart(2,'0')+'-'+String(d.getDate()).padStart(2,'0');
  var a=document.querySelector('a[href="./'+iso+'.html"]');
  if(a)a.insertAdjacentHTML('beforeend','<span class="auj">aujourd\\u2019hui</span>');
})();
</script>
</body></html>"""


if __name__ == "__main__":
    jour = sys.argv[1] if len(sys.argv) > 1 else date.today().isoformat()
    rendre(jour)
