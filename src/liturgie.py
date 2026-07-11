"""
liturgie.py — dérive la COULEUR du jour depuis le calendrier, pas depuis un LLM.

C'est le cœur du parti pris visuel : le filet vertical qui court le long de la
page (l'axe de la croix) porte la couleur liturgique. Elle ENCODE une information
vraie — le temps liturgique — au lieu de décorer.

    vert    temps ordinaire
    violet  avent, carême
    blanc   Noël, Pâques, fêtes du Seigneur et de la Vierge, saints non-martyrs
    rouge   Pentecôte, Passion, martyrs, apôtres
    rose    Gaudete (3e dim. Avent), Laetare (4e dim. Carême) — optionnel

L'API AELF expose généralement la couleur dans informations["couleur"].
On la lit si elle est là ; sinon on retombe sur « vert » (défaut du temps
ordinaire) plutôt que d'inventer.
"""

from __future__ import annotations
from dataclasses import dataclass


@dataclass(frozen=True)
class CouleurLiturgique:
    cle: str
    nom: str
    hex: str          # sur papier ivoire (thème clair)
    hex_sombre: str   # sur encre profonde (thème sombre) — MÊME teinte, éclaircie

    def as_dict(self) -> dict:
        return {"cle": self.cle, "nom": self.nom,
                "hex": self.hex, "hex_sombre": self.hex_sombre}


# Teintes sourdes, jamais saturées : elles doivent tenir en filet de 2px.
# Chaque couleur existe en deux versions car une teinte lisible sur ivoire
# s'éteint sur fond sombre. Ce n'est pas un dégradé automatique : chaque
# variante est choisie pour garder le même « caractère » de couleur.
COULEURS = {
    "vert":   CouleurLiturgique("vert", "vert", "#345E44", "#6E9B7C"),
    "violet": CouleurLiturgique("violet", "violet", "#4C3A63", "#9B84B8"),
    # Le blanc ne peut pas être un filet sur papier ivoire → on l'exprime en or
    # sourd, comme les ornements blancs le sont traditionnellement.
    "blanc":  CouleurLiturgique("blanc", "blanc", "#8C7B4E", "#D6BE83"),
    "rouge":  CouleurLiturgique("rouge", "rouge", "#8C2B22", "#D2685A"),
    "rose":   CouleurLiturgique("rose", "rose", "#9C5F6B", "#D094A0"),
    "noir":   CouleurLiturgique("noir", "noir", "#2A2A28", "#9A9890"),
}

DEFAUT = COULEURS["vert"]

# Normalisation des libellés AELF possibles → clé interne.
_ALIAS = {
    "vert": "vert", "verte": "vert",
    "violet": "violet", "violette": "violet", "pourpre": "violet",
    "blanc": "blanc", "blanche": "blanc", "or": "blanc", "doré": "blanc",
    "rouge": "rouge",
    "rose": "rose",
    "noir": "noir", "noire": "noir",
}


def depuis_aelf(informations: dict) -> CouleurLiturgique:
    """Lit informations["couleur"] renvoyé par l'API AELF.
    ⚠️ La clé exacte est à confirmer contre une réponse réelle ; en cas
    d'absence on retourne le vert, jamais une couleur inventée."""
    brut = (informations or {}).get("couleur", "")
    if not isinstance(brut, str):
        return DEFAUT
    cle = _ALIAS.get(brut.strip().lower())
    return COULEURS.get(cle, DEFAUT) if cle else DEFAUT


def depuis_cle(cle: str) -> CouleurLiturgique:
    """Pour écrire un JSON à la main (étape 1) sans appeler l'API."""
    return COULEURS.get(cle.strip().lower(), DEFAUT)


if __name__ == "__main__":
    for c in COULEURS.values():
        print(f"  {c.cle:7} {c.hex}  {c.nom}")
    print()
    print("AELF { couleur: 'Vert' } →", depuis_aelf({"couleur": "Vert"}).hex)
    print("AELF { }                →", depuis_aelf({}).hex, "(défaut, non inventé)")
