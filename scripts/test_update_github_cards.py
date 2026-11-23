"""Tests for update_github_cards.py. Run: python3 -m unittest discover -s scripts -p 'test_*.py'"""

import json
import sys
import unittest
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import update_github_cards as cards  # noqa: E402

GLYPHS = "".join(chr(c) for c in range(0x20, 0x7F)) + "·…"


class FontTests(unittest.TestCase):
    def test_metrics_cover_ascii_and_symbols(self):
        metrics = json.loads((cards.FONTS / "metrics.json").read_text())
        self.assertEqual(set(metrics), set(cards.FACES))
        for face, m in metrics.items():
            missing = [ch for ch in GLYPHS if ch not in m["adv"]]
            self.assertEqual(missing, [], face)

    def test_subsets_are_small_woff2(self):
        for face in cards.FACES:
            data = (cards.FONTS / f"{face}.woff2").read_bytes()
            self.assertEqual(data[:4], b"wOF2", face)
            self.assertLess(len(data), 12000, face)

    def test_licences_name_each_family(self):
        text = (cards.FONTS / "LICENSES.txt").read_text()
        for name in ("Rajdhani", "JetBrains Mono", "Instrument Sans", "SIL OPEN FONT LICENSE Version 1.1"):
            self.assertIn(name, text)


TODAY = date(2026, 11, 23)


class StreakTests(unittest.TestCase):
    def test_today_without_contributions_keeps_the_streak(self):
        days = {"2026-11-20": 1, "2026-11-21": 2, "2026-11-22": 3, "2026-11-23": 0}
        self.assertEqual(cards.streaks(days, TODAY), (3, 3))

    def test_today_counts_when_it_has_contributions(self):
        self.assertEqual(cards.streaks({"2026-11-22": 1, "2026-11-23": 5}, TODAY), (2, 2))

    def test_a_gap_resets_the_current_streak_only(self):
        days = {"2026-11-01": 1, "2026-11-02": 1, "2026-11-03": 1, "2026-11-04": 0, "2026-11-22": 1, "2026-11-23": 1}
        self.assertEqual(cards.streaks(days, TODAY), (2, 3))

    def test_no_contributions(self):
        self.assertEqual(cards.streaks({}, TODAY), (0, 0))


class WeekTests(unittest.TestCase):
    def test_last_column_ends_today(self):
        cols = cards.weekly_columns({"2026-11-23": 4, "2026-11-17": 2, "2026-11-16": 7}, TODAY)
        self.assertEqual(len(cols), 52)
        self.assertEqual(cols[-1], 6)
        self.assertEqual(cols[-2], 7)


class CellsTests(unittest.TestCase):
    def test_cells(self):
        self.assertEqual(cards.cells(0, 10, 25), 0)
        self.assertEqual(cards.cells(1, 1000, 25), 1)
        self.assertEqual(cards.cells(1000, 1000, 25), 25)
        self.assertEqual(cards.cells(5, 0, 25), 0)
        self.assertEqual(cards.cells(4, 23, 25), 4)
        self.assertEqual(cards.cells(30, 23, 25), 25)


class Top5Tests(unittest.TestCase):
    def test_ties_break_by_name(self):
        counts = {"Shell": 2, "TypeScript": 2, "Rust": 23, "Vue": 1, "QML": 1, "Python": 3, "JavaScript": 4}
        self.assertEqual(cards.top5(counts),
                         [("Rust", 23), ("JavaScript", 4), ("Python", 3), ("Shell", 2), ("TypeScript", 2)])


class CountLanguagesTests(unittest.TestCase):
    def test_repos_without_a_language_are_skipped(self):
        repos = [{"primaryLanguage": {"name": "Rust"}}, {"primaryLanguage": None},
                 {"primaryLanguage": {"name": "Rust"}}, {"primaryLanguage": {"name": "Lua"}}]
        self.assertEqual(cards.count_languages(repos), {"Rust": 2, "Lua": 1})


class MonthLabelTests(unittest.TestCase):
    def test_labels_sit_on_the_first_of_each_month(self):
        labels = cards.month_labels(TODAY)
        self.assertEqual(labels[0], (0, "DEC"))
        self.assertEqual(labels[1], (5, "JAN"))
        for (a, _), (b, _) in zip(labels, labels[1:]):
            self.assertGreaterEqual(b - a, 4)
        for col, month in labels:
            end = TODAY - timedelta(7 * (51 - col))
            week = [end - timedelta(k) for k in range(7)]
            self.assertTrue(any(d.day == 1 and d.strftime("%b").upper() == month for d in week), (col, month))


class FitTests(unittest.TestCase):
    def test_short_names_are_kept(self):
        self.assertEqual(cards.fit("rajdhani-600", 15, "JavaScript", 108), "JavaScript")

    def test_long_names_get_an_ellipsis(self):
        out = cards.fit("rajdhani-600", 15, "Jupyter Notebook Extended", 108)
        self.assertTrue(out.endswith("…"))
        self.assertLessEqual(cards.text_width("rajdhani-600", 15, out), 108)


if __name__ == "__main__":
    unittest.main()
