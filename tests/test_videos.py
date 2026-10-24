from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import videos  # noqa: E402


class ExtraireTests(unittest.TestCase):
    def test_extraire_lit_les_deux_formats(self) -> None:
        d = {"a": [
            {"lockupViewModel": {"contentId": "1g4u57TSY0g", "metadata": {
                "lockupMetadataViewModel": {"title": {"content": "Shema / Écouter"}}}}},
            {"videoId": "FuQp4baBpPU", "title": {"runs": [{"text": "Lev / "}, {"text": "Cœur"}]}},
            {"videoId": "FLrm_KlwLv8", "title": {"simpleText": "Nephesh / Âme"}},
        ]}
        self.assertEqual(videos.extraire_videos(d), {
            "1g4u57TSY0g": "Shema / Écouter",
            "FuQp4baBpPU": "Lev / Cœur",
            "FLrm_KlwLv8": "Nephesh / Âme",
        })


class CatalogueTests(unittest.TestCase):
    def test_charger_catalogue_absent_renvoie_vide(self) -> None:
        self.assertEqual(videos.charger_catalogue(Path("/nexiste/pas.json")), {})

    def test_charger_catalogue_lit_id_et_titre(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            chemin = Path(tmp) / "videos.json"
            chemin.write_text(json.dumps({"chaine": videos.CHAINE, "videos": [
                {"id": "1g4u57TSY0g", "titre": "Shema / Écouter"}]}), encoding="utf-8")
            self.assertEqual(videos.charger_catalogue(chemin), {"1g4u57TSY0g": "Shema / Écouter"})

    def test_rafraichir_refuse_un_catalogue_trop_court(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            chemin = Path(tmp) / "videos.json"
            chemin.write_text("ancien", encoding="utf-8")
            with patch("videos._recuperer_tout", return_value={"a" * 11: "x"}):
                with self.assertRaisesRegex(RuntimeError, "100"):
                    videos.rafraichir(chemin, minimum=100)
            self.assertEqual(chemin.read_text(encoding="utf-8"), "ancien")

    def test_rafraichir_ecrit_trie_par_titre(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            chemin = Path(tmp) / "videos.json"
            with patch("videos._recuperer_tout", return_value={"b" * 11: "Zacharie", "a" * 11: "Amos"}):
                self.assertEqual(videos.rafraichir(chemin, minimum=2), 2)
            d = json.loads(chemin.read_text(encoding="utf-8"))
            self.assertEqual(d["chaine"], videos.CHAINE)
            self.assertEqual([v["titre"] for v in d["videos"]], ["Amos", "Zacharie"])


class RecupererTests(unittest.TestCase):
    def test_recuperer_refuse_la_page_de_consentement(self) -> None:
        # En Europe, sans cookie, YouTube redirige vers consent.youtube.com.
        page = ('<script>var ytInitialData = {"x": {"videoId": "1g4u57TSY0g", '
                '"title": {"simpleText": "Shema / Écouter"}}};</script>'
                '"INNERTUBE_API_KEY":"k","INNERTUBE_CLIENT_VERSION":"v"')
        reponse = Mock(text=page, status_code=200)
        with patch("videos.requests.get", return_value=reponse) as get:
            self.assertEqual(videos._recuperer_tout(), {"1g4u57TSY0g": "Shema / Écouter"})
        self.assertIn("SOCS=", get.call_args.kwargs["headers"].get("Cookie", ""))


if __name__ == "__main__":
    unittest.main()
