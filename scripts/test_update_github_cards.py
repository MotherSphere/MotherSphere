"""Tests for update_github_cards.py. Run: python3 -m unittest discover -s scripts -p 'test_*.py'"""

import json
import sys
import unittest
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


if __name__ == "__main__":
    unittest.main()
