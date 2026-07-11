"""
gravure.py — compose un bois gravé au trait à partir d'une SCÈNE déclarative.

Le problème résolu : un LLM ne sait pas produire un SVG cohérent chaque jour.
Il produit des paths tordus, des couleurs en dur, des viewBox incohérents.

La solution : on ne lui demande pas de dessiner. On lui demande de CHOISIR
dans un lexique de motifs, et de les placer dans quatre zones. Le tracé est
déterministe.

    scène (le modèle décide)          SVG (le code trace)
    ────────────────────────          ───────────────────
    {"gauche": {"motif":"ronce"},  →  paths exacts, grille 340×150,
     "droite": {"motif":"pousse"},    classes de trait, zéro couleur
     "sol": "sillons",                en dur
     "ciel": {"motif":"soleil"}}

Trois classes de trait, jamais de hex :
    trait-encre      le trait courant (suit le thème clair/sombre)
    trait-liturgie   la couleur du jour (vert, violet, rouge…)
    trait-rubrique   le rouge de missel — à réserver aux accents

Usage :
    from gravure import composer
    svg = composer({"gauche": {...}, "droite": {...}, "sol": "...", "ciel": {...}})
"""

from __future__ import annotations
from typing import Callable

L, H = 340, 150          # grille fixe
SOL = 120                # ligne d'horizon
ZONES = {                # bornes horizontales de chaque zone
    "gauche": (30, 150),
    "droite": (195, 315),
    "bande": (28, 312),
}
CIEL = (296, 42)         # ancre du motif céleste

# --------------------------------------------------------------------------
# LEXIQUE DES MOTIFS
# Chaque motif est une fonction (x, échelle) -> liste de paths (chaînes « d »).
# Ancré sur le sol, dessiné vers le haut. Trait seul, jamais de remplissage.
# --------------------------------------------------------------------------

def _ble(x: float, s: float = 1) -> list[str]:
    h = 46 * s
    p = [f"M{x} {SOL} V{SOL-h}"]
    for i, dy in enumerate((0, 9, 18)):
        y = SOL - h + 4 + dy
        p += [f"M{x} {y} q-7 -3 -10 -10", f"M{x} {y} q7 -3 10 -10"]
    return p

def _ble_plie(x: float, s: float = 1) -> list[str]:
    h = 44 * s
    return [f"M{x} {SOL} q3 -{h*0.6:.0f} -16 -{h:.0f}",
            f"M{x-16} {SOL-h} q-6 2 -9 7",
            f"M{x-14} {SOL-h+6} q-6 2 -9 7"]

def _ronce(x: float, s: float = 1) -> list[str]:
    h = 34 * s
    return [f"M{x} {SOL} q-14 -{h*0.9:.0f} 12 -{h:.0f} q-20 {h*0.55:.0f} 4 {h*0.8:.0f}",
            f"M{x} {SOL} q18 -{h*0.65:.0f} -6 -{h*1.05:.0f}",
            f"M{x-8} {SOL-h+4} l6 -5", f"M{x+10} {SOL-h+12} l-6 -5"]

def _pousse(x: float, s: float = 1) -> list[str]:
    h = 30 * s
    return [f"M{x} {SOL} v-{h:.0f}",
            f"M{x} {SOL-h+10} q-8 -5 -12 -14",
            f"M{x} {SOL-h+8} q8 -5 12 -14"]

def _arbre(x: float, s: float = 1) -> list[str]:
    h = 58 * s
    return [f"M{x} {SOL} v-{h:.0f}",
            f"M{x} {SOL-h*0.55:.0f} q-14 -6 -20 -20",
            f"M{x} {SOL-h*0.62:.0f} q14 -6 20 -20",
            f"M{x} {SOL-h*0.8:.0f} q-10 -5 -14 -16",
            f"M{x} {SOL-h*0.85:.0f} q10 -5 14 -16"]

def _vigne(x: float, s: float = 1) -> list[str]:
    h = 50 * s
    return [f"M{x} {SOL} q-8 -{h*0.35:.0f} 4 -{h*0.6:.0f} q10 -{h*0.25:.0f} -2 -{h*0.4:.0f}",
            f"M{x+2} {SOL-h*0.6:.0f} q10 -2 14 -10",
            f"M{x-2} {SOL-h*0.35:.0f} q-11 -2 -15 -10",
            f"M{x+1} {SOL-h:.0f} a4 4 0 1 1 0.1 0"]

def _brebis(x: float, s: float = 1) -> list[str]:
    return [f"M{x-14} {SOL-14} a14 10 0 1 1 26 2",
            f"M{x+12} {SOL-16} a5 5 0 1 0 7 4",
            f"M{x-10} {SOL-4} v4 M{x-2} {SOL-3} v3 M{x+6} {SOL-4} v4"]

def _montagne(x: float, s: float = 1) -> list[str]:
    h = 52 * s
    return [f"M{x-28} {SOL} l{14} -{h*0.62:.0f} l10 {h*0.2:.0f} l12 -{h*0.55:.0f} l20 {h:.0f}"]

def _flamme(x: float, s: float = 1) -> list[str]:
    h = 36 * s
    return [f"M{x} {SOL} q-11 -{h*0.4:.0f} -1 -{h*0.72:.0f} q-3 {h*0.3:.0f} 6 {h*0.34:.0f} "
            f"q7 -{h*0.45:.0f} -3 -{h:.0f} q14 {h*0.5:.0f} 3 {h:.0f} q9 -6 6 -{h*0.4:.0f} "
            f"q8 {h*0.45:.0f} -11 {h*0.78:.0f}"]

def _porte(x: float, s: float = 1) -> list[str]:
    w, h = 26 * s, 52 * s
    return [f"M{x-w/2:.0f} {SOL} v-{h*0.62:.0f} a{w/2:.0f} {w/2:.0f} 0 0 1 {w:.0f} 0 v{h*0.62:.0f}",
            f"M{x} {SOL} v-{h*0.86:.0f}"]

def _pain(x: float, s: float = 1) -> list[str]:
    return [f"M{x-20} {SOL} q0 -20 20 -20 q20 0 20 20 z",
            f"M{x-9} {SOL-13} l5 -5 M{x+1} {SOL-15} l5 -5 M{x+11} {SOL-13} l5 -5"]

def _coupe(x: float, s: float = 1) -> list[str]:
    return [f"M{x-13} {SOL-40} q0 18 13 20 q13 -2 13 -20 z",
            f"M{x} {SOL-20} v14", f"M{x-11} {SOL} h22"]

def _filet(x: float, s: float = 1) -> list[str]:
    p = []
    for i in range(-2, 3):
        p.append(f"M{x + i*11} {SOL} l{11} -{40}")
        p.append(f"M{x + i*11} {SOL} l-{11} -{40}")
    return p

def _pierre(x: float, s: float = 1) -> list[str]:
    return [f"M{x-15} {SOL} q2 -13 15 -13 q13 0 15 13"]

def _maillon(x: float, s: float = 1) -> list[str]:
    return [f"M{x} {SOL-38} a11 17 0 1 0 0.1 0"]

def _maillon_ouvert(x: float, s: float = 1) -> list[str]:
    """Le maillon rompu : là où la chaîne cesse."""
    return [f"M{x+4} {SOL-55} a11 17 0 0 0 -8 30",
            f"M{x-4} {SOL-21} a11 17 0 0 0 8 -30"]

MOTIFS_SOL: dict[str, Callable] = {
    "ble": _ble, "ble_plie": _ble_plie, "ronce": _ronce, "pousse": _pousse,
    "arbre": _arbre, "vigne": _vigne, "brebis": _brebis, "montagne": _montagne,
    "flamme": _flamme, "porte": _porte, "pain": _pain, "coupe": _coupe,
    "filet": _filet, "pierre": _pierre,
    "maillon": _maillon, "maillon_ouvert": _maillon_ouvert,
}

# --- motifs célestes : un seul, ancré en haut à droite -------------------

def _soleil(cx: float, cy: float) -> list[str]:
    p = [f"M{cx} {cy} m-16 0 a16 16 0 1 0 32 0 a16 16 0 1 0 -32 0"]
    for dx, dy in ((0,-24),(0,24),(-24,0),(24,0),(17,-17),(-17,17),(17,17),(-17,-17)):
        p.append(f"M{cx+dx*0.78:.0f} {cy+dy*0.78:.0f} l{dx*0.28:.0f} {dy*0.28:.0f}")
    return p

def _lune(cx: float, cy: float) -> list[str]:
    return [f"M{cx+6} {cy-15} a16 16 0 1 0 0 30 a19 19 0 0 1 0 -30"]

def _etoile(cx: float, cy: float) -> list[str]:
    return [f"M{cx} {cy-17} v34", f"M{cx-15} {cy-9} l30 18", f"M{cx-15} {cy+9} l30 -18"]

def _nuee(cx: float, cy: float) -> list[str]:
    return [f"M{cx-22} {cy+8} a10 10 0 0 1 4 -18 a13 13 0 0 1 24 -4 a9 9 0 0 1 8 22 z"]

def _rayons(cx: float, cy: float) -> list[str]:
    p = []
    for dx, dy in ((26,0),(24,-12),(24,12),(18,-22),(18,22),(8,-27),(8,27)):
        p.append(f"M{cx-16} {cy} l{dx} {dy}")
    return p

def _croix(cx: float, cy: float) -> list[str]:
    return [f"M{cx} {cy-20} v40", f"M{cx-13} {cy-7} h26"]

MOTIFS_CIEL: dict[str, Callable] = {
    "soleil": _soleil, "lune": _lune, "etoile": _etoile,
    "nuee": _nuee, "rayons": _rayons, "croix": _croix,
}

# --- styles de sol -------------------------------------------------------

def _sol_sillons() -> list[tuple[str, str]]:
    p = [("trait-encre", f"M6 {SOL} q120 -12 328 0")]
    for dy in (8, 16, 24):
        p.append(("trait-encre", f"M6 {SOL+dy} q120 -{12-dy//3} 328 0"))
    for x in (44, 76, 108, 240, 272, 304):
        p.append(("trait-encre", f"M{x} {SOL+2} l{-4 if x<170 else 4} 22"))
    return p

def _sol_eau() -> list[tuple[str, str]]:
    return [("trait-encre", f"M6 {SOL+d} q22 -7 44 0 t44 0 t44 0 t44 0 t44 0 t44 0 t44 0")
            for d in (0, 10, 20)]

def _sol_pierres() -> list[tuple[str, str]]:
    p = [("trait-encre", f"M6 {SOL} h328")]
    for x in range(30, 330, 42):
        p.append(("trait-encre", f"M{x} {SOL+14} q3 -10 12 -10 q9 0 12 10"))
    return p

def _sol_plat() -> list[tuple[str, str]]:
    return [("trait-encre", f"M6 {SOL} h328")]

SOLS: dict[str, Callable] = {
    "sillons": _sol_sillons, "eau": _sol_eau,
    "pierres": _sol_pierres, "plat": _sol_plat, "aucun": lambda: [],
}

TRAITS = {"encre": "trait-encre", "liturgie": "trait-liturgie",
          "rubrique": "trait-rubrique"}


# --------------------------------------------------------------------------
# COMPOSITION
# --------------------------------------------------------------------------

def _placer(zone: str, n: int) -> list[float]:
    a, b = ZONES[zone]
    if n == 1:
        return [(a + b) / 2]
    pas = (b - a) / (n - 1)
    return [a + i * pas for i in range(n)]


def _zone(spec: dict, zone: str) -> list[tuple[str, str]]:
    if not spec:
        return []
    motif = spec.get("motif")
    if motif not in MOTIFS_SOL:
        raise ValueError(f"Motif inconnu : {motif!r}. "
                         f"Lexique : {sorted(MOTIFS_SOL)}")
    n = int(spec.get("n", 3))
    trait = TRAITS[spec.get("trait", "encre")]
    rupture = spec.get("rupture_a")     # index 1-based, pour la chaîne brisée
    echelle = float(spec.get("echelle", 1))

    sorties: list[tuple[str, str]] = []
    for i, x in enumerate(_placer(zone, n), start=1):
        if rupture and i == rupture:
            for d in _maillon_ouvert(x, echelle):
                sorties.append((TRAITS["liturgie"], d))
        else:
            for d in MOTIFS_SOL[motif](x, echelle):
                sorties.append((trait, d))
    return sorties


def composer(scene: dict) -> str:
    """scene → chaîne SVG prête à coller dans le JSON du jour."""
    paths: list[tuple[str, str]] = []

    style_sol = scene.get("sol", "plat")
    if style_sol not in SOLS:
        raise ValueError(f"Sol inconnu : {style_sol!r}. Choix : {sorted(SOLS)}")
    paths += SOLS[style_sol]()

    if "bande" in scene:
        paths += _zone(scene["bande"], "bande")
    else:
        paths += _zone(scene.get("gauche", {}), "gauche")
        paths += _zone(scene.get("droite", {}), "droite")

    ciel = scene.get("ciel")
    if ciel:
        m = ciel.get("motif")
        if m not in MOTIFS_CIEL:
            raise ValueError(f"Motif céleste inconnu : {m!r}. "
                             f"Choix : {sorted(MOTIFS_CIEL)}")
        trait = TRAITS[ciel.get("trait", "rubrique")]
        cx, cy = ciel.get("x", CIEL[0]), ciel.get("y", CIEL[1])
        for d in MOTIFS_CIEL[m](cx, cy):
            paths.append((trait, d))

    # regrouper par classe de trait : moins de balises, SVG plus propre
    groupes: dict[str, list[str]] = {}
    for cls, d in paths:
        groupes.setdefault(cls, []).append(d)

    corps = "".join(
        f'<g class="{cls}">' + "".join(f'<path d="{d}"/>' for d in ds) + "</g>"
        for cls, ds in groupes.items()
    )
    return (f'<svg viewBox="0 0 {L} {H}" xmlns="http://www.w3.org/2000/svg" '
            f'fill="none" stroke-width="1.3" stroke-linecap="round" '
            f'stroke-linejoin="round">{corps}</svg>')


def lexique() -> str:
    return (f"motifs au sol : {', '.join(sorted(MOTIFS_SOL))}\n"
            f"motifs célestes : {', '.join(sorted(MOTIFS_CIEL))}\n"
            f"styles de sol : {', '.join(sorted(SOLS))}\n"
            f"traits : {', '.join(sorted(TRAITS))}")


if __name__ == "__main__":
    print(lexique())
