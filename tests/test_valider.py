from __future__ import annotations

import copy
import json
import sys
import unittest
from pathlib import Path

RACINE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RACINE / "src"))

import valider  # noqa: E402

BASE = json.loads((RACINE / "data" / "jours" / "2026-10-25.json").read_text(encoding="utf-8"))
CATALOGUE = {"1g4u57TSY0g", "FuQp4baBpPU", "GIdz46OiA5s"} | {f"vid{i:08d}" for i in range(10)}


def _avec(videos: list[dict]) -> dict:
    d = copy.deepcopy(BASE)
    d["videos"] = videos
    return d


def _v(vid: str = "1g4u57TSY0g", raison: str = "Jésus cite le Shema.", groupe: str = "mot") -> dict:
    return {"id": vid, "raison": raison, "groupe": groupe}


class VideosTests(unittest.TestCase):
    def _fautes(self, videos: list[dict]) -> list[str]:
        return valider.valider_contrat(_avec(videos), catalogue=CATALOGUE)

    def test_jour_sans_videos_reste_valide(self) -> None:
        self.assertEqual(valider.valider_contrat(copy.deepcopy(BASE), catalogue=CATALOGUE), [])

    def test_videos_valides_acceptees(self) -> None:
        self.assertEqual(self._fautes([_v(), _v("GIdz46OiA5s", "Ex 22 suit le Sinaï.", "livre")]), [])

    def test_video_hors_catalogue_refusee(self) -> None:
        self.assertTrue(any("hors catalogue" in f for f in self._fautes([_v("inventee123")])))

    def test_video_sans_raison_refusee(self) -> None:
        self.assertTrue(any("raison manquante" in f for f in self._fautes([_v(raison="  ")])))

    def test_groupe_inconnu_refuse(self) -> None:
        self.assertTrue(any("groupe inconnu" in f for f in self._fautes([_v(groupe="theme")])))

    def test_doublon_refuse(self) -> None:
        self.assertTrue(any("doublon" in f for f in self._fautes([_v(), _v()])))

    def test_plus_de_huit_refuse(self) -> None:
        neuf = [_v(f"vid{i:08d}") for i in range(9)]
        self.assertTrue(any("au plus 8" in f for f in self._fautes(neuf)))

    def test_catalogue_par_defaut_lu_depuis_data(self) -> None:
        # Sans catalogue explicite, data/videos.json fait foi.
        self.assertEqual(valider.valider_contrat(_avec([_v()])), [])
        self.assertTrue(any("hors catalogue" in f for f in valider.valider_contrat(_avec([_v("inventee123")]))))


if __name__ == "__main__":
    unittest.main()
