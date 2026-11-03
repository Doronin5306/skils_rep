#!/usr/bin/env python3
"""Проверяет структуру скила.

Использование:
    python3 validate_skill.py <путь-к-папке-скила> [...]
    python3 validate_skill.py --all        # все скилы в репозитории

Код выхода 1, если есть ошибки (ERROR). Предупреждения (WARN) не валят проверку.
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.realpath(__file__)))
from _common import NAME_RE, SKILLS_DIR, parse_frontmatter  # noqa: E402

KNOWN_FIELDS = {
    "name", "description", "allowed-tools", "argument-hint",
    "disable-model-invocation", "model", "license", "metadata",
    "user-invocable", "when_to_use", "version",
}
MAX_BODY_LINES = 500


def validate(path):
    errors, warns = [], []
    path = os.path.abspath(path)
    dirname = os.path.basename(path.rstrip("/"))
    skill_md = os.path.join(path, "SKILL.md")

    if not os.path.isfile(skill_md):
        return ["нет файла SKILL.md"], warns

    with open(skill_md, encoding="utf-8") as f:
        text = f.read()
    fm, body = parse_frontmatter(text)
    if fm is None:
        return ["SKILL.md должен начинаться с YAML frontmatter (--- ... ---)"], warns

    name = fm.get("name", "")
    desc = fm.get("description", "")

    if not name:
        errors.append("нет поля name")
    else:
        if not NAME_RE.match(name):
            errors.append("name должен быть kebab-case: %r" % name)
        if len(name) > 64:
            errors.append("name длиннее 64 символов")
        if name != dirname:
            errors.append("name (%s) не совпадает с именем папки (%s)" % (name, dirname))

    if not desc:
        errors.append("нет поля description")
    else:
        if len(desc) > 1024:
            errors.append("description длиннее 1024 символов (%d)" % len(desc))
        if "<" in desc or ">" in desc:
            errors.append("description не должен содержать угловые скобки < >")
        if "TODO" in desc:
            errors.append("в description остался TODO")
        if len(desc) < 80:
            warns.append("description очень короткий (%d симв.) — добавь, КОГДА использовать скил" % len(desc))
        if not re.search(r"(используй|use when|use this|когда|when)", desc, re.I):
            warns.append("в description не видно, когда использовать скил («Используй, когда…»)")

    unknown = set(fm) - KNOWN_FIELDS
    if unknown:
        warns.append("неизвестные поля frontmatter: %s" % ", ".join(sorted(unknown)))

    body_lines = body.strip().count("\n") + 1 if body.strip() else 0
    if body_lines == 0:
        errors.append("пустое тело SKILL.md")
    elif body_lines > MAX_BODY_LINES:
        warns.append("тело SKILL.md %d строк (> %d) — вынеси справку в references/" % (body_lines, MAX_BODY_LINES))
    if re.search(r"\bTODO\b", body):
        errors.append("в теле SKILL.md остались TODO")

    # Ссылки на файлы скила должны существовать
    for ref in sorted(set(re.findall(r"(?<![\w/])((?:references|scripts|assets)/[\w./-]+\.\w+)", body))):
        if not os.path.exists(os.path.join(path, ref)):
            errors.append("ссылка на несуществующий файл: %s" % ref)

    for sub in ("references", "scripts", "assets"):
        d = os.path.join(path, sub)
        if os.path.isdir(d) and not os.listdir(d):
            warns.append("пустая папка %s/ — удали или заполни" % sub)

    scripts_dir = os.path.join(path, "scripts")
    if os.path.isdir(scripts_dir):
        for fn in os.listdir(scripts_dir):
            fp = os.path.join(scripts_dir, fn)
            if fn.endswith((".py", ".sh")) and not fn.startswith("_") and not os.access(fp, os.X_OK):
                warns.append("scripts/%s не исполняемый (chmod +x)" % fn)

    for junk in ("README.md", "CHANGELOG.md"):
        if os.path.exists(os.path.join(path, junk)):
            warns.append("%s внутри скила не нужен — всё важное держи в SKILL.md" % junk)

    return errors, warns


def main():
    args = sys.argv[1:]
    if not args:
        sys.exit(__doc__)
    if args == ["--all"]:
        args = [os.path.join(SKILLS_DIR, d) for d in sorted(os.listdir(SKILLS_DIR))
                if os.path.isdir(os.path.join(SKILLS_DIR, d))]

    failed = False
    for p in args:
        errors, warns = validate(p)
        status = "FAIL" if errors else "OK"
        print("[%s] %s" % (status, os.path.basename(os.path.abspath(p).rstrip("/"))))
        for e in errors:
            print("  ERROR: " + e)
        for w in warns:
            print("  WARN:  " + w)
        failed = failed or bool(errors)
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
