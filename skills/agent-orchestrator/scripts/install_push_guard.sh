#!/usr/bin/env bash
# Ставит git pre-push хук, который запрещает пушить в main/master
# (и в защищённые ветки из PROTECTED_BRANCHES).
#
#   install_push_guard.sh [путь-к-репозиторию]
#
# Хук общий для всех worktree репозитория. Существующий pre-push хук не затирается:
# он сохраняется как pre-push.local и вызывается после проверки.
set -euo pipefail

REPO="${1:-.}"
HOOKS_DIR="$(git -C "$REPO" rev-parse --git-common-dir)/hooks"
HOOK="$HOOKS_DIR/pre-push"
MARK="# agent-orchestrator push guard"

mkdir -p "$HOOKS_DIR"
if [[ -f "$HOOK" ]] && grep -q "$MARK" "$HOOK"; then
  echo "push guard уже установлен: $HOOK"; exit 0
fi
if [[ -f "$HOOK" ]]; then
  mv "$HOOK" "$HOOKS_DIR/pre-push.local"
  echo "существующий pre-push сохранён как pre-push.local"
fi

cat > "$HOOK" <<'EOF'
#!/usr/bin/env bash
# agent-orchestrator push guard
PROTECTED="${PROTECTED_BRANCHES:-main master}"
while read -r local_ref local_sha remote_ref remote_sha; do
  branch="${remote_ref#refs/heads/}"
  for p in $PROTECTED; do
    if [[ "$branch" == "$p" ]]; then
      echo "ЗАПРЕЩЕНО: пуш в '$p'. Работай в ветке задачи и открывай MR." >&2
      exit 1
    fi
  done
done
HOOK_DIR="$(dirname "$0")"
if [[ -x "$HOOK_DIR/pre-push.local" ]]; then exec "$HOOK_DIR/pre-push.local" "$@"; fi
exit 0
EOF
chmod +x "$HOOK"
echo "push guard установлен: $HOOK (защищены: main master)"
