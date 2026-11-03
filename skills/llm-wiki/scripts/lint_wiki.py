#!/usr/bin/env python3
"""Структурная проверка базы знаний LLM Wiki.

Использование:
    python3 lint_wiki.py <путь-к-базе>

Проверяет:
  - битые вики-ссылки [[...]]
  - страницы-сироты (на них никто не ссылается, кроме index/log)
  - страницы, отсутствующие в wiki/index.md
  - дубли имён файлов (Obsidian резолвит ссылки по имени)
  - frontmatter: наличие, обязательные поля, совпадение type с папкой
  - сырые источники в raw/ без страницы в wiki/sources/
  - ссылки frontmatter `sources:` на несуществующие страницы

Смысловые проблемы (противоречия, устаревшее) скрипт не ищет — это делает Claude.
Код выхода 1, если найдены проблемы.
"""
import os
import re
import sys

LINK_RE = re.compile(r"!?\[\[([^\]|#]+)(?:#[^\]|]*)?(?:\|[^\]]*)?\]\]")
CODE_RE = re.compile(r"```.*?```|`[^`\n]*`", re.S)
REQUIRED = ("title", "type", "updated")
FOLDER_TYPE = {"sources": "source", "entities": "entity", "concepts": "concept", "syntheses": "synthesis"}
SPECIAL = {"index", "log", "overview"}


def parse_frontmatter(text):
    if not text.startswith("---"):
        return None, text
    m = re.match(r"^---\n(.*?)\n---\n?", text, re.S)
    if not m:
        return None, text
    data = {}
    for line in m.group(1).split("\n"):
        kv = re.match(r"^([A-Za-z0-9_-]+):\s*(.*)$", line)
        if kv:
            data[kv.group(1)] = kv.group(2).strip()
    return data, text[m.end():]


def parse_list(val):
    val = val.strip()
    if val.startswith("[") and val.endswith("]"):
        val = val[1:-1]
    return [x.strip().strip("\"'").replace("[[", "").replace("]]", "") for x in val.split(",") if x.strip()]


def main():
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    root = os.path.abspath(os.path.expanduser(sys.argv[1]))
    wiki = os.path.join(root, "wiki")
    raw = os.path.join(root, "raw")
    if not os.path.isdir(wiki):
        sys.exit("ERROR: нет папки wiki/ в %s — это не база LLM Wiki?" % root)

    pages = {}  # slug -> relpath
    dupes = []
    for dirpath, _, files in os.walk(wiki):
        for fn in files:
            if not fn.endswith(".md"):
                continue
            slug = fn[:-3]
            rel = os.path.relpath(os.path.join(dirpath, fn), wiki)
            if slug in pages:
                dupes.append((slug, pages[slug], rel))
            pages[slug] = rel

    # raw-файлы тоже можно линковать (картинки, исходники)
    raw_names = set()
    raw_sources = []
    if os.path.isdir(raw):
        for dirpath, _, files in os.walk(raw):
            for fn in files:
                if fn.startswith("."):
                    continue
                raw_names.add(fn)
                raw_names.add(os.path.splitext(fn)[0])
                if os.path.relpath(dirpath, raw).split(os.sep)[0] != "assets":
                    raw_sources.append(os.path.relpath(os.path.join(dirpath, fn), root))

    inbound = {s: set() for s in pages}
    broken, fm_issues, bad_sources = [], [], []
    index_links = set()
    raw_cited = set()

    for slug, rel in sorted(pages.items()):
        with open(os.path.join(wiki, rel), encoding="utf-8") as f:
            text = f.read()
        fm, body = parse_frontmatter(text)
        links = set(LINK_RE.findall(CODE_RE.sub("", body)))
        links = {l.strip().split("/")[-1] for l in links}
        if slug == "index":
            index_links = links
        for target in sorted(links):
            if target in pages:
                if target != slug:
                    inbound[target].add(slug)
            elif target not in raw_names:
                broken.append((rel, target))

        folder = rel.split(os.sep)[0] if os.sep in rel else ""
        if folder in FOLDER_TYPE:
            if fm is None:
                fm_issues.append((rel, "нет frontmatter"))
                continue
            missing = [k for k in REQUIRED if not fm.get(k)]
            if missing:
                fm_issues.append((rel, "нет полей: " + ", ".join(missing)))
            if fm.get("type") and fm["type"] != FOLDER_TYPE[folder]:
                fm_issues.append((rel, "type: %s, а папка %s/ ожидает %s" % (fm["type"], folder, FOLDER_TYPE[folder])))
            for s in parse_list(fm.get("sources", "")):
                if s not in pages:
                    bad_sources.append((rel, s))
            if folder == "sources":
                r = fm.get("raw", "").strip("\"'")
                if r:
                    raw_cited.add(os.path.normpath(r))
                    if not os.path.exists(os.path.join(root, r)):
                        fm_issues.append((rel, "raw: файл не найден: %s" % r))

    # источник raw считается обработанным, если на него указывает raw: или есть sources/<имя>.md
    source_slugs = {s for s, r in pages.items() if r.startswith("sources" + os.sep)}
    uningested = [r for r in sorted(raw_sources)
                  if os.path.normpath(r) not in raw_cited
                  and os.path.splitext(os.path.basename(r))[0] not in source_slugs]

    content = [s for s in pages if s not in SPECIAL]
    orphans = sorted(s for s in content if not (inbound[s] - SPECIAL))
    not_in_index = sorted(s for s in content if s not in index_links)

    sections = [
        ("Битые ссылки", ["%s → [[%s]]" % b for b in broken]),
        ("Дубли имён файлов", ["%s: %s и %s" % d for d in dupes]),
        ("Проблемы frontmatter", ["%s: %s" % x for x in fm_issues]),
        ("sources: ссылается на несуществующую страницу", ["%s → %s" % x for x in bad_sources]),
        ("Нет в index.md", not_in_index),
        ("Сироты (никто не ссылается, кроме index/log)", orphans),
        ("Необработанные источники в raw/", uningested),
    ]

    total = 0
    print("База: %s — страниц: %d, сырых источников: %d" % (root, len(pages), len(raw_sources)))
    for title, items in sections:
        if items:
            total += len(items)
            print("\n## %s (%d)" % (title, len(items)))
            for i in items:
                print("- " + i)
    print("\nИтого проблем: %d" % total)
    sys.exit(1 if total else 0)


if __name__ == "__main__":
    main()
