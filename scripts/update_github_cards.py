#!/usr/bin/env python3
"""Draw the GitHub stats cards of the profile README as SVG files.

The cards use the colors, fonts and window frame of mothersphere.dev. The fonts are embedded
as base64 subsets because an SVG shown through an <img> tag cannot load anything else.
"""

from pathlib import Path

FONTS = Path(__file__).parent / "fonts"
FACES = ("rajdhani-600", "mono-400", "mono-500", "instrument-500")
