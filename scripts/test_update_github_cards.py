"""Tests for update_github_cards.py. Run: python3 -m unittest discover -s scripts -p 'test_*.py'"""

import json
import sys
import unittest
import xml.etree.ElementTree as ET
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


SVG = "{http://www.w3.org/2000/svg}"
STATS = {
    "created_at": "2025-10-02T12:11:56Z",
    "public_repos": 28,
    "days": {"2026-01-05": 40, "2026-11-20": 3, "2026-11-21": 0, "2026-11-22": 5, "2026-11-23": 0},
    "langs_by_repo": {"Rust": 23, "C++": 4, "A&B <x>": 3, "Python": 3, "Jupyter Notebook Extended": 2},
    "langs_by_commit": {"Rust": 3286, "Lua": 1112},
}
NAMES = ("github-profile.svg", "github-langs-repo.svg", "github-langs-commit.svg")


def texts(svg):
    return ["".join(t.itertext()) for t in ET.fromstring(svg).iter(SVG + "text")]


class RenderTests(unittest.TestCase):
    def setUp(self):
        self.out = cards.render_all(STATS, TODAY)

    def test_cards_are_well_formed_svg(self):
        self.assertEqual(sorted(self.out), sorted(NAMES))
        for svg in self.out.values():
            self.assertEqual(ET.fromstring(svg).tag, SVG + "svg")

    def test_no_external_references(self):
        for name, svg in self.out.items():
            self.assertEqual(svg.count("http"), 1, name)

    def test_fonts_are_embedded(self):
        self.assertEqual(self.out["github-profile.svg"].count("data:font/woff2;base64,"), 4)
        self.assertEqual(self.out["github-langs-repo.svg"].count("data:font/woff2;base64,"), 3)
        self.assertEqual(self.out["github-langs-commit.svg"].count("data:font/woff2;base64,"), 3)

    def test_profile_shows_numbers(self):
        shown = texts(self.out["github-profile.svg"])
        for value in ("48", "28", "1 day", "Oct 2025", "SYNC 2026-11-23"):
            self.assertIn(value, shown)

    def test_language_names_are_escaped(self):
        shown = texts(self.out["github-langs-repo.svg"])
        self.assertIn("A&B <x>", shown)
        self.assertIn("C++", shown)
        self.assertTrue(any(t.startswith("Jupyter") and t.endswith("…") for t in shown))

    def test_fewer_than_five_languages(self):
        root = ET.fromstring(self.out["github-langs-commit.svg"])
        rows = ["".join(t.itertext()) for t in root.iter(SVG + "text") if t.get("font-size") == "15"]
        self.assertEqual(rows, ["Rust", "Lua"])

    def test_empty_history(self):
        shown = texts(cards.render_all(dict(STATS, days={}), TODAY)["github-profile.svg"])
        self.assertIn("0 days", shown)

    def test_size_under_100kb(self):
        for name, svg in self.out.items():
            self.assertLess(len(svg.encode()), 100_000, name)

    def test_render_is_deterministic(self):
        self.assertEqual(self.out, cards.render_all(STATS, TODAY))

    def test_reduced_motion_rule(self):
        for name in NAMES[1:]:
            self.assertIn("prefers-reduced-motion", self.out[name])

    def test_titles(self):
        for name, start in zip(NAMES, ("MotherSphere on GitHub", "Top languages by repo", "Top languages by commit")):
            title = ET.fromstring(self.out[name]).find(SVG + "title").text
            self.assertTrue(title.startswith(start), title)


if __name__ == "__main__":
    unittest.main()
