#!/usr/bin/env python3
"""Draw the GitHub stats cards of the profile README as SVG files.

The cards use the colors, fonts and window frame of mothersphere.dev. The fonts are embedded
as base64 subsets because an SVG shown through an <img> tag cannot load anything else.
"""

import json
from datetime import date, timedelta
from pathlib import Path

FONTS = Path(__file__).parent / "fonts"
FACES = ("rajdhani-600", "mono-400", "mono-500", "instrument-500")
METRICS = json.loads((FONTS / "metrics.json").read_text())
MONTHS = ("JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC")


def weekly_columns(days, today, weeks=52):
    """Contributions per week; the last column is the 7 days ending today."""
    return [sum(days.get((today - timedelta(7 * (weeks - 1 - c) + k)).isoformat(), 0) for k in range(7))
            for c in range(weeks)]


def streaks(days, today):
    """(current, longest) runs of days with contributions. A quiet today does not end the current run yet."""
    if not days:
        return 0, 0
    start = min(date.fromisoformat(d) for d in days)
    counts = [days.get((start + timedelta(n)).isoformat(), 0) for n in range((today - start).days + 1)]
    longest = run = 0
    for n in counts:
        run = run + 1 if n else 0
        longest = max(longest, run)
    if counts and counts[-1] == 0:
        counts.pop()
    current = 0
    while counts and counts.pop():
        current += 1
    return current, longest


def cells(n, top, total):
    """How many of `total` cells a value fills; any non-zero value shows at least one."""
    if n <= 0 or top <= 0:
        return 0
    return min(total, max(1, round(n / top * total)))


def top5(counts):
    return sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))[:5]


def count_languages(repos):
    counts = {}
    for repo in repos:
        lang = (repo.get("primaryLanguage") or {}).get("name")
        if lang:
            counts[lang] = counts.get(lang, 0) + 1
    return counts


def month_labels(today, weeks=52, gap=4):
    """(column, month) for each month starting inside a week column, at least `gap` columns apart."""
    labels = []
    for c in range(weeks):
        end = today - timedelta(7 * (weeks - 1 - c))
        for k in range(7):
            day = end - timedelta(k)
            if day.day == 1 and (not labels or c - labels[-1][0] >= gap):
                labels.append((c, MONTHS[day.month - 1]))
    return labels


def text_width(face, size, s, ls=0.0):
    """Width in px from the font's advance widths; a character outside the subset counts as half an em."""
    m = METRICS[face]
    return sum(m["adv"].get(ch, m["upm"] / 2) for ch in s) / m["upm"] * size + ls * len(s)


def fit(face, size, s, max_w, ls=0.0):
    """The string, or its longest prefix plus an ellipsis that fits in max_w."""
    if text_width(face, size, s, ls) <= max_w:
        return s
    while s and text_width(face, size, s + "…", ls) > max_w:
        s = s[:-1]
    return s.rstrip() + "…"
