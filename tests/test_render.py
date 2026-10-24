from __future__ import annotations

import json
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


def _qr(question: str = "Pourquoi deux commandements ?") -> dict:
    return {"question": question, "reponse_html": "<p>Jésus récite le Shema.</p>",
            "sources": {"jour": ["Mt 22, 34-40"],
                        "tradition": [{"oeuvre": "heidelberg", "reference": "Q. 4"}]}}


class TemplateCarnetTests(unittest.TestCase):
    def _jour(self, videos: list[dict], carnet: list[dict]) -> str:
        d = _jour(videos)
        d["carnet"] = carnet
        return render.rendre_html(d)

    def test_carnet_affiche_avertissement_et_sources(self) -> None:
        html = self._jour([_video("1g4u57TSY0g", "Shema / Écouter")], [_qr(), _qr("Qui est mon prochain ?")])
        self.assertIn('data-porte="demander"', html)
        self.assertIn('class="onglets"', html)
        self.assertIn("Généré par intelligence artificielle. Les réponses peuvent se tromper : "
                      "relis-les et vérifie toujours dans les textes cités.", html)
        self.assertEqual(html.count("Réponse générée par IA — à vérifier."), 2)
        self.assertIn("Pères et Réformateurs", html)
        self.assertIn("Catéchisme de Heidelberg (1563), Q. 4", html)
        self.assertIn("<p>Jésus récite le Shema.</p>", html)
        self.assertNotIn("<input", html)

    def test_carnet_sans_videos(self) -> None:
        html = self._jour([], [_qr()])
        self.assertIn('class="compagnon"', html)
        self.assertIn('data-porte="demander"', html)
        self.assertNotIn('data-porte="voir"', html)
        self.assertNotIn('class="onglets"', html)
        self.assertNotIn('id="ecran"', html)

    def test_videos_sans_carnet_pas_d_onglets(self) -> None:
        html = self._jour([_video("1g4u57TSY0g", "Shema / Écouter")], [])
        self.assertNotIn('class="onglets"', html)
        self.assertNotIn('data-porte="demander"', html)
        self.assertIn('id="ecran"', html)

    def test_sans_carnet_pas_de_porte_demander(self) -> None:
        html = self._jour([], [])
        self.assertNotIn('data-porte="demander"', html)
        self.assertNotIn('class="compagnon"', html)

    def test_question_echappee(self) -> None:
        html = self._jour([], [_qr('Pourquoi "semblable" <et> pas égal ?')])
        self.assertIn("Pourquoi &#34;semblable&#34; &lt;et&gt; pas égal ?", html)


class ContexteTests(unittest.TestCase):
    def test_contexte_compact_sans_html(self) -> None:
        d = render.charger_jour("2026-10-25")
        d["carnet"] = [{"question": "Pourquoi deux ?", "reponse_html": "<p>Parce <em>que</em>.</p>",
                        "sources": {"jour": ["Mt 22"], "tradition": []}}]
        c = render.contexte_du_jour(d)
        self.assertEqual(set(c), {"date", "titre", "references", "lectures", "gloses", "contexte", "carnet"})
        self.assertEqual(c["date"], "2026-10-25")
        self.assertEqual(c["lectures"][0]["reference"], "Ex 22, 20-26")
        self.assertTrue(c["lectures"][0]["texte"].startswith("21 Tu ne maltraiteras point l'étranger"))
        self.assertNotIn("<", json.dumps(c, ensure_ascii=False))
        self.assertEqual(c["carnet"], [{"question": "Pourquoi deux ?", "reponse": "Parce que."}])
        self.assertTrue(any(g["lemme"] == "ger" for g in c["gloses"]))

    def test_rendre_ecrit_le_contexte(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, patch("render.DOCS", Path(tmp)), \
                patch("render.RACINE", Path(tmp)), patch("render.reconstruire_index"):
            render.rendre("2026-10-25")
            c = json.loads((Path(tmp) / "contexte" / "2026-10-25.json").read_text(encoding="utf-8"))
        self.assertEqual(c["titre"], "Un seul amour")


if __name__ == "__main__":
    unittest.main()
