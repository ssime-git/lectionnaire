from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
import render
import scene
import valider


class SceneTests(unittest.TestCase):
    def test_meme_date_meme_image_et_dates_differentes_images_differentes(self):
        self.assertEqual(scene.composition('2026-10-30'), scene.composition('2026-10-30'))
        self.assertNotEqual(scene.composition('2026-10-30'), scene.composition('2026-10-31'))
        self.assertEqual(scene.fond_ouverture('x'), scene.fond_ouverture('x'))

    def test_aucune_couleur_en_dur_hors_blanc_de_neige(self):
        import re
        for svg in (scene.composition('a'), scene.fond_ouverture('a')):
            couleurs = set(re.findall(r'#[0-9A-Fa-f]{3,6}\b', svg))
            self.assertLessEqual(couleurs, {'#fff'})
            self.assertIn('var(--c-', svg)
            for m in ('m-soleil', 'm-nuage', 'm-pluie', 'm-neige'):
                self.assertIn(m, svg)


class EclairagesAppariementTests(unittest.TestCase):
    CORPUS = [
        {'id': 'plage', 'auteur': 'A', 'ancrages': [['Lc', 15, 11, 32]]},
        {'id': 'psaume', 'auteur': 'B', 'ancrages': [['Ps', 23, 1, 6]]},
        {'id': 'meme-auteur', 'auteur': 'A', 'ancrages': [['Mt', 5, 1, 12]]},
    ]

    def _avec(self, lectures):
        with patch('render.json.loads', side_effect=[self.CORPUS]):
            return [e['id'] for e in render._eclairages({'lectures': lectures})]

    def test_plage_de_versets_et_nom_de_livre_en_toutes_lettres(self):
        self.assertEqual(self._avec([{'reference': 'Luc 15, 1-3.11-32'}]), ['plage'])
        self.assertEqual(self._avec([{'reference': 'Lc 15, 1-10'}]), [])

    def test_psaume_numerotation_hebraique_entre_parentheses(self):
        self.assertEqual(self._avec([{'reference': 'Ps 22 (23), 1-2ab, 2c-3, 4, 5, 6'}]), ['psaume'])
        self.assertEqual(self._avec([{'reference': 'Lc 14, 25-15, 3'}]), [])  # deux chapitres
        self.assertEqual(self._avec([{'reference': 'Ps 22 (23), 1-6'}]), ['psaume'])

    def test_deux_auteurs_differents_evangile_d_abord(self):
        ids = self._avec([{'reference': 'Mt 5, 1-12'}, {'reference': 'Ps 22 (23), 1-6'},
                          {'reference': 'Lc 15, 11-32'}])
        self.assertEqual(ids, ['plage', 'psaume'])

    def test_corpus_reel_bien_forme(self):
        import json
        corpus = json.loads(render.ECLAIRAGES.read_text(encoding='utf-8'))
        ids = [e['id'] for e in corpus]
        self.assertEqual(len(ids), len(set(ids)))
        for e in corpus:
            with self.subTest(e=e['id']):
                self.assertIn('annee', e)  # peut rester vide si la source ne date pas l'œuvre
                for cle in ('auteur', 'titre', 'oeuvre', 'repere', 'url', 'verifie_le',
                            'ancrages', 'analyse', 'lien', 'limite'):
                    self.assertTrue(e.get(cle), cle)
                self.assertTrue(e['url'].startswith('https://'))
                for a in e['ancrages']:
                    self.assertIn(len(a), (3, 4))
                    self.assertIsInstance(a[1], int)


class PageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.d = render.charger_jour('2026-10-30')
        cls.html = render.rendre_html(cls.d)

    def test_scene_d_ouverture_et_scene_de_la_question(self):
        self.assertIn('class="scene-ouverture"', self.html)
        self.assertIn('<filter id="pastel"', self.html)
        self.assertIn('<div class="cadre">', self.html.split('id="question"')[1])

    def test_pause_et_resonance_contemporaine_des_gloses(self):
        self.assertIn('class="pause reveler"', self.html)
        self.assertIn('Je m\'arrête 30 secondes', self.html)
        self.assertIn('<p class="aujourdhui">', self.html)
        self.assertIn('data-vitre="mot"', self.html)

    def test_sans_pause_aucun_bloc_pause(self):
        d = dict(self.d, pauses=[])
        self.assertNotIn('class="pause reveler"', render.rendre_html(d))

    def test_contenu_visible_sans_javascript(self):
        # Les règles qui cachent ou animent ne s'appliquent que sous .js.
        self.assertIn("document.documentElement.classList.add('js')", self.html)
        self.assertIn('.js .reveler:not(.vu){opacity:0', self.html)
        self.assertNotIn('.reveler{opacity:0', self.html)

    def test_valider_pauses(self):
        base = dict(self.d)
        self.assertFalse([f for f in valider.valider_contrat(base) if 'pauses' in f])
        for mauvais in ([{'suite': 'x'}], [{'question': 'a'}, {'question': 'b'}], 'texte'):
            with self.subTest(mauvais=mauvais):
                fautes = valider.valider_contrat(dict(base, pauses=mauvais))
                self.assertTrue([f for f in fautes if 'pauses' in f])


if __name__ == '__main__':
    unittest.main()
