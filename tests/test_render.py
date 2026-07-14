from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import render  # noqa: E402


class DateCompleteTests(unittest.TestCase):
    def test_compose_la_date_francaise_complete(self) -> None:
        self.assertEqual(render._date_complete("2026-07-14"), "mardi 14 juillet 2026")
        self.assertEqual(render._date_complete("2026-12-17"), "jeudi 17 décembre 2026")
        self.assertEqual(render._date_complete("2026-02-21"), "samedi 21 février 2026")

    def test_retombe_sur_la_chaine_brute_si_date_invalide(self) -> None:
        self.assertEqual(render._date_complete("pas-une-date"), "pas-une-date")


if __name__ == "__main__":
    unittest.main()
