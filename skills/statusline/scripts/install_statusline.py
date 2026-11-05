#!/usr/bin/env python3
"""Подключает statusline.py в settings.json Claude Code.

  install_statusline.py                     # глобально: ~/.claude/settings.json
  install_statusline.py --project DIR       # в DIR/.claude/settings.json (копирует скрипт в DIR/.claude/)
  install_statusline.py --uninstall [--project DIR]
  install_statusline.py --force             # перезаписать чужой statusLine

Остальные ключи settings.json не трогает. Перед записью кладёт .bak.
"""
import argparse
import json
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCRIPT = HERE / "statusline.py"
# Глобально ссылаемся на путь через симлинк скила — он стабилен при переустановке.
GLOBAL_CMD = "python3 ~/.claude/skills/statusline/scripts/statusline.py"
PROJECT_CMD = 'python3 "$CLAUDE_PROJECT_DIR/.claude/statusline.py"'
MARK = "statusline.py"


def load(path):
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text() or "{}")
    except json.JSONDecodeError as e:
        sys.exit(f"ОШИБКА: {path} — невалидный JSON ({e}); поправь вручную")


def save(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        shutil.copy2(path, path.with_suffix(".json.bak"))
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--project", type=Path)
    ap.add_argument("--uninstall", action="store_true")
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args()

    if a.project:
        root = a.project.expanduser().resolve()
        settings = root / ".claude" / "settings.json"
        cmd = PROJECT_CMD
    else:
        settings = Path.home() / ".claude" / "settings.json"
        cmd = GLOBAL_CMD

    data = load(settings)
    cur = data.get("statusLine")
    ours = isinstance(cur, dict) and MARK in str(cur.get("command", ""))

    if a.uninstall:
        if cur is None:
            print(f"нечего удалять: в {settings} нет statusLine")
            return
        if not ours and not a.force:
            sys.exit(f"ОШИБКА: statusLine в {settings} не наш ({cur}); --force чтобы удалить")
        del data["statusLine"]
        save(settings, data)
        print(f"удалён statusLine из {settings}")
        return

    if cur is not None and not ours and not a.force:
        sys.exit(f"ОШИБКА: в {settings} уже свой statusLine: {cur}\n  --force чтобы заменить")

    if a.project:
        dst = root / ".claude" / "statusline.py"
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(SCRIPT, dst)
        print(f"скопирован скрипт → {dst}")

    data["statusLine"] = {"type": "command", "command": cmd, "padding": 2}
    save(settings, data)
    print(f"statusLine записан в {settings}\n  command: {cmd}")


if __name__ == "__main__":
    main()
