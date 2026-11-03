#!/usr/bin/env python3
"""Храповик уровня тестирования: уровень можно повышать, понижать — нельзя.

Базовая линия хранится в <проект>/.test-ratchet.json.

Команды:
  init   [--level N]                               создать базовую линию (по умолчанию уровень 3)
  status                                           показать базовую линию
  check  --level N --tests T [--coverage C]        сравнить текущие метрики с базовой линией
  update --level N --tests T [--coverage C]        check + записать новые максимумы
  raise  --level N                                 поднять уровень (понизить нельзя)
  guard  [--base REF]                              найти ослабление тестов в git-изменениях

Общие опции: --root PATH (по умолчанию — корень git-репозитория или текущая папка).
Код выхода 1 — найдено понижение/ослабление, 2 — ошибка использования.
"""
import argparse
import datetime
import json
import os
import re
import subprocess
import sys

BASELINE = ".test-ratchet.json"
MIN_LEVEL, MAX_LEVEL, DEFAULT_LEVEL = 1, 5, 3

TEST_PATH_RE = re.compile(
    r"(^|/)(tests?|__tests__|spec|src/test)/"
    r"|(^|/)test_[^/]+\.py$|_test\.(py|go)$"
    r"|\.(test|spec)\.(js|jsx|ts|tsx|mjs|cjs)$"
    r"|Tests?\.(java|kt|cs)$"
)
TEST_DEF_RE = re.compile(
    r"^\s*(async\s+)?def\s+test_\w*"           # python
    r"|\b(it|test)\s*\(\s*['\"`]"              # js/ts
    r"|^func\s+Test\w*\s*\("                   # go
    r"|@Test\b"                                # java/kotlin
    r"|#\[(tokio::)?test\]"                    # rust
    r"|\[(Fact|Theory|Test|TestMethod)\]",     # c#
    re.M,
)
ASSERT_RE = re.compile(
    r"\bassert\w*\b|\bexpect\s*\(|\bt\.(Error|Errorf|Fatal|Fatalf|Fail)\b"
    r"|\brequire\.\w+\(|\bshould\b|\bAssert\.\w+\(|\bpytest\.raises\b"
)
SKIP_RE = re.compile(
    r"@pytest\.mark\.(skip|skipif|xfail)|\bpytest\.(skip|xfail)\s*\(|@unittest\.(skip\w*|expectedFailure)"
    r"|\b(it|test|describe)\.(skip|only|todo)\s*\(|\b(xit|xtest|xdescribe|fit|fdescribe)\s*\("
    r"|\bt\.Skip(f|Now)?\s*\(|#\[ignore\]|@(Disabled|Ignore)\b|\[Ignore\]|\bSkip\s*="
)
THRESHOLD_RE = re.compile(
    r"(fail[_-]under|cov-fail-under|coverageThreshold|minimum_coverage|min[_-]coverage"
    r"|branches|lines|functions|statements)\s*[:=]?\s*[\"']?(\d+(\.\d+)?)",
    re.I,
)
CONFIG_NAMES = (
    "pyproject.toml", "setup.cfg", "tox.ini", ".coveragerc", "pytest.ini",
    "package.json", "jest.config.js", "jest.config.ts", "vitest.config.ts", "vitest.config.js",
    ".nycrc", ".nycrc.json", "codecov.yml", ".codecov.yml", "Makefile",
)


def git(root, *args, check=True):
    r = subprocess.run(["git", "-C", root] + list(args), capture_output=True, text=True)
    if check and r.returncode != 0:
        raise RuntimeError(r.stderr.strip() or "git %s failed" % " ".join(args))
    return r.stdout


def find_root(explicit):
    if explicit:
        return os.path.abspath(explicit)
    try:
        return git(os.getcwd(), "rev-parse", "--show-toplevel").strip()
    except Exception:
        return os.getcwd()


def load(root):
    p = os.path.join(root, BASELINE)
    if not os.path.exists(p):
        return None
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def save(root, data):
    data["updated"] = datetime.date.today().isoformat()
    with open(os.path.join(root, BASELINE), "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")


def need_baseline(root):
    b = load(root)
    if b is None:
        print("ERROR: нет %s — сначала: ratchet.py init" % BASELINE)
        sys.exit(2)
    return b


def compare(b, level, tests, coverage):
    errors = []
    if level < b["level"]:
        errors.append("уровень понижен: %d < %d" % (level, b["level"]))
    if b.get("tests") is not None and tests < b["tests"]:
        errors.append("тестов стало меньше: %d < %d" % (tests, b["tests"]))
    if b.get("coverage") is not None:
        if coverage is None:
            errors.append("покрытие не измерено, а в базовой линии %.2f%% — измерение нельзя отключать" % b["coverage"])
        elif coverage + 0.01 < b["coverage"]:
            errors.append("покрытие снизилось: %.2f%% < %.2f%%" % (coverage, b["coverage"]))
    return errors


def cmd_init(root, a):
    if load(root) is not None:
        print("ERROR: %s уже есть. Понизить нельзя; поднять — `raise`." % BASELINE)
        sys.exit(2)
    lvl = a.level or DEFAULT_LEVEL
    save(root, {"level": lvl, "tests": None, "coverage": None, "history": [
        {"date": datetime.date.today().isoformat(), "event": "init", "level": lvl}]})
    print("Создан %s, уровень %d" % (os.path.join(root, BASELINE), lvl))


def cmd_status(root, a):
    print(json.dumps(need_baseline(root), ensure_ascii=False, indent=2))


def cmd_check(root, a, write=False):
    b = need_baseline(root)
    errors = compare(b, a.level, a.tests, a.coverage)
    if errors:
        print("RATCHET FAIL — уровень тестирования понижен:")
        for e in errors:
            print("  - " + e)
        sys.exit(1)
    print("RATCHET OK: уровень %d (база %d), тестов %d (база %s), покрытие %s (база %s)" % (
        a.level, b["level"], a.tests, b.get("tests"),
        "-" if a.coverage is None else "%.2f%%" % a.coverage,
        "-" if b.get("coverage") is None else "%.2f%%" % b["coverage"]))
    if write:
        new = dict(b)
        new["level"] = max(b["level"], a.level)
        new["tests"] = max(b.get("tests") or 0, a.tests)
        if a.coverage is not None:
            new["coverage"] = round(max(b.get("coverage") or 0.0, a.coverage), 2)
        new.setdefault("history", []).append({
            "date": datetime.date.today().isoformat(), "event": "update",
            "level": new["level"], "tests": new["tests"], "coverage": new.get("coverage")})
        save(root, new)
        print("Базовая линия обновлена.")


def cmd_raise(root, a):
    b = need_baseline(root)
    if a.level < b["level"]:
        print("ERROR: понижать уровень нельзя (%d → %d)." % (b["level"], a.level))
        sys.exit(1)
    if a.level == b["level"]:
        print("Уровень уже %d." % a.level)
        return
    old = b["level"]
    b["level"] = a.level
    b.setdefault("history", []).append({"date": datetime.date.today().isoformat(), "event": "raise",
                                        "from": old, "level": a.level})
    save(root, b)
    print("Уровень поднят: %d → %d" % (old, a.level))


def cmd_guard(root, a):
    base = a.base
    try:
        git(root, "rev-parse", "--verify", base + "^{commit}")
    except Exception:
        print("guard: базовая ревизия %r не найдена (нет коммитов?) — проверка пропущена" % base)
        return
    issues = []
    status = git(root, "diff", "--name-status", "-M", base)
    for line in status.splitlines():
        parts = line.split("\t")
        code = parts[0]
        old_path = parts[1]
        new_path = parts[-1]
        is_test = TEST_PATH_RE.search(old_path) or TEST_PATH_RE.search(new_path)
        is_cfg = os.path.basename(new_path) in CONFIG_NAMES or new_path == BASELINE

        if code.startswith("D") and is_test:
            issues.append("удалён тестовый файл: %s" % old_path)
            continue
        if not (is_test or is_cfg):
            continue
        old = git(root, "show", "%s:%s" % (base, old_path), check=False)
        new_full = os.path.join(root, new_path)
        new = open(new_full, encoding="utf-8", errors="replace").read() if os.path.exists(new_full) else ""

        if new_path == BASELINE:
            try:
                ob, nb = json.loads(old or "{}"), json.loads(new or "{}")
                for k in ("level", "tests", "coverage"):
                    if ob.get(k) is not None and (nb.get(k) is None or nb[k] < ob[k]):
                        issues.append("%s: %s понижен вручную (%s → %s)" % (BASELINE, k, ob.get(k), nb.get(k)))
            except ValueError:
                issues.append("%s повреждён" % BASELINE)
            continue

        if is_test:
            od, nd = len(TEST_DEF_RE.findall(old)), len(TEST_DEF_RE.findall(new))
            if nd < od:
                issues.append("%s: тестов стало меньше (%d → %d)" % (new_path, od, nd))
            oa, na = len(ASSERT_RE.findall(old)), len(ASSERT_RE.findall(new))
            if na < oa:
                issues.append("%s: проверок (assert/expect) стало меньше (%d → %d)" % (new_path, oa, na))
            os_, ns = len(SKIP_RE.findall(old)), len(SKIP_RE.findall(new))
            if ns > os_:
                issues.append("%s: добавлены skip/xfail/only (%d → %d)" % (new_path, os_, ns))

        if is_cfg:
            ot = {m.group(1).lower(): float(m.group(2)) for m in THRESHOLD_RE.finditer(old)}
            nt = {m.group(1).lower(): float(m.group(2)) for m in THRESHOLD_RE.finditer(new)}
            for k, v in ot.items():
                if k not in nt:
                    issues.append("%s: убран порог %s (был %g)" % (new_path, k, v))
                elif nt[k] < v:
                    issues.append("%s: порог %s понижен (%g → %g)" % (new_path, k, v, nt[k]))

    # Новые (неотслеживаемые) тестовые файлы со skip
    for path in git(root, "ls-files", "--others", "--exclude-standard").splitlines():
        if TEST_PATH_RE.search(path):
            full = os.path.join(root, path)
            try:
                if SKIP_RE.search(open(full, encoding="utf-8", errors="replace").read()):
                    issues.append("%s: новый тестовый файл содержит skip/xfail/only" % path)
            except OSError:
                pass

    if issues:
        print("GUARD FAIL — тесты ослаблены относительно %s:" % base)
        for i in issues:
            print("  - " + i)
        print("Если изменение обоснованно (например, тест был ошибочным) — нужно согласие всех трёх агентов или человека.")
        sys.exit(1)
    print("GUARD OK: ослабления тестов относительно %s не найдено" % base)


def main():
    p = argparse.ArgumentParser(description="Храповик уровня тестирования")
    p.add_argument("--root")
    sub = p.add_subparsers(dest="cmd")
    s = sub.add_parser("init"); s.add_argument("--level", type=int)
    sub.add_parser("status")
    for name in ("check", "update"):
        s = sub.add_parser(name)
        s.add_argument("--level", type=int, required=True)
        s.add_argument("--tests", type=int, required=True, help="число тестов в полном прогоне")
        s.add_argument("--coverage", type=float, help="покрытие, %%")
    s = sub.add_parser("raise"); s.add_argument("--level", type=int, required=True)
    s = sub.add_parser("guard"); s.add_argument("--base", default="HEAD")
    a = p.parse_args()
    if not a.cmd:
        p.print_help()
        sys.exit(2)
    lvl = getattr(a, "level", None)
    if lvl is not None and not (MIN_LEVEL <= lvl <= MAX_LEVEL):
        print("ERROR: уровень должен быть от %d до %d" % (MIN_LEVEL, MAX_LEVEL))
        sys.exit(2)
    root = find_root(a.root)
    {"init": cmd_init, "status": cmd_status, "raise": cmd_raise, "guard": cmd_guard,
     "check": lambda r, x: cmd_check(r, x), "update": lambda r, x: cmd_check(r, x, write=True)}[a.cmd](root, a)


if __name__ == "__main__":
    main()
