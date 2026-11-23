#!/usr/bin/env python3
"""Cut the fonts of the stats cards down to the characters they print.

Run this by hand when the glyph list or a font changes; the workflow uses the files it writes.
It needs fontTools and brotli (pip install fonttools brotli) and the @fontsource packages
installed by mothersphere.dev.
"""

import argparse
import json
from pathlib import Path

from fontTools import subset
from fontTools.ttLib import TTFont

FACES = {
    "rajdhani-600": "rajdhani/files/rajdhani-latin-600-normal.woff2",
    "mono-400": "jetbrains-mono/files/jetbrains-mono-latin-400-normal.woff2",
    "mono-500": "jetbrains-mono/files/jetbrains-mono-latin-500-normal.woff2",
    "instrument-500": "instrument-sans/files/instrument-sans-latin-500-normal.woff2",
}
GLYPHS = "".join(chr(c) for c in range(0x20, 0x7F)) + "·…"


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--src", type=Path,
                        default=Path.home() / "Documents/Repositories/mothersphere.dev/node_modules/@fontsource")
    parser.add_argument("--out", type=Path, default=Path(__file__).parent / "fonts")
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    metrics = {}
    for face, rel in FACES.items():
        font = TTFont(args.src / rel)
        options = subset.Options()
        options.flavor = "woff2"
        options.layout_features = ["kern", "tnum"]
        options.name_IDs = [0, 1, 2, 3, 4, 5, 6, 13, 14]  # 13 and 14 carry the OFL text and URL
        subsetter = subset.Subsetter(options)
        subsetter.populate(text=GLYPHS)
        subsetter.subset(font)
        font.flavor = "woff2"
        font.save(args.out / f"{face}.woff2")
        cmap, hmtx = font.getBestCmap(), font["hmtx"]
        metrics[face] = {"upm": font["head"].unitsPerEm,
                         "adv": {ch: hmtx[cmap[ord(ch)]][0] for ch in GLYPHS if ord(ch) in cmap}}
        print(f"{face}: {(args.out / f'{face}.woff2').stat().st_size} bytes")
    (args.out / "metrics.json").write_text(json.dumps(metrics, ensure_ascii=False, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()
