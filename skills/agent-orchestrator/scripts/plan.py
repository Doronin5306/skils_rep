#!/usr/bin/env python3
"""Работа с файлом-планом tasks.md (формат — assets/tasks.template.md).

Использование:
  plan.py [--file tasks.md] validate              проверить формат, зависимости, циклы
  plan.py [--file tasks.md] list                  таблица задач
  plan.py [--file tasks.md] next                  следующая задача, готовая к работе
  plan.py [--file tasks.md] show T3               полный текст задачи
  plan.py [--file tasks.md] branch T3             имя ветки задачи
  plan.py [--file tasks.md] set T3 STATUS [--mr URL] [--branch NAME]

Статусы: todo, in-progress, testing, fixing, review, done, blocked.
Задача готова к работе (next), если она todo и все её depends — done.
"""
import argparse
import re
import sys

STATUSES = ("todo", "in-progress", "testing", "fixing", "review", "done", "blocked")
HEAD_RE = re.compile(r"^##\s+(T\d+)\s*[:.\-—]\s*(.+?)\s*$")
FIELD_RE = re.compile(r"^-\s+(status|depends|branch|mr|priority):\s*(.*?)\s*$", re.I)

TRANSLIT = dict(zip(
    "абвгдеёжзийклмнопрстуфхцчшщъыьэюя",
    ["a", "b", "v", "g", "d", "e", "e", "zh", "z", "i", "y", "k", "l", "m", "n", "o", "p",
     "r", "s", "t", "u", "f", "h", "ts", "ch", "sh", "sch", "", "y", "", "e", "yu", "ya"]))


def slugify(text, limit=40):
    s = "".join(TRANSLIT.get(c, c) for c in text.lower())
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    if len(s) > limit:
        s = s[:limit].rsplit("-", 1)[0] or s[:limit]
    return s or "task"


def parse(path):
    try:
        lines = open(path, encoding="utf-8").read().split("\n")
    except FileNotFoundError:
        sys.exit("ERROR: нет файла %s" % path)
    tasks, cur = [], None
    for i, line in enumerate(lines):
        m = HEAD_RE.match(line)
        if m:
            cur = {"id": m.group(1), "title": m.group(2), "line": i, "fields": {}, "field_lines": {}, "end": i}
            tasks.append(cur)
            continue
        if line.startswith("## ") or line.startswith("# "):
            cur = None
            continue
        if cur is not None:
            cur["end"] = i
            f = FIELD_RE.match(line)
            if f and f.group(1).lower() not in cur["fields"]:
                k = f.group(1).lower()
                cur["fields"][k] = f.group(2)
                cur["field_lines"][k] = i
    for t in tasks:
        f = t["fields"]
        t["status"] = f.get("status", "todo").lower()
        t["depends"] = [d.strip() for d in re.split(r"[,\s]+", f.get("depends", "")) if re.match(r"^T\d+$", d.strip())]
        t["branch"] = f.get("branch") or "%s-%s" % (t["id"].lower(), slugify(t["title"]))
        t["mr"] = f.get("mr", "")
    return lines, tasks


def find(tasks, tid):
    for t in tasks:
        if t["id"].upper() == tid.upper():
            return t
    sys.exit("ERROR: нет задачи %s" % tid)


def validate(tasks):
    errors = []
    ids = [t["id"] for t in tasks]
    if not tasks:
        errors.append("нет задач (заголовки вида `## T1: Название`)")
    for d in set(x for x in ids if ids.count(x) > 1):
        errors.append("повторяется id %s" % d)
    known = set(ids)
    for t in tasks:
        if t["status"] not in STATUSES:
            errors.append("%s: неизвестный статус %r" % (t["id"], t["status"]))
        for d in t["depends"]:
            if d not in known:
                errors.append("%s: зависит от несуществующей %s" % (t["id"], d))
        if "status" not in t["fields"]:
            errors.append("%s: нет поля status" % t["id"])
    graph = {t["id"]: t["depends"] for t in tasks}
    state = {}

    def dfs(n, stack):
        state[n] = 1
        for m in graph.get(n, []):
            if state.get(m) == 1:
                errors.append("цикл зависимостей: %s" % " → ".join(stack + [n, m]))
            elif m in graph and not state.get(m):
                dfs(m, stack + [n])
        state[n] = 2

    for n in graph:
        if not state.get(n):
            dfs(n, [])
    return errors


def main():
    p = argparse.ArgumentParser(description="Файл-план задач")
    p.add_argument("--file", default="tasks.md")
    sub = p.add_subparsers(dest="cmd")
    sub.add_parser("validate"); sub.add_parser("list"); sub.add_parser("next")
    s = sub.add_parser("show"); s.add_argument("id")
    s = sub.add_parser("branch"); s.add_argument("id")
    s = sub.add_parser("set"); s.add_argument("id"); s.add_argument("status")
    s.add_argument("--mr"); s.add_argument("--branch")
    a = p.parse_args()
    if not a.cmd:
        p.print_help(); sys.exit(2)

    lines, tasks = parse(a.file)

    if a.cmd == "validate":
        errs = validate(tasks)
        for e in errs:
            print("ERROR: " + e)
        print("OK: %d задач" % len(tasks) if not errs else "Ошибок: %d" % len(errs))
        sys.exit(1 if errs else 0)

    if a.cmd == "list":
        done = {t["id"] for t in tasks if t["status"] == "done"}
        print("%-5s %-12s %-6s %-45s %s" % ("ID", "СТАТУС", "ГОТОВА", "НАЗВАНИЕ", "MR"))
        for t in tasks:
            ready = "да" if t["status"] == "todo" and all(d in done for d in t["depends"]) else ""
            print("%-5s %-12s %-6s %-45s %s" % (t["id"], t["status"], ready, t["title"][:45], t["mr"]))
        return

    if a.cmd == "next":
        done = {t["id"] for t in tasks if t["status"] == "done"}
        for t in tasks:
            if t["status"] == "todo" and all(d in done for d in t["depends"]):
                print("%s\t%s\t%s" % (t["id"], t["branch"], t["title"]))
                return
        waiting = [t["id"] for t in tasks if t["status"] == "todo"]
        if waiting:
            print("NONE: задачи %s ждут зависимостей (смержи MR зависимостей)" % ", ".join(waiting))
        else:
            print("NONE: открытых задач нет")
        sys.exit(1)

    t = find(tasks, a.id)
    if a.cmd == "show":
        print("\n".join(lines[t["line"]:t["end"] + 1]).rstrip())
        return
    if a.cmd == "branch":
        print(t["branch"])
        return
    if a.cmd == "set":
        st = a.status.lower()
        if st not in STATUSES:
            sys.exit("ERROR: статус должен быть одним из: %s" % ", ".join(STATUSES))
        updates = {"status": st}
        if a.mr:
            updates["mr"] = a.mr
        if a.branch:
            updates["branch"] = a.branch
        insert_at = t["field_lines"].get("status", t["line"]) + 1
        for k, v in updates.items():
            if k in t["field_lines"]:
                lines[t["field_lines"][k]] = "- %s: %s" % (k, v)
            else:
                lines.insert(insert_at, "- %s: %s" % (k, v))
                insert_at += 1
        with open(a.file, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
        print("%s → %s%s" % (t["id"], st, (" (mr: %s)" % a.mr) if a.mr else ""))


if __name__ == "__main__":
    main()
