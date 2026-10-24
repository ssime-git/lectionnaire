#!/usr/bin/env python3
"""
videos.py — le catalogue des vidéos BibleProject - Français.

Le catalogue (data/videos.json) est la SEULE source d'identifiants de vidéos :
le brouillon de nuit choisit dedans, le validateur refuse ce qui n'y est pas,
le rendu y reprend les titres. Il se rafraîchit en lisant la page publique de
la chaîne — pas d'API YouTube Data, donc ni clé ni quota.

    python src/videos.py        # rafraîchit data/videos.json
"""

from __future__ import annotations
import json
import re
from pathlib import Path
from typing import Any

import requests

RACINE = Path(__file__).resolve().parent.parent
CATALOGUE = RACINE / "data" / "videos.json"
CHAINE = {
    "nom": "BibleProject - Français",
    "url": "https://www.youtube.com/@BibleProject-Fran%C3%A7ais",
}
_PAGE = CHAINE["url"] + "/videos"
_BROWSE = "https://www.youtube.com/youtubei/v1/browse?key={cle}"
_ENTETES = {
    "Accept-Language": "fr-FR,fr",
    "User-Agent": ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                   "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36"),
    # En Europe, YouTube redirige vers consent.youtube.com sans ce cookie
    # (valeur « cookies optionnels refusés »).
    "Cookie": "SOCS=CAI",
}


def charger_catalogue(chemin: Path = CATALOGUE) -> dict[str, str]:
    """id → titre ; vide si le catalogue n'existe pas encore."""
    if not chemin.exists():
        return {}
    d = json.loads(chemin.read_text(encoding="utf-8"))
    return {v["id"]: v["titre"] for v in d.get("videos", [])}


def telecharger_vignette(vid: str, dossier: Path) -> Path | None:
    """Vignette servie depuis le site : le lecteur ne contacte Google qu'en
    cliquant. Jamais d'exception — sans image, la façade affiche le titre."""
    chemin = dossier / f"{vid}.jpg"
    if chemin.exists():
        return chemin
    try:
        r = requests.get(f"https://i.ytimg.com/vi/{vid}/hqdefault.jpg", timeout=20)
        r.raise_for_status()
    except requests.RequestException:
        return None
    dossier.mkdir(parents=True, exist_ok=True)
    chemin.write_bytes(r.content)
    return chemin


def extraire_videos(donnees: Any) -> dict[str, str]:
    """Collecte les vidéos d'un JSON YouTube, quel que soit son niveau
    d'imbrication. Deux formats coexistent selon les pages."""
    trouvees: dict[str, str] = {}

    def parcourir(o: Any) -> None:
        if isinstance(o, list):
            for x in o:
                parcourir(x)
        elif isinstance(o, dict):
            lock = o.get("lockupViewModel")
            if isinstance(lock, dict):
                titre = (((lock.get("metadata") or {}).get("lockupMetadataViewModel") or {})
                         .get("title") or {}).get("content")
                if lock.get("contentId") and titre:
                    trouvees[lock["contentId"]] = titre
            if isinstance(o.get("videoId"), str) and isinstance(o.get("title"), dict):
                t = o["title"]
                titre = "".join(r.get("text", "") for r in t["runs"]) if "runs" in t else t.get("simpleText")
                if titre:
                    trouvees[o["videoId"]] = titre
            for v in o.values():
                parcourir(v)

    parcourir(donnees)
    return trouvees


def _continuation(o: Any) -> str | None:
    if isinstance(o, list):
        for x in o:
            c = _continuation(x)
            if c:
                return c
    elif isinstance(o, dict):
        jeton = (o.get("continuationCommand") or {}).get("token")
        if jeton:
            return jeton
        for v in o.values():
            c = _continuation(v)
            if c:
                return c
    return None


def _recuperer_tout() -> dict[str, str]:
    """Lit la page /videos puis suit les continuations jusqu'au bout."""
    page = requests.get(_PAGE, headers=_ENTETES, timeout=30)
    page.raise_for_status()
    html = page.text
    m = re.search(r"var ytInitialData = (\{.*?\});</script>", html, re.S)
    cle = re.search(r'"INNERTUBE_API_KEY":"([^"]+)"', html)
    version = re.search(r'"INNERTUBE_CLIENT_VERSION":"([^"]+)"', html)
    if not (m and cle and version):
        raise RuntimeError("Page de la chaîne illisible : le format YouTube a changé.")
    initial = json.loads(m.group(1))
    trouvees = extraire_videos(initial)
    jeton = _continuation(initial)
    for _ in range(50):  # garde-fou : ~30 vidéos par page
        if not jeton:
            break
        r = requests.post(
            _BROWSE.format(cle=cle.group(1)),
            headers={**_ENTETES, "Content-Type": "application/json"},
            json={"context": {"client": {"clientName": "WEB", "clientVersion": version.group(1), "hl": "fr"}},
                  "continuation": jeton},
            timeout=30,
        )
        r.raise_for_status()
        suite = r.json()
        trouvees.update(extraire_videos(suite))
        jeton = _continuation(suite)
    return trouvees


def rafraichir(chemin: Path = CATALOGUE, minimum: int = 100) -> int:
    """Réécrit le catalogue. Refuse — sans rien écrire — un résultat trop
    court : un format YouTube changé ne doit jamais vider le catalogue."""
    trouvees = _recuperer_tout()
    if len(trouvees) < minimum:
        raise RuntimeError(
            f"Seulement {len(trouvees)} vidéos trouvées (minimum {minimum}) : "
            f"catalogue conservé tel quel."
        )
    liste = sorted(({"id": i, "titre": t} for i, t in trouvees.items()),
                   key=lambda v: (v["titre"].casefold(), v["id"]))
    chemin.parent.mkdir(parents=True, exist_ok=True)
    chemin.write_text(json.dumps({"chaine": CHAINE, "videos": liste},
                                 ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return len(liste)


if __name__ == "__main__":
    print(f"✓ {rafraichir()} vidéos dans {CATALOGUE.relative_to(RACINE)}")
