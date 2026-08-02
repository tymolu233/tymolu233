#!/usr/bin/env python3
"""Generate self-hosted GitHub statistics cards for the profile README.

The cards intentionally use only GitHub's public API and repository-local SVGs.
That keeps the profile independent from third-party Vercel/Heroku services that
can be rate-limited or blocked when GitHub renders a README.
"""

from __future__ import annotations

import html
import json
import os
import tempfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

API_ROOT = "https://api.github.com"
OWNER = os.environ.get("PROFILE_USER", "tymolu233")
TOKEN = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
ROOT = Path(__file__).resolve().parents[1]
ASSET_DIR = ROOT / "assets"

BG = "#080a0f"
PANEL = "#11151e"
BORDER = "#29333d"
TEXT = "#edf1f6"
MUTED = "#9aa7a1"
DIM = "#697771"
ACCENT = "#a5f26b"
BLUE = "#7fcbff"
LANGUAGE_COLORS = [ACCENT, BLUE, "#ffca80", "#d39cff", "#ff8ca8", "#72e0cb"]


def api_get(path: str, params: dict[str, Any] | None = None) -> Any:
    """Fetch JSON from GitHub's API with a small, dependency-free client."""
    url = path if path.startswith("http") else f"{API_ROOT}{path}"
    if params:
        url = f"{url}?{urlencode(params)}"

    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "tymolu233-profile-stats",
    }
    if TOKEN:
        headers["Authorization"] = f"Bearer {TOKEN}"

    request = Request(url, headers=headers)
    with urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def get_all_owned_public_repositories() -> list[dict[str, Any]]:
    repositories: list[dict[str, Any]] = []
    for page in range(1, 20):
        batch = api_get(
            f"/users/{quote(OWNER)}/repos",
            {"type": "owner", "sort": "updated", "per_page": 100, "page": page},
        )
        if not batch:
            break
        repositories.extend(batch)
        if len(batch) < 100:
            break

    # Forks are deliberately excluded: these cards represent the author's own
    # projects, matching the Selected projects section of the README.
    return [
        repo
        for repo in repositories
        if not repo.get("private") and not repo.get("fork") and not repo.get("archived")
    ]


def language_bytes(repo: dict[str, Any]) -> dict[str, int]:
    try:
        result = api_get(f"/repos/{OWNER}/{quote(repo['name'])}/languages")
        return {str(name): int(value) for name, value in result.items()}
    except Exception as error:  # A single unavailable repository should not break the card.
        print(f"warning: could not read languages for {repo['name']}: {error}")
        return {}


def collect_languages(repositories: list[dict[str, Any]]) -> dict[str, int]:
    totals: dict[str, int] = {}
    with ThreadPoolExecutor(max_workers=8) as executor:
        requests = [executor.submit(language_bytes, repo) for repo in repositories]
        for request in as_completed(requests):
            for language, amount in request.result().items():
                totals[language] = totals.get(language, 0) + amount
    return dict(sorted(totals.items(), key=lambda item: item[1], reverse=True))


def esc(value: Any) -> str:
    return html.escape(str(value), quote=True)


def text(x: int, y: int, value: Any, *, size: int = 12, fill: str = TEXT,
         weight: int = 400, family: str = "DM Sans, Arial, sans-serif",
         anchor: str = "start", letter_spacing: str | None = None) -> str:
    spacing = f' letter-spacing="{letter_spacing}"' if letter_spacing else ""
    return (
        f'<text x="{x}" y="{y}" fill="{fill}" font-family="{family}" '
        f'font-size="{size}px" font-weight="{weight}" text-anchor="{anchor}"{spacing}>'
        f"{esc(value)}</text>"
    )


def write_svg(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    # Atomic replacement prevents GitHub from ever seeing a half-written SVG.
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as handle:
        handle.write(content)
        temporary = Path(handle.name)
    temporary.replace(path)


def compact_number(value: int) -> str:
    if value >= 1_000_000:
        return f"{value / 1_000_000:.1f}m"
    if value >= 1_000:
        return f"{value / 1_000:.1f}k"
    return str(value)


def stats_svg(profile: dict[str, Any], repositories: list[dict[str, Any]]) -> str:
    stars = sum(int(repo.get("stargazers_count", 0)) for repo in repositories)
    forks = sum(int(repo.get("forks_count", 0)) for repo in repositories)
    values = [
        ("PUBLIC REPOS", int(profile.get("public_repos", len(repositories))), ACCENT),
        ("ORIGINAL REPOS", len(repositories), BLUE),
        ("STARS EARNED", stars, "#ffca80"),
        ("FOLLOWERS", int(profile.get("followers", 0)), "#d39cff"),
    ]
    generated = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    chunks = [
        '<svg xmlns="http://www.w3.org/2000/svg" width="495" height="205" viewBox="0 0 495 205" role="img" aria-labelledby="title desc">',
        '<title id="title">GitHub statistics for tymolu233</title>',
        '<desc id="desc">Public repositories, original repositories, stars earned, and followers.</desc>',
        f'<rect width="495" height="205" rx="10" fill="{BG}"/>',
        f'<rect x="0.5" y="0.5" width="494" height="204" rx="9.5" fill="none" stroke="{BORDER}"/>',
        text(24, 34, "GitHub statistics", size=18, weight=600, family="Space Grotesk, Arial, sans-serif"),
        text(24, 57, f"{OWNER} · original work", size=11, fill=MUTED, family="IBM Plex Mono, monospace"),
        f'<line x1="24" y1="73" x2="471" y2="73" stroke="{BORDER}"/>',
    ]

    positions = [(24, 108), (255, 108), (24, 160), (255, 160)]
    for (label, value, color), (x, y) in zip(values, positions):
        chunks.extend([
            f'<rect x="{x}" y="{y - 19}" width="4" height="30" rx="2" fill="{color}"/>',
            text(x + 15, y - 3, compact_number(value), size=21, weight=600, family="Space Grotesk, Arial, sans-serif"),
            text(x + 15, y + 15, label, size=9, fill=MUTED, family="IBM Plex Mono, monospace", letter_spacing="0.7px"),
        ])

    chunks.extend([
        f'<line x1="24" y1="181" x2="471" y2="181" stroke="{BORDER}"/>',
        text(24, 196, f"updated {generated} · public GitHub API", size=9, fill=DIM, family="IBM Plex Mono, monospace"),
        "</svg>",
    ])
    return "\n".join(chunks)


def language_svg(languages: dict[str, int]) -> str:
    width, height = 410, 205
    total = sum(languages.values())
    entries = list(languages.items())

    if total:
        top = entries[:5]
        remaining = sum(value for _, value in entries[5:])
        if remaining:
            top.append(("Other", remaining))
    else:
        top = [("No language data", 1)]
        total = 1

    chunks = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-labelledby="title desc">',
        '<title id="title">Top languages for tymolu233</title>',
        '<desc id="desc">Language usage across original, non-archived public repositories.</desc>',
        f'<rect width="{width}" height="{height}" rx="10" fill="{BG}"/>',
        f'<rect x="0.5" y="0.5" width="{width - 1}" height="{height - 1}" rx="9.5" fill="none" stroke="{BORDER}"/>',
        text(24, 34, "Top languages", size=18, weight=600, family="Space Grotesk, Arial, sans-serif"),
        text(24, 57, "original repositories only", size=11, fill=MUTED, family="IBM Plex Mono, monospace"),
        f'<rect x="24" y="76" width="362" height="10" rx="5" fill="#202a2b"/>',
    ]

    cursor = 24.0
    bar_width = 362.0
    for index, (language, amount) in enumerate(top):
        segment = bar_width * amount / total
        # Keep small languages visible while preserving the overall bar width.
        if index < len(top) - 1 and segment < 3:
            segment = 3
        if index == len(top) - 1:
            segment = 24 + bar_width - cursor
        color = LANGUAGE_COLORS[index % len(LANGUAGE_COLORS)]
        chunks.append(f'<rect x="{cursor:.2f}" y="76" width="{max(segment, 0):.2f}" height="10" fill="{color}"/>')
        cursor += segment

    if languages:
        legend = top[:6]
        for index, (language, amount) in enumerate(legend):
            column, row = divmod(index, 3)
            x = 24 + column * 184
            y = 119 + row * 24
            percentage = amount / total * 100
            color = LANGUAGE_COLORS[index % len(LANGUAGE_COLORS)]
            chunks.extend([
                f'<circle cx="{x + 4}" cy="{y - 4}" r="4" fill="{color}"/>',
                text(x + 15, y, language, size=10, fill=TEXT),
                text(x + 160, y, f"{percentage:.1f}%", size=10, fill=MUTED, family="IBM Plex Mono, monospace", anchor="end"),
            ])
    else:
        chunks.append(text(24, 119, "No language data available yet.", size=10, fill=MUTED))

    chunks.extend([
        f'<line x1="24" y1="181" x2="386" y2="181" stroke="{BORDER}"/>',
        text(24, 196, f"{len(languages)} languages · forks excluded", size=9, fill=DIM, family="IBM Plex Mono, monospace"),
        "</svg>",
    ])
    return "\n".join(chunks)


def main() -> None:
    profile = api_get(f"/users/{quote(OWNER)}")
    repositories = get_all_owned_public_repositories()
    languages = collect_languages(repositories)

    write_svg(ASSET_DIR / "github-stats.svg", stats_svg(profile, repositories))
    write_svg(ASSET_DIR / "top-languages.svg", language_svg(languages))

    print(f"Generated cards for {OWNER}: {len(repositories)} original repositories, {len(languages)} languages")
    print(f"Stars: {sum(int(repo.get('stargazers_count', 0)) for repo in repositories)}")
    print(f"Languages: {', '.join(languages) if languages else 'none'}")


if __name__ == "__main__":
    main()
