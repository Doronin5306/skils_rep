#!/usr/bin/env bash
# Устанавливает скилы из репозитория в Claude Code через симлинки.
#
#   ./install.sh                 # все скилы
#   ./install.sh name1 name2     # выбранные
#   ./install.sh --uninstall [name...]
#
# Каталог назначения можно переопределить: CLAUDE_SKILLS_DIR=... ./install.sh
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SRC="$REPO/skills"
DEST="${CLAUDE_SKILLS_DIR:-$HOME/.claude/skills}"

uninstall=false
if [[ "${1:-}" == "--uninstall" ]]; then uninstall=true; shift; fi

if [[ $# -gt 0 ]]; then
  names=("$@")
else
  names=()
  for d in "$SRC"/*/; do [[ -f "$d/SKILL.md" ]] && names+=("$(basename "$d")"); done
fi

mkdir -p "$DEST"
for name in "${names[@]}"; do
  src="$SRC/$name"
  dst="$DEST/$name"
  if $uninstall; then
    if [[ -L "$dst" && "$(readlink "$dst")" == "$src" ]]; then
      rm "$dst"; echo "удалён:      $name"
    else
      echo "пропущен:    $name (не наш симлинк)"
    fi
    continue
  fi
  if [[ ! -f "$src/SKILL.md" ]]; then
    echo "ОШИБКА:      $name — нет $src/SKILL.md" >&2; exit 1
  fi
  if [[ -L "$dst" ]]; then
    if [[ "$(readlink "$dst")" == "$src" ]]; then echo "уже есть:    $name"; continue; fi
    echo "ОШИБКА:      $dst — симлинк на другое место ($(readlink "$dst"))" >&2; exit 1
  elif [[ -e "$dst" ]]; then
    echo "ОШИБКА:      $dst уже существует и не является симлинком — разберись вручную" >&2; exit 1
  fi
  ln -s "$src" "$dst"
  echo "установлен:  $name → $dst"
done
