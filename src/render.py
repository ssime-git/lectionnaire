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
import json
import sys
from datetime import date, datetime
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

RACINE = Path(__file__).resolve().parent.parent
DATA_JOURS = RACINE / "data" / "jours"
TEMPLATE_DIR = RACINE / "template"
DOCS = RACINE / "docs"


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
    return donnees


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


def rendre(jour: str) -> Path:
    donnees = charger_jour(jour)

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
    template = env.get_template("jour.html.j2")
    html = template.render(**donnees)

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
  --papier:#EFEAE0;--ink:#26302A;--muet:#8E8B7C;--filet:#DAD1BE;--accent:#7A5230;--rubrique:#A33324}
@media (prefers-color-scheme: dark){:root:not([data-theme="light"]){
  --papier:#17161B;--ink:#E9E5DB;--muet:#918B7C;--filet:#332F38;--accent:#C99A6B;--rubrique:#D4705B}}
:root[data-theme="dark"]{
  --papier:#17161B;--ink:#E9E5DB;--muet:#918B7C;--filet:#332F38;--accent:#C99A6B;--rubrique:#D4705B}
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
