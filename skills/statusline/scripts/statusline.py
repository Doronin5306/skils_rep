#!/usr/bin/env python3
# Claude Code status line. Reads session JSON from stdin, prints one line:
#   ⬡ claude-opus-5-5 · 📁 dir · 🌿 branch · 42% ctx · $1.23
# model.id is shown instead of display_name because it is unambiguous
# (claude-opus-4-8 vs claude-opus-5). Never fails: bad input -> empty line.
import json
import os
import subprocess
import sys


def git_branch(cwd):
    for cmd in (["git", "branch", "--show-current"], ["git", "rev-parse", "--short", "HEAD"]):
        try:
            out = subprocess.check_output(
                cmd, cwd=cwd, text=True, stderr=subprocess.DEVNULL, timeout=1
            ).strip()
        except Exception:
            out = ""
        if out:
            return out
    return ""


def main():
    try:
        data = json.load(sys.stdin)
    except Exception:
        return

    model_id = (data.get("model") or {}).get("id") or "?"

    ws = data.get("workspace") or {}
    cwd = ws.get("current_dir") or data.get("cwd") or ""
    dirname = os.path.basename(cwd.rstrip("/")) if cwd else ""

    branch = git_branch(cwd) if cwd else ""
    if not branch:
        branch = ws.get("git_worktree") or ""

    pct = int((data.get("context_window") or {}).get("used_percentage") or 0)
    cost = (data.get("cost") or {}).get("total_cost_usd") or 0

    parts = [f"⬡ {model_id}"]
    if dirname:
        parts.append(f"\U0001f4c1 {dirname}")
    if branch:
        parts.append(f"\U0001f33f {branch}")
    parts.append(f"{pct}% ctx")
    parts.append(f"${cost:.2f}")
    print(" · ".join(parts))


if __name__ == "__main__":
    main()
