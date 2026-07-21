#!/usr/bin/env python3
"""Build a single-file interactive site from the interview question bank + solutions."""
import html
import json
import re
from pathlib import Path

ROOT = Path("/Users/dnissim")
BANK = (ROOT / "interview-question-bank.md").read_text()
SOLS = (ROOT / "interview-question-bank-solutions.md").read_text()
OUT = Path("/Users/dnissim/interview-bank-site/dist/index.html")
DIFF = json.loads(Path("/Users/dnissim/interview-bank-site/difficulty.json").read_text())
DIFF_A = {int(k): v for k, v in DIFF["tierA"].items()}
SCALE = DIFF["scale"]
PROMPTS = json.loads(Path("/Users/dnissim/interview-bank-site/prompts.json").read_text())
PROMPTS_A = {int(k): v for k, v in PROMPTS["tierA"].items()}

def dots(score, rationale):
    tip = html.escape(f"Difficulty {score}/5 — {SCALE[str(score)]}. {rationale}", quote=True)
    pips = "".join(f'<i class="{"on" if i < score else ""}"></i>' for i in range(5))
    return (f'<span class="dots d{score}" title="{tip}" '
            f'aria-label="Difficulty {score} of 5">{pips}</span>')

# ---------------------------------------------------------------- inline md
def inline(text: str) -> str:
    """Escape HTML then convert inline markdown: code, bold, italic, arrows."""
    text = html.escape(text, quote=False)
    # protect code spans
    codes = []
    def stash(m):
        codes.append(m.group(1))
        return f"\x00{len(codes)-1}\x00"
    text = re.sub(r"`([^`]+)`", stash, text)
    text = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(r"(?<!\*)\*([^*]+)\*(?!\*)", r"<em>\1</em>", text)
    text = re.sub(r"\x00(\d+)\x00", lambda m: f"<code>{codes[int(m.group(1))]}</code>", text)
    return text

# ------------------------------------------------------------- block md → html
def blocks_to_html(lines):
    """Convert a list of markdown lines (paragraphs, lists, code fences) to HTML."""
    out = []
    i = 0
    n = len(lines)
    while i < n:
        line = lines[i]
        if not line.strip():
            i += 1
            continue
        if line.startswith("```"):
            lang = line.strip()[3:]
            code_lines = []
            i += 1
            while i < n and not lines[i].startswith("```"):
                code_lines.append(lines[i])
                i += 1
            i += 1  # closing fence
            code = html.escape("\n".join(code_lines))
            out.append(f'<pre><code class="lang-{lang or "text"}">{code}</code></pre>')
            continue
        m = re.match(r"^(\s*)- (.*)$", line)
        if m:
            # gather list block (with nesting by indent)
            items = []  # (indent, text)
            while i < n:
                lm = re.match(r"^(\s*)- (.*)$", lines[i])
                if lm:
                    items.append((len(lm.group(1)), lm.group(2)))
                    i += 1
                elif lines[i].strip() and re.match(r"^\s{2,}\S", lines[i]) and items:
                    items[-1] = (items[-1][0], items[-1][1] + " " + lines[i].strip())
                    i += 1
                else:
                    break
            out.append(render_list(items))
            continue
        m = re.match(r"^(\d+)\.\s+(.*)$", line)
        if m:
            out.append("<ol>")
            while i < n:
                lm = re.match(r"^(\d+)\.\s+(.*)$", lines[i])
                if not lm:
                    break
                out.append(f"<li>{inline(lm.group(2))}</li>")
                i += 1
            out.append("</ol>")
            continue
        # paragraph: gather until blank / structural line
        para = [line.strip()]
        i += 1
        while i < n and lines[i].strip() and not re.match(r"^(\s*-\s|\d+\.\s|```|#)", lines[i]):
            para.append(lines[i].strip())
            i += 1
        out.append(f"<p>{inline(' '.join(para))}</p>")
    return "\n".join(out)

def render_list(items):
    """Render (indent, text) tuples as nested <ul>."""
    out = ["<ul>"]
    prev = items[0][0]
    open_li = False
    for indent, text in items:
        if indent > prev:
            out.append("<ul>")
        elif indent < prev:
            out.append("</li></ul>")
            if open_li:
                out.append("</li>")
                open_li = False
        elif open_li:
            out.append("</li>")
        out.append(f"<li>{inline(text)}")
        open_li = True
        prev = indent
    depth = (prev - items[0][0]) // 2
    out.append("</li>")
    for _ in range(depth):
        out.append("</ul></li>")
    out.append("</ul>")
    return "".join(out)

# ------------------------------------------------------------- parse solutions
def parse_solutions(text):
    """Return (numbered: {int: html}, sections: {heading: html}, a_section_notes: {a_key: html})."""
    lines = text.split("\n")
    numbered = {}
    sections = {}
    a_notes = {}
    cur_h2 = cur_h3 = None
    cur_nums = None
    buf = []
    section_buf = []

    def flush_entry():
        nonlocal buf, cur_nums
        if cur_nums is not None:
            htmlv = blocks_to_html(buf)
            for num in cur_nums:
                numbered[num] = htmlv
        buf = []
        cur_nums = None

    def flush_section():
        nonlocal section_buf
        if cur_h3 and section_buf and any(l.strip() for l in section_buf):
            key = cur_h3
            if cur_h2 == "TIER A":
                am = re.match(r"(A\d)", cur_h3)
                if am:
                    a_notes[am.group(1)] = blocks_to_html(section_buf)
            else:
                sections.setdefault(cur_h2, []).append((cur_h3, blocks_to_html(section_buf)))
        elif cur_h2 and not cur_h3 and section_buf and any(l.strip() for l in section_buf):
            sections.setdefault(cur_h2, []).append((None, blocks_to_html(section_buf)))
        section_buf = []

    in_fence = False
    for line in lines:
        if line.startswith("```"):
            in_fence = not in_fence
        if not in_fence:
            h2 = re.match(r"^## (.*)$", line)
            h3 = re.match(r"^### (.*)$", line)
            if h2:
                flush_entry(); flush_section()
                cur_h2 = h2.group(1).strip()
                cur_h3 = None
                continue
            if h3:
                flush_entry(); flush_section()
                cur_h3 = h3.group(1).strip()
                continue
            em = re.match(r"^\*\*(\d+(?:\s*&\s*\d+)*)\.\s", line)
            if em and cur_h2 == "TIER A":
                flush_entry(); flush_section()
                cur_nums = [int(x) for x in re.findall(r"\d+", em.group(1))]
                # strip the leading "**N. Title.**" label but keep the rest of the line
                rest = re.sub(r"^\*\*\d+(?:\s*&\s*\d+)*\.\s*", "**", line)
                buf.append(rest)
                continue
        if cur_nums is not None:
            buf.append(line)
        else:
            section_buf.append(line)
    flush_entry(); flush_section()
    return numbered, sections, a_notes

SOL_NUM, SOL_SECTIONS, SOL_A_NOTES = parse_solutions(SOLS)

# ------------------------------------------------------------- parse bank
def split_top(text):
    """Split bank into intro + top-level '# ' sections."""
    parts = {}
    cur = "INTRO"
    parts[cur] = []
    in_fence = False
    for line in text.split("\n"):
        if line.startswith("```"):
            in_fence = not in_fence
        if not in_fence and line.startswith("# ") and not line.startswith("##"):
            cur = line[2:].strip()
            parts[cur] = []
        else:
            parts[cur].append(line)
    return parts

TOP = split_top(BANK)

def find_key(prefix):
    for k in TOP:
        if k.startswith(prefix):
            return k
    raise KeyError(prefix)

def split_h2(lines):
    """Split section lines into (preamble_lines, [(h2_title, lines)])."""
    pre, subs = [], []
    cur = None
    for line in lines:
        m = re.match(r"^## (.*)$", line)
        if m:
            cur = [m.group(1).strip(), []]
            subs.append(cur)
        elif cur:
            cur[1].append(line)
        else:
            pre.append(line)
    return pre, subs

# Tier A: numbered question items
def parse_tier_a(lines):
    pre, subs = split_h2(lines)
    groups = []
    for title, sub_lines in subs:
        intro_lines = []
        questions = []
        for line in sub_lines:
            m = re.match(r"^(\d+)\.\s+\*\*(.+?)\*\*\s*(.*)$", line)
            if m:
                questions.append({
                    "num": int(m.group(1)),
                    "title": m.group(2).rstrip(),
                    "body": m.group(3).strip(),
                })
            elif line.strip() and not questions:
                intro_lines.append(line)
        groups.append({"title": title, "intro": blocks_to_html(intro_lines) if intro_lines else "",
                       "questions": questions})
    return blocks_to_html(pre), groups

TIER_A_PRE, TIER_A_GROUPS = parse_tier_a(TOP[find_key("TIER A")])
TOTAL_A = sum(len(g["questions"]) for g in TIER_A_GROUPS)

def tier_generic(key):
    pre, subs = split_h2(TOP[find_key(key)])
    return blocks_to_html(pre), [(t, blocks_to_html(ls)) for t, ls in subs]

TIER_B_PRE, TIER_B_SUBS = tier_generic("TIER B")
TIER_C_PRE, TIER_C_SUBS = tier_generic("TIER C")

# ---- difficulty badges on Tier B list items (matched by title substring) ----
def plain(fragment):
    return html.unescape(re.sub(r"<[^>]+>", "", fragment))

ITEM_KEYS = [(k, s) for k, s in DIFF["items"]]
PROMPT_KEYS_C = dict(PROMPTS["itemsC"])

def ask_details(prompt):
    return ('<details class="ask-inline"><summary>Full question</summary>'
            f'<p>{html.escape(prompt, quote=False)}</p></details>')

def inject_before_close(chunk, insertion):
    """Insert HTML just before this <li>'s closing tag (first </li> in the chunk)."""
    pos = chunk.find("</li>")
    if pos == -1:
        return chunk + insertion
    return chunk[:pos] + insertion + chunk[pos:]

def badge_items(html_text):
    """Insert difficulty pills, data-diff, and full-question panels on matched <li>."""
    chunks = re.split(r"(<li>)", html_text)
    for idx in range(len(chunks)):
        if chunks[idx] != "<li>" or idx + 1 >= len(chunks):
            continue
        text = plain(chunks[idx + 1][:300]).strip().lstrip("\"'“”‘’")
        for pos, (key, score) in enumerate(ITEM_KEYS):
            if text.startswith(key):
                tip = html.escape(f"Difficulty {score}/5 — {SCALE[str(score)]}", quote=True)
                chunks[idx] = f'<li data-diff="{score}">'
                chunk = (f'<span class="diff d{score}" title="{tip}" '
                         f'aria-label="Difficulty {score} of 5">{score}</span>'
                         + chunks[idx + 1])
                prompt = PROMPTS["items"].get(key)
                if prompt:
                    chunk = inject_before_close(chunk, ask_details(prompt))
                chunks[idx + 1] = chunk
                ITEM_KEYS.pop(pos)
                break
    return "".join(chunks)

def ask_items_c(html_text):
    """Insert full-question panels on Tier C <li> matched by prompt key."""
    chunks = re.split(r"(<li>)", html_text)
    unused = dict(PROMPT_KEYS_C)
    for idx in range(len(chunks)):
        if chunks[idx] != "<li>" or idx + 1 >= len(chunks):
            continue
        text = plain(chunks[idx + 1][:300]).strip().lstrip("\"'“”‘’")
        for key in list(unused):
            if text.startswith(key):
                chunks[idx + 1] = inject_before_close(chunks[idx + 1], ask_details(unused.pop(key)))
                PROMPT_KEYS_C.pop(key, None)
                break
    return "".join(chunks)

TIER_B_SUBS = [(t, badge_items(b)) for t, b in TIER_B_SUBS]
# Tier C: every item is a screener — difficulty 1 by design (filterable, no pill noise)
TIER_C_SUBS = [(t, ask_items_c(b).replace("<li>", '<li data-diff="1">')) for t, b in TIER_C_SUBS]
TIER_D_PRE, TIER_D_SUBS = tier_generic("TIER D")
APP_PRE, APP_SUBS = tier_generic("APPENDIX")

# Tier D bank section has no ## subsections — body is in pre
INTRO_PRE, INTRO_SUBS = tier_generic("Interview Question Bank")

# ------------------------------------------------------------- counts
def count_items(html_text):
    return len(re.findall(r"<li>", html_text))

TOTAL_B = sum(count_items(h) for _, h in TIER_B_SUBS)
TOTAL_C = sum(count_items(h) for _, h in TIER_C_SUBS)
TOTAL_D = count_items(TIER_D_PRE) + sum(count_items(h) for _, h in TIER_D_SUBS)

# ------------------------------------------------------------- render page
def anchor(s):
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")

def qcard(q, group_title):
    sol = SOL_NUM.get(q["num"])
    sol_html = ""
    if sol:
        sol_html = f"""
      <details class="solution">
        <summary><span class="sol-icon" aria-hidden="true"></span>Reference solution</summary>
        <div class="sol-body">{sol}</div>
      </details>"""
    body = f'<p class="q-body">{inline(q["body"])}</p>' if q["body"] else ""
    ask = (f'<div class="ask"><span class="ask-label">Ask the candidate</span>'
           f'<p>{html.escape(PROMPTS_A[q["num"]], quote=False)}</p></div>')
    score, rationale = DIFF_A[q["num"]]
    return f"""
    <article class="card" id="q{q['num']}" data-search data-diff="{score}">
      <div class="card-head">
        <a class="qnum" href="#q{q['num']}" title="Link to question {q['num']}">{q['num']}</a>
        <h4 class="q-title">{inline(q['title'])}</h4>
        {dots(score, rationale)}
      </div>
      {body}{ask}{sol_html}
    </article>"""

def tier_a_html():
    parts = []
    for g in TIER_A_GROUPS:
        gid = anchor(g["title"].split("·")[0].strip())
        label = g["title"]
        parts.append(f'<section class="group" id="{gid}">')
        parts.append(f'<h3 class="group-title">{inline(label)}</h3>')
        if g["intro"]:
            parts.append(f'<div class="group-intro">{g["intro"]}</div>')
        note_key = g["title"].split(" ")[0]
        for q in g["questions"]:
            parts.append(qcard(q, g["title"]))
        if note_key in SOL_A_NOTES:
            parts.append(f"""
      <details class="solution keynote" data-search>
        <summary><span class="sol-icon" aria-hidden="true"></span>Interviewer key — what to look for</summary>
        <div class="sol-body">{SOL_A_NOTES[note_key]}</div>
      </details>""")
        parts.append("</section>")
    return "\n".join(parts)

def subs_html(subs, key_sections=None, key_title="Answer keys"):
    parts = []
    for title, body in subs:
        sid = anchor(title)
        parts.append(f"""
    <section class="group" id="{sid}">
      <h3 class="group-title">{inline(title)}</h3>
      <div class="prose" data-search>{body}</div>
    </section>""")
    if key_sections:
        blocks = []
        for t, b in key_sections:
            heading = f"<h4>{inline(t)}</h4>" if t else ""
            blocks.append(f"{heading}{b}")
        parts.append(f"""
    <details class="solution keynote big" data-search>
      <summary><span class="sol-icon" aria-hidden="true"></span>{key_title}</summary>
      <div class="sol-body">{''.join(blocks)}</div>
    </details>""")
    return "\n".join(parts)

def sub_links(groups):
    links = []
    for g in groups:
        code = g["title"].split("·")[0].strip()
        label = g["title"].split("·")[1].strip() if "·" in g["title"] else code
        links.append(f'<a href="#{anchor(code)}">{inline(code)} <span>{inline(label)}</span></a>')
    return "\n".join(links)

INTRO_HTML = "\n".join(
    f'<div class="intro-block"><h3>{inline(t)}</h3><div class="prose">{b}</div></div>'
    for t, b in INTRO_SUBS if not t.startswith("Contents")
)

page = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Interview Question Bank — curated &amp; quality-ranked</title>
<meta name="description" content="A curated, quality-ranked bank of technical and behavioral interview questions for systems, networking, ML, infrastructure, and AI/LLM engineering roles — with reference solutions and interviewer keys.">
<style>
:root {{
  --bg: #f7f8f7; --bg-card: #ffffff; --bg-inset: #eef1ee;
  --fg: #1a1f1a; --fg-soft: #4c554c; --fg-faint: #7a837a;
  --line: #dde3dd; --accent: #4d8f00; --accent-soft: #e8f3d9;
  --tier-a: #4d8f00; --tier-b: #0b6bcb; --tier-c: #b26a00; --tier-d: #c0392b;
  --sol-bg: #f2f7ea; --sol-line: #cfe3ad;
  --code-bg: #eef1ee; --shadow: 0 1px 2px rgba(20,30,20,.06), 0 4px 16px rgba(20,30,20,.05);
  --mono: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
}}
html[data-theme="dark"] {{
  --bg: #101410; --bg-card: #181d18; --bg-inset: #1f261f;
  --fg: #e8ece6; --fg-soft: #b4bdb0; --fg-faint: #7d867a;
  --line: #2a322a; --accent: #8fd436; --accent-soft: #24310f;
  --tier-a: #8fd436; --tier-b: #6cb2ff; --tier-c: #ffb85c; --tier-d: #ff7b6b;
  --sol-bg: #171f0f; --sol-line: #354b17;
  --code-bg: #10160e; --shadow: 0 1px 2px rgba(0,0,0,.4), 0 6px 20px rgba(0,0,0,.3);
}}
* {{ box-sizing: border-box; }}
html {{ scroll-behavior: smooth; scroll-padding-top: 84px; }}
body {{
  margin: 0; background: var(--bg); color: var(--fg);
  font: 16px/1.65 -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
  -webkit-font-smoothing: antialiased; text-rendering: optimizeLegibility;
}}
a {{ color: var(--accent); text-decoration: none; }}
a:hover {{ text-decoration: underline; }}
code {{ font-family: var(--mono); font-size: .86em; background: var(--code-bg); border: 1px solid var(--line); border-radius: 5px; padding: .08em .35em; }}
pre {{ background: var(--code-bg); border: 1px solid var(--line); border-radius: 10px; padding: 14px 16px; overflow-x: auto; }}
pre code {{ background: none; border: 0; padding: 0; font-size: .84em; line-height: 1.55; }}

/* ---------- header ---------- */
.topbar {{
  position: sticky; top: 0; z-index: 50; backdrop-filter: blur(12px);
  background: color-mix(in srgb, var(--bg) 82%, transparent);
  border-bottom: 1px solid var(--line);
}}
.topbar-in {{ max-width: 1200px; margin: 0 auto; padding: 10px 20px; display: flex; align-items: center; gap: 14px; }}
.brand {{ font-weight: 750; letter-spacing: -.02em; white-space: nowrap; color: var(--fg); }}
.brand:hover {{ text-decoration: none; }}
.brand .dot {{ color: var(--accent); }}
.searchwrap {{ flex: 1; max-width: 460px; margin-left: auto; position: relative; }}
.searchwrap svg {{ position: absolute; left: 11px; top: 50%; transform: translateY(-50%); width: 15px; height: 15px; stroke: var(--fg-faint); fill: none; stroke-width: 2; pointer-events: none; }}
#search {{
  width: 100%; padding: 8px 34px 8px 34px; border-radius: 999px; border: 1px solid var(--line);
  background: var(--bg-card); color: var(--fg); font: inherit; font-size: 14px; outline: none;
}}
#search:focus {{ border-color: var(--accent); box-shadow: 0 0 0 3px color-mix(in srgb, var(--accent) 22%, transparent); }}
#search-count {{ position: absolute; right: 12px; top: 50%; transform: translateY(-50%); font-size: 12px; color: var(--fg-faint); }}
.iconbtn {{
  border: 1px solid var(--line); background: var(--bg-card); color: var(--fg-soft); border-radius: 999px;
  width: 36px; height: 36px; cursor: pointer; display: grid; place-items: center; flex: none;
}}
.iconbtn:hover {{ border-color: var(--accent); color: var(--accent); }}
.iconbtn svg {{ width: 17px; height: 17px; fill: none; stroke: currentColor; stroke-width: 1.8; stroke-linecap: round; stroke-linejoin: round; }}
html[data-theme="dark"] .sun {{ display: block; }} html[data-theme="dark"] .moon {{ display: none; }}
html:not([data-theme="dark"]) .sun {{ display: none; }} html:not([data-theme="dark"]) .moon {{ display: block; }}

/* ---------- tier nav ---------- */
.tiernav {{ display: flex; gap: 8px; overflow-x: auto; max-width: 1200px; margin: 0 auto; padding: 0 20px 10px; scrollbar-width: none; }}
.tiernav::-webkit-scrollbar {{ display: none; }}
.tiernav a {{
  flex: none; font-size: 13px; font-weight: 600; padding: 5px 13px; border-radius: 999px;
  border: 1px solid var(--line); color: var(--fg-soft); background: var(--bg-card);
}}
.tiernav a:hover {{ text-decoration: none; border-color: var(--accent); color: var(--accent); }}
.tiernav a b {{ font-weight: 750; }}

/* ---------- hero ---------- */
.hero {{ max-width: 1200px; margin: 0 auto; padding: 56px 20px 8px; }}
.hero h1 {{ font-size: clamp(30px, 5vw, 46px); line-height: 1.12; letter-spacing: -.03em; margin: 0 0 14px; font-weight: 800; }}
.hero h1 em {{ font-style: normal; color: var(--accent); }}
.hero .lede {{ max-width: 62ch; color: var(--fg-soft); font-size: 17.5px; margin: 0 0 26px; }}
.stats {{ display: flex; flex-wrap: wrap; gap: 12px; margin: 0 0 8px; }}
.stat {{
  background: var(--bg-card); border: 1px solid var(--line); border-radius: 14px;
  padding: 12px 18px; box-shadow: var(--shadow); min-width: 128px;
}}
.stat b {{ display: block; font-size: 26px; letter-spacing: -.02em; }}
.stat span {{ font-size: 12.5px; color: var(--fg-faint); text-transform: uppercase; letter-spacing: .06em; font-weight: 600; }}
.stat[data-tier="A"] b {{ color: var(--tier-a); }} .stat[data-tier="B"] b {{ color: var(--tier-b); }}
.stat[data-tier="C"] b {{ color: var(--tier-c); }} .stat[data-tier="D"] b {{ color: var(--tier-d); }}

/* ---------- layout ---------- */
.wrap {{ max-width: 1200px; margin: 0 auto; padding: 12px 20px 80px; display: grid; grid-template-columns: 230px minmax(0,1fr); gap: 44px; }}
@media (max-width: 900px) {{ .wrap {{ grid-template-columns: 1fr; gap: 0; }} .sidebar {{ display: none; }} }}
.sidebar {{ position: sticky; top: 88px; align-self: start; max-height: calc(100vh - 110px); overflow-y: auto; font-size: 13.5px; padding-right: 6px; }}
.sidebar h5 {{ margin: 18px 0 6px; font-size: 11px; text-transform: uppercase; letter-spacing: .09em; color: var(--fg-faint); }}
.sidebar a {{ display: block; padding: 4px 10px; border-left: 2px solid var(--line); color: var(--fg-soft); border-radius: 0 6px 6px 0; }}
.sidebar a span {{ color: var(--fg-faint); font-weight: 400; }}
.sidebar a:hover {{ text-decoration: none; color: var(--accent); border-left-color: var(--accent); background: var(--accent-soft); }}

/* ---------- sections ---------- */
.tier {{ margin-top: 44px; }}
.tier-head {{ display: flex; align-items: baseline; gap: 14px; flex-wrap: wrap; margin-bottom: 6px; }}
.tier-badge {{
  font-weight: 800; font-size: 15px; letter-spacing: .02em; color: #fff; border-radius: 9px; padding: 3px 12px;
}}
#tier-a .tier-badge {{ background: var(--tier-a); }} #tier-b .tier-badge {{ background: var(--tier-b); }}
#tier-c .tier-badge {{ background: var(--tier-c); }} #tier-d .tier-badge {{ background: var(--tier-d); }}
html[data-theme="dark"] .tier-badge {{ color: #0d120d; }}
.tier h2 {{ font-size: 26px; letter-spacing: -.02em; margin: 0; font-weight: 750; }}
.tier-pre {{ color: var(--fg-soft); max-width: 72ch; }}
.group {{ margin-top: 30px; }}
.group-title {{ font-size: 19px; letter-spacing: -.01em; margin: 0 0 4px; font-weight: 700; }}
.group-intro {{ color: var(--fg-soft); font-size: 14.5px; max-width: 72ch; margin-bottom: 10px; }}

/* ---------- cards ---------- */
.card {{
  background: var(--bg-card); border: 1px solid var(--line); border-radius: 14px;
  padding: 16px 18px 14px; margin: 12px 0; box-shadow: var(--shadow);
  transition: border-color .15s ease;
}}
.card:target {{ border-color: var(--accent); box-shadow: 0 0 0 3px color-mix(in srgb, var(--accent) 25%, transparent); }}
.card-head {{ display: flex; gap: 12px; align-items: baseline; }}
.qnum {{
  flex: none; font-family: var(--mono); font-weight: 700; font-size: 13px; color: var(--accent);
  background: var(--accent-soft); border-radius: 8px; padding: 2px 9px; margin-top: 2px;
}}
.qnum:hover {{ text-decoration: none; outline: 1px solid var(--accent); }}
.q-title {{ margin: 0; font-size: 16.5px; font-weight: 700; letter-spacing: -.01em; line-height: 1.45; }}
.q-body {{ margin: 8px 0 4px; color: var(--fg-soft); font-size: 14.8px; }}

/* ---------- solutions ---------- */
details.solution {{ margin-top: 10px; border: 1px solid var(--sol-line); border-radius: 10px; background: var(--sol-bg); overflow: hidden; }}
details.solution summary {{
  cursor: pointer; list-style: none; padding: 9px 14px; font-weight: 650; font-size: 13.5px;
  color: var(--accent); display: flex; align-items: center; gap: 9px; user-select: none;
}}
details.solution summary::-webkit-details-marker {{ display: none; }}
.sol-icon {{ width: 8px; height: 8px; border-right: 2px solid currentColor; border-bottom: 2px solid currentColor; transform: rotate(-45deg); transition: transform .18s ease; margin-top: -2px; }}
details[open] > summary .sol-icon {{ transform: rotate(45deg); margin-top: -5px; }}
.sol-body {{ padding: 2px 16px 12px; font-size: 14.6px; border-top: 1px dashed var(--sol-line); }}
.sol-body > :first-child {{ margin-top: 10px; }}
details.keynote {{ margin: 16px 0; }}
details.keynote.big .sol-body {{ font-size: 14.4px; }}

/* ---------- prose ---------- */
.prose {{ font-size: 15px; }}
.prose ul, .sol-body ul {{ padding-left: 22px; margin: 8px 0; }}
.prose li, .sol-body li {{ margin: 5px 0; }}
.prose li li {{ color: var(--fg-soft); }}
.prose p, .sol-body p {{ margin: 10px 0; }}
.prose h4, .sol-body h4 {{ margin: 20px 0 6px; font-size: 15.5px; }}
.intro-block {{ background: var(--bg-card); border: 1px solid var(--line); border-radius: 14px; padding: 6px 22px 12px; margin: 14px 0; box-shadow: var(--shadow); }}
.intro-block h3 {{ font-size: 17px; margin: 14px 0 2px; }}
.intro-block .prose {{ color: var(--fg-soft); font-size: 14.6px; }}

/* ---------- full-form questions ---------- */
.ask {{
  margin: 12px 0 4px; padding: 10px 16px 12px; border-left: 3px solid var(--accent);
  background: color-mix(in srgb, var(--accent) 6%, transparent); border-radius: 0 10px 10px 0;
}}
.ask-label {{
  display: block; font-size: 10.5px; font-weight: 800; text-transform: uppercase;
  letter-spacing: .1em; color: var(--accent); margin-bottom: 4px;
}}
.ask p {{ margin: 0; font-size: 14.6px; line-height: 1.62; }}
details.ask-inline {{ display: block; margin-top: 6px; }}
details.ask-inline summary {{
  cursor: pointer; list-style: none; display: inline-flex; align-items: center; gap: 6px;
  font-size: 12.5px; font-weight: 650; color: var(--accent); user-select: none;
}}
details.ask-inline summary::-webkit-details-marker {{ display: none; }}
details.ask-inline summary::before {{
  content: ""; width: 6px; height: 6px; border-right: 2px solid currentColor;
  border-bottom: 2px solid currentColor; transform: rotate(-45deg); transition: transform .15s ease;
}}
details.ask-inline[open] summary::before {{ transform: rotate(45deg); }}
details.ask-inline p {{
  margin: 6px 0 2px; padding: 8px 14px; border-left: 3px solid var(--accent);
  background: color-mix(in srgb, var(--accent) 6%, transparent); border-radius: 0 8px 8px 0;
  font-size: 13.8px; color: var(--fg);
}}

/* ---------- difficulty ---------- */
.dots {{ display: inline-flex; gap: 3px; align-items: center; margin-left: auto; padding: 4px 2px 0 10px; flex: none; cursor: help; }}
.dots i {{ width: 7px; height: 7px; border-radius: 50%; background: var(--line); }}
.dots.d1 i.on, .dots.d2 i.on {{ background: var(--tier-a); }}
.dots.d3 i.on {{ background: var(--tier-c); }}
.dots.d4 i.on, .dots.d5 i.on {{ background: var(--tier-d); }}
span.diff {{
  display: inline-grid; place-items: center; width: 17px; height: 17px; border-radius: 5px;
  font-size: 11px; font-weight: 750; margin-right: 7px; vertical-align: 1px; cursor: help;
  font-family: var(--mono);
}}
span.diff.d1, span.diff.d2 {{ background: color-mix(in srgb, var(--tier-a) 16%, transparent); color: var(--tier-a); }}
span.diff.d3 {{ background: color-mix(in srgb, var(--tier-c) 16%, transparent); color: var(--tier-c); }}
span.diff.d4, span.diff.d5 {{ background: color-mix(in srgb, var(--tier-d) 16%, transparent); color: var(--tier-d); }}
.difffilter {{ display: flex; gap: 6px; align-items: center; flex-wrap: wrap; }}
.difflabel {{ font-size: 12px; font-weight: 700; text-transform: uppercase; letter-spacing: .07em; color: var(--fg-faint); margin-right: 2px; }}
.dchip {{
  font: inherit; font-size: 13px; font-weight: 700; width: 32px; height: 28px; border-radius: 8px;
  border: 1px solid var(--line); background: var(--bg-card); color: var(--fg-soft); cursor: pointer;
}}
.dchip:hover {{ border-color: var(--accent); color: var(--accent); }}
.dchip[aria-pressed="true"] {{ background: var(--accent); border-color: var(--accent); color: #fff; }}
html[data-theme="dark"] .dchip[aria-pressed="true"] {{ color: #0d120d; }}
.diff-legend {{ font-size: 12.5px; color: var(--fg-faint); margin: 6px 0 0; }}

/* ---------- controls / misc ---------- */
.controls {{ display: flex; gap: 10px; margin: 22px 0 -6px; }}
.controls button {{
  font: inherit; font-size: 13px; font-weight: 600; padding: 6px 14px; border-radius: 999px;
  border: 1px solid var(--line); background: var(--bg-card); color: var(--fg-soft); cursor: pointer;
}}
.controls button:hover {{ border-color: var(--accent); color: var(--accent); }}
.no-results {{ display: none; text-align: center; color: var(--fg-faint); padding: 60px 0; font-size: 15px; }}
mark {{ background: color-mix(in srgb, var(--accent) 30%, transparent); color: inherit; border-radius: 3px; padding: 0 1px; }}
.search-hidden {{ display: none !important; }}
footer {{ border-top: 1px solid var(--line); color: var(--fg-faint); font-size: 13px; }}
footer .in {{ max-width: 1200px; margin: 0 auto; padding: 26px 20px; display: flex; gap: 14px; flex-wrap: wrap; justify-content: space-between; }}
.totop {{ position: fixed; right: 22px; bottom: 22px; opacity: 0; pointer-events: none; transition: opacity .2s ease; z-index: 40; }}
.totop.show {{ opacity: 1; pointer-events: auto; }}
@media print {{
  .topbar, .sidebar, .controls, .totop {{ display: none !important; }}
  details.solution {{ border: 1px solid #bbb; }}
  details.solution:not([open]) .sol-body {{ display: block; }}
  .card {{ break-inside: avoid; box-shadow: none; }}
  .wrap {{ display: block; }}
}}
</style>
</head>
<body>
<header class="topbar">
  <div class="topbar-in">
    <a class="brand" href="#top">Interview Question Bank<span class="dot">.</span></a>
    <div class="searchwrap">
      <svg viewBox="0 0 24 24"><circle cx="11" cy="11" r="7"/><path d="m20 20-3.8-3.8"/></svg>
      <input id="search" type="search" placeholder="Search questions, topics, solutions…  ( / )" autocomplete="off">
      <span id="search-count"></span>
    </div>
    <button class="iconbtn" id="theme-toggle" title="Toggle theme" aria-label="Toggle color theme">
      <svg class="moon" viewBox="0 0 24 24"><path d="M21 12.8A9 9 0 1 1 11.2 3 7 7 0 0 0 21 12.8z"/></svg>
      <svg class="sun" viewBox="0 0 24 24"><circle cx="12" cy="12" r="4"/><path d="M12 2v2m0 16v2M4.9 4.9l1.4 1.4m11.4 11.4 1.4 1.4M2 12h2m16 0h2M4.9 19.1l1.4-1.4m11.4-11.4 1.4-1.4"/></svg>
    </button>
  </div>
  <nav class="tiernav">
    <a href="#tier-a"><b>Tier A</b> · Centerpieces</a>
    <a href="#tier-b"><b>Tier B</b> · Supporting</a>
    <a href="#tier-c"><b>Tier C</b> · Screeners</a>
    <a href="#tier-d"><b>Tier D</b> · Avoid</a>
    <a href="#appendix"><b>Appendix</b> · Running interviews</a>
  </nav>
</header>

<main id="top">
  <section class="hero">
    <h1>Better interviews start with <em>better questions</em>.</h1>
    <p class="lede">A curated, quality-ranked set of technical and behavioral interview questions for systems, networking, ML, infrastructure, and AI/LLM engineering roles — every question placed in a quality tier, ordered best-first, with reference solutions and interviewer keys built in.</p>
    <div class="stats">
      <div class="stat" data-tier="A"><b>{TOTAL_A}</b><span>Tier-A centerpieces</span></div>
      <div class="stat" data-tier="B"><b>{TOTAL_B}+</b><span>Tier-B supporting</span></div>
      <div class="stat" data-tier="C"><b>{TOTAL_C}+</b><span>Tier-C screeners</span></div>
      <div class="stat" data-tier="D"><b>{TOTAL_D}</b><span>Tier-D traps to avoid</span></div>
    </div>
  </section>

  <div class="wrap">
    <aside class="sidebar">
      <h5>Orientation</h5>
      <a href="#guide">How to use this bank</a>
      <h5>Tier A — Centerpieces</h5>
      {sub_links(TIER_A_GROUPS)}
      <h5>Tier B — Supporting</h5>
      {"".join(f'<a href="#{anchor(t)}">{inline(t.split("·")[0].strip())} <span>{inline(t.split("·")[1].strip() if "·" in t else "")}</span></a>' for t, _ in TIER_B_SUBS)}
      <h5>Tier C — Screeners</h5>
      {"".join(f'<a href="#{anchor(t)}">{inline(t.split("·")[0].strip())} <span>{inline(t.split("·")[1].strip() if "·" in t else "")}</span></a>' for t, _ in TIER_C_SUBS)}
      <h5>Tier D</h5>
      <a href="#tier-d">Avoid (with reasons)</a>
      <h5>Appendix</h5>
      {"".join(f'<a href="#{anchor(t)}">{inline(t)}</a>' for t, _ in APP_SUBS)}
    </aside>

    <div class="content">
      <section id="guide" class="tier" style="margin-top:8px">
        {INTRO_HTML}
      </section>

      <div class="controls" style="flex-wrap:wrap; align-items:center; gap:16px">
        <div class="difffilter" role="group" aria-label="Filter by difficulty">
          <span class="difflabel">Difficulty</span>
          <button class="dchip" data-d="1" aria-pressed="false" title="{html.escape(SCALE['1'])}">1</button>
          <button class="dchip" data-d="2" aria-pressed="false" title="{html.escape(SCALE['2'])}">2</button>
          <button class="dchip" data-d="3" aria-pressed="false" title="{html.escape(SCALE['3'])}">3</button>
          <button class="dchip" data-d="4" aria-pressed="false" title="{html.escape(SCALE['4'])}">4</button>
          <button class="dchip" data-d="5" aria-pressed="false" title="{html.escape(SCALE['5'])}">5</button>
        </div>
        <button id="expand-all">Expand all solutions</button>
        <button id="collapse-all">Collapse all</button>
      </div>
      <p class="diff-legend">Difficulty is scored 1–5 per question (1 = warm-up · 3 = solid mid-level · 5 = expert-discriminating) and is independent of the tier — tiers rank <em>quality</em>. Hover any badge for the rationale. Tier-C screeners are all difficulty 1 by design.</p>

      <section class="tier" id="tier-a">
        <div class="tier-head"><span class="tier-badge">TIER A</span><h2>Centerpieces</h2></div>
        <div class="tier-pre prose" data-search>{TIER_A_PRE}</div>
        {tier_a_html()}
      </section>

      <section class="tier" id="tier-b">
        <div class="tier-head"><span class="tier-badge">TIER B</span><h2>Supporting questions</h2></div>
        <div class="tier-pre prose" data-search>{TIER_B_PRE}</div>
        {subs_html(TIER_B_SUBS, SOL_SECTIONS.get("TIER B"), "Tier B answer keys")}
      </section>

      <section class="tier" id="tier-c">
        <div class="tier-head"><span class="tier-badge">TIER C</span><h2>Screeners &amp; warm-ups</h2></div>
        <div class="tier-pre prose" data-search>{TIER_C_PRE}</div>
        {subs_html(TIER_C_SUBS, SOL_SECTIONS.get("TIER C"), "Tier C answer notes")}
      </section>

      <section class="tier" id="tier-d">
        <div class="tier-head"><span class="tier-badge">TIER D</span><h2>Avoid — with reasons</h2></div>
        <div class="tier-pre prose" data-search>{TIER_D_PRE}</div>
        {subs_html(TIER_D_SUBS, SOL_SECTIONS.get("TIER D — verified outputs (for the code-reading gotchas you should *avoid* posing, but should recognize)") or next((v for k, v in SOL_SECTIONS.items() if k.startswith("TIER D")), None), "Tier D — verified outputs (recognize, don't pose)")}
      </section>

      <section class="tier" id="appendix">
        <div class="tier-head"><span class="tier-badge" style="background:var(--fg-soft)">APPENDIX</span><h2>Running interviews</h2></div>
        <div class="tier-pre prose" data-search>{APP_PRE}</div>
        {subs_html(APP_SUBS)}
      </section>

      <p class="no-results" id="no-results">No matches — try fewer or different words.</p>
    </div>
  </div>
</main>

<footer>
  <div class="in">
    <span>Interview Question Bank — curated, quality-ranked, with reference solutions.</span>
    <span>Tiers rank quality, not difficulty · numbering is shared between questions and solutions.</span>
  </div>
</footer>

<button class="iconbtn totop" id="totop" title="Back to top" aria-label="Back to top">
  <svg viewBox="0 0 24 24"><path d="m5 14 7-7 7 7"/></svg>
</button>

<script>
(function () {{
  // ---------- theme ----------
  const root = document.documentElement;
  const stored = localStorage.getItem('iqb-theme');
  const preferDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
  root.dataset.theme = stored || (preferDark ? 'dark' : 'light');
  document.getElementById('theme-toggle').addEventListener('click', () => {{
    root.dataset.theme = root.dataset.theme === 'dark' ? 'light' : 'dark';
    localStorage.setItem('iqb-theme', root.dataset.theme);
  }});

  // ---------- expand / collapse ----------
  const allDetails = () => document.querySelectorAll('details.solution');
  document.getElementById('expand-all').addEventListener('click', () => allDetails().forEach(d => d.open = true));
  document.getElementById('collapse-all').addEventListener('click', () => allDetails().forEach(d => d.open = false));

  // open a solution when deep-linking to its question
  function openTarget() {{
    const el = document.querySelector(location.hash ? location.hash : null);
    if (el) el.querySelectorAll('details').forEach(d => d.open = true);
  }}
  window.addEventListener('hashchange', openTarget);
  if (location.hash) setTimeout(openTarget, 60);

  // ---------- search ----------
  const input = document.getElementById('search');
  const countEl = document.getElementById('search-count');
  const noResults = document.getElementById('no-results');
  const units = Array.from(document.querySelectorAll('.card, .prose[data-search] > ul > li, details.keynote'));
  units.forEach(u => u.dataset.text = u.textContent.toLowerCase());
  const sections = Array.from(document.querySelectorAll('.tier, .group'));

  const diffSel = new Set();
  const chips = Array.from(document.querySelectorAll('.dchip'));
  chips.forEach(c => c.addEventListener('click', () => {{
    const d = c.dataset.d;
    diffSel.has(d) ? diffSel.delete(d) : diffSel.add(d);
    c.setAttribute('aria-pressed', diffSel.has(d));
    applyFilters();
  }}));

  function diffOk(u) {{
    if (!diffSel.size) return true;
    if (u.dataset.diff && diffSel.has(u.dataset.diff)) return true;
    // a group item (e.g. the "famous / one-trick" list) passes if a child matches
    return Array.from(u.querySelectorAll('[data-diff]')).some(el => diffSel.has(el.dataset.diff));
  }}

  function applyFilters() {{
    const q = input.value.trim().toLowerCase();
    const terms = q.split(/\\s+/).filter(Boolean);
    const active = terms.length > 0 || diffSel.size > 0;
    let shown = 0;
    units.forEach(u => {{
      const hit = (!terms.length || terms.every(t => u.dataset.text.includes(t))) && diffOk(u);
      u.classList.toggle('search-hidden', !hit);
      if (hit && active) shown++;
    }});
    // hide empty groups/sections while filtering
    sections.forEach(s => {{
      if (!active) {{ s.classList.remove('search-hidden'); return; }}
      const any = s.querySelector('.card:not(.search-hidden), .prose[data-search] > ul > li:not(.search-hidden), details.keynote:not(.search-hidden)');
      s.classList.toggle('search-hidden', !any);
    }});
    document.querySelectorAll('.tier-pre, .group-intro, .intro-block, .diff-legend').forEach(el =>
      el.classList.toggle('search-hidden', active));
    countEl.textContent = active ? shown + ' hit' + (shown === 1 ? '' : 's') : '';
    noResults.style.display = active && !shown ? 'block' : 'none';
  }}
  let t;
  input.addEventListener('input', () => {{ clearTimeout(t); t = setTimeout(applyFilters, 90); }});
  document.addEventListener('keydown', e => {{
    if (e.key === '/' && document.activeElement !== input) {{ e.preventDefault(); input.focus(); }}
    if (e.key === 'Escape' && document.activeElement === input) {{ input.value = ''; applyFilters(); input.blur(); }}
  }});

  // ---------- back to top ----------
  const totop = document.getElementById('totop');
  addEventListener('scroll', () => totop.classList.toggle('show', scrollY > 900), {{ passive: true }});
  totop.addEventListener('click', () => scrollTo({{ top: 0, behavior: 'smooth' }}));
}})();
</script>
</body>
</html>
"""

OUT.write_text(page)
missing = [n for n in range(1, TOTAL_A + 1) if n not in SOL_NUM]
print(f"Wrote {OUT} ({len(page)/1024:.0f} KB)")
print(f"Tier A questions: {TOTAL_A}; solutions matched: {len([n for n in range(1, TOTAL_A+1) if n in SOL_NUM])}")
print(f"No per-question solution (expected for behavioral 50-63): {missing}")
print(f"Solution sections captured: {[(k, len(v)) for k, v in SOL_SECTIONS.items()]}")
print(f"A-section notes: {list(SOL_A_NOTES.keys())}")
print(f"Unmatched difficulty keys ({len(ITEM_KEYS)}): {[k for k, _ in ITEM_KEYS]}")
print(f"Unmatched C prompt keys ({len(PROMPT_KEYS_C)}): {list(PROMPT_KEYS_C)}")
b_prompts_used = len(PROMPTS['items'])
print(f"A prompts: {len(PROMPTS_A)}; B item prompts: {b_prompts_used}; C prompts: {len(PROMPTS['itemsC'])}")
