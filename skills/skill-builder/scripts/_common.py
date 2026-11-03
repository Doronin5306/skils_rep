"""Общие помощники для скриптов skill-builder."""
import os
import re

SCRIPT_DIR = os.path.dirname(os.path.realpath(__file__))
SKILL_DIR = os.path.dirname(SCRIPT_DIR)
SKILLS_DIR = os.path.dirname(SKILL_DIR)
REPO_ROOT = os.path.dirname(SKILLS_DIR)

NAME_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")


def parse_frontmatter(text):
    """Возвращает (dict, body) или (None, text), если frontmatter нет.

    Поддерживает простые `key: value` и многострочные значения (`|`, `>`
    или продолжение с отступом) — этого достаточно для SKILL.md.
    """
    if not text.startswith("---"):
        return None, text
    lines = text.split("\n")
    end = None
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            end = i
            break
    if end is None:
        return None, text
    data = {}
    key = None
    for line in lines[1:end]:
        m = re.match(r"^([A-Za-z0-9_-]+):\s*(.*)$", line)
        if m and not line.startswith((" ", "\t")):
            key = m.group(1)
            val = m.group(2).strip()
            data[key] = "" if val in ("|", ">", "|-", ">-") else val
        elif key is not None and line.strip():
            sep = " " if data[key] else ""
            data[key] = data[key] + sep + line.strip()
    for k, v in data.items():
        if len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'":
            data[k] = v[1:-1]
    body = "\n".join(lines[end + 1:])
    return data, body
