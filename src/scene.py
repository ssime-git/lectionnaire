"""
scene.py — compose les scènes colorées de la page, sans modèle et sans réseau.

Deux usages :
    fond_ouverture(graine)  → aplats derrière le bois gravé du jour (340×150)
    composition(graine)     → scène abstraite d'une pause (1000×300)

Même graine, même image : la page d'un jour ne change pas d'un rendu à
l'autre. Aucune couleur en dur : les aplats prennent des variables CSS
(--c-ocre, --c-rose…) que la météo et le thème font glisser. Les marques de
météo (spirale, nuages, pluie, neige) sont toutes présentes ; le CSS montre
celle du jour.
"""

from __future__ import annotations

import hashlib
import random

PALETTE = ["ocre", "rose", "terre", "bleu", "jaune", "lavande"]


def _alea(graine: str) -> random.Random:
    return random.Random(int(hashlib.sha256(graine.encode()).hexdigest()[:12], 16))


def _meteo(r: random.Random, largeur: int, hauteur: int, echelle: float) -> str:
    """Les quatre états de la météo, dessinés au crayon."""
    sx, sy = largeur * 0.88, hauteur * 0.2
    t = 4 * echelle
    spirale = (f'<path d="M{sx:.0f} {sy:.0f} m-{t:.0f} 0 a{t:.0f} {t:.0f} 0 1 1 {2*t:.0f} 0 '
               f'a{2.2*t:.0f} {2.2*t:.0f} 0 1 1 -{4.4*t:.0f} 0 a{3.6*t:.0f} {3.6*t:.0f} 0 1 1 {7.2*t:.0f} 0 '
               f'a{5.2*t:.0f} {5.2*t:.0f} 0 1 1 -{10.4*t:.0f} 0" fill="none" stroke="var(--c-terre)" '
               f'stroke-width="{0.6*echelle:.1f}" stroke-linecap="round"/>')
    nuages = "".join(
        f'<ellipse cx="{x:.0f}" cy="{y:.0f}" rx="{w:.0f}" ry="{w*.28:.0f}"/>'
        for x, y, w in ((largeur * .12, hauteur * .14, 18 * echelle), (largeur * .2, hauteur * .1, 12 * echelle),
                        (largeur * .68, hauteur * .16, 22 * echelle), (largeur * .76, hauteur * .11, 13 * echelle)))
    gouttes = "".join(
        f'<path class="goutte" style="animation-delay:-{r.random()*1.3:.2f}s" '
        f'd="M{r.random()*largeur*1.04:.0f} 0 l-{2*echelle:.1f} {5.5*echelle:.1f}"/>' for _ in range(26))
    flocons = "".join(
        f'<circle class="flocon" style="animation-delay:-{r.random()*9:.2f}s" cx="{r.random()*largeur:.0f}" '
        f'cy="0" r="{(.4 + r.random()*.6)*echelle:.1f}"/>' for _ in range(30))
    return (f'<g class="m m-soleil" filter="url(#encre)"><g class="spirale">{spirale}</g></g>'
            f'<g class="m m-nuage" fill="var(--c-fond)" filter="url(#pastel)" opacity=".9">{nuages}</g>'
            f'<g class="m m-pluie" stroke="var(--c-bleu)" stroke-width="{0.6*echelle:.1f}" stroke-linecap="round">{gouttes}</g>'
            f'<g class="m m-neige" fill="#fff">{flocons}</g>')


def _plans(r: random.Random, largeur: int, hauteur: int, couleurs: list[str], opacite: str) -> str:
    """Trois pans aux bords obliques, comme des papiers découpés."""
    x1 = largeur * (.3 + r.random() * .1)
    x2 = largeur * (.62 + r.random() * .1)
    d1, d2 = largeur * (r.random() - .5) * .12, largeur * (r.random() - .5) * .12
    pans = [
        f"M0 0H{x1:.0f}L{x1 + d1:.0f} {hauteur}H0Z",
        f"M{x1:.0f} 0H{x2:.0f}L{x2 + d2:.0f} {hauteur}H{x1 + d1:.0f}Z",
        f"M{x2:.0f} 0H{largeur}V{hauteur}H{x2 + d2:.0f}Z",
    ]
    return "".join(f'<path d="{p}" fill="var(--c-{c})" opacity="{opacite}"/>' for p, c in zip(pans, couleurs))


def fond_ouverture(graine: str) -> str:
    """Aplats chauds derrière le bois gravé : la gravure reste lisible."""
    r = _alea("ouverture:" + graine)
    couleurs = r.sample(["ocre", "rose", "lavande", "jaune"], 3)
    disque = (f'<circle cx="{340 * (.15 + r.random() * .2):.0f}" cy="{150 * (.25 + r.random() * .2):.0f}" '
              f'r="{18 + r.random() * 10:.0f}" fill="var(--c-jaune)" opacity=".55"/>')
    return (f'<svg class="fond-scene" viewBox="0 0 340 150" preserveAspectRatio="xMidYMid slice" aria-hidden="true">'
            f'<rect width="340" height="150" fill="var(--c-fond)"/>'
            f'<g filter="url(#pastel)">{_plans(r, 340, 150, couleurs, ".5")}{disque}</g>'
            f'{_meteo(r, 340, 150, 3.4)}</svg>')


def composition(graine: str) -> str:
    """Une scène abstraite de pause : pans, disques, un œil, un trait liturgique."""
    r = _alea("pause:" + graine)
    L, H = 1000, 300
    couleurs = r.sample(PALETTE, 3)
    formes = []
    # Un grand disque concentrique (puits, soleil, cible : chacun y voit son image).
    cx, cy, rr = L * (.22 + r.random() * .2), H * (.45 + r.random() * .15), 80 + r.random() * 40
    c1, c2, c3 = r.sample(["bleu", "terre", "jaune", "lavande", "rose"], 3)
    formes.append(f'<circle cx="{cx:.0f}" cy="{cy:.0f}" r="{rr:.0f}" fill="var(--c-{c1})"/>'
                  f'<circle cx="{cx:.0f}" cy="{cy:.0f}" r="{rr * .6:.0f}" fill="var(--c-{c2})" opacity=".85"/>'
                  f'<circle cx="{cx:.0f}" cy="{cy:.0f}" r="{rr * .28:.0f}" fill="var(--c-{c3})"/>')
    # Un visage de profil réduit à deux plans (clin d'œil cubiste), ou des carrés.
    fx = L * (.62 + r.random() * .12)
    if r.random() < .6:
        formes.append(
            f'<path d="M{fx:.0f} 40 C{fx + 70:.0f} 40 {fx + 100:.0f} 90 {fx + 102:.0f} 130 L{fx + 130:.0f} 160 '
            f'L{fx + 100:.0f} 170 C{fx + 102:.0f} 210 {fx + 70:.0f} 250 {fx:.0f} 260Z" fill="var(--c-{couleurs[1]})"/>'
            f'<path d="M{fx:.0f} 40 C{fx - 70:.0f} 40 {fx - 90:.0f} 110 {fx - 85:.0f} 160 C{fx - 80:.0f} 220 '
            f'{fx - 40:.0f} 260 {fx:.0f} 260Z" fill="var(--c-{couleurs[2]})"/>')
        oeil = (f'<path d="M{fx + 30:.0f} 125 Q{fx + 52:.0f} 108 {fx + 74:.0f} 125 Q{fx + 52:.0f} 140 {fx + 30:.0f} 125Z" '
                f'fill="var(--c-fond)"/><circle cx="{fx + 53:.0f}" cy="{125}" r="6" fill="var(--encre)"/>'
                f'<path d="M{fx:.0f} 40 C{fx + 70:.0f} 40 {fx + 100:.0f} 90 {fx + 102:.0f} 130 L{fx + 130:.0f} 160 '
                f'L{fx + 100:.0f} 170 C{fx + 102:.0f} 210 {fx + 70:.0f} 250 {fx:.0f} 260"/>')
    else:
        for i in range(4):
            x, y = fx - 60 + (i % 2) * 95, 50 + (i // 2) * 105
            plein = r.random() < .5
            formes.append(f'<rect x="{x:.0f}" y="{y}" width="85" height="90" '
                          f'fill="{"var(--c-" + r.choice(PALETTE) + ")" if plein else "none"}"/>')
        tiret = ' stroke-dasharray="6 6"'
        oeil = "".join(f'<rect x="{fx - 60 + (i % 2) * 95:.0f}" y="{50 + (i // 2) * 105}" width="85" height="90"'
                       f'{"" if i % 3 else tiret}/>' for i in range(4))
    trait_y = H * (.78 + r.random() * .1)
    trait = (f'<path d="M{L * .08:.0f} {trait_y:.0f} C{L * .35:.0f} {trait_y - 40:.0f} {L * .6:.0f} {trait_y + 30:.0f} '
             f'{L * .94:.0f} {trait_y - 20:.0f}" stroke="var(--liturgie)" stroke-width="9" fill="none" stroke-linecap="round"/>')
    return (f'<svg viewBox="0 0 {L} {H}" preserveAspectRatio="xMidYMid slice" aria-hidden="true">'
            f'<rect width="{L}" height="{H}" fill="var(--c-fond)"/>'
            f'<g filter="url(#pastel)">{_plans(r, L, H, couleurs, ".6")}{"".join(formes)}{trait}</g>'
            f'{_meteo(r, L, H, 4)}'
            f'<g filter="url(#encre)" stroke="var(--encre)" stroke-width="2.2" fill="none" stroke-linecap="round">'
            f'<circle cx="{cx:.0f}" cy="{cy:.0f}" r="{rr:.0f}"/>{oeil}</g></svg>')


# Filtres partagés : un seul jeu par page.
FILTRES = (
    '<svg width="0" height="0" style="position:absolute" aria-hidden="true" focusable="false"><defs>'
    '<filter id="pastel" x="-5%" y="-5%" width="110%" height="110%">'
    '<feTurbulence type="fractalNoise" baseFrequency=".018" numOctaves="3" seed="3" result="onde"/>'
    '<feDisplacementMap in="SourceGraphic" in2="onde" scale="10" xChannelSelector="R" yChannelSelector="G" result="forme"/>'
    '<feTurbulence type="fractalNoise" baseFrequency=".9 .22" numOctaves="2" seed="8" result="grain"/>'
    '<feColorMatrix in="grain" type="matrix" values="0 0 0 0 0  0 0 0 0 0  0 0 0 0 0  -2.4 0 0 0 1.85" result="masque"/>'
    '<feComposite in="forme" in2="masque" operator="in"/></filter>'
    '<filter id="encre" x="-5%" y="-5%" width="110%" height="110%">'
    '<feTurbulence type="fractalNoise" baseFrequency=".04" numOctaves="2" seed="11" result="t"/>'
    '<feDisplacementMap in="SourceGraphic" in2="t" scale="4" xChannelSelector="R" yChannelSelector="G"/></filter>'
    '</defs></svg>'
)
