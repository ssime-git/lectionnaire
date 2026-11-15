from __future__ import annotations

import sys
import unittest
from html.parser import HTMLParser
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
import render


class PageParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.readings = []
        self.notes = []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == 'article' and a.get('id', '').startswith('lecture-'):
            self.readings.append(a['id'])
        if tag == 'details' and a.get('class') == 'glose':
            self.notes.append(a['id'])


class CompleteReadingTests(unittest.TestCase):
    def test_toutes_les_lectures_et_notes_sont_dans_le_document(self):
        d = render.charger_jour('2026-10-25')
        page = render.rendre_html(d)
        p = PageParser()
        p.feed(page)
        self.assertEqual(p.readings, [f'lecture-{i}' for i in range(len(d['lectures']))])
        self.assertEqual(p.notes, [g['id'] for l in d['lectures'] for g in l['gloses']])
        self.assertIn('#r-textes,#r-racines{display:block;overflow:visible', page)
        self.assertNotIn('.reveler{opacity:0', page)

    def test_meteo_absente_ne_fabrique_pas_de_ville(self):
        d = render.charger_jour('2026-10-25')
        d['meteo'] = {}
        page = render.rendre_html(d)
        self.assertIn('id="meteo-config" type="application/json">{}</script>', page)

    def test_configuration_meteo_echappee_pour_un_script(self):
        d = render.charger_jour('2026-10-25')
        d['meteo'] = {'ville': '</script><script>alert(1)</script>', 'latitude': 0, 'longitude': 0}
        page = render.rendre_html(d)
        self.assertNotIn('</script><script>alert(1)</script>', page)
        self.assertIn('\\u003c/script\\u003e', page)
