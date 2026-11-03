#!/usr/bin/env python3
"""Создаёт каркас нового скила в skills/<name>/.

Использование:
    python3 init_skill.py <skill-name> [--with references,scripts,assets]
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.realpath(__file__)))
from _common import NAME_RE, SKILL_DIR, SKILLS_DIR  # noqa: E402

ALLOWED_SUBDIRS = ("references", "scripts", "assets")


def main():
    p = argparse.ArgumentParser(description="Создать каркас скила")
    p.add_argument("name", help="имя скила в kebab-case")
    p.add_argument("--with", dest="subdirs", default="",
                   help="подпапки через запятую: " + ",".join(ALLOWED_SUBDIRS))
    args = p.parse_args()

    name = args.name.strip()
    if not NAME_RE.match(name) or len(name) > 64:
        sys.exit("ERROR: имя должно быть kebab-case (a-z, 0-9, дефис), ≤ 64 символа: %r" % name)

    target = os.path.join(SKILLS_DIR, name)
    if os.path.exists(target):
        sys.exit("ERROR: скил уже существует: %s" % target)

    subdirs = [s.strip() for s in args.subdirs.split(",") if s.strip()]
    bad = [s for s in subdirs if s not in ALLOWED_SUBDIRS]
    if bad:
        sys.exit("ERROR: неизвестные подпапки: %s (допустимо: %s)" % (", ".join(bad), ", ".join(ALLOWED_SUBDIRS)))

    with open(os.path.join(SKILL_DIR, "assets", "SKILL.template.md"), encoding="utf-8") as f:
        template = f.read()
    title = " ".join(w.capitalize() for w in name.split("-"))
    content = template.replace("{{name}}", name).replace("{{title}}", title)

    os.makedirs(target)
    with open(os.path.join(target, "SKILL.md"), "w", encoding="utf-8") as f:
        f.write(content)
    for s in subdirs:
        os.makedirs(os.path.join(target, s))

    print("Создан скил: %s" % target)
    for root, dirs, files in os.walk(target):
        rel = os.path.relpath(root, SKILLS_DIR)
        for d in sorted(dirs):
            print("  %s/" % os.path.join(rel, d))
        for fn in sorted(files):
            print("  %s" % os.path.join(rel, fn))
    print("Дальше: заполни TODO в SKILL.md и запусти validate_skill.py")


if __name__ == "__main__":
    main()
