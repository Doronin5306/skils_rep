---
name: statusline
description: Настраивает строку статуса Claude Code - внизу терминала показываются точный id модели, текущая папка, ветка git, заполненность контекста в процентах и стоимость сессии (как в digitender-platform). Ставит глобально в ~/.claude/settings.json или в конкретный проект, умеет снять. Используй, когда пользователь просит настроить или поменять статус-строку, статусбар, показывать модель / ветку / контекст / стоимость внизу, перенести статус-строку из другого проекта, а также когда строка статуса пропала или ломается. English - status line, statusline, statusbar, show model branch context cost.
---

# Statusline

Строка статуса вида:

```
⬡ claude-opus-5-5 · 📁 skils_rep · 🌿 main · 42% ctx · $1.23
```

Показывается `model.id`, а не display name — он однозначен (claude-opus-4-8 vs claude-opus-5). Ветка берётся из git (`branch --show-current`, при detached HEAD — короткий sha), с фолбэком на `workspace.git_worktree`.

Файлы (пути относительно папки скила):
- `scripts/statusline.py` — сам скрипт: читает JSON сессии из stdin, печатает одну строку. На любой ошибке молча печатает пустоту — строка статуса не должна валить сессию.
- `scripts/install_statusline.py` — прописывает `statusLine` в settings.json, не трогая остальные ключи, делает `.bak`.

## Установка

Глобально (все проекты) — вариант по умолчанию:

```bash
python3 scripts/install_statusline.py
```

Команда ссылается на `~/.claude/skills/statusline/scripts/statusline.py`, то есть на симлинк скила — правки в репозитории подхватываются сразу. Поэтому скил должен быть установлен через `install.sh`.

В один проект (скрипт копируется в `<DIR>/.claude/statusline.py`, чтобы проект был самодостаточен и работал у коллег):

```bash
python3 scripts/install_statusline.py --project <DIR>
```

Снять: `--uninstall [--project DIR]`.

Учти приоритет настроек: project `.claude/settings.json` перекрывает глобальный. Если в проекте свой `statusLine`, глобальный там не виден — это нормально (например, в digitender-platform стоит такой же скрипт).

Если `statusLine` уже есть и он не наш (в команде нет `statusline.py`), установщик откажется. Покажи пользователю текущее значение и спроси; заменять — только с `--force` и его согласия.

## Проверка

```bash
echo '{"model":{"id":"claude-opus-5-5"},"workspace":{"current_dir":"'"$PWD"'"},"context_window":{"used_percentage":42},"cost":{"total_cost_usd":1.234}}' | python3 scripts/statusline.py
```

Новая строка видна сразу или после следующего сообщения в сессии; перезапуск не нужен.

## Изменить содержимое строки

Правь `scripts/statusline.py`. Поля входного JSON: `model.id`, `model.display_name`, `workspace.current_dir`, `workspace.project_dir`, `cwd`, `context_window.used_percentage`, `cost.total_cost_usd`, `cost.total_duration_ms`, `cost.total_lines_added/removed`, `session_id`, `transcript_path`, `version`, `output_style.name`. Держи скрипт быстрым (он вызывается часто): никаких сетевых вызовов, у git-команд таймаут.
