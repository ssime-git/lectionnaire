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
BASE.pop("videos", None)  # chaque test fournit ses vidéos face à son propre catalogue
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


OEUVRES = {"heidelberg", "calvin-commentaires", "augustin-confessions"}


def _qr(question: str = "Pourquoi deux commandements ?", reponse: str = "<p>Parce que…</p>",
        jour: list | None = None, tradition: list | None = None) -> dict:
    return {"question": question, "reponse_html": reponse,
            "sources": {"jour": ["Mt 22, 34-40"] if jour is None else jour,
                        "tradition": [{"oeuvre": "heidelberg", "reference": "Q. 4"}] if tradition is None else tradition}}


class CarnetTests(unittest.TestCase):
    def _fautes(self, carnet: list[dict]) -> list[str]:
        d = copy.deepcopy(BASE)
        d["carnet"] = carnet
        return valider.valider_contrat(d, catalogue=CATALOGUE, oeuvres=OEUVRES)

    def test_jour_sans_carnet_reste_valide(self) -> None:
        self.assertEqual(valider.valider_contrat(copy.deepcopy(BASE), catalogue=CATALOGUE, oeuvres=OEUVRES), [])

    def test_carnet_valide_accepte(self) -> None:
        self.assertEqual(self._fautes([_qr(), _qr("Qui est le prochain ?", tradition=[])]), [])

    def test_oeuvre_hors_liste_refusee(self) -> None:
        fautes = self._fautes([_qr(tradition=[{"oeuvre": "pseudo-denys", "reference": "I"}])])
        self.assertTrue(any("hors liste blanche" in f for f in fautes))

    def test_reponse_sans_source_refusee(self) -> None:
        self.assertTrue(any("sans source" in f for f in self._fautes([_qr(jour=[], tradition=[])])))

    def test_question_ou_reponse_vide_refusee(self) -> None:
        self.assertTrue(any("vide" in f for f in self._fautes([_qr(question=" ")])))
        self.assertTrue(any("vide" in f for f in self._fautes([_qr(reponse="")])))

    def test_plus_de_cinq_refuse(self) -> None:
        self.assertTrue(any("au plus 5" in f for f in self._fautes([_qr(f"Q{i} ?") for i in range(6)])))

    def test_reference_vide_refusee(self) -> None:
        fautes = self._fautes([_qr(tradition=[{"oeuvre": "heidelberg", "reference": ""}])])
        self.assertTrue(any("référence manquante" in f for f in fautes))

    def test_liste_par_defaut_lue_depuis_data(self) -> None:
        d = copy.deepcopy(BASE)
        d["carnet"] = [_qr(tradition=[{"oeuvre": "augustin-confessions", "reference": "X, 27"}])]
        self.assertEqual(valider.valider_contrat(d, catalogue=CATALOGUE), [])
        self.assertEqual(valider.charger_oeuvres()["heidelberg"], "Catéchisme de Heidelberg (1563)")


class PassagesValidationTests(unittest.TestCase):
    def test_passage_inconnu_refuse(self) -> None:
        d = copy.deepcopy(BASE)
        d["passages_tradition"] = ["chrysostome-Mt-INVENTEE"]
        self.assertTrue(any("passage inconnu" in f for f in valider.valider_contrat(d, catalogue=CATALOGUE)))

    def test_passage_enregistre_accepte(self) -> None:
        d = copy.deepcopy(BASE)
        d["passages_tradition"] = ["chrysostome-Mt-LXXI"]
        self.assertEqual(valider.valider_contrat(d, catalogue=CATALOGUE), [])

if __name__ == "__main__":
    unittest.main()
