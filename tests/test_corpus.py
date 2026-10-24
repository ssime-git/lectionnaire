from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import corpus  # noqa: E402


class ParserReferenceTests(unittest.TestCase):
    def test_chapitre_romain_et_jusqua(self) -> None:
        self.assertEqual(corpus.parser_reference("(CHAP. I, VERS. 1, 2 JUSQU’À 7)", None), ((1, 1), (1, 7), False))

    def test_chapitre_herite(self) -> None:
        self.assertEqual(corpus.parser_reference("(8 JUSQU’A 17)", 1), ((1, 8), (1, 17), True))

    def test_verset_seul_herite(self) -> None:
        self.assertEqual(corpus.parser_reference("(VERSET 1)", 1), ((1, 1), (1, 1), True))

    def test_chapitre_arabe_virgule(self) -> None:
        self.assertEqual(corpus.parser_reference("(CHAP. 12,33, JUSQU’AU VERSET 37)", None), ((12, 33), (12, 37), False))
        self.assertEqual(corpus.parser_reference("(CHAP. 1, V. 1, JUSQU’AU VERSET 16)", None), ((1, 1), (1, 16), False))

    def test_a_cheval_sur_deux_chapitres(self) -> None:
        self.assertEqual(
            corpus.parser_reference("(CHAP. XIII, VERSET 53, JUSQU’AU VERSET 13 DU CHAP. XIV)", None),
            ((13, 53), (14, 13), False))

    def test_vers_jusquau_vers(self) -> None:
        self.assertEqual(corpus.parser_reference("(VERS. 20, JUSQU’AU VERS. 30)", 8), ((8, 20), (8, 30), True))

    def test_forme_courte_romaine(self) -> None:
        self.assertEqual(corpus.parser_reference("(V, 19-23)", None), ((5, 19), (5, 23), False))
        self.assertEqual(corpus.parser_reference("(II, 11, 12 JUSQU’À 16)", None), ((2, 11), (2, 16), False))

    def test_jusqua_la_fin_du_chapitre(self) -> None:
        self.assertEqual(corpus.parser_reference("(IX, JUSQU’A LA FIN DU CHAPITRE)", 8), ((9, 1), (9, 999), False))

    def test_illisible_renvoie_none(self) -> None:
        self.assertIsNone(corpus.parser_reference("(voyez plus haut)", 3))
        self.assertIsNone(corpus.parser_reference("(8 JUSQU’A 17)", None))  # chapitre inconnu


TEXTE = (
    "Préface sans homélie. "
    "HOMÉLIE I. [ modifier ] PAUL, SERVITEUR DE JÉSUS-CHRIST. (CHAP. I, VERS. 1, 2 JUSQU’À 7) "
    "Analyse. [ modifier ] 1. Explication très-détaillée. 2. Du salut. "
    "1. Paul commence ainsi sa lettre. Corps de la première homélie. "
    "HOMÉLIE II. [ modifier ] PREMIÈREMENT, JE RENDS GRÂCES. (8 JUSQU’A 17) "
    "Analyse. [ modifier ] 1. Comment l’on doit rendre grâces. "
    "1. Corps de la deuxième homélie. "
    "HOMÉLIE III. [ modifier ] SANS RÉFÉRENCE LISIBLE. "
    "Analyse. 1. Rien. 1. Corps. "
)


class DecouperTests(unittest.TestCase):
    def test_decoupe_et_indexe(self) -> None:
        unites, ignorees = corpus.decouper_homelies(TEXTE, "Rm", "https://fr.wikisource.org/wiki/X")
        self.assertEqual([u["homelie"] for u in unites], ["I", "II"])
        self.assertEqual(ignorees, ["III"])
        u1, u2 = unites
        self.assertEqual((u1["debut"], u1["fin"], u1["chapitre_herite"]), ([1, 1], [1, 7], False))
        self.assertEqual((u2["debut"], u2["fin"], u2["chapitre_herite"]), ([1, 8], [1, 17], True))
        self.assertEqual(u1["id"], "chrysostome-Rm-I")
        self.assertEqual(u1["lemme"], "PAUL, SERVITEUR DE JÉSUS-CHRIST.")
        self.assertEqual(u1["analyse"], "1. Explication très-détaillée. 2. Du salut.")
        self.assertTrue(u1["texte"].startswith("1. Paul commence ainsi sa lettre."))
        self.assertNotIn("HOMÉLIE II", u1["texte"])
        self.assertNotIn("[ modifier ]", u2["texte"] + u2["analyse"])
        self.assertEqual(u1["source_url"], "https://fr.wikisource.org/wiki/X")


class EtendueLectureTests(unittest.TestCase):
    def test_sigles_avec_chiffre_et_lettres_de_verset(self) -> None:
        self.assertEqual(corpus.etendue("1 Th 1, 5c-10"), ("1Th", (1, 5), (1, 10)))
        self.assertEqual(corpus.etendue("Mt 22, 34-40"), ("Mt", (22, 34), (22, 40)))
        self.assertEqual(corpus.etendue("Os 10, 1-3.7-8.12"), ("Os", (10, 1), (10, 12)))
        self.assertEqual(corpus.etendue("Ep 2, 19-22"), ("Ep", (2, 19), (2, 22)))

    def test_illisible(self) -> None:
        self.assertIsNone(corpus.etendue("Ps 17 (18), 2-3, 4.20"))  # psaumes : hors périmètre 3b-1
        self.assertIsNone(corpus.etendue("n'importe quoi"))


class PassagesTests(unittest.TestCase):
    UNITES = {"Mt": [
        {"id": "a", "debut": [22, 15], "fin": [22, 34]},
        {"id": "b", "debut": [22, 34], "fin": [22, 46]},
        {"id": "c", "debut": [23, 1], "fin": [23, 12]},
    ]}

    def test_chevauchement(self) -> None:
        ids = [u["id"] for u in corpus.passages_pour("Mt 22, 34-40", self.UNITES)]
        self.assertEqual(ids, ["b", "a"])  # meilleur recouvrement d'abord

    def test_au_plus_deux(self) -> None:
        self.assertEqual(len(corpus.passages_pour("Mt 22, 1-46", self.UNITES)), 2)

    def test_aucun(self) -> None:
        self.assertEqual(corpus.passages_pour("Mt 5, 1-12", self.UNITES), [])
        self.assertEqual(corpus.passages_pour("Lc 6, 12-19", self.UNITES), [])


class AuBesoinTests(unittest.TestCase):
    """Le corpus grandit chaque nuit : index du livre à la première lecture,
    texte gardé seulement pour les homélies utilisées."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.dossier = Path(self._tmp.name) / "chrysostome"
        self.cache = Path(self._tmp.name) / "cache"

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_indexer_ecrit_un_index_sans_texte(self) -> None:
        with patch("corpus._html_de_la_page", return_value="<p>" + TEXTE + "</p>"):
            bilan = corpus.indexer("Rm", dossier=self.dossier, cache=self.cache)
        self.assertEqual(bilan["ignorees"], ["III"])
        d = json.loads((self.dossier / "Rm.index.json").read_text(encoding="utf-8"))
        self.assertEqual([u["homelie"] for u in d["unites"]], ["I", "II"])
        self.assertTrue(all("texte" not in u for u in d["unites"]))
        self.assertEqual(d["unites"][0]["analyse"], "1. Explication très-détaillée. 2. Du salut.")
        self.assertFalse((self.dossier / "homelies").exists())

    def test_preparer_indexe_au_besoin_et_ne_garde_que_l_utile(self) -> None:
        with patch("corpus._html_de_la_page", return_value="<p>" + TEXTE + "</p>") as lire:
            extraits = corpus.preparer(["Rm 1, 8-10", "Lc 6, 12-19"], dossier=self.dossier, cache=self.cache)
        self.assertEqual([u["id"] for u in extraits], ["chrysostome-Rm-II"])
        self.assertTrue(extraits[0]["texte"].startswith("1. Corps de la deuxième homélie."))
        self.assertEqual(lire.call_count, 1)  # une page Wikisource pour Romains, rien pour Luc
        homelies = sorted(p.name for p in (self.dossier / "homelies").iterdir())
        self.assertEqual(homelies, ["chrysostome-Rm-II.json"])

    def test_preparer_reutilise_le_stocke_sans_reseau(self) -> None:
        with patch("corpus._html_de_la_page", return_value="<p>" + TEXTE + "</p>"):
            corpus.preparer(["Rm 1, 8-10"], dossier=self.dossier, cache=self.cache)
        with patch("corpus._html_de_la_page") as lire:
            extraits = corpus.preparer(["Rm 1, 8-10"], dossier=self.dossier, cache=self.cache)
        lire.assert_not_called()
        self.assertEqual([u["id"] for u in extraits], ["chrysostome-Rm-II"])

    def test_panne_reseau_ne_bloque_pas_la_nuit(self) -> None:
        with patch("corpus._html_de_la_page", side_effect=RuntimeError("Wikisource indisponible")):
            self.assertEqual(corpus.preparer(["Rm 1, 8-10"], dossier=self.dossier, cache=self.cache), [])
        self.assertFalse((self.dossier / "Rm.index.json").exists())

    def test_hors_ligne_rien_n_est_lu(self) -> None:
        with patch("corpus._html_de_la_page") as lire:
            self.assertEqual(corpus.preparer(["Rm 1, 8-10"], dossier=self.dossier, cache=self.cache, reseau=False), [])
        lire.assert_not_called()

    def test_texte_et_index_relus(self) -> None:
        with patch("corpus._html_de_la_page", return_value="<p>" + TEXTE + "</p>"):
            corpus.preparer(["Rm 1, 8-10"], dossier=self.dossier, cache=self.cache)
        self.assertEqual(sorted(corpus.charger_index(self.dossier)), ["Rm"])
        self.assertTrue(corpus.texte_homelie("chrysostome-Rm-II", self.dossier).startswith("1. Corps"))
        self.assertIsNone(corpus.texte_homelie("chrysostome-Rm-I", self.dossier))

class DecouperCasReelsTests(unittest.TestCase):
    def test_parenthese_ouvrante_manquante(self) -> None:
        t = ("HOMÉLIE XVI. [ modifier ] AU COMMENCEMENT. (CHAP. I, VERSET 19) Analyse. 1. A. 1. Corps. "
             "HOMÉLIE XVII. [ modifier ] VOICI L’AGNEAU DE DIEU. VERS. 28, 29, JUSQU’AU VERS. 34) "
             "ANALYSE. [ modifier ] 1. B. 1. Corps.")
        unites, ignorees = corpus.decouper_homelies(t, "Jn", "u")
        self.assertEqual(ignorees, [])
        self.assertEqual(unites[1]["debut"], [1, 28])
        self.assertEqual(unites[1]["fin"], [1, 34])

    def test_commentaire_commence_au_chapitre_un(self) -> None:
        t = "HOMÉLIE II. [ modifier ] AU COMMENCEMENT ÉTAIT LE VERBE. (VERSET 1) ANALYSE. 1. A. 1. Corps."
        unites, _ = corpus.decouper_homelies(t, "Jn", "u")
        self.assertEqual((unites[0]["debut"], unites[0]["chapitre_herite"]), ([1, 1], True))


class FinDeChapitreDecoupeTests(unittest.TestCase):
    def test_reference_sans_chiffre_fin_du_chapitre(self) -> None:
        t = ("HOMÉLIE XVI. [ modifier ] JE DIS LA VÉRITÉ. (IX, JUSQU’A LA FIN DU CHAPITRE) "
             "Analyse. [ modifier ] 1. A. 1. Corps.")
        unites, ignorees = corpus.decouper_homelies(t, "Rm", "u")
        self.assertEqual(ignorees, [])
        self.assertEqual((unites[0]["debut"], unites[0]["fin"]), ([9, 1], [9, 999]))


class SansParentheseTests(unittest.TestCase):
    def test_reference_sans_aucune_parenthese(self) -> None:
        t = ("HOMÉLIE XVI. [ modifier ] X. (CHAP. I, VERSET 19) Analyse. 1. A. 1. Corps. "
             "HOMÉLIE XVII. [ modifier ] VOICI L’AGNEAU DE DIEU. VERS. 28, 29, JUSQU’AU VERS. 35 "
             "ANALYSE. [ modifier ] 1. B. 1. Corps.")
        unites, ignorees = corpus.decouper_homelies(t, "Jn", "u")
        self.assertEqual(ignorees, [])
        self.assertEqual((unites[1]["debut"], unites[1]["fin"]), ([1, 28], [1, 35]))


class FormatsReelsTests(unittest.TestCase):
    """En-têtes relevés tels quels dans l'édition Jeannin sur Wikisource."""
    def test_fin_dans_un_autre_chapitre_forme_courte(self) -> None:
        self.assertEqual(corpus.parser_reference("(CHAP. 2,9-12 JUSQU’À III, 4)", None), ((2, 9), (3, 4), False))
        self.assertEqual(corpus.parser_reference("(I, 28, JUSQU’À II, 16)", None), ((1, 28), (2, 16), False))

    def test_fin_du_chap_sans_chapitre_de_depart(self) -> None:
        self.assertEqual(corpus.parser_reference("(VERS. 49, 50, JUSQU’AU VERS. 4 DU CHAP. II)", 1), ((1, 49), (2, 4), True))
        self.assertEqual(corpus.parser_reference("(VERSET 23, JUSQU’AU VERSET 4 DU CHAPITRE III)", 2), ((2, 23), (3, 4), True))
        self.assertEqual(corpus.parser_reference("(CHAP. 17,21, 22, JUSQU’AU VERSET 7, DU CHAP. XVIII)", None),
                         ((17, 21), (18, 7), False))

    def test_nombres_nus_sont_des_versets(self) -> None:
        self.assertEqual(corpus.parser_reference("(26, 27)", 1), ((1, 26), (1, 27), True))

    def test_point_virgule_change_de_chapitre(self) -> None:
        self.assertEqual(corpus.parser_reference("(IV, 32 ; V, 1, 2, JUSQU’À 4)", None), ((4, 32), (5, 4), False))

    def test_fin_du_chapitre_avec_chapitre_herite(self) -> None:
        self.assertEqual(corpus.parser_reference("(VERS. 54, 55, JUSQU’À LA FIN DU CHAPITRE)", 6), ((6, 54), (6, 999), True))
        self.assertEqual(corpus.parser_reference("(III, 8-11 JUSQU’À LA FIN DU CHAP)", None), ((3, 8), (3, 999), False))


class ControlesTests(unittest.TestCase):
    def test_chapitre_hors_du_livre_et_recul_ecartes(self) -> None:
        t = ("HOMÉLIE LXXI. [ modifier ] A. (CHAP. 22,34, JUSQU’AU VERSET 46) Analyse. 1. A. 1. Corps. "
             "HOMÉLIE LXXII. [ modifier ] B. (CHAP. 33,1, 2, 3, JUSQU’AU VERSET 13) Analyse. 1. B. 1. Corps. "
             "HOMÉLIE LXXIII. [ modifier ] C. (CHAP. 23,14, JUSQU’AU VERSET 29) Analyse. 1. C. 1. Corps. "
             "HOMÉLIE LXXIV. [ modifier ] D. (CHAP. 21, 1-5) Analyse. 1. D. 1. Corps.")
        unites, ignorees = corpus.decouper_homelies(t, "Mt", "u", nb_chapitres=28)
        self.assertEqual([u["homelie"] for u in unites], ["LXXI", "LXXIII"])
        self.assertEqual(ignorees, ["LXXII", "LXXIV"])


class PagesSuccessivesTests(unittest.TestCase):
    def test_etat_transmis_et_doublons_ignores(self) -> None:
        p1 = "HOMÉLIE L. [ modifier ] A. (CHAP. 7, VERS. 25, JUSQU’AU VERS. 36) Analyse. 1. A. 1. Corps."
        p2 = ("HOMÉLIE L. [ modifier ] A. (VERS. 25, 26, 27, JUSQU’AU VERS. 36) Analyse. 1. A. 1. Corps. "
              "HOMÉLIE LI. [ modifier ] B. (VERSET 37, 38, JUSQU’AU VERS. 44) Analyse. 1. B. 1. Corps.")
        u1, _ = corpus.decouper_homelies(p1, "Jn", "u1", nb_chapitres=21)
        u2, ig2 = corpus.decouper_homelies(p2, "Jn", "u2", nb_chapitres=21, precedentes=u1)
        self.assertEqual([(u["homelie"], u["debut"]) for u in u2], [("LI", [7, 37])])
        self.assertEqual(ig2, [])


class ChaineRompueTests(unittest.TestCase):
    def test_pas_d_heritage_apres_une_homelie_ecartee(self) -> None:
        t = ("HOMÉLIE LXXXIV. [ modifier ] A. (CHAP. 19, VERS. 16, JUSQU’AU VERS. 42) Analyse. 1. A. 1. Corps. "
             "HOMÉLIE LXXXV. [ modifier ] B. SANS RÉFÉRENCE. Analyse. 1. B. 1. Corps. "
             "HOMÉLIE LXXXVI. [ modifier ] C. (VERS. 30, JUSQU’AU VERS. 40) Analyse. 1. C. 1. Corps. "
             "HOMÉLIE LXXXVII. [ modifier ] D. (CHAP. 21, VERS. 1, JUSQU’AU VERS. 14) Analyse. 1. D. 1. Corps.")
        unites, ignorees = corpus.decouper_homelies(t, "Jn", "u", nb_chapitres=21)
        self.assertEqual([u["homelie"] for u in unites], ["LXXXIV", "LXXXVII"])
        self.assertEqual(ignorees, ["LXXXV", "LXXXVI"])


    def test_introduction_en_tete_de_livre_ne_rompt_pas(self) -> None:
        t = ("HOMÉLIE I. [ modifier ] TRADUCTION REVUE. ANALYSE. 1. Éloge. 1. Corps. "
             "HOMÉLIE II. [ modifier ] AU COMMENCEMENT. (VERSET 1) ANALYSE. 1. A. 1. Corps.")
        unites, ignorees = corpus.decouper_homelies(t, "Jn", "u", nb_chapitres=21)
        self.assertEqual([(u["homelie"], u["debut"]) for u in unites], [("II", [1, 1])])
        self.assertEqual(ignorees, ["I"])


class SuiteSansDepartTests(unittest.TestCase):
    def test_jusquau_seul_reprend_apres_la_precedente(self) -> None:
        t = ("HOMÉLIE V. [ modifier ] A. (VERSET 3, JUSQU’AU VERSET 6) Analyse. 1. A. 1. Corps. "
             "HOMÉLIE VI. [ modifier ] B. (JUSQU’AU VERSET 9) Analyse. 1. B. 1. Corps. "
             "HOMÉLIE VII. [ modifier ] C. (VERSET 9) Analyse. 1. C. 1. Corps. "
             "HOMÉLIE VIII. [ modifier ] D. (JUSQU’AU VERSET 9) Analyse. 1. D. 1. Corps.")
        unites, ignorees = corpus.decouper_homelies(t, "Jn", "u", nb_chapitres=21)
        self.assertEqual(ignorees, [])
        self.assertEqual([(u["debut"], u["fin"]) for u in unites],
                         [([1, 3], [1, 6]), ([1, 7], [1, 9]), ([1, 9], [1, 9]), ([1, 9], [1, 9])])


class NettoyageTests(unittest.TestCase):
    def test_marqueur_modifier_toutes_variantes(self) -> None:
        t = ("HOMÉLIE V. [\xa0modifier\xa0] A. (II, 11, 12 JUSQU’À 16) Analyse. [modifier] "
             "1 et 2. De la vocation des gentils. 3 et 4. Des rapports de l’âme. 1. Bien des choses montrent.")
        u = corpus.decouper_homelies(t, "Ep", "u")[0][0]
        self.assertNotIn("modifier", u["lemme"] + u["analyse"] + u["texte"])
        self.assertEqual(u["analyse"], "1 et 2. De la vocation des gentils. 3 et 4. Des rapports de l’âme.")
        self.assertTrue(u["texte"].startswith("1. Bien des choses montrent."))


class CorrectionsTests(unittest.TestCase):
    def test_corrections_appliquees_et_motivees(self) -> None:
        unites = [{"homelie": "LXXXVII", "debut": [19, 24], "fin": [21, 15]},
                  {"homelie": "LXXXVIII", "debut": [21, 15], "fin": [21, 25]}]
        corrections = {"LXXXVII": {"debut": [20, 24], "fin": [21, 15], "motif": "Thomas : Jn 20, 24"}}
        corpus.appliquer_corrections(unites, corrections)
        self.assertEqual(unites[0]["debut"], [20, 24])
        self.assertEqual(unites[0]["correction"], "Thomas : Jn 20, 24")
        self.assertNotIn("correction", unites[1])

    def test_fichier_de_corrections_jean(self) -> None:
        c = json.loads(corpus.CORRECTIONS.read_text(encoding="utf-8"))["Jn"]
        self.assertEqual(c["LXXXVII"]["debut"], [20, 24])
        self.assertTrue(all(v.get("motif") for v in c.values()))


if __name__ == "__main__":
    unittest.main()
