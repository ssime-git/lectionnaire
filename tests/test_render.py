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


def _video(vid: str, titre: str, groupe: str = "mot", vignette: str | None = "auto") -> dict:
    return {"id": vid, "titre": titre, "raison": f"Raison de {titre}.", "groupe": groupe,
            "vignette": f"vignettes/{vid}.jpg" if vignette == "auto" else vignette}


def _jour(videos: list[dict]) -> dict:
    d = render.charger_jour("2026-10-25")  # jour réel, sans vidéos : aucun réseau
    d["videos"] = videos
    return d


class TemplateCompagnonTests(unittest.TestCase):
    def test_sans_videos_pas_de_compagnon(self) -> None:
        html = render.rendre_html(_jour([]))
        self.assertNotIn('data-porte="voir"', html)
        self.assertNotIn('class="compagnon"', html)
        self.assertIn('data-porte="lire"', html)
        self.assertIn('data-porte="comprendre"', html)
        self.assertIn("Gloses, contexte et réponses du carnet rédigés avec l'aide d'une "
                      "intelligence artificielle : à relire et vérifier.", html)

    def test_videos_affichees_avec_credit_et_sans_youtube_avant_clic(self) -> None:
        html = render.rendre_html(_jour([
            _video("1g4u57TSY0g", "Shema / Écouter"),
            _video("FuQp4baBpPU", "Lev / Cœur"),
            _video("GIdz46OiA5s", "Exode 19–40 - Panorama", "livre"),
        ]))
        self.assertIn('data-porte="voir"', html)
        self.assertIn('class="compagnon"', html)
        self.assertIn('Vidéo : <a href="https://www.youtube.com/@BibleProject-Fran%C3%A7ais"', html)
        self.assertIn("BibleProject - Français</a>", html)
        self.assertIn('href="https://www.youtube.com/watch?v=1g4u57TSY0g"', html)
        self.assertIn('data-yt="1g4u57TSY0g"', html)
        self.assertIn("Vidéo 1 sur 3", html)
        self.assertIn('class="pellicule"', html)
        self.assertIn("Les mots du jour", html)
        self.assertIn("Situer les livres", html)
        self.assertIn('src="vignettes/1g4u57TSY0g.jpg"', html)
        self.assertNotIn("i.ytimg.com", html)
        self.assertNotIn("<iframe", html)
        self.assertIn("youtube-nocookie.com/embed/", html)

    def test_une_video_sans_pellicule(self) -> None:
        html = render.rendre_html(_jour([_video("GIdz46OiA5s", "Exode 19–40 - Panorama", "livre")]))
        self.assertIn('data-yt="GIdz46OiA5s"', html)
        self.assertNotIn('class="pellicule"', html)
        self.assertNotIn("Vidéo 1 sur 1", html)

    def test_titre_echappe_dans_les_attributs(self) -> None:
        html = render.rendre_html(_jour([_video("cXwM1xW8LEI", "Me'od / Force")]))
        self.assertIn('data-titre="Me&#39;od / Force"', html)

    def test_vignette_absente_affiche_le_titre(self) -> None:
        html = render.rendre_html(_jour([_video("1g4u57TSY0g", "Shema / Écouter", vignette=None)]))
        self.assertNotIn('src="None"', html)
        self.assertIn('class="facade-titre"', html)


if __name__ == "__main__":
    unittest.main()
