"""Render a neofetch-style profile card as SVG (dark and light).

Usage: GITHUB_TOKEN=... python3 scripts/neofetch.py
Writes neofetch/dark.svg and neofetch/light.svg. Lines-of-code totals are
cached per repository in neofetch/loc-cache.json, because the GitHub stats
API often answers 202 (still computing) and we fall back to the last value.
"""

import calendar
import datetime as dt
import html
import json
import os
import time
import urllib.error
import urllib.request
from pathlib import Path

USER = os.environ.get("USERNAME") or "imaimai17468"
TOKEN = os.environ["GITHUB_TOKEN"]
OUT = Path(__file__).resolve().parent.parent / "neofetch"
CACHE = OUT / "loc-cache.json"

FROG = r"""
         _,-.         .-._
       ,'    `.     ,'    `.
      /  ,--.  \___/  ,--.  \
     |  ( () )       ( () )  |
      \  `--'         `--'  /
       `.                 ,'
       / `-._         _.-' \
      /      `-------'      \
     |                       |
     |    .           .      |
      \    `-._____.-'      /
       `._               _,'
      ,-' `--.._____..--' `-.
     (__/ \__)       (__/ \__)
""".strip("\n").splitlines()

THEMES = {
    "dark": dict(bg="#1a1b27", fg="#c0caf5", key="#7aa2f7", value="#9ece6a",
                 dim="#565f89", art="#9ece6a", add="#9ece6a", delete="#f7768e"),
    "light": dict(bg="#f6f8fa", fg="#24292f", key="#0550ae", value="#116329",
                  dim="#8c959f", art="#1a7f37", add="#1a7f37", delete="#cf222e"),
}
PALETTE = ["#f7768e", "#ff9e64", "#e0af68", "#9ece6a", "#73daca",
           "#7dcfff", "#7aa2f7", "#bb9af7"]


def request(url, body=None):
    req = urllib.request.Request(url, data=body, headers={
        "Authorization": f"bearer {TOKEN}",
        "Accept": "application/vnd.github+json",
        "User-Agent": "neofetch-readme",
    })
    with urllib.request.urlopen(req, timeout=60) as res:
        return res.status, json.loads(res.read() or b"null")


def graphql(query, **variables):
    body = json.dumps({"query": query, "variables": variables}).encode()
    _, data = request("https://api.github.com/graphql", body)
    if data.get("errors"):
        raise RuntimeError(data["errors"])
    return data["data"]


def fetch_profile():
    user = graphql("""
      query($login: String!) {
        user(login: $login) {
          createdAt
          followers { totalCount }
          repositoriesContributedTo(privacy: PUBLIC,
            contributionTypes: [COMMIT, PULL_REQUEST, REPOSITORY]) { totalCount }
        }
      }""", login=USER)["user"]

    repos, cursor = [], None
    while True:
        page = graphql("""
          query($login: String!, $cursor: String) {
            user(login: $login) {
              repositories(first: 100, after: $cursor, privacy: PUBLIC,
                           ownerAffiliations: OWNER) {
                pageInfo { hasNextPage endCursor }
                nodes { name isFork stargazerCount }
              }
            }
          }""", login=USER, cursor=cursor)["user"]["repositories"]
        repos += page["nodes"]
        if not page["pageInfo"]["hasNextPage"]:
            break
        cursor = page["pageInfo"]["endCursor"]

    created = dt.datetime.fromisoformat(user["createdAt"].replace("Z", "+00:00"))
    commits = 0
    for year in range(created.year, dt.date.today().year + 1):
        start = max(created, dt.datetime(year, 1, 1, tzinfo=dt.timezone.utc))
        end = dt.datetime(year, 12, 31, 23, 59, 59, tzinfo=dt.timezone.utc)
        commits += graphql("""
          query($login: String!, $from: DateTime!, $to: DateTime!) {
            user(login: $login) {
              contributionsCollection(from: $from, to: $to) {
                totalCommitContributions restrictedContributionsCount
              }
            }
          }""", login=USER, **{"from": start.isoformat(), "to": end.isoformat()}
        )["user"]["contributionsCollection"]["totalCommitContributions"]

    return dict(
        created=created,
        followers=user["followers"]["totalCount"],
        contributed=user["repositoriesContributedTo"]["totalCount"],
        repos=len(repos),
        stars=sum(r["stargazerCount"] for r in repos),
        commits=commits,
        own_repos=[r["name"] for r in repos if not r["isFork"]],
    )


def fetch_loc(repo_names):
    cache = json.loads(CACHE.read_text()) if CACHE.exists() else {}
    pending = set(repo_names)
    for attempt in range(6):
        for name in sorted(pending):
            try:
                status, data = request(
                    f"https://api.github.com/repos/{USER}/{name}/stats/contributors")
            except urllib.error.HTTPError:
                continue
            if status == 202:
                continue
            mine = next((c for c in data or []
                         if c.get("author") and c["author"]["login"] == USER), None)
            weeks = mine["weeks"] if mine else []
            cache[name] = [sum(w["a"] for w in weeks), sum(w["d"] for w in weeks)]
            pending.discard(name)
        if not pending:
            break
        time.sleep(10)
    cache = {k: v for k, v in cache.items() if k in repo_names}
    CACHE.write_text(json.dumps(cache, indent=2, sort_keys=True) + "\n")
    return sum(v[0] for v in cache.values()), sum(v[1] for v in cache.values())


def uptime(since):
    today = dt.date.today()
    start = since.date()
    months = (today.year - start.year) * 12 + today.month - start.month
    if today.day < start.day:
        months -= 1
    anchor_year, anchor_month = divmod(start.month - 1 + months, 12)
    year, month = start.year + anchor_year, anchor_month + 1
    anchor = dt.date(year, month, min(start.day, calendar.monthrange(year, month)[1]))
    days = (today - anchor).days
    return f"{months // 12} years, {months % 12} months, {days} days"


WIDTH = 58  # characters in the info column


def row(key, value, style="value"):
    """Key, dot leader and value padded to WIDTH characters."""
    dots = max(WIDTH - len(key) - len(value) - 4, 1)
    return [("key", key), ("fg", ":"), ("dim", " " + "." * dots + " "), (style, value)]


def build_lines(p, loc):
    add, delete = loc
    header = f"{USER}@github"
    return [
        [("key", header)],
        [("dim", "─" * WIDTH)],
        row("OS", "Accenture Song (YUMEMI)"),
        row("Uptime", uptime(p["created"])),
        row("Host", "imaim.ai"),
        row("Kernel", "Front-end Engineer"),
        row("Shell", "zsh + Claude Code"),
        row("Languages.Programming", "TypeScript, Rust, Python"),
        row("Languages.Web", "React, Next.js, Astro"),
        row("Hobbies", "UI, Design Systems, Keyboards"),
        [],
        [("dim", "─ Contact " + "─" * (WIDTH - 10))],
        row("Portfolio", "https://imaim.ai"),
        row("X", "@imaimai17468"),
        row("Zenn", "zenn.dev/imaimai17468"),
        row("sizu.me", "sizu.me/imaimai17468"),
        [],
        [("dim", "─ GitHub Stats " + "─" * (WIDTH - 15))],
        row("Repos", f"{p['repos']} {{Contributed: {p['contributed']}}}"),
        row("Stars", f"{p['stars']:,}"),
        row("Commits", f"{p['commits']:,}"),
        row("Followers", f"{p['followers']:,}"),
        row("Lines of Code", f"{add - delete:,}")
        + [("fg", " ( "), ("add", f"{add:,}++"), ("fg", ", "),
           ("delete", f"{delete:,}--"), ("fg", " )")],
    ]


def render(lines, theme):
    t = THEMES[theme]
    char_w, line_h, pad = 8.4, 20, 24
    art_w = max(len(l) for l in FROG) * char_w
    info_x = pad + art_w + 32
    height = pad * 2 + (len(lines) + 2) * line_h
    width = info_x + (WIDTH + 30) * char_w + pad
    art_y = pad + (height - pad * 2 - len(FROG) * line_h) / 2

    out = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width:.0f}" height="{height:.0f}" '
        f'viewBox="0 0 {width:.0f} {height:.0f}" font-family="ui-monospace, SFMono-Regular, '
        f'Consolas, \'Liberation Mono\', Menlo, monospace" font-size="14">',
        "<style>"
        + "".join(f".{k}{{fill:{v}}}" for k, v in t.items() if k != "bg")
        + "@keyframes in{from{opacity:0}to{opacity:1}}"
        + "text{white-space:pre;animation:in .4s ease backwards}"
        + "</style>",
        f'<rect width="100%" height="100%" rx="12" fill="{t["bg"]}"/>',
    ]
    for i, art in enumerate(FROG):
        y = art_y + (i + 1) * line_h - 6
        out.append(f'<text x="{pad}" y="{y:.0f}" class="art" '
                   f'style="animation-delay:{i * 0.04:.2f}s">{html.escape(art)}</text>')
    for i, parts in enumerate(lines):
        if not parts:
            continue
        y = pad + (i + 1) * line_h - 4
        spans = "".join(f'<tspan class="{c}">{html.escape(s)}</tspan>' for c, s in parts)
        out.append(f'<text x="{info_x:.0f}" y="{y}" '
                   f'style="animation-delay:{0.3 + i * 0.05:.2f}s">{spans}</text>')
    block_y = pad + (len(lines) + 1) * line_h - 6
    for i, color in enumerate(PALETTE):
        out.append(f'<rect x="{info_x + i * 30:.0f}" y="{block_y}" width="26" height="14" '
                   f'rx="3" fill="{color}"/>')
    out.append("</svg>")
    return "\n".join(out) + "\n"


def main():
    OUT.mkdir(exist_ok=True)
    profile = fetch_profile()
    lines = build_lines(profile, fetch_loc(profile["own_repos"]))
    for theme in THEMES:
        (OUT / f"{theme}.svg").write_text(render(lines, theme))


if __name__ == "__main__":
    main()
