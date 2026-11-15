from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
import render


class EclairagesTests(unittest.TestCase):
    def test_amour_du_prochain_avec_source_et_limite(self):
        d = {'lectures': [{'reference': 'Mt 22, 34-40'}]}
        e, = render._eclairages(d)
        self.assertEqual(e['id'], 'lewis-charite')
        self.assertEqual(e['lecture'], 'Mt 22, 34-40')
        self.assertTrue(e['url'].startswith('https://www.cslewisinstitute.org/'))
        self.assertIn('chapitre 9', e['repere'])
        self.assertTrue(e['limite'])

    def test_pas_de_rapprochement_force_ou_de_verset_absent(self):
        for ref in ('Mt 22, 15-21', 'Mt 22, 34-38.40', 'Lc 21, 5-19',
                    'Mt 21, 33-22, 14', 'référence inconnue'):
            with self.subTest(ref=ref):
                self.assertEqual(render._eclairages({'lectures': [{'reference': ref}]}), [])

    def test_un_seul_encart_meme_si_plusieurs_lectures_correspondent(self):
        d = {'lectures': [{'reference': 'Mt 22, 39'}, {'reference': 'Mt 5, 43-48'}]}
        self.assertEqual(len(render._eclairages(d)), 1)

    def test_rendu_conditionnel_et_source_echappee(self):
        d = render.charger_jour('2026-10-25')
        html = render.rendre_html(d)
        self.assertIn('id="eclairages"', html)
        self.assertIn('Reformulation éditoriale', html)
        self.assertIn('Consulter la source', html)
        d['eclairages'][0]['titre'] = '<script>test</script>'
        self.assertIn('&lt;script&gt;test&lt;/script&gt;', render.rendre_html(d))
        d['eclairages'] = []
        self.assertNotIn('id="eclairages"', render.rendre_html(d))
