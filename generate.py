#!/usr/bin/env python3
"""
GitHub Trending Weekly - Auto-generator
Scrapes GitHub Trending (weekly), picks top repos, generates a styled HTML page.
Designed to run in GitHub Actions on a cron schedule.
"""

import re
import json
import sys
from datetime import datetime, timezone, timedelta

import requests
from bs4 import BeautifulSoup

TRENDING_URL = "https://github.com/trending?since=weekly"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

# ---------- Category detection ----------
CATEGORY_KEYWORDS = [
    ("AI \u667a\u80fd\u4f53 & \u7f16\u7801", [
        "ai", "agent", "llm", "gpt", "claude", "model", "neural", "machine learning",
        "deep learning", "transformer", "embedding", "rag", "langchain", "copilot",
        "chatbot", "inference", "fine-tune", "fine tune", "lora", "diffusion",
        "generative", "prompt", "vector", "autonomous", "mcp", "skill",
    ]),
    ("AI \u57fa\u7840\u8bbe\u65bd & \u6a21\u578b", [
        "training", "gpu", "cuda", "tensorrt", "vllm", "ollama", "huggingface",
        "pytorch", "tensorflow", "keras", "onnx", "quantiz", "accelerat",
        "dataset", "benchmark", "pipeline", "orchestrat",
    ]),
    ("\u5f00\u53d1\u5de5\u5177", [
        "cli", "terminal", "tool", "dev", "build", "deploy", "ci/cd", "docker",
        "kubernetes", "k8s", "monitor", "debug", "test", "lint", "format",
        "ide", "editor", "plugin", "extension", "compiler", "automation",
        "ci ", "cd ", "observability", "auth", "database", "sql", "api",
    ]),
    ("\u5b66\u4e60\u8d44\u6e90", [
        "tutorial", "course", "learn", "beginner", "guide", "handbook",
        "awesome", "roadmap", "interview", "book", "curriculum", "lesson",
        "education", "challenge", "30 days", "100 days", "leetcode",
    ]),
    ("\u5b89\u5168 & \u7a7f\u900f", [
        "security", "vuln", "exploit", "pentest", "crypto", "auth", "firewall",
        "malware", "reverse engineer", "forensic", "siem", "zero-day",
    ]),
]

DEFAULT_CATEGORY = "\u5f00\u53d1\u5de5\u5177"

# Category -> short Chinese intro template
CATEGORY_INTRO = {
    "AI \u667a\u80fd\u4f53 & \u7f16\u7801": "\u8fd9\u662f\u4e00\u4e2a AI / \u667a\u80fd\u4f53\u65b9\u5411\u7684\u9879\u76ee\uff0c",
    "AI \u57fa\u7840\u8bbe\u65bd & \u6a21\u578b": "\u8fd9\u662f\u4e00\u4e2a AI \u57fa\u7840\u8bbe\u65bd / \u6a21\u578b\u5de5\u7a0b\u9879\u76ee\uff0c",
    "\u5f00\u53d1\u5de5\u5177": "\u8fd9\u662f\u4e00\u4e2a\u5f00\u53d1\u5de5\u5177\u9879\u76ee\uff0c",
    "\u5b66\u4e60\u8d44\u6e90": "\u8fd9\u662f\u4e00\u4efd\u5b66\u4e60\u8d44\u6e90\uff0c",
    "\u5b89\u5168 & \u7a7f\u900f": "\u8fd9\u662f\u4e00\u4e2a\u5b89\u5168\u65b9\u5411\u7684\u9879\u76ee\uff0c",
}

LANG_COLORS = {
    "Python": "#3572A5", "JavaScript": "#f1e05a", "TypeScript": "#3178c6",
    "Rust": "#dea584", "Go": "#00ADD8", "Java": "#b07219", "C++": "#f34b7d",
    "C": "#555555", "C#": "#178600", "Ruby": "#701516", "Swift": "#F05138",
    "Kotlin": "#A97BFF", "Dart": "#00B4AB", "Shell": "#89e051", "PowerShell": "#012456",
    "Jupyter Notebook": "#DA5B0B", "HTML": "#e34c26", "CSS": "#563d7c",
    "Vue": "#41b883", "Svelte": "#ff3e00", "PHP": "#4F5D95", "Scala": "#c22d40",
    "Lua": "#000080", "Zig": "#ec915c", "Elixir": "#6e4a7e", "Haskell": "#5e5086",
}


def detect_category(name, desc, lang):
    text = f"{name} {desc} {lang}".lower()
    for cat, keywords in CATEGORY_KEYWORDS:
        for kw in keywords:
            if kw in text:
                return cat
    return DEFAULT_CATEGORY


def parse_int(text):
    """Parse '1,234' or '1.2k' to int."""
    text = text.strip().replace(",", "")
    if text.endswith("k"):
        return int(float(text[:-1]) * 1000)
    if text.endswith("M"):
        return int(float(text[:-1]) * 1_000_000)
    try:
        return int(text)
    except ValueError:
        return 0


def fetch_trending():
    """Fetch and parse GitHub Trending weekly page."""
    resp = requests.get(TRENDING_URL, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    repos = []
    articles = soup.select("article.Box-row")
    if not articles:
        # Fallback selector
        articles = soup.select("article")

    for article in articles:
        # Repo name
        h2 = article.find("h2")
        if not h2:
            continue
        a = h2.find("a")
        if not a:
            continue
        href = a.get("href", "").strip("/")
        parts = href.split("/")
        if len(parts) < 2:
            continue
        owner, name = parts[0], parts[1]

        # Description
        p = article.find("p")
        desc = p.get_text(strip=True) if p else ""

        # Language
        lang_span = article.select_one("[itemprop='programmingLanguage']")
        lang = lang_span.get_text(strip=True) if lang_span else "N/A"

        # Stars
        stars = 0
        for link in article.find_all("a"):
            href = link.get("href", "")
            if "/stargazers" in href:
                stars = parse_int(link.get_text(strip=True))
                break

        # Weekly stars
        week_stars = 0
        for span in article.find_all("span"):
            txt = span.get_text(strip=True)
            m = re.search(r"([\d,]+)\s+stars?\s+this\s+week", txt, re.IGNORECASE)
            if m:
                week_stars = parse_int(m.group(1))
                break

        if not desc:
            desc = f"{name} - {owner}'s repository on GitHub"

        category = detect_category(name, desc, lang)
        intro = CATEGORY_INTRO.get(category, "")
        full_desc = f"{intro}{desc}\u3002\u4e3b\u8bed\u8a00 {lang}\uff0c\u603b Star {stars:,}\uff0c\u672c\u5468\u65b0\u589e {week_stars:,}\u3002"

        repos.append({
            "owner": owner,
            "name": name,
            "cat": category,
            "desc": full_desc,
            "lang": lang,
            "stars": stars,
            "week": week_stars,
        })

    return repos


def select_repos(repos, count=12):
    """Select top repos by weekly stars, ensuring category diversity."""
    # Sort by weekly stars
    sorted_repos = sorted(repos, key=lambda r: r["week"], reverse=True)

    # Greedy selection: ensure at least 2 per category, then fill by weekly stars
    selected = []
    seen_cats = {}

    # First pass: top repos ensuring no more than 4 from same category early
    for r in sorted_repos:
        cat_count = seen_cats.get(r["cat"], 0)
        if cat_count < 4:
            selected.append(r)
            seen_cats[r["cat"]] = cat_count + 1
        if len(selected) >= count:
            break

    # If not enough, fill remaining
    if len(selected) < count:
        existing = {(r["owner"], r["name"]) for r in selected}
        for r in sorted_repos:
            if (r["owner"], r["name"]) not in existing:
                selected.append(r)
                if len(selected) >= count:
                    break

    return selected[:count]


def generate_html(repos, date_str):
    """Generate the full HTML page."""
    langs = sorted(set(r["lang"] for r in repos if r["lang"] != "N/A"))
    total_week = sum(r["week"] for r in repos)

    # Build JS data
    repos_json = json.dumps(repos, ensure_ascii=False, indent=2)

    # Language color CSS
    lang_css = "\n".join(
        f'  .lc-{i}{{background:{LANG_COLORS.get(lang, "#8b949e")}}}'
        for i, lang in enumerate(langs)
    )

    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>GitHub Trending \u5468\u520a \xb7 \u672c\u5468\u70ed\u70b9\u7cbe\u9009</title>
<style>
  :root{{
    --bg:#0d1117; --card:#161b22; --border:#30363d; --text:#e6edf3;
    --muted:#8b949e; --accent:#58a6ff; --accent2:#3fb950; --chip:#21262d;
    --orange:#f0883e; --purple:#a371f7;
  }}
  *{{box-sizing:border-box;margin:0;padding:0}}
  body{{
    font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC","Microsoft YaHei",Helvetica,Arial,sans-serif;
    background:var(--bg);color:var(--text);line-height:1.65;padding:0 20px 60px;
  }}
  .wrap{{max-width:1080px;margin:0 auto}}
  .hero{{padding:44px 0 32px;border-bottom:1px solid var(--border);margin-bottom:28px}}
  .eyebrow{{
    display:inline-flex;align-items:center;gap:8px;color:var(--accent);font-size:12px;
    font-weight:700;letter-spacing:.8px;text-transform:uppercase;margin-bottom:14px;
    background:rgba(88,166,255,.08);border:1px solid rgba(88,166,255,.25);
    padding:5px 12px;border-radius:999px;
  }}
  .eyebrow .pulse{{
    width:7px;height:7px;border-radius:50%;background:var(--accent2);
    box-shadow:0 0 0 0 rgba(63,185,80,.5);animation:pulse 2s infinite;
  }}
  @keyframes pulse{{
    0%{{box-shadow:0 0 0 0 rgba(63,185,80,.5)}}
    70%{{box-shadow:0 0 0 6px rgba(63,185,80,0)}}
    100%{{box-shadow:0 0 0 0 rgba(63,185,80,0)}}
  }}
  h1{{font-size:34px;font-weight:800;letter-spacing:-.5px;line-height:1.2}}
  h1 .dot{{color:var(--accent)}}
  .tagline{{font-size:17px;color:var(--muted);margin-top:12px;max-width:760px}}
  .intro-grid{{
    display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:16px;margin-top:28px;
  }}
  .intro-card{{background:var(--card);border:1px solid var(--border);border-radius:14px;padding:18px}}
  .intro-card h3{{font-size:14px;font-weight:700;color:var(--text);margin-bottom:8px;display:flex;align-items:center;gap:8px}}
  .intro-card h3 .icon{{font-size:16px}}
  .intro-card p{{font-size:13.2px;color:var(--muted)}}
  .stats{{display:flex;flex-wrap:wrap;gap:18px;margin-top:26px;align-items:center}}
  .stat{{
    background:var(--chip);border:1px solid var(--border);border-radius:10px;padding:10px 16px;
    display:flex;flex-direction:column;gap:2px;
  }}
  .stat .num{{font-size:18px;font-weight:800;color:var(--accent)}}
  .stat .label{{font-size:11.5px;color:var(--muted)}}
  .toolbar{{display:flex;flex-wrap:wrap;gap:10px;align-items:center;margin:22px 0 22px}}
  .search{{
    flex:1;min-width:200px;background:var(--card);border:1px solid var(--border);
    color:var(--text);padding:11px 16px;border-radius:10px;font-size:14px;outline:none;
  }}
  .search:focus{{border-color:var(--accent)}}
  .filters{{display:flex;flex-wrap:wrap;gap:8px}}
  .filter{{
    background:var(--chip);border:1px solid var(--border);color:var(--muted);
    padding:7px 14px;border-radius:999px;font-size:13px;cursor:pointer;transition:.15s;
  }}
  .filter:hover{{color:var(--text);border-color:var(--accent)}}
  .filter.active{{background:var(--accent);color:#0d1117;border-color:var(--accent);font-weight:600}}
  .section-title{{
    font-size:15px;font-weight:700;color:var(--text);margin-bottom:14px;display:flex;
    align-items:center;justify-content:space-between;gap:10px;
  }}
  .section-title .muted{{font-weight:400;color:var(--muted);font-size:13px}}
  .grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(320px,1fr));gap:16px}}
  .card{{
    background:var(--card);border:1px solid var(--border);border-radius:14px;
    padding:18px;display:flex;flex-direction:column;gap:10px;text-decoration:none;
    color:inherit;transition:.18s;position:relative;overflow:hidden;
  }}
  .card:hover{{transform:translateY(-3px);border-color:var(--accent);box-shadow:0 8px 24px rgba(88,166,255,.12)}}
  .card .top{{display:flex;justify-content:space-between;align-items:flex-start;gap:10px}}
  .repo{{font-size:16px;font-weight:700;color:var(--accent);word-break:break-all}}
  .repo .owner{{color:var(--muted);font-weight:500}}
  .desc{{font-size:13.5px;color:var(--text);opacity:.92;flex:1;min-height:66px}}
  .meta{{display:flex;flex-wrap:wrap;gap:8px;align-items:center;font-size:12.5px;color:var(--muted)}}
  .lang{{display:flex;align-items:center;gap:5px}}
  .lang .lc{{width:10px;height:10px;border-radius:50%;background:var(--accent2)}}
  .star{{color:var(--accent2);font-weight:600}}
  .wk{{color:var(--orange);font-weight:600}}
  .cat{{font-size:11px;color:var(--muted);background:var(--chip);border:1px solid var(--border);padding:2px 9px;border-radius:999px}}
  .arrow{{position:absolute;top:14px;right:14px;color:var(--muted);font-size:14px;opacity:0;transition:.18s}}
  .card:hover .arrow{{opacity:1;color:var(--accent)}}
  .empty{{grid-column:1/-1;text-align:center;color:var(--muted);padding:40px}}
  footer{{margin-top:44px;text-align:center;color:var(--muted);font-size:12.5px;border-top:1px solid var(--border);padding-top:24px}}
  footer a{{color:var(--accent);text-decoration:none}}
  footer a:hover{{text-decoration:underline}}
</style>
</head>
<body>
<div class="wrap">
  <section class="hero">
    <div class="eyebrow"><span class="pulse"></span>GitHub Trending \u5468\u520a</div>
    <h1>\u672c\u5468 GitHub \u70ed\u70b9\u7cbe\u9009<span class="dot">.</span></h1>
    <p class="tagline">
      \u81ea\u52a8\u805a\u5408 GitHub \u5468\u699c\u70ed\u95e8\u4ed3\u5e93\uff0c\u7528\u4e2d\u6587\u63d0\u70bc\u9879\u76ee\u80cc\u666f\u3001\u6838\u5fc3\u80fd\u529b\u4e0e\u672c\u5468\u70ed\u5ea6\u3002
      \u5e2e\u4f60\u5feb\u901f\u5224\u65ad\u54ea\u4e9b\u9879\u76ee\u503c\u5f97\u6df1\u5165\u7814\u7a76\uff0c\u70b9\u4e00\u4e0b\u5373\u53ef\u8df3\u8f6c\u5230 GitHub \u67e5\u770b\u6e90\u7801\u3002
    </p>
    <div class="intro-grid">
      <div class="intro-card">
        <h3><span class="icon">\U0001f3af</span>\u6570\u636e\u6765\u6e90</h3>
        <p>\u76f4\u63a5\u91c7\u96c6 <a href="https://www.github.com/trending?since=weekly" target="_blank" rel="noopener" style="color:var(--accent);text-decoration:none">GitHub Trending \u5468\u699c</a>\uff0c\u6bcf\u5468\u66f4\u65b0\u4e00\u6b21\uff0c\u805a\u7126\u589e\u957f\u6700\u5feb\u7684\u5f00\u6e90\u9879\u76ee\u3002</p>
      </div>
      <div class="intro-card">
        <h3><span class="icon">\U0001f4e6</span>\u7b5b\u9009\u903b\u8f91</h3>
        <p>\u6309\u672c\u5468\u65b0\u589e Star \u6392\u5e8f\uff0c\u517c\u987e\u8bed\u8a00\u591a\u6837\u6027\uff08Rust / Python / Go / TypeScript \u7b49\uff09\u548c\u5b9e\u7528\u6027\uff0c\u53bb\u6389\u7eaf\u5a31\u4e50\u6216\u91cd\u590d\u9879\u76ee\u3002</p>
      </div>
      <div class="intro-card">
        <h3><span class="icon">\U0001f50d</span>\u4f7f\u7528\u65b9\u5f0f</h3>
        <p>\u7528\u9876\u90e8\u641c\u7d22\u6846\u5feb\u901f\u5b9a\u4f4d\uff1b\u70b9\u51fb\u5206\u7c7b\u7b5b\u9009\u53ea\u770b AI \u667a\u80fd\u4f53\u3001\u5f00\u53d1\u5de5\u5177\u6216\u5b66\u4e60\u8d44\u6e90\uff1b\u70b9\u51fb\u5361\u7247\u76f4\u8fbe GitHub \u4ed3\u5e93\u3002</p>
      </div>
      <div class="intro-card">
        <h3><span class="icon">\u26a1</span>\u9002\u7528\u4eba\u7fa4</h3>
        <p>\u9002\u5408\u60f3\u4e86\u89e3\u5f00\u6e90\u98ce\u5411\u7684\u5f00\u53d1\u8005\u3001\u67b6\u6784\u5e08\u3001\u6280\u672f\u7ba1\u7406\u8005\uff0c\u4ee5\u53ca\u51c6\u5907\u9762\u8bd5 / \u5b66\u4e60 AI / \u7cfb\u7edf\u8bbe\u8ba1\u7684\u4eba\u7fa4\u3002</p>
      </div>
    </div>
    <div class="stats">
      <div class="stat"><div class="num">{len(repos)}</div><div class="label">\u672c\u671f\u7cbe\u9009\u4ed3\u5e93</div></div>
      <div class="stat"><div class="num">{len(langs)}</div><div class="label">\u8986\u76d6\u8bed\u8a00/\u6280\u672f\u6808</div></div>
      <div class="stat"><div class="num">+{total_week/1000:.1f}k</div><div class="label">\u672c\u5468\u65b0\u589e Star \u603b\u8ba1</div></div>
      <div class="stat"><div class="num">{date_str}</div><div class="label">\u6700\u8fd1\u6574\u7406\u65e5\u671f</div></div>
    </div>
  </section>
  <div class="toolbar">
    <input class="search" id="search" placeholder="\u641c\u7d22\u4ed3\u5e93\u540d / \u63cf\u8ff0 / \u8bed\u8a00\u2026" oninput="render()">
    <div class="filters" id="filters"></div>
  </div>
  <div class="section-title">
    <span>\u7cbe\u9009\u4ed3\u5e93\u5217\u8868</span>
    <span class="muted">\u70b9\u51fb\u5361\u7247\u8df3\u8f6c GitHub \xb7 \u6309\u672c\u5468\u65b0\u589e Star \u6392\u5e8f</span>
  </div>
  <div class="grid" id="grid"></div>
  <footer>
    \u7531 GitHub Actions \u81ea\u52a8\u6574\u7406 \xb7 \u6570\u636e\u622a\u81f3 <span>{date_str}</span> \xb7
    <a href="https://www.github.com/trending?since=weekly" target="_blank" rel="noopener">\u67e5\u770b\u539f\u59cb GitHub Trending \u5468\u699c \u2197</a>
  </footer>
</div>
<script>
const repos = {repos_json};
const langColors = {json.dumps(LANG_COLORS, ensure_ascii=False)};
const cats = ["\u5168\u90e8", ...new Set(repos.map(r=>r.cat))];
let activeCat = "\u5168\u90e8";
const filtersEl = document.getElementById("filters");
cats.forEach(c=>{{
  const b=document.createElement("button");
  b.className="filter"+(c==="\u5168\u90e8"?" active":"");
  b.textContent=c;
  b.onclick=()=>{{activeCat=c;[...filtersEl.children].forEach(x=>x.classList.remove("active"));b.classList.add("active");render();}};
  filtersEl.appendChild(b);
}});
function fmt(n){{return n>=1000?(n/1000).toFixed(1)+"k":n;}}
function render(){{
  const q=document.getElementById("search").value.trim().toLowerCase();
  const grid=document.getElementById("grid");
  grid.innerHTML="";
  const list=repos.filter(r=>{{
    const okCat = activeCat==="\u5168\u90e8"||r.cat===activeCat;
    const okQ = !q || (r.owner+r.name).toLowerCase().includes(q) || r.desc.toLowerCase().includes(q) || r.lang.toLowerCase().includes(q);
    return okCat && okQ;
  }});
  if(!list.length){{grid.innerHTML='<div class="empty">\u6ca1\u6709\u5339\u914d\u7684\u7ed3\u679c</div>';return;}}
  list.forEach((r,i)=>{{
    const url="https://www.github.com/"+r.owner+"/"+r.name;
    const a=document.createElement("a");
    a.className="card";
    a.href=url; a.target="_blank"; a.rel="noopener";
    const lc = langColors[r.lang] || "#3fb950";
    a.innerHTML=`
      <span class="arrow">\u2197</span>
      <div class="top">
        <div class="repo"><span class="owner">${{r.owner}}/</span>${{r.name}}</div>
      </div>
      <div class="desc">${{r.desc}}</div>
      <div class="meta">
        <span class="cat">${{r.cat}}</span>
        <span class="lang"><span class="lc" style="background:${{lc}}"></span>${{r.lang}}</span>
        <span class="star">\u2605 ${{fmt(r.stars)}}</span>
        <span class="wk">\u672c\u5468 +${{fmt(r.week)}}</span>
      </div>`;
    grid.appendChild(a);
  }});
}}
render();
</script>
</body>
</html>"""
    return html


def main():
    print("[1/4] Fetching GitHub Trending (weekly)...")
    try:
        repos = fetch_trending()
    except Exception as e:
        print(f"  ERROR fetching trending: {e}", file=sys.stderr)
        sys.exit(1)

    if not repos:
        print("  ERROR: No repos found. GitHub page structure may have changed.", file=sys.stderr)
        sys.exit(1)

    print(f"  Found {len(repos)} repos from trending page.")

    print("[2/4] Selecting top repos...")
    selected = select_repos(repos, count=12)
    print(f"  Selected {len(selected)} repos across {len(set(r['cat'] for r in selected))} categories.")

    print("[3/4] Generating HTML...")
    tz = timezone(timedelta(hours=8))
    date_str = datetime.now(tz).strftime("%Y-%m-%d")
    html = generate_html(selected, date_str)

    print("[4/4] Writing index.html...")
    with open("index.html", "w", encoding="utf-8") as f:
        f.write(html)

    print(f"\nDone! Generated index.html with {len(selected)} repos.")
    print(f"Date: {date_str}")
    print(f"Top repo: {selected[0]['owner']}/{selected[0]['name']} (+{selected[0]['week']:,} stars this week)")


if __name__ == "__main__":
    main()
