#!/usr/bin/env python3
"""Перегенерирует таблицу скилов в README.md репозитория.

Таблица вставляется между маркерами
<!-- skills:start --> и <!-- skills:end -->.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.realpath(__file__)))
from _common import REPO_ROOT, SKILLS_DIR, parse_frontmatter  # noqa: E402

START = "<!-- skills:start -->"
END = "<!-- skills:end -->"


def short(desc, limit=160):
    first = desc.split(". ")[0].rstrip(".")
    return first if len(first) <= limit else first[: limit - 1].rstrip() + "…"


def main():
    rows = []
    for d in sorted(os.listdir(SKILLS_DIR)):
        md = os.path.join(SKILLS_DIR, d, "SKILL.md")
        if not os.path.isfile(md):
            continue
        with open(md, encoding="utf-8") as f:
            fm, _ = parse_frontmatter(f.read())
        desc = (fm or {}).get("description", "").replace("|", "\\|")
        rows.append("| [`%s`](skills/%s/SKILL.md) | %s |" % (d, d, short(desc)))

    table = "\n".join(["| Скил | Описание |", "|---|---|"] + rows) if rows else "_Пока нет скилов._"

    readme = os.path.join(REPO_ROOT, "README.md")
    with open(readme, encoding="utf-8") as f:
        text = f.read()
    if START not in text or END not in text:
        sys.exit("ERROR: в README.md нет маркеров %s / %s" % (START, END))
    head, rest = text.split(START, 1)
    _, tail = rest.split(END, 1)
    with open(readme, "w", encoding="utf-8") as f:
        f.write(head + START + "\n" + table + "\n" + END + tail)
    print("README.md обновлён: %d скил(ов)" % len(rows))


if __name__ == "__main__":
    main()
