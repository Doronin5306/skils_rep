#!/usr/bin/env python3
"""Создаёт структуру базы знаний LLM Wiki.

Использование:
    python3 init_wiki.py <путь> [--topic "Тема"]

Ничего не перезаписывает: существующие файлы и папки пропускаются.
"""
import argparse
import datetime
import os

SKILL_DIR = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))

DIRS = [
    "raw", "raw/assets",
    "wiki", "wiki/sources", "wiki/entities", "wiki/concepts", "wiki/syntheses",
]


def write_new(path, content, created, skipped):
    if os.path.exists(path):
        skipped.append(path)
        return
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    created.append(path)


def main():
    p = argparse.ArgumentParser(description="Создать базу знаний LLM Wiki")
    p.add_argument("path")
    p.add_argument("--topic", default="Без темы")
    args = p.parse_args()

    root = os.path.abspath(os.path.expanduser(args.path))
    today = datetime.date.today().isoformat()
    created, skipped = [], []

    for d in DIRS:
        full = os.path.join(root, d)
        if os.path.isdir(full):
            continue
        os.makedirs(full)
        created.append(full + "/")
        if d in ("raw/assets", "wiki/sources", "wiki/entities", "wiki/concepts", "wiki/syntheses"):
            open(os.path.join(full, ".gitkeep"), "w").close()

    with open(os.path.join(SKILL_DIR, "assets", "CLAUDE.md"), encoding="utf-8") as f:
        schema = f.read().replace("{{topic}}", args.topic)
    write_new(os.path.join(root, "CLAUDE.md"), schema, created, skipped)

    write_new(os.path.join(root, "wiki", "index.md"),
              "# Индекс: %s\n\n"
              "Каталог всех страниц вики. Обновляется при каждом ingest.\n\n"
              "- [[overview]] — обзор области знаний\n\n"
              "## Источники\n\n## Сущности\n\n## Концепты\n\n## Синтезы\n" % args.topic,
              created, skipped)

    write_new(os.path.join(root, "wiki", "log.md"),
              "# Журнал\n\nХронологический журнал операций. Только дописывается.\n\n"
              "## [%s] init | Создана база «%s»\n" % (today, args.topic),
              created, skipped)

    write_new(os.path.join(root, "wiki", "overview.md"),
              "---\ntitle: Обзор\ntype: overview\nupdated: %s\n---\n\n"
              "# Обзор: %s\n\n"
              "Общая картина области знаний. Пока источников нет — обзор появится после первых ingest.\n\n"
              "См. [[index]].\n" % (today, args.topic),
              created, skipped)

    print("База знаний: %s" % root)
    for c in created:
        print("  создано:   %s" % os.path.relpath(c, root))
    for s in skipped:
        print("  пропущено: %s (уже есть)" % os.path.relpath(s, root))


if __name__ == "__main__":
    main()
