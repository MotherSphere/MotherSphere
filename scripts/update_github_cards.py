#!/usr/bin/env python3
"""Draw the GitHub stats cards of the profile README as SVG files.

The cards use the colors, fonts and window frame of mothersphere.dev. The fonts are embedded
as base64 subsets because an SVG shown through an <img> tag cannot load anything else.
"""

import argparse
import base64
import json
import os
import sys
import urllib.request
from datetime import date, datetime, timedelta
from pathlib import Path
from xml.sax.saxutils import escape
from zoneinfo import ZoneInfo

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


# Drawing. Colors and shapes come from mothersphere.dev (src/styles/kit.css, desktop.css).
TEXT, WHITE, GREY, BETA, TEAL, RAIL, DASH, BG = (
    "#ececec", "#ffffff", "#b5b5b5", "#cce9f4", "#add1c4", "#dedbde", "#444444", "#0a0e12")
EASE = "cubic-bezier(.333,0,.667,1)"
FAMILY = {"rajdhani-600": ("ms-raj", "Rajdhani,sans-serif"), "mono-400": ("ms-mono", "'JetBrains Mono',monospace"),
          "mono-500": ("ms-mono5", "'JetBrains Mono',monospace"),
          "instrument-500": ("ms-ins", "'Instrument Sans',sans-serif")}
CLASS = {"rajdhani-600": "r", "mono-400": "m", "mono-500": "m5", "instrument-500": "i"}
TZ = ZoneInfo("Europe/Brussels")


def text(x, y, s, face, size, fill, ls=0.0, anchor="start"):
    a = f' text-anchor="{anchor}"' if anchor != "start" else ""
    spacing = f' letter-spacing="{ls:g}"' if ls else ""
    return (f'<text x="{x:g}" y="{y:g}" class="{CLASS[face]}" font-size="{size:g}" fill="{fill}"{spacing}{a}>'
            f"{escape(s)}</text>")


def style(faces):
    out = []
    for face in faces:
        family, fallback = FAMILY[face]
        b64 = base64.b64encode((FONTS / f"{face}.woff2").read_bytes()).decode()
        out.append(f"@font-face{{font-family:'{family}';src:url(data:font/woff2;base64,{b64}) format('woff2')}}")
        out.append(f".{CLASS[face]}{{font-family:'{family}',{fallback}}}")
    out.append(f"@keyframes p{{from{{opacity:.3}}to{{opacity:1}}}}.pulse{{animation:p 500ms {EASE} infinite alternate}}")
    out.append("@media (prefers-reduced-motion:reduce){.pulse{animation:none}}")
    return "<style>" + "".join(out) + "</style>"


def marker(x, y):
    """The '::' marker of both sites: four small squares."""
    return "".join(f'<rect x="{x + dx:g}" y="{y + dy:g}" width="2" height="2" fill="{BETA}"/>'
                   for dx in (0, 4.4) for dy in (0, 5.3))


def emblem(x, y, h=19):
    """The rhombus with four square holes (Emblem.astro)."""
    holes = "".join(f"M{hx} {hy}h5.4v5.4h-5.4z" for hx, hy in ((11.3, 22.1), (23.3, 22.1), (11.3, 36.5), (23.3, 36.5)))
    return (f'<path transform="translate({x:g} {y:g}) scale({h / 64:.4f})" fill="{TEXT}" fill-rule="evenodd" '
            f'd="M20 2 38 32 20 62 2 32Z{holes}"/>')


def controls(x_right, y):
    """Minimize, maximize and close, drawn with 3x3 squares (WinControls.astro)."""
    glyphs = ([(0, 10), (5, 10), (10, 10)], [(0, 0), (10, 0), (0, 10), (10, 10)],
              [(0, 0), (10, 0), (5, 5), (0, 10), (10, 10)])
    out, x = [], x_right - 3 * 13 - 2 * 9
    for glyph in glyphs:
        out += [f'<rect x="{x + dx}" y="{y + dy}" width="3" height="3" fill="{GREY}"/>' for dx, dy in glyph]
        x += 13 + 9
    return "".join(out)


def tag(x_right, y_mid, s, color):
    """An outlined mono tag, right-aligned on x_right."""
    size, ls = 9.5, 0.57
    w, h = text_width("mono-500", size, s, ls) + 10, 16
    x = x_right - w
    return (f'<rect x="{x + .5:g}" y="{y_mid - h / 2 + .5:g}" width="{w - 1:g}" height="{h - 1}" fill="none" '
            f'stroke="{color}"/>' + text(x + 5 + ls / 2, y_mid + 3.4, s, "mono-500", size, color, ls))


def title(s, sub=None):
    out = text(38, 38, s, "rajdhani-600", 20, TEXT, 0.8)
    if sub:
        out += text(38 + text_width("rajdhani-600", 20, s, 0.8) + 8, 38, "// " + sub, "rajdhani-600", 20, GREY, 0.8)
    return out


def rule(x, y, w, h=1):
    return f'<rect x="{x:g}" y="{y:g}" width="{w:g}" height="{h:g}" fill="{RAIL}" fill-opacity=".25"/>'


def frame(w, h, head, body, faces, label):
    """Window frame: edge, corner ticks, dotted rails, emblem, title row and separator."""
    rail_w = (w - 20) // 5 * 5 - 2
    ticks = (f"M.5 10.5V.5H10.5M{w - 10.5} .5H{w - .5}V10.5"
             f"M.5 {h - 10.5}V{h - .5}H10.5M{w - 10.5} {h - .5}H{w - .5}V{h - 10.5}")
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}" role="img" '
            f'aria-labelledby="t"><title id="t">{escape(label)}</title>{style(faces)}'
            f'<defs><pattern id="rail" x="10" y="0" width="5" height="3" patternUnits="userSpaceOnUse">'
            f'<rect width="3" height="3" fill="{RAIL}" fill-opacity=".25"/></pattern></defs>'
            f'<rect width="{w}" height="{h}" fill="{BG}"/>'
            f'<rect x=".5" y=".5" width="{w - 1}" height="{h - 1}" fill="none" stroke="{RAIL}" stroke-opacity=".14"/>'
            f'<path d="{ticks}" fill="none" stroke="{BETA}" shape-rendering="crispEdges"/>'
            f'<rect x="10" y="6" width="{rail_w}" height="3" fill="url(#rail)"/>'
            f'<rect x="10" y="{h - 9}" width="{rail_w}" height="3" fill="url(#rail)"/>'
            f'{emblem(18, 21)}{head}{rule(12, 52, w - 24)}{body}</svg>')


def plural(n, word):
    return f"{n:,} {word}{'' if n == 1 else 's'}"


def joined(stats):
    when = datetime.fromisoformat(stats["created_at"].replace("Z", "+00:00")).astimezone(TZ)
    return f"{MONTHS[when.month - 1].title()} {when.year}"


def profile_card(stats, today):
    w, h, weeks, rows, pitch, size, gx, gy = 850, 230, 52, 9, 10, 6, 30, 100
    days = stats["days"]
    cols = weekly_columns(days, today, weeks)
    top = max(cols)
    body = [marker(24, 74.5), text(36, 82, "CONTRIBUTIONS · LAST 52 WEEKS", "mono-400", 10.5, GREY, 0.42),
            text(gx + weeks * pitch - 4, 82, f"{sum(cols):,}", "mono-500", 11.5, TEXT, anchor="end"),
            f'<defs><pattern id="cell" x="{gx}" y="{gy}" width="{pitch}" height="{pitch}" patternUnits="userSpaceOnUse">'
            f'<rect width="{size}" height="{size}" fill="{RAIL}" fill-opacity=".18"/></pattern></defs>',
            f'<rect x="{gx}" y="{gy}" width="{weeks * pitch - pitch + size}" height="{rows * pitch - pitch + size}" '
            f'fill="url(#cell)"/>']
    for c, n in enumerate(cols):
        for r in range(cells(n, top, rows)):
            body.append(f'<rect x="{gx + c * pitch}" y="{gy + (rows - 1 - r) * pitch}" width="{size}" '
                        f'height="{size}" fill="{BETA}"/>')
    for c, month in month_labels(today, weeks):
        body.append(text(gx + c * pitch, gy + rows * pitch + 12, month, "mono-400", 9.5, GREY, 0.38))
    current, longest = streaks(days, today)
    total = sum(days.values())
    facts = [("TOTAL CONTRIBUTIONS", f"{total:,}"), ("PUBLIC REPOS", f"{stats['public_repos']:,}"),
             ("CURRENT STREAK", plural(current, "day")), ("LONGEST STREAK", plural(longest, "day")),
             ("JOINED", joined(stats))]
    body.append(f'<rect x="590" y="66" width="1" height="146" fill="{RAIL}" fill-opacity=".25"/>')
    for i, (key, value) in enumerate(facts):
        y = 64 + i * 30
        body.append(text(608, y + 19, key, "mono-400", 10, GREY, 0.4))
        body.append(text(826, y + 19.5, value, "instrument-500", 14, TEXT, anchor="end"))
        if i < len(facts) - 1:
            body.append(rule(608, y + 29, 218))
    head = title("MOTHERSPHERE", "GITHUB") + tag(w - 24 - 57 - 16, 32, f"SYNC {today.isoformat()}", TEAL)
    head += controls(w - 24, 26)
    label = (f"MotherSphere on GitHub: {total:,} contributions, {stats['public_repos']} public repos, "
             f"current streak {plural(current, 'day')}, longest {plural(longest, 'day')}, joined {joined(stats)}.")
    return frame(w, h, head, "".join(body), FACES, label)


def lang_card(active, items, caption, unit):
    w, h, pitch, size, gx = 420, 240, 8, 5, 140
    body = [f'<defs><pattern id="dash" x="12" y="0" width="4" height="1" patternUnits="userSpaceOnUse">'
            f'<rect width="2.4" height="1" fill="{DASH}"/></pattern></defs>',
            f'<rect x="12" y="83" width="{w - 24}" height="1" fill="url(#dash)"/>']
    x = 24
    for label, key in (("BY REPO", "repo"), ("BY COMMIT", "commit")):
        tab_w = text_width("rajdhani-600", 14, label, 0.56)
        body.append(text(x, 76, label, "rajdhani-600", 14, WHITE if key == active else GREY, 0.56))
        if key == active:
            body.append(f'<rect x="{x - 4:g}" y="82" width="{tab_w + 8:g}" height="3" fill="{BETA}"/>')
        x += tab_w + 28
    body += [marker(24, 97.5), text(36, 105, caption, "mono-400", 10, GREY, 0.4),
             text(w - 24, 105, unit, "mono-400", 10, GREY, 0.4, anchor="end")]
    top = items[0][1] if items else 0
    for i, (name, n) in enumerate(items):
        y = 116 + i * 22
        if i == 0:
            body.append(f'<g class="pulse"><rect x="12" y="{y}" width="{w - 24}" height="22" fill="{BETA}" '
                        f'fill-opacity=".12"/><rect x="12" y="{y}" width="3" height="22" fill="{BETA}"/></g>')
        body.append(text(24, y + 16, fit("rajdhani-600", 15, name, 108), "rajdhani-600", 15, WHITE if i == 0 else TEXT))
        filled = cells(n, top, 25)
        for c in range(25):
            on = c < filled
            body.append(f'<rect x="{gx + c * pitch}" y="{y + 8.5}" width="{size}" height="{size}" '
                        f'fill="{BETA if on else RAIL}"' + ("/>" if on else ' fill-opacity=".18"/>'))
        body.append(text(w - 24, y + 15.5, f"{n:,}", "mono-500", 11, TEXT if i == 0 else GREY, anchor="end"))
    label = f"Top languages by {active}: " + ", ".join(f"{k} {v:,}" for k, v in items) + "."
    return frame(w, h, title("LANGUAGES") + controls(w - 24, 26), "".join(body), FACES[:3], label)


# Data. Public data only, so the workflow's GITHUB_TOKEN is enough.
USER, ORG = "MotherSphere", "Project-Colony"
API = "https://api.github.com/graphql"
BASE_QUERY = "query($login:String!){user(login:$login){createdAt contributionsCollection{contributionYears}}}"
REPOS = ("repositories(first:100,after:$cursor,privacy:PUBLIC,isFork:false{owned}){{totalCount "
         "pageInfo{{hasNextPage endCursor}} nodes{{primaryLanguage{{name}}}}}}")
USER_REPOS = ("query($login:String!,$cursor:String){user(login:$login){"
              + REPOS.format(owned=",ownerAffiliations:OWNER") + "}}")
ORG_REPOS = "query($login:String!,$cursor:String){organization(login:$login){" + REPOS.format(owned="") + "}}"
# shortcut: the API returns at most 100 repositories per year here; page by month if a year ever has more.
YEAR_QUERY = """query($login:String!,$start:DateTime!,$end:DateTime!){user(login:$login){
contributionsCollection(from:$start,to:$end){contributionCalendar{weeks{contributionDays{date contributionCount}}}
commitContributionsByRepository(maxRepositories:100){repository{primaryLanguage{name}} contributions{totalCount}}}}}"""


def gql(query, token, **variables):
    req = urllib.request.Request(API, data=json.dumps({"query": query, "variables": variables}).encode(), headers={
        "Authorization": f"bearer {token}", "Content-Type": "application/json", "User-Agent": "MotherSphere-cards"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        body = json.load(resp)
    if body.get("errors") or "data" not in body:
        raise RuntimeError(f"GraphQL error: {body.get('errors')}")
    return body["data"]


def owner_repos(call, login, org):
    """(total count, every node) of an owner's public non-fork repos, following the pages."""
    key, query = ("organization", ORG_REPOS) if org else ("user", USER_REPOS)
    nodes, cursor = [], None
    while True:
        page = call(query, login=login, cursor=cursor)[key]["repositories"]
        nodes += page["nodes"]
        if not page["pageInfo"]["hasNextPage"]:
            return page["totalCount"], nodes
        cursor = page["pageInfo"]["endCursor"]


def fetch_stats(call):
    base = call(BASE_QUERY, login=USER)["user"]
    public_repos, user_repos = owner_repos(call, USER, org=False)
    _, org_repos = owner_repos(call, ORG, org=True)
    days, commits = {}, {}
    for year in sorted(base["contributionsCollection"]["contributionYears"]):
        coll = call(YEAR_QUERY, login=USER, start=f"{year}-01-01T00:00:00Z",
                    end=f"{year}-12-31T23:59:59Z")["user"]["contributionsCollection"]
        for week in coll["contributionCalendar"]["weeks"]:
            for day in week["contributionDays"]:
                days[day["date"]] = day["contributionCount"]
        for repo in coll["commitContributionsByRepository"]:
            name = (repo["repository"]["primaryLanguage"] or {}).get("name")
            if name:
                commits[name] = commits.get(name, 0) + repo["contributions"]["totalCount"]
    return {"created_at": base["createdAt"], "public_repos": public_repos, "days": dict(sorted(days.items())),
            "langs_by_repo": count_languages(user_repos + org_repos), "langs_by_commit": commits}


def render_all(stats, today):
    since = joined(stats).upper()
    return {
        "github-profile.svg": profile_card(stats, today),
        "github-langs-repo.svg": lang_card("repo", top5(stats["langs_by_repo"]),
                                           "PUBLIC REPOS · MOTHERSPHERE + COLONY", "REPOS"),
        "github-langs-commit.svg": lang_card("commit", top5(stats["langs_by_commit"]),
                                             f"COMMITS · SINCE {since}", "COMMITS"),
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description="Draw the GitHub stats cards of the profile README.")
    parser.add_argument("--out", type=Path, required=True, help="folder for the three SVG files")
    parser.add_argument("--data", type=Path, help="render from a saved stats file instead of the API")
    parser.add_argument("--save-data", type=Path, help="also write the fetched stats to this file")
    args = parser.parse_args(argv)
    if args.data:
        stats = json.loads(args.data.read_text())
    else:
        token = os.environ.get("GITHUB_TOKEN")
        if not token:
            print("GITHUB_TOKEN is not set", file=sys.stderr)
            return 2
        try:
            stats = fetch_stats(lambda query, **variables: gql(query, token, **variables))
        except Exception as e:  # any failure keeps the cards that are already published
            print(f"fetch failed, nothing written: {e}", file=sys.stderr)
            return 1
        if not any(stats["days"].values()) or not stats["langs_by_repo"] or not stats["langs_by_commit"]:
            print("the API answered with empty data, nothing written", file=sys.stderr)
            return 1
    svgs = render_all(stats, datetime.now(TZ).date())
    if args.save_data:
        args.save_data.write_text(json.dumps(stats, indent=1, sort_keys=True) + "\n")
    args.out.mkdir(parents=True, exist_ok=True)
    for name, svg in svgs.items():
        (args.out / name).write_text(svg, encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
