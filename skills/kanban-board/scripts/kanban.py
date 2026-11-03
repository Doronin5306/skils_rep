#!/usr/bin/env python3
"""Строит канбан-доску из tasks.md или ROADMAP.md.

Использование:
  kanban.py [ПЛАН] [--out-dir DIR] [--check]

  ПЛАН       путь к tasks.md / ROADMAP.md; по умолчанию ищется в текущей папке
             (tasks.md, ROADMAP.md, docs/tasks.md, docs/ROADMAP.md)
  --out-dir  куда писать KANBAN.md и KANBAN.html (по умолчанию — рядом с планом)
  --check    ничего не писать; код 1, если доска устарела или правилась вручную

Форматы плана:
  * tasks.md (формат agent-orchestrator): `## T1: Название` + `- status: …`,
    `- depends:`, `- priority:`, `- mr:`, `- branch:`; чек-лист критериев в теле.
  * любой другой markdown (ROADMAP.md): заголовки — эпики/разделы, пункты
    `- [ ]` / `- [x]` / `- [~]` — карточки. Статус также берётся из заголовка
    раздела (Done/Готово, In progress/В работе, Blocked…) и маркеров в тексте
    (✅ 🚧 ⛔ 🔍, [WIP], (в работе), [blocked], [review]).

Вывод детерминирован (без даты генерации) — повторный запуск без изменений плана
не меняет файлы, а --check годится для CI.
"""
import argparse
import html
import os
import re
import sys

COLUMNS = [
    ("backlog", "Бэклог"),
    ("ready", "К работе"),
    ("in-progress", "В работе"),
    ("testing", "Тестирование"),
    ("review", "Ревью (MR)"),
    ("done", "Готово"),
    ("blocked", "Заблокировано"),
]
STATUS_TO_COL = {
    "todo": "ready", "in-progress": "in-progress", "testing": "testing", "fixing": "testing",
    "review": "review", "done": "done", "blocked": "blocked",
}
CANDIDATES = ("tasks.md", "ROADMAP.md", "docs/tasks.md", "docs/ROADMAP.md", "roadmap.md", "TASKS.md")

# ---------- tasks.md ----------
T_HEAD = re.compile(r"^##\s+(T\d+)\s*[:.\-—]\s*(.+?)\s*$")
T_FIELD = re.compile(r"^-\s+(status|depends|branch|mr|priority):\s*(.*?)\s*$", re.I)
CHECK_RE = re.compile(r"^\s*[-*+]\s+\[([ xX~/\-])\]\s+")


def is_tasks_format(text):
    return bool(re.search(r"^##\s+T\d+\s*[:.\-—]", text, re.M)) and bool(re.search(r"^-\s+status:", text, re.M | re.I))


def parse_tasks(text):
    cards, cur = [], None
    for line in text.split("\n"):
        m = T_HEAD.match(line)
        if m:
            cur = {"id": m.group(1), "title": m.group(2), "status": "todo", "depends": [],
                   "priority": "", "mr": "", "branch": "", "epic": "", "done": 0, "total": 0}
            cards.append(cur)
            continue
        if line.startswith("# ") or line.startswith("## "):
            cur = None
            continue
        if cur is None:
            continue
        f = T_FIELD.match(line)
        if f:
            k, v = f.group(1).lower(), f.group(2)
            if k == "depends":
                cur["depends"] = re.findall(r"T\d+", v)
            elif k == "status":
                cur["status"] = v.lower() or "todo"
            else:
                cur[k] = v
            continue
        c = CHECK_RE.match(line)
        if c:
            cur["total"] += 1
            cur["done"] += c.group(1) in "xX"
    done_ids = {c["id"] for c in cards if c["status"] == "done"}
    for c in cards:
        col = STATUS_TO_COL.get(c["status"], "backlog")
        if col == "ready" and any(d not in done_ids for d in c["depends"]):
            col = "backlog"
        c["col"] = col
        c["fixing"] = c["status"] == "fixing"
        c["deps_state"] = [(d, d in done_ids) for d in c["depends"]]
    return cards


# ---------- ROADMAP.md ----------
HEADING_STATUS = [
    ("done", r"done|completed|finished|shipped|released|готово|сделано|выполнено|завершено"),
    ("in-progress", r"in[ -]?progress|doing|wip|current|now|в работе|в процессе|текущ"),
    ("testing", r"testing|qa|тестирован"),
    ("review", r"review|ревью"),
    ("blocked", r"blocked|on hold|заблокир|отложено"),
    ("todo", r"todo|to do|planned|next|backlog|later|future|ideas|план|бэклог|далее|потом|идеи"),
]
INLINE_STATUS = [
    ("done", r"✅|✔️|\[done\]|\(готово\)|\(done\)"),
    ("blocked", r"⛔|🚫|\[blocked\]|\(заблокировано\)|\(blocked\)"),
    ("review", r"🔍|\[review\]|\(ревью\)|\(review\)"),
    ("testing", r"🧪|\[testing\]|\(тестирование\)"),
    ("in-progress", r"🚧|⏳|\[wip\]|\[in progress\]|\(в работе\)|\(wip\)|\(in progress\)"),
]
BULLET_RE = re.compile(r"^([-*+]|\d+[.)])\s+(.*)$")
H_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*#*\s*$")
LINK_RE = re.compile(r"https?://\S+/(pull|merge_requests)/\d+")


def heading_status(text):
    t = text.lower()
    for st, pat in HEADING_STATUS:
        if re.search(pat, t):
            return st
    return None


def clean_title(t):
    for _, pat in INLINE_STATUS:
        t = re.sub(pat, "", t, flags=re.I)
    t = re.sub(r"\*\*|__", "", t)
    return re.sub(r"\s{2,}", " ", t).strip(" -—:")


def parse_roadmap(text):
    cards = []
    epic, sec_status = "", None
    stack = []  # (level, title, status)
    in_code = False
    plain_ok = True  # обычные пункты считаются задачами только сразу под статусным заголовком
    for raw in text.split("\n"):
        if raw.strip().startswith("```"):
            in_code = not in_code
            continue
        if in_code:
            continue
        h = H_RE.match(raw)
        if h:
            level, title = len(h.group(1)), h.group(2).strip()
            if level == 1:
                stack = []
                continue
            stack = [s for s in stack if s[0] < level]
            stack.append((level, title, heading_status(title)))
            sec_status = next((s[2] for s in reversed(stack) if s[2]), None)
            named = [s[1] for s in stack if not s[2]]
            epic = named[-1] if named else ""
            plain_ok = True
            continue
        indent = len(raw) - len(raw.lstrip(" \t"))
        line = raw.strip()
        b = BULLET_RE.match(line)
        if not b:
            if line and indent == 0:
                plain_ok = False  # абзац текста: дальше обычные пункты — не задачи
            continue
        body = b.group(2)
        cm = re.match(r"^\[([ xX~/\-])\]\s+(.*)$", body)
        if indent > 0:
            # подпункты — прогресс родительской карточки
            if cards and cm:
                cards[-1]["total"] += 1
                cards[-1]["done"] += cm.group(1) in "xX"
            continue
        if not cm and not (sec_status and plain_ok):
            continue  # обычный список вне статусного раздела — не задача
        mark, title = (cm.group(1), cm.group(2)) if cm else (None, body)
        status = sec_status or "todo"
        if mark in ("x", "X"):
            status = "done"
        elif mark in ("~", "/", "-"):
            status = "in-progress"
        for st, pat in INLINE_STATUS:
            if re.search(pat, title, re.I):
                status = st
                break
        mr = LINK_RE.search(title)
        if mr:
            title = re.sub(r"\(?\s*" + re.escape(mr.group(0)) + r"\s*\)?", "", title)
        mid = re.match(r"^(T\d+)\s*[:.\-—]?\s*(.*)$", clean_title(title))
        cards.append({
            "id": mid.group(1) if mid else "", "title": (mid.group(2) if mid else clean_title(title)),
            "status": status, "depends": [], "deps_state": [], "priority": "", "branch": "",
            "mr": mr.group(0) if mr else "", "epic": epic, "done": 0, "total": 0,
            "fixing": False,
        })
    for i, c in enumerate(cards, 1):
        if not c["id"]:
            c["id"] = "R%d" % i
        c["col"] = "backlog" if c["status"] == "todo" else STATUS_TO_COL.get(c["status"], "backlog")
    return cards


# ---------- render ----------
def md_link_title(c):
    t = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", c["title"])
    return t


def tag(text):
    return re.sub(r"[^\w-]+", "-", text.lower(), flags=re.U).strip("-") or "epic"


def render_md(cards, source):
    out = ["---", "", "kanban-plugin: basic", "", "---", ""]
    for key, name in COLUMNS:
        out.append("## " + name)
        out.append("")
        if key == "done":
            out.append("**Complete**")
        for c in [c for c in cards if c["col"] == key]:
            parts = ["**%s** %s" % (c["id"], md_link_title(c))]
            if c["priority"]:
                parts.append("#%s" % c["priority"])
            if c["epic"]:
                parts.append("#" + tag(c["epic"]))
            if c.get("fixing"):
                parts.append("#исправления")
            if c["total"]:
                parts.append("☑ %d/%d" % (c["done"], c["total"]))
            if c["deps_state"]:
                parts.append("⟵ " + ", ".join(d + ("✓" if ok else "") for d, ok in c["deps_state"]))
            if c["mr"]:
                parts.append("[MR](%s)" % c["mr"])
            out.append("- [%s] %s" % ("x" if key == "done" else " ", " ".join(parts)))
        out.append("")
        out.append("")
    out.append("%% Сгенерировано kanban.py из " + source + " — не редактируй вручную: файл перезаписывается. %%")
    out.append("")
    out.append("%% kanban:settings")
    out.append("```")
    out.append('{"kanban-plugin":"basic","show-checkboxes":false}')
    out.append("```")
    out.append("%%")
    return "\n".join(out) + "\n"


CSS = """
:root{--bg:#f6f7f9;--col:#eceef2;--card:#fff;--text:#1d2129;--muted:#667085;--border:#dde1e7;
--accent:#3b6fd8;--ok:#2f9e5b;--warn:#c98a12;--bad:#d14343;--chip:#eef1f6}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){--bg:#14161a;--col:#1c1f25;--card:#252932;
--text:#e6e8ec;--muted:#9aa3b2;--border:#323844;--accent:#6c9bff;--ok:#4cc27e;--warn:#e0a83a;--bad:#ef6b6b;--chip:#2d323d}}
:root[data-theme="dark"]{--bg:#14161a;--col:#1c1f25;--card:#252932;--text:#e6e8ec;--muted:#9aa3b2;
--border:#323844;--accent:#6c9bff;--ok:#4cc27e;--warn:#e0a83a;--bad:#ef6b6b;--chip:#2d323d}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--text);
font:14px/1.45 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif}
header{padding:20px 16px 8px;max-width:1600px;margin:0 auto}
h1{font-size:20px;margin:0 0 4px}.sub{color:var(--muted);font-size:13px}
.progress{height:8px;background:var(--col);border-radius:4px;margin:12px 0 4px;overflow:hidden}
.progress>div{height:100%;background:var(--ok)}
.tools{display:flex;gap:8px;margin-top:10px}
.tools input{flex:1;max-width:320px;padding:7px 10px;border:1px solid var(--border);border-radius:6px;
background:var(--card);color:var(--text);font:inherit}
.board{display:grid;grid-template-columns:repeat(7,minmax(220px,1fr));gap:12px;padding:12px 16px 32px;
max-width:1600px;margin:0 auto;overflow-x:auto}
@media (max-width:900px){.board{grid-template-columns:1fr;overflow-x:visible}}
.col{background:var(--col);border-radius:10px;padding:10px;min-height:80px}
.col h2{font-size:13px;margin:2px 4px 10px;display:flex;justify-content:space-between;color:var(--muted);
text-transform:uppercase;letter-spacing:.04em}
.col h2 span{background:var(--chip);border-radius:10px;padding:0 8px;color:var(--text)}
.card{background:var(--card);border:1px solid var(--border);border-left:4px solid var(--border);
border-radius:8px;padding:10px;margin-bottom:8px}
.card.p-high{border-left-color:var(--bad)}.card.p-medium{border-left-color:var(--warn)}
.card.p-low{border-left-color:var(--ok)}
.id{font-weight:600;color:var(--accent);margin-right:4px}.title{font-weight:500}
.meta{display:flex;flex-wrap:wrap;gap:4px;margin-top:8px}
.chip{background:var(--chip);border-radius:4px;padding:1px 6px;font-size:12px;color:var(--muted)}
.chip.ok{color:var(--ok)}.chip.wait{color:var(--warn)}.chip.fix{color:var(--bad)}
.bar{height:4px;background:var(--chip);border-radius:2px;margin-top:8px;overflow:hidden}
.bar>div{height:100%;background:var(--accent)}
a{color:var(--accent);text-decoration:none}a:hover{text-decoration:underline}
.empty{color:var(--muted);font-size:12px;text-align:center;padding:8px}
"""

JS = """
const q=document.getElementById('q');q.addEventListener('input',()=>{const v=q.value.toLowerCase();
document.querySelectorAll('.card').forEach(c=>{c.style.display=c.textContent.toLowerCase().includes(v)?'':'none'})});
"""


def render_html(cards, source, project):
    e = html.escape
    total = len(cards)
    done = sum(1 for c in cards if c["col"] == "done")
    pct = int(round(100.0 * done / total)) if total else 0
    cols = []
    for key, name in COLUMNS:
        items = [c for c in cards if c["col"] == key]
        body = []
        for c in items:
            chips = []
            if c["epic"]:
                chips.append('<span class="chip">%s</span>' % e(c["epic"]))
            if c["priority"]:
                chips.append('<span class="chip">%s</span>' % e(c["priority"]))
            if c.get("fixing"):
                chips.append('<span class="chip fix">исправления</span>')
            for d, ok in c["deps_state"]:
                chips.append('<span class="chip %s" title="зависимость">⟵ %s</span>' % ("ok" if ok else "wait", e(d)))
            if c["branch"]:
                chips.append('<span class="chip" title="ветка">⎇ %s</span>' % e(c["branch"]))
            if c["mr"]:
                chips.append('<a class="chip" href="%s">MR ↗</a>' % e(c["mr"], quote=True))
            if c["total"]:
                chips.append('<span class="chip">☑ %d/%d</span>' % (c["done"], c["total"]))
            bar = ('<div class="bar"><div style="width:%d%%"></div></div>' % (100 * c["done"] // c["total"])) if c["total"] else ""
            body.append('<div class="card p-%s"><span class="id">%s</span><span class="title">%s</span>'
                        '<div class="meta">%s</div>%s</div>' % (
                            e(c["priority"].lower() or "none"), e(c["id"]), e(md_link_title(c)), "".join(chips), bar))
        if not body:
            body.append('<div class="empty">пусто</div>')
        cols.append('<section class="col"><h2>%s<span>%d</span></h2>%s</section>' % (e(name), len(items), "".join(body)))
    return ("<!doctype html>\n<html lang=\"ru\"><head><meta charset=\"utf-8\">"
            "<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">"
            "<title>Канбан: %s</title><style>%s</style></head><body>"
            "<header><h1>Канбан: %s</h1><div class=\"sub\">Источник: %s · задач: %d · готово: %d (%d%%)</div>"
            "<div class=\"progress\"><div style=\"width:%d%%\"></div></div>"
            "<div class=\"tools\"><input id=\"q\" placeholder=\"Фильтр по задачам…\"></div></header>"
            "<main class=\"board\">%s</main><script>%s</script></body></html>\n") % (
        e(project), CSS, e(project), e(source), total, done, pct, pct, "".join(cols), JS)


def find_plan(arg):
    if arg:
        if not os.path.isfile(arg):
            sys.exit("ERROR: нет файла %s" % arg)
        return arg
    for c in CANDIDATES:
        if os.path.isfile(c):
            return c
    sys.exit("ERROR: не найден tasks.md или ROADMAP.md — укажи путь к плану")


def main():
    p = argparse.ArgumentParser(description="Канбан-доска из tasks.md / ROADMAP.md")
    p.add_argument("plan", nargs="?")
    p.add_argument("--out-dir")
    p.add_argument("--check", action="store_true")
    a = p.parse_args()

    plan = find_plan(a.plan)
    text = open(plan, encoding="utf-8").read()
    fmt = "tasks" if is_tasks_format(text) else "roadmap"
    cards = parse_tasks(text) if fmt == "tasks" else parse_roadmap(text)
    if not cards:
        sys.exit("ERROR: в %s не найдено задач. Ожидаются `## T1: …` + `- status:` или пункты-чекбоксы `- [ ] …`." % plan)

    out_dir = a.out_dir or os.path.dirname(os.path.abspath(plan))
    m = re.search(r"^#\s+(.+)$", text, re.M)
    project = re.sub(r"^(План|Roadmap|Plan|Tasks)\s*[:—-]\s*", "", m.group(1).strip(), flags=re.I) if m else os.path.basename(out_dir)
    source = os.path.basename(plan)
    outputs = {
        os.path.join(out_dir, "KANBAN.md"): render_md(cards, source),
        os.path.join(out_dir, "KANBAN.html"): render_html(cards, source, project),
    }

    if a.check:
        stale = []
        for path, content in outputs.items():
            cur = open(path, encoding="utf-8").read() if os.path.exists(path) else None
            if cur != content:
                stale.append("%s %s" % (os.path.basename(path), "отсутствует" if cur is None else "устарел или правился вручную"))
        if stale:
            print("STALE: " + "; ".join(stale))
            sys.exit(1)
        print("OK: доска актуальна")
        return

    changed = []
    for path, content in outputs.items():
        cur = open(path, encoding="utf-8").read() if os.path.exists(path) else None
        if cur != content:
            with open(path, "w", encoding="utf-8") as f:
                f.write(content)
            changed.append(os.path.basename(path))

    print("План: %s (формат: %s) → %s" % (plan, fmt, out_dir))
    for key, name in COLUMNS:
        ids = [c["id"] for c in cards if c["col"] == key]
        if ids:
            print("  %-14s %2d  %s" % (name, len(ids), ", ".join(ids)))
    print("Обновлено: %s" % (", ".join(changed) if changed else "ничего — доска уже актуальна"))


if __name__ == "__main__":
    main()
