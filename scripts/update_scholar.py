#!/usr/bin/env python3
"""Weekly Google Scholar update for index.html (via SerpApi).

Usage:
  SERPAPI_KEY=... python3 scripts/update_scholar.py            # fetch + update
  python3 scripts/update_scholar.py --json saved.json          # update from a saved response
Updates: headline metrics, citations-per-year chart, per-paper citation counts
and their Google Scholar links, and the "as of" date.
"""
import datetime, html, json, os, re, sys, urllib.parse, urllib.request

AUTHOR_ID = "UyaIfEkAAAAJ"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INDEX = os.path.join(ROOT, "index.html")


def fetch():
    key = os.environ.get("SERPAPI_KEY")
    if not key:
        sys.exit("SERPAPI_KEY is not set")
    arts, data, start = [], None, 0
    while True:
        q = urllib.parse.urlencode({"engine": "google_scholar_author", "author_id": AUTHOR_ID,
                                    "hl": "en", "num": 100, "start": start, "api_key": key})
        with urllib.request.urlopen("https://serpapi.com/search.json?" + q, timeout=60) as r:
            page = json.load(r)
        if "error" in page:
            sys.exit("SerpApi error: " + page["error"])
        data = data or page
        got = page.get("articles", [])
        arts += got
        if len(got) < 100:
            break
        start += 100
    data["articles"] = arts
    return data


def norm(t):
    t = html.unescape(re.sub(r"<[^>]+>", "", t)).lower()
    return re.sub(r"[^a-z0-9]+", "", t)


def fmt(n):
    return f"{int(n):,}"


def nice_max(v):
    for step in (25, 50, 75, 100, 125, 150, 200, 250, 300, 375, 400, 500, 625, 750, 1000, 1250, 1500, 2000, 2500, 3000, 4000, 5000):
        if step * 4 >= v:
            return step * 4
    return ((v // 4000) + 1) * 4000


def chart(graph, this_year):
    graph = sorted(graph, key=lambda g: g["year"])
    top = nice_max(max(g["citations"] for g in graph) or 1)
    x0, x1, yb, yt = 44, 710, 216.0, 14.0
    out = []
    for i in range(5):
        v = top * i / 4
        y = yb - (yb - yt) * i / 4
        out.append(f'<line x1="{x0}" x2="{x1}" y1="{y:.1f}" y2="{y:.1f}" stroke="var(--line)" stroke-width="1"/>'
                   f'<text x="36" y="{y + 4:.1f}" text-anchor="end" font-size="11" fill="var(--muted)">{fmt(v)}</text>')
    n = len(graph)
    slot = (x1 - x0 - 10) / n
    bw = slot * 0.6
    for i, g in enumerate(graph):
        h = (yb - yt) * g["citations"] / top
        x = x0 + 10 + slot * i + (slot - bw) / 2 - 5
        light = ' fill-opacity=".5"' if g["year"] == this_year else ""
        out.append(f'<rect x="{x:.1f}" y="{yb - h:.1f}" width="{bw:.1f}" height="{h:.1f}" rx="2" fill="var(--hema)"{light}/>'
                   f'<text x="{x + bw / 2:.1f}" y="236" text-anchor="middle" font-size="11" fill="var(--muted)">{g["year"]}</text>')
    return ('<svg viewBox="0 0 720 250" role="img" aria-labelledby="ct" style="min-width:560px;width:100%;height:auto;display:block">'
            '<title id="ct">Citations per year, Google Scholar</title>' + "".join(out) + "</svg>")


def update(s, data, today):
    tbl = data["cited_by"]["table"]
    cit, h, i10 = tbl[0]["citations"], tbl[1]["h_index"], tbl[2]["i10_index"]
    since_key = next(k for k in cit if k != "all")
    metrics = [cit, h, i10]
    parts = s.split('<div class="metric">')
    if len(parts) != 4:
        raise SystemExit("metrics block not found")
    for k in range(3):
        m = metrics[k]
        p = parts[k + 1]
        p = re.sub(r'<div class="n">[^<]*</div>', f'<div class="n">{fmt(m["all"])}</div>', p, count=1)
        p = re.sub(r'(<div class="s">.*?</span> · )[\d,]+', lambda mm: mm.group(1) + fmt(m[since_key]), p, count=1, flags=re.S)
        parts[k + 1] = p
    s = '<div class="metric">'.join(parts)

    year = today.year
    s, c = re.subn(r'<svg viewBox="0 0 720 250".*?</svg>', lambda _: chart(data["cited_by"]["graph"], year), s, count=1, flags=re.S)
    if not c:
        raise SystemExit("chart not found")

    d_zh = f"{today.year} 年 {today.month} 月 {today.day} 日"
    d_en = today.strftime("%-d %B %Y")
    s = re.sub(r"截至 \d{4} 年 \d{1,2} 月 \d{1,2} 日", "截至 " + d_zh, s)
    s = re.sub(r"as of \d{1,2} [A-Z][a-z]+ \d{4}", "as of " + d_en, s)

    by_title = {}
    for a in data.get("articles", []):
        by_title.setdefault(norm(a.get("title", "")), a)
    blocks = s.split('<div class="pub">')
    hits = 0
    for idx in range(1, len(blocks)):
        b = blocks[idx]
        t = re.search(r'<p class="t">(.*?)</p>', b, re.S)
        if not t:
            continue
        a = by_title.get(norm(t.group(1)))
        if not a:
            continue
        cb = a.get("cited_by") or {}
        val = cb.get("value")
        if not val:
            continue
        hits += 1
        link = cb.get("link") or ("https://scholar.google.com/scholar?q=" + urllib.parse.quote('"' + a["title"] + '"'))
        badge = (f'<a class="cn" href="{html.escape(link)}" target="_blank" rel="noopener" title="Google Scholar">'
                 f'<b>{fmt(val)}</b> <span class="zh">被引</span><span class="en">citations</span> ↗</a>')
        if '<a class="cn"' in b:
            b = re.sub(r'<a class="cn".*?</a>', lambda _: badge, b, count=1, flags=re.S)
        else:
            b = b.replace('<div class="bd">', '<div class="bd">' + badge, 1)
        blocks[idx] = b
    print(f"matched {hits} papers")
    return '<div class="pub">'.join(blocks)


def main():
    if "--json" in sys.argv:
        data = json.load(open(sys.argv[sys.argv.index("--json") + 1]))
    else:
        data = fetch()
    s = open(INDEX, encoding="utf-8").read()
    new = update(s, data, datetime.date.today())
    if new != s:
        open(INDEX, "w", encoding="utf-8").write(new)
        print("index.html updated")
    else:
        print("no changes")


if __name__ == "__main__":
    main()
