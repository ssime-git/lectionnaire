from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import render  # noqa: E402


class DateCompleteTests(unittest.TestCase):
    def test_compose_la_date_francaise_complete(self) -> None:
        self.assertEqual(render._date_complete("2026-07-14"), "mardi 14 juillet 2026")
        self.assertEqual(render._date_complete("2026-12-17"), "jeudi 17 décembre 2026")
        self.assertEqual(render._date_complete("2026-02-21"), "samedi 21 février 2026")

    def test_retombe_sur_la_chaine_brute_si_date_invalide(self) -> None:
        self.assertEqual(render._date_complete("pas-une-date"), "pas-une-date")


CATALOGUE = {"1g4u57TSY0g": "Shema / Écouter", "GIdz46OiA5s": "Exode 19–40 - Panorama",
             "cXwM1xW8LEI": "Me'od / Force"}


class PreparerVideosTests(unittest.TestCase):
    def test_preparer_ordonne_et_reprend_le_titre(self) -> None:
        d = {"videos": [
            {"id": "GIdz46OiA5s", "raison": "Ex 22.", "groupe": "livre"},
            {"id": "1g4u57TSY0g", "raison": "Le Shema.", "groupe": "mot", "titre": "inventé"},
            {"id": "cXwM1xW8LEI", "raison": "Me'od.", "groupe": "mot"},
        ]}
        with tempfile.TemporaryDirectory() as tmp, \
                patch("render.telecharger_vignette", side_effect=lambda vid, dossier: dossier / f"{vid}.jpg"):
            render._preparer_videos(d, CATALOGUE, Path(tmp))
        self.assertEqual([v["id"] for v in d["videos"]], ["1g4u57TSY0g", "cXwM1xW8LEI", "GIdz46OiA5s"])
        self.assertEqual(d["videos"][0]["titre"], "Shema / Écouter")
        self.assertEqual(d["videos"][0]["vignette"], "vignettes/1g4u57TSY0g.jpg")
        self.assertEqual(d["chaine"]["nom"], "BibleProject - Français")

    def test_vignette_absente_ne_bloque_pas(self) -> None:
        d = {"videos": [{"id": "1g4u57TSY0g", "raison": "Le Shema.", "groupe": "mot"}]}
        with tempfile.TemporaryDirectory() as tmp, patch("render.telecharger_vignette", return_value=None):
            render._preparer_videos(d, CATALOGUE, Path(tmp))
        self.assertIsNone(d["videos"][0]["vignette"])
        self.assertEqual(d["videos"][0]["titre"], "Shema / Écouter")

    def test_sans_videos_liste_vide(self) -> None:
        d: dict = {}
        render._preparer_videos(d, CATALOGUE, Path("/inutile"))
        self.assertEqual(d["videos"], [])


if __name__ == "__main__":
    unittest.main()
