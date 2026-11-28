#!/usr/bin/env python3
"""Generate the profile statistic cards (SVG) from live GitHub data.

  python3 generate_stats.py --user NAME --out assets     # live data (GH_TOKEN optional but recommended)
  python3 generate_stats.py --out assets --placeholder    # empty "waiting for first update" state
  python3 generate_stats.py --out assets --sample         # fake numbers, for design preview only

Writes: lang-radar.svg, lang-top.svg, stats-row.svg (+ stats-data.json for live data).
Languages listed in EXCLUDE_LANGS (comma separated, default "Jupyter Notebook") are left out,
because notebook output files would otherwise dominate the byte counts.
"""
import argparse
import datetime as dt
import json
import math
import os
import sys
import urllib.request
from xml.sax.saxutils import escape

API = "https://api.github.com"
BG, PANEL, CYAN, TEXT, MUTED, GRID = "#0B1020", "#0F1A30", "#00D9FF", "#E6F1FF", "#8B949E", "#1B2D50"
SANS = "-apple-system,'Segoe UI',Roboto,'Helvetica Neue',Arial,sans-serif"
MONO = "'Fira Code','JetBrains Mono','SF Mono',Consolas,'DejaVu Sans Mono','Courier New',monospace"
STYLE = f"<style>.m{{font-family:{MONO}}}.s{{font-family:{SANS}}}</style>"
COLORS = {
    "JavaScript": "#F1E05A", "TypeScript": "#3178C6", "PHP": "#8892BF", "Python": "#3572A5", "C++": "#F34B7D",
    "C": "#7C8A99", "HTML": "#E34C26", "CSS": "#9B6FD6", "Shell": "#89E051", "Java": "#B07219", "Go": "#00ADD8",
    "Rust": "#DEA584", "Dart": "#00B4AB", "Kotlin": "#A97BFF", "Blade": "#F7523F", "SCSS": "#C6538C",
    "Jupyter Notebook": "#DA5B0B", "Dockerfile": "#384D54", "Vue": "#41B883",
}
FALLBACK = ["#00D9FF", "#8B7CFF", "#3DDC97", "#FFB454", "#FF7A8A"]
EXCLUDE = {s.strip() for s in os.environ.get("EXCLUDE_LANGS", "Jupyter Notebook").split(",") if s.strip()}


# ----------------------------------------------------------------- data
def req(url, token=None, body=None):
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "profile-stats-generator"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    data = None
    if body is not None:
        data = json.dumps(body).encode()
        headers["Content-Type"] = "application/json"
    with urllib.request.urlopen(urllib.request.Request(url, data=data, headers=headers), timeout=30) as r:
        return json.load(r)


def build(langs, repos, commits, prs, stars):
    langs = sorted(((n, b) for n, b in langs.items() if n not in EXCLUDE and b > 0), key=lambda x: -x[1])
    total = sum(b for _, b in langs) or 1
    top = []
    for i, (n, b) in enumerate(langs[:5]):
        top.append((n, 100.0 * b / total, COLORS.get(n, FALLBACK[i % len(FALLBACK)])))
    return {"top": top, "repos": repos, "commits": commits, "prs": prs, "stars": stars,
            "updated": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d")}


def fetch(user, token):
    repos, page = [], 1
    while True:
        chunk = req(f"{API}/users/{user}/repos?per_page=100&type=owner&page={page}", token)
        repos += chunk
        if len(chunk) < 100:
            break
        page += 1
    own = [r for r in repos if not r.get("fork")]
    by = {}
    for r in own:
        try:
            for k, v in req(f"{API}/repos/{user}/{r['name']}/languages", token).items():
                by[k] = by.get(k, 0) + v
        except Exception as e:  # one broken repo should not stop the run
            print(f"languages failed for {r['name']}: {e}", file=sys.stderr)
    stars = sum(r.get("stargazers_count", 0) for r in own)
    since = (dt.date.today() - dt.timedelta(days=365)).isoformat()
    commits = prs = None
    if token:
        try:
            q = ("query($u:String!,$f:DateTime!){user(login:$u){contributionsCollection(from:$f)"
                 "{totalCommitContributions totalPullRequestContributions}}}")
            d = req(f"{API}/graphql", token, {"query": q, "variables": {"u": user, "f": since + "T00:00:00Z"}})
            c = d["data"]["user"]["contributionsCollection"]
            commits, prs = c["totalCommitContributions"], c["totalPullRequestContributions"]
        except Exception as e:
            print(f"graphql failed, falling back to search: {e}", file=sys.stderr)
    if commits is None:
        try:
            commits = req(f"{API}/search/commits?q=author:{user}+author-date:>={since}", token)["total_count"]
        except Exception:
            commits = 0
    if prs is None:
        try:
            prs = req(f"{API}/search/issues?q=author:{user}+type:pr+created:>={since}", token)["total_count"]
        except Exception:
            prs = 0
    return build(by, len(own), commits, prs, stars)


def sample():
    return build({"JavaScript": 4200, "PHP": 3100, "Python": 1800, "C++": 900}, 8, 126, 4, 0)


# ----------------------------------------------------------------- svg
def head(W, H, aria):
    return (f'<?xml version="1.0" encoding="UTF-8"?>\n<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" '
            f'viewBox="0 0 {W} {H}" role="img" aria-label="{escape(aria, {chr(34): "&quot;"})}">\n{STYLE}\n')


def frame(W, H):
    return (f'<rect x="0.75" y="0.75" width="{W - 1.5}" height="{H - 1.5}" rx="14" fill="{BG}" '
            f'stroke="{CYAN}" stroke-opacity="0.55" stroke-width="1.5"/>\n')


def pct(p):
    return f"{p:.0f}%" if p >= 10 else f"{p:.1f}%"


def radar_svg(d):
    W, H, cx, cy, R = 440, 290, 220, 148, 84
    top = d["top"] if d else []
    axes = list(top[:5])
    while len(axes) < 3:
        axes.append(("", 0.0, GRID))
    n = len(axes)
    ang = [-math.pi / 2 + 2 * math.pi * i / n for i in range(n)]
    pmax = max([a[1] for a in axes] + [0.0001])
    s = [head(W, H, "Language radar: share of code per language (square-root scale)"), frame(W, H)]
    s.append(f'<text class="s" x="24" y="36" font-size="15" font-weight="700" fill="{CYAN}">Language radar</text>\n')
    for k in (0.25, 0.5, 0.75, 1):
        pts = " ".join(f"{cx + k * R * math.cos(a):.1f},{cy + k * R * math.sin(a):.1f}" for a in ang)
        s.append(f'<polygon points="{pts}" fill="none" stroke="{GRID}" stroke-width="1"/>')
    for a in ang:
        s.append(f'<line x1="{cx}" y1="{cy}" x2="{cx + R * math.cos(a):.1f}" y2="{cy + R * math.sin(a):.1f}" stroke="{GRID}"/>')
    if d:
        rel = [R * math.sqrt(a[1] / pmax) for a in axes]
        pts = " ".join(f"{r * math.cos(t):.1f},{r * math.sin(t):.1f}" for r, t in zip(rel, ang))
        dots = "".join(f'<circle cx="{r * math.cos(t):.1f}" cy="{r * math.sin(t):.1f}" r="4" fill="{a[2]}" stroke="{BG}" stroke-width="1.5"/>'
                       for r, t, a in zip(rel, ang, axes) if a[1] > 0)
        s.append(f'<g transform="translate({cx} {cy})"><g>'
                 f'<animateTransform attributeName="transform" type="scale" from="0" to="1" dur="1.1s" fill="freeze" '
                 f'calcMode="spline" keyTimes="0;1" keySplines=".2 .8 .2 1"/>'
                 f'<polygon points="{pts}" fill="{CYAN}" fill-opacity="0.18" stroke="{CYAN}" stroke-width="2" stroke-linejoin="round"/>{dots}</g></g>')
    else:
        s.append(f'<text class="s" x="{cx}" y="{cy + 4}" text-anchor="middle" font-size="13" fill="{MUTED}">Waiting for the first update</text>')
    for a, t in zip(axes, ang):
        if not a[0]:
            continue
        lx, ly = cx + (R + 18) * math.cos(t), cy + (R + 18) * math.sin(t) + 4
        c = math.cos(t)
        anchor = "start" if c > 0.3 else "end" if c < -0.3 else "middle"
        s.append(f'<text class="s" x="{lx:.1f}" y="{ly:.1f}" text-anchor="{anchor}" font-size="13" fill="{TEXT}">{escape(a[0])}</text>')
    s.append(f'\n<text class="m" x="24" y="274" font-size="10.5" fill="{MUTED}">Code share per language, square-root scale</text>\n</svg>\n')
    return "".join(s)


def top_svg(d):
    W, H, x0, bw = 440, 290, 24, 392
    top = d["top"] if d else []
    s = [head(W, H, "Top languages by share of code"), frame(W, H)]
    s.append(f'<text class="s" x="24" y="36" font-size="15" font-weight="700" fill="{CYAN}">Top languages</text>\n')
    s.append(f'<defs><clipPath id="cb"><rect x="{x0}" y="52" width="{bw}" height="8" rx="4"/></clipPath></defs>')
    s.append(f'<rect x="{x0}" y="52" width="{bw}" height="8" rx="4" fill="{GRID}"/>')
    if top:
        tot = sum(t[1] for t in top)
        x, segs = float(x0), []
        for n, p, c in top:
            w = bw * p / tot
            segs.append(f'<rect x="{x - x0:.1f}" y="0" width="{w + 0.5:.1f}" height="8" fill="{c}"/>')
            x += w
        s.append(f'<g clip-path="url(#cb)"><g transform="translate({x0} 52)"><g>'
                 f'<animateTransform attributeName="transform" type="scale" from="0 1" to="1 1" dur="0.9s" fill="freeze"/>'
                 f'{"".join(segs)}</g></g></g>')
        for i, (n, p, c) in enumerate(top):
            y = 96 + i * 34
            w = max(3.0, bw * p / 100)
            s.append(f'\n<circle cx="{x0 + 6}" cy="{y - 5}" r="5" fill="{c}"/>'
                     f'<text class="s" x="{x0 + 22}" y="{y}" font-size="14" fill="{TEXT}">{escape(n)}</text>'
                     f'<text class="s" x="{x0 + bw}" y="{y}" text-anchor="end" font-size="14" fill="{c}">{pct(p)}</text>'
                     f'<rect x="{x0}" y="{y + 9}" width="{bw}" height="3" rx="1.5" fill="#16253F"/>'
                     f'<rect x="{x0}" y="{y + 9}" width="{w:.1f}" height="3" rx="1.5" fill="{c}">'
                     f'<animate attributeName="width" from="0" to="{w:.1f}" dur="0.9s" begin="{0.15 * i:.2f}s" fill="freeze"/></rect>')
        foot = f'updated on {d["updated"]}'
    else:
        for i in range(4):
            y = 96 + i * 34
            s.append(f'\n<circle cx="{x0 + 6}" cy="{y - 5}" r="5" fill="{GRID}"/><rect x="{x0 + 22}" y="{y - 11}" width="{90 - i * 8}" height="10" rx="5" fill="{GRID}"/>'
                     f'<rect x="{x0}" y="{y + 9}" width="{bw}" height="3" rx="1.5" fill="#16253F"/>')
        foot = "waiting for the first update"
    s.append(f'\n<text class="m" x="24" y="274" font-size="10.5" fill="{MUTED}">{foot}</text>\n</svg>\n')
    return "".join(s)


def stats_svg(d):
    W, H = 900, 96
    cells = [("Repositories", "repos"), ("Commits in the last year", "commits"), ("Pull requests", "prs"), ("Stars received", "stars")]
    s = [head(W, H, "Repositories, commits in the last year, pull requests and stars received"), frame(W, H)]
    cw = (W - 24) / 4
    for i, (label, key) in enumerate(cells):
        x = 24 + i * cw
        val = f"{d[key]:,}" if d else "–"
        if i:
            s.append(f'<line x1="{x - 14:.0f}" y1="22" x2="{x - 14:.0f}" y2="{H - 22}" stroke="{GRID}"/>')
        s.append(f'<text class="s" x="{x:.0f}" y="38" font-size="13" fill="{TEXT}">{escape(label)}</text>'
                 f'<text class="s" x="{x:.0f}" y="73" font-size="32" fill="{CYAN}" opacity="0">{val}'
                 f'<animate attributeName="opacity" from="0" to="1" dur="0.6s" begin="{0.12 * i:.2f}s" fill="freeze"/></text>\n')
    s.append("</svg>\n")
    return "".join(s)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--user", default=os.environ.get("GH_USER") or os.environ.get("GITHUB_REPOSITORY_OWNER"))
    ap.add_argument("--out", default="assets")
    ap.add_argument("--placeholder", action="store_true")
    ap.add_argument("--sample", action="store_true")
    a = ap.parse_args()
    if a.placeholder:
        data = None
    elif a.sample:
        data = sample()
    else:
        if not a.user:
            sys.exit("Pass --user NAME (or set GH_USER).")
        data = fetch(a.user, os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN"))
    os.makedirs(a.out, exist_ok=True)
    for name, svg in (("lang-radar.svg", radar_svg(data)), ("lang-top.svg", top_svg(data)), ("stats-row.svg", stats_svg(data))):
        with open(os.path.join(a.out, name), "w", encoding="utf-8") as fh:
            fh.write(svg)
    if data and not a.sample:
        with open(os.path.join(a.out, "stats-data.json"), "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2)
    print("written to", a.out, "-", "placeholder" if a.placeholder else "sample" if a.sample else "live data")


if __name__ == "__main__":
    main()
