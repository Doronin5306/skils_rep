# Скилы для Claude Code

Личная коллекция скилов. Каждый скил — папка в `skills/` с файлом `SKILL.md`.

## Установка

```bash
./install.sh            # все скилы → симлинки в ~/.claude/skills/
./install.sh <name>     # один скил
./install.sh --uninstall <name>
```

Симлинки означают, что правки в репозитории сразу подхватываются Claude Code (в новой сессии).

## Как добавить скил

Попроси Claude: «сделай скил для …» — сработает `skill-builder`, который создаст каркас, поможет написать SKILL.md, проверит его, установит и обновит этот каталог.

Вручную:

```bash
python3 skills/skill-builder/scripts/init_skill.py my-skill
# … заполнить skills/my-skill/SKILL.md …
python3 skills/skill-builder/scripts/validate_skill.py skills/my-skill
./install.sh my-skill
python3 skills/skill-builder/scripts/update_catalog.py
```

## Каталог

<!-- skills:start -->
| Скил | Описание |
|---|---|
| [`agent-orchestrator`](skills/agent-orchestrator/SKILL.md) | Оркестратор команды агентов в отдельных сессиях Claude Code - ведёт проект по ROADMAP.md или tasks.md (если плана нет - подробно опрашивает пользователя и сост… |
| [`llm-wiki`](skills/llm-wiki/SKILL.md) | Создаёт и ведёт базу знаний по схеме LLM Wiki Андрея Карпати — Claude сам пишет и поддерживает связанную markdown-вики (Obsidian) из сырых источников - статей,… |
| [`skill-builder`](skills/skill-builder/SKILL.md) | Создаёт новые скилы для Claude Code и дорабатывает существующие в личном репозитории скилов (/Users/b2b-connect/Doronin/skils_rep) |
| [`test-council`](skills/test-council/SKILL.md) | Тестирует код советом из трёх агентов — Оптимист, Реалист, Пессимист — которые независимо гоняют полный набор тестов, пишут новые общие тесты и аргументированн… |
<!-- skills:end -->
