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


def charger_jour(jour: str) -> dict:
    chemin = DATA_JOURS / f"{jour}.json"
    if not chemin.exists():
        raise FileNotFoundError(
            f"Pas de JSON pour {jour} ({chemin}). "
            f"Écris-le à la main (étape 1) ou lance generate.py (étape 2)."
        )
    donnees = json.loads(chemin.read_text(encoding="utf-8"))
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

    index = f"""<!DOCTYPE html>
<html lang="fr"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Lectionnaire — archive</title>
<link href="https://fonts.googleapis.com/css2?family=EB+Garamond:wght@400;500&family=Archivo:wght@500;600&display=swap" rel="stylesheet">
<style>
body{{font-family:'EB Garamond',serif;background:#EFEAE0;color:#26302A;max-width:640px;margin:0 auto;padding:3rem 1.5rem}}
h1{{font-weight:500;font-size:2.2rem;margin-bottom:.3rem}}
p.sous{{color:#8E8B7C;margin-bottom:2.5rem}}
ul{{list-style:none;padding:0}}
li a{{display:flex;gap:1rem;align-items:baseline;padding:.9rem 0;border-bottom:1px solid #DAD1BE;text-decoration:none;color:inherit}}
li a:hover .t{{color:#7A5230}}
.d{{font-family:'Archivo',sans-serif;font-size:.8rem;color:#8E8B7C;min-width:5.5rem}}
.t{{font-size:1.25rem;transition:color .2s}}
</style></head><body>
<h1>Lectionnaire</h1>
<p class="sous">Une invitation quotidienne à la découverte des Écritures.</p>
<ul>
{chr(10).join(liens)}
</ul>
</body></html>"""
    (DOCS / "index.html").write_text(index, encoding="utf-8")
    print(f"✓ docs/index.html  ({len(jours)} jour·s)")


if __name__ == "__main__":
    jour = sys.argv[1] if len(sys.argv) > 1 else date.today().isoformat()
    rendre(jour)
