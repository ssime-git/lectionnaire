"""Rattrape les vidéos des jours publiés avant le compagnon (phase 1).

    LECTIONNAIRE_MOTEUR=claude python src/rattraper_videos.py

Seuls les jours sans clé « videos » sont traités, par lots (un appel pour
plusieurs jours, pour ménager le quota). Mêmes règles que la nuit : ids du
catalogue uniquement, une raison par vidéo, filtrées avant écriture. Relancer
reprend là où l'on s'est arrêté.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from generate import MAX_VIDEOS, _appel, _filtrer_videos, _json_propre  # type: ignore
from videos import charger_catalogue

JOURS = Path(__file__).resolve().parent.parent / "data" / "jours"
LOT = 10

CONSIGNE = (
    "Tu choisis des vidéos de la chaîne BibleProject - Français pour des pages "
    "de lectionnaire. Pour chaque jour, 0 à " + str(MAX_VIDEOS) + " vidéos "
    "{id, raison, groupe: 'mot'|'livre'}, uniquement des ids de catalogue_videos : "
    "'mot' pour une étude de mot ou un thème qui touche un verset précis du jour, "
    "'livre' pour le panorama d'un livre lu ce jour ; raison = une phrase qui relie "
    "la vidéo à un verset ou à un livre du jour. Une liste vide vaut mieux qu'une "
    "vidéo sans lien réel. Réponds UNIQUEMENT par un objet JSON {date: [vidéos]}."
)


def rattraper(jours: Path, catalogue: dict[str, str], lot: int = LOT) -> list[str]:
    a_faire = [f for f in sorted(jours.glob("*.json"))
               if "videos" not in json.loads(f.read_text(encoding="utf-8"))]
    faits: list[str] = []
    for i in range(0, len(a_faire), lot):
        fichiers = a_faire[i:i + lot]
        donnees = {f.stem: json.loads(f.read_text(encoding="utf-8")) for f in fichiers}
        demande = {
            "catalogue_videos": [f"{k} | {t}" for k, t in catalogue.items()],
            "jours": [{"date": d.get("date", k), "titre": d.get("titre", ""),
                       "sous_titre": d.get("sous_titre", ""),
                       "lectures": [lec.get("reference", "") for lec in d.get("lectures", [])]}
                      for k, d in donnees.items()],
        }
        try:
            reponse = _json_propre(_appel(CONSIGNE, json.dumps(demande, ensure_ascii=False)))
        except (RuntimeError, ValueError) as exc:
            print(f"⚠  lot {i // lot + 1} : {exc}")
            continue
        for f in fichiers:
            if f.stem not in reponse:
                continue
            d = donnees[f.stem]
            d["videos"] = reponse[f.stem]
            _filtrer_videos(d, catalogue)
            f.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
            faits.append(f.stem)
        print(f"lot {i // lot + 1} : {len(fichiers)} jours")
    return faits


if __name__ == "__main__":
    faits = rattraper(JOURS, charger_catalogue())
    print(f"✓ {len(faits)} jours complétés.")
    sys.exit(0)
