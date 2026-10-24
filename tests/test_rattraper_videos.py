"""Rattrapage des vidéos des jours publiés avant la phase 1."""
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import rattraper_videos  # noqa: E402

CATALOGUE = {"aaa": "Matthieu 1–13 - Panorama", "bbb": "Agape / Amour"}


class RattrapageTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.jours = Path(self._tmp.name)
        for date, extra in (("2026-01-01", {}), ("2026-01-02", {"videos": []})):
            (self.jours / f"{date}.json").write_text(json.dumps(
                {"date": date, "titre": "T", "sous_titre": "S",
                 "lectures": [{"reference": "Mt 22, 34-40"}], **extra}), encoding="utf-8")

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_seuls_les_jours_sans_cle_videos_sont_completes_et_filtres(self) -> None:
        reponse = json.dumps({"2026-01-01": [
            {"id": "bbb", "raison": "Mt 22, 37 : aimer Dieu.", "groupe": "mot"},
            {"id": "inventee", "raison": "x", "groupe": "mot"},
            {"id": "aaa", "raison": "", "groupe": "livre"}]})
        with patch("rattraper_videos._appel", return_value=reponse) as appel:
            faits = rattraper_videos.rattraper(self.jours, CATALOGUE)
        self.assertEqual(faits, ["2026-01-01"])
        demande = json.loads(appel.call_args[0][1])
        self.assertEqual([j["date"] for j in demande["jours"]], ["2026-01-01"])
        d = json.loads((self.jours / "2026-01-01.json").read_text(encoding="utf-8"))
        self.assertEqual(d["videos"], [{"id": "bbb", "raison": "Mt 22, 37 : aimer Dieu.", "groupe": "mot"}])
        self.assertEqual(json.loads((self.jours / "2026-01-02.json").read_text(encoding="utf-8"))["videos"], [])

    def test_jour_absent_de_la_reponse_reste_a_faire(self) -> None:
        with patch("rattraper_videos._appel", return_value="{}"):
            self.assertEqual(rattraper_videos.rattraper(self.jours, CATALOGUE), [])
        self.assertNotIn("videos", json.loads((self.jours / "2026-01-01.json").read_text(encoding="utf-8")))


if __name__ == "__main__":
    unittest.main()
