#!/usr/bin/env python3
"""Generate a Steam showcase SVG using the Steam Web API.

The script resolves a vanity URL (or accepts an existing SteamID64), pulls the
player summary, level, and recently played games, then renders a compact SVG
suited for README embeds. When API access is not available the script can fall
back to cached JSON data provided via ``--cache``.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
import textwrap
import base64
import mimetypes
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

try:  # pragma: no cover - urllib is part of stdlib
    from urllib.request import urlopen
except ImportError:  # pragma: no cover
    urlopen = None  # type: ignore

try:
    import requests
except ImportError:  # pragma: no cover - requests is part of the environment
    requests = None  # type: ignore

from xml.sax.saxutils import escape

API_BASE = "https://api.steampowered.com"

_DEFAULT_AVATAR_SVG = """
<svg xmlns='http://www.w3.org/2000/svg' width='88' height='88' viewBox='0 0 88 88'>
  <defs>
    <linearGradient id='avatarGradient' x1='0' y1='0' x2='1' y2='1'>
      <stop offset='0%' stop-color='#1B2838'/>
      <stop offset='100%' stop-color='#3C9BD6'/>
    </linearGradient>
  </defs>
  <rect width='88' height='88' rx='18' fill='url(#avatarGradient)'/>
  <g fill='none' stroke='rgba(255,255,255,0.4)' stroke-width='2'>
    <circle cx='44' cy='36' r='16'/>
    <path d='M18 76c6-12 15-20 26-20s20 8 26 20' stroke-linecap='round'/>
  </g>
</svg>
""".strip()

DEFAULT_AVATAR_DATA_URI = "data:image/svg+xml;base64," + base64.b64encode(
    _DEFAULT_AVATAR_SVG.encode("utf-8")
).decode("ascii")


@dataclass
class BadgeHighlight:
    name: str
    level: Optional[int] = None


@dataclass
class RecentGame:
    name: str
    playtime_2weeks: int


@dataclass
class SteamProfile:
    steamid: str
    personaname: str
    profileurl: str
    avatarfull: str
    avatar_data_uri: Optional[str] = None
    realname: Optional[str] = None
    loccountrycode: Optional[str] = None
    timecreated: Optional[int] = None
    lastlogoff: Optional[int] = None
    personastate: int = 0
    personastateflags: Optional[int] = None
    level: Optional[int] = None
    badge_highlights: List[BadgeHighlight] = field(default_factory=list)
    recent_games: List[RecentGame] = field(default_factory=list)

    @property
    def persona_state_label(self) -> str:
        states = {
            0: "Offline",
            1: "Online",
            2: "Busy",
            3: "Away",
            4: "Snooze",
            5: "Looking to Trade",
            6: "Looking to Play",
        }
        return states.get(self.personastate, "Unknown")

    @property
    def country_flag(self) -> Optional[str]:
        if not self.loccountrycode:
            return None
        code = self.loccountrycode.upper()
        if len(code) != 2:
            return None
        base = 0x1F1E6
        try:
            return "".join(chr(base + ord(ch) - ord("A")) for ch in code)
        except ValueError:
            return None

    @property
    def member_since(self) -> Optional[str]:
        if not self.timecreated:
            return None
        try:
            date = dt.datetime.fromtimestamp(self.timecreated, tz=dt.timezone.utc)
        except (OverflowError, OSError, ValueError):
            return None
        return date.strftime("%b %Y")

    @property
    def last_seen(self) -> Optional[str]:
        if not self.lastlogoff:
            return None
        try:
            delta = dt.datetime.now(dt.timezone.utc) - dt.datetime.fromtimestamp(
                self.lastlogoff, tz=dt.timezone.utc
            )
        except (OverflowError, OSError, ValueError):
            return None
        if delta.days >= 1:
            return f"{delta.days}d ago"
        hours = delta.seconds // 3600
        if hours:
            return f"{hours}h ago"
        minutes = max(1, delta.seconds // 60)
        return f"{minutes}m ago"


def fetch_json(session: requests.Session, path: str, *, params: Dict[str, Any]) -> Dict[str, Any]:
    response = session.get(f"{API_BASE}{path}", params=params, timeout=15)
    response.raise_for_status()
    return response.json()


def resolve_vanity(session: requests.Session, api_key: str, vanity: str) -> str:
    data = fetch_json(
        session,
        "/ISteamUser/ResolveVanityURL/v1/",
        params={"key": api_key, "vanityurl": vanity},
    )
    response = data.get("response", {})
    if response.get("success") != 1:
        raise RuntimeError(f"Failed to resolve vanity URL '{vanity}': {response}")
    steamid = response.get("steamid")
    if not steamid:
        raise RuntimeError(f"No steamid returned for vanity '{vanity}'")
    return str(steamid)


def _normalize_content_type(header: Optional[str], url: str) -> str:
    if header:
        ctype = header.split(";", 1)[0].strip()
        if ctype:
            return ctype
    guess, _ = mimetypes.guess_type(url)
    return guess or "image/jpeg"


def fetch_avatar_data(session: Optional[requests.Session], url: str) -> Optional[str]:
    if not url:
        return None
    try:
        if session is not None:
            response = session.get(url, timeout=15)
            response.raise_for_status()
            data = response.content
            content_type = response.headers.get("Content-Type")
        elif urlopen is not None:  # pragma: no cover - fallback branch
            with urlopen(url, timeout=15) as fh:  # type: ignore[arg-type]
                data = fh.read()
                content_type = getattr(fh, "headers", {}).get("Content-Type") if hasattr(fh, "headers") else None
        else:  # pragma: no cover - only triggered when urllib missing
            return None
    except Exception:  # pragma: no cover - network dependent
        return None
    if not data:
        return None
    ctype = _normalize_content_type(content_type, url)
    return f"data:{ctype};base64,{base64.b64encode(data).decode('ascii')}"


def fetch_profile(session: requests.Session, api_key: str, *, steamid: str) -> SteamProfile:
    summary = fetch_json(
        session,
        "/ISteamUser/GetPlayerSummaries/v2/",
        params={"key": api_key, "steamids": steamid},
    )
    players = summary.get("response", {}).get("players", [])
    if not players:
        raise RuntimeError(f"No player data returned for steamid {steamid}")
    player = players[0]

    level_data = fetch_json(
        session,
        "/IPlayerService/GetSteamLevel/v1/",
        params={"key": api_key, "steamid": steamid},
    )
    level = level_data.get("response", {}).get("player_level")

    badge_data = fetch_json(
        session,
        "/IPlayerService/GetBadges/v1/",
        params={"key": api_key, "steamid": steamid},
    )
    badges = badge_data.get("response", {}).get("badges", []) or []
    badge_highlights: List[BadgeHighlight] = []
    for badge in badges[:3]:
        name = badge.get("name") or badge.get("description") or "Badge"
        badge_highlights.append(BadgeHighlight(name=name, level=badge.get("level")))

    recent_data = fetch_json(
        session,
        "/IPlayerService/GetRecentlyPlayedGames/v1/",
        params={"key": api_key, "steamid": steamid, "count": 3},
    )
    recent_games_raw = recent_data.get("response", {}).get("games", []) or []
    recent_games = [
        RecentGame(name=game.get("name", "Unknown"), playtime_2weeks=game.get("playtime_2weeks", 0))
        for game in recent_games_raw
    ]

    avatar_data_uri = fetch_avatar_data(session, player.get("avatarfull", ""))

    return SteamProfile(
        steamid=str(player.get("steamid")),
        personaname=player.get("personaname", "Unknown"),
        profileurl=player.get("profileurl", f"https://steamcommunity.com/profiles/{steamid}"),
        avatarfull=player.get("avatarfull", ""),
        avatar_data_uri=avatar_data_uri,
        realname=player.get("realname"),
        loccountrycode=player.get("loccountrycode"),
        timecreated=player.get("timecreated"),
        lastlogoff=player.get("lastlogoff"),
        personastate=int(player.get("personastate", 0) or 0),
        personastateflags=player.get("personastateflags"),
        level=level,
        badge_highlights=badge_highlights,
        recent_games=recent_games,
    )


def load_cached_profile(path: str) -> SteamProfile:
    with open(path, "r", encoding="utf-8") as fh:
        raw = json.load(fh)
    badge_highlights = [
        BadgeHighlight(name=item.get("name", "Badge"), level=item.get("level"))
        for item in raw.get("badge_highlights", [])
    ]
    recent_games = [
        RecentGame(name=item.get("name", "Unknown"), playtime_2weeks=item.get("playtime_2weeks", 0))
        for item in raw.get("recent_games", [])
    ]
    return SteamProfile(
        steamid=str(raw.get("steamid", "")),
        personaname=raw.get("personaname", "Unknown"),
        profileurl=raw.get("profileurl", "https://steamcommunity.com"),
        avatarfull=raw.get("avatarfull", ""),
        avatar_data_uri=raw.get("avatar_data_uri"),
        realname=raw.get("realname"),
        loccountrycode=raw.get("loccountrycode"),
        timecreated=raw.get("timecreated"),
        lastlogoff=raw.get("lastlogoff"),
        personastate=int(raw.get("personastate", 0) or 0),
        personastateflags=raw.get("personastateflags"),
        level=raw.get("level"),
        badge_highlights=badge_highlights,
        recent_games=recent_games,
    )


def human_minutes(minutes: int) -> str:
    hours, mins = divmod(minutes, 60)
    if hours and mins:
        return f"{hours}h {mins}m"
    if hours:
        return f"{hours}h"
    return f"{mins}m"


def render_svg(profile: SteamProfile) -> str:
    recent = profile.recent_games[:3]
    if not recent:
        recent = [RecentGame(name="No recent games", playtime_2weeks=0)]
    badges = profile.badge_highlights[:3]
    if not badges:
        badges = [BadgeHighlight(name="Collector", level=None)]

    def badge_label(badge: BadgeHighlight) -> str:
        label = badge.name
        if badge.level:
            label += f" · Lv{badge.level}"
        return label

    info_lines: List[str] = []
    if profile.realname:
        info_lines.append(profile.realname)
    flag = profile.country_flag
    if flag:
        info_lines.append(flag)
    if profile.member_since:
        info_lines.append(f"Member since {profile.member_since}")
    info_line = "  ·  ".join(info_lines)

    recent_lines = "".join(
        f"<tspan x='20' dy='16'>{escape(game.name)} — {human_minutes(game.playtime_2weeks)}</tspan>"
        for game in recent[1:]
    )

    badge_lines = "".join(
        f"<tspan x='20' dy='16'>{escape(badge_label(badge))}</tspan>" for badge in badges[1:]
    )

    status = profile.persona_state_label
    if profile.last_seen and profile.personastate == 0:
        status += f" ({profile.last_seen})"

    avatar = escape(profile.avatar_data_uri or DEFAULT_AVATAR_DATA_URI)
    level_text = f"Level {profile.level}" if profile.level is not None else "Level hidden"

    return textwrap.dedent(
        f"""
        <svg width="360" height="260" viewBox="0 0 360 260" fill="none" xmlns="http://www.w3.org/2000/svg">
          <defs>
            <linearGradient id="steamCardGradient" x1="0" y1="0" x2="1" y2="1">
              <stop offset="0%" stop-color="#0B141C" />
              <stop offset="45%" stop-color="#13283D" />
              <stop offset="100%" stop-color="#1E405F" />
            </linearGradient>
            <filter id="steamCardShadow" x="-20%" y="-20%" width="140%" height="140%">
              <feDropShadow dx="0" dy="14" stdDeviation="18" flood-color="#040A14" flood-opacity="0.55" />
            </filter>
            <clipPath id="avatarClip">
              <rect x="24" y="26" width="88" height="88" rx="18" />
            </clipPath>
          </defs>
          <g filter="url(#steamCardShadow)">
            <rect x="0" y="0" width="360" height="260" rx="22" fill="url(#steamCardGradient)" stroke="rgba(102,192,244,0.35)" />
          </g>
          <image href="{avatar}" x="24" y="26" width="88" height="88" clip-path="url(#avatarClip)" preserveAspectRatio="xMidYMid slice" />
          <rect x="24" y="26" width="88" height="88" rx="18" fill="rgba(15, 29, 44, 0.4)" stroke="rgba(102,192,244,0.45)" />
          <g transform="translate(128 40)" font-family="'Segoe UI', 'Inter', sans-serif">
            <text x="0" y="0" font-size="24" font-weight="700" fill="#F5FAFF">{escape(profile.personaname)}</text>
            <text x="0" y="18" font-size="12" fill="#90ABC4">{escape(level_text)}</text>
            <text x="0" y="38" font-size="12" fill="#6E8BA8">{escape(status)}</text>
            <text x="0" y="58" font-size="11" fill="#4DA6DA">{escape(info_line)}</text>
          </g>
          <g transform="translate(24 136)" font-family="'Segoe UI', 'Inter', sans-serif">
            <rect width="312" height="52" rx="16" fill="rgba(15, 29, 44, 0.7)" stroke="rgba(102,192,244,0.3)" />
            <text x="20" y="24" font-size="13" font-weight="600" fill="#66C0F4">Recent playtime</text>
            <text x="20" y="36" font-size="12" fill="#B5D8F2">
              <tspan x="20" dy="0">{escape(recent[0].name)} — {human_minutes(recent[0].playtime_2weeks)}</tspan>
              {recent_lines}
            </text>
          </g>
          <g transform="translate(24 196)" font-family="'Segoe UI', 'Inter', sans-serif">
            <rect width="312" height="52" rx="16" fill="rgba(12, 24, 36, 0.65)" stroke="rgba(102,192,244,0.3)" />
            <text x="20" y="24" font-size="13" font-weight="600" fill="#66C0F4">Badge highlights</text>
            <text x="20" y="36" font-size="12" fill="#B5D8F2">
              <tspan x="20" dy="0">{escape(badge_label(badges[0]))}</tspan>
              {badge_lines}
            </text>
          </g>
          <a href="{escape(profile.profileurl)}" target="_blank" rel="noreferrer">
            <rect x="260" y="30" width="76" height="30" rx="10" fill="rgba(18, 42, 60, 0.75)" stroke="rgba(102,192,244,0.4)" />
            <text x="298" y="50" font-family="'Segoe UI', 'Inter', sans-serif" font-size="11" font-weight="600" fill="#F5FAFF" text-anchor="middle">View</text>
          </a>
        </svg>
        """
    ).strip()


def save_profile_cache(profile: SteamProfile, path: str) -> None:
    data = {
        "steamid": profile.steamid,
        "personaname": profile.personaname,
        "profileurl": profile.profileurl,
        "avatarfull": profile.avatarfull,
        "avatar_data_uri": profile.avatar_data_uri,
        "realname": profile.realname,
        "loccountrycode": profile.loccountrycode,
        "timecreated": profile.timecreated,
        "lastlogoff": profile.lastlogoff,
        "personastate": profile.personastate,
        "personastateflags": profile.personastateflags,
        "level": profile.level,
        "badge_highlights": [
            {"name": badge.name, "level": badge.level}
            for badge in profile.badge_highlights
        ],
        "recent_games": [
            {"name": game.name, "playtime_2weeks": game.playtime_2weeks}
            for game in profile.recent_games
        ],
    }
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2)


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Generate a Steam showcase SVG from the Steam Web API.")
    parser.add_argument("--vanity", help="Steam vanity URL handle")
    parser.add_argument("--steamid", help="SteamID64 (skips vanity resolution)")
    parser.add_argument("--api-key", dest="api_key", help="Steam Web API key (falls back to STEAM_API_KEY env var)")
    parser.add_argument("--output", default="img/steam-profile-showcase.svg", help="Path to write the SVG output")
    parser.add_argument("--cache", help="Optional cache JSON to read when API is unavailable")
    parser.add_argument("--write-cache", help="Optional path to write fetched data for offline reuse")

    args = parser.parse_args(argv)

    api_key = args.api_key or os.environ.get("STEAM_API_KEY")

    session = requests.Session() if requests else None
    profile: Optional[SteamProfile] = None

    if api_key and session:
        try:
            steamid = args.steamid or (
                resolve_vanity(session, api_key, args.vanity) if args.vanity else None
            )
            if not steamid:
                raise RuntimeError("A vanity handle or steamid must be provided when using the API")
            profile = fetch_profile(session, api_key, steamid=steamid)
        except Exception as exc:  # pragma: no cover - network dependent
            print(f"Warning: API fetch failed ({exc}).", file=sys.stderr)
            profile = None

    if profile is None:
        if not args.cache:
            parser.error("API fetch failed and no cache provided")
        profile = load_cached_profile(args.cache)

    if args.write_cache:
        save_profile_cache(profile, args.write_cache)

    svg = render_svg(profile)
    with open(args.output, "w", encoding="utf-8") as fh:
        fh.write(svg + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
