#!/usr/bin/env python3
"""Прогон мутантов для pytest: каждый мутант обязан уронить ИМЕННО свой тест.

Мутант — это код БЕЗ проверяемой правки. Для каждого мутанта скрипт:
  1. контрольный прогон на чистом коде — тесты запустились (>0), всё зелёное,
     ожидаемый тест есть среди прошедших (имя написано верно и тест собирается);
  2. применяет мутант (замена строки / откат коммита / патч) и проверяет,
     что файл действительно изменился;
  3. прогоняет те же тесты, каждый прогон — со свежим PYTHONPYCACHEPREFIX
     (устаревший .pyc той же секунды и того же размера иначе подменит мутант);
  4. сверяет ИМЯ упавшего теста с ожидаемым;
  5. возвращает файл байт-в-байт и после всех мутантов делает прогон отката —
     он обязан быть зелёным.

Запуск:
  mutate.py SPEC.json [--only ID ...] [--json-out FILE]
  mutate.py --path F --replace OLD NEW --expect TEST [--tests T ...] [--cmd "..."]
  mutate.py --path F --revert SHA --expect TEST ...

Код возврата: 0 — все мутанты KILLED; 1 — есть иные вердикты; 2 — ошибка ввода.
"""
import argparse
import json
import os
import re
import shlex
import subprocess
import sys
import tempfile

PYTEST_FLAGS = ["-rA", "-p", "no:cacheprovider", "--color=no"]
SUMMARY_RE = re.compile(r"^(PASSED|FAILED|ERROR|SKIPPED|XFAIL|XPASS)\s+(\S+)")
COUNT_RE = re.compile(r"(\d+) (passed|failed|errors?|skipped|xfailed|xpassed)")

VERDICT_HELP = {
    "KILLED": "упал ожидаемый тест — правка доказана",
    "WRONG_TEST": "упал не тот тест — вероятно прежний байткод или тест мерит другое; правка НЕ доказана",
    "SURVIVED": "ни один тест не упал — разбор: пустой мутант / слабый тест / правка-пустышка",
    "BROKEN_MUTANT": "мутант ломает сбор или импорт (ERROR), а не поведение — переписать мутант",
    "NO_TESTS": "прогон не запустил ни одного теста — врёт прибор, а не мутация",
    "EMPTY_DIFF": "мутант не изменил файл — переписать мутант",
    "CONTROL_RED": "на чистом коде цели не зелёные или ожидаемого теста нет среди прошедших",
    "APPLY_FAILED": "мутант не применился (строка не найдена/неоднозначна, патч не лёг)",
}


def die(msg):
    print("ОШИБКА: " + msg, file=sys.stderr)
    sys.exit(2)


def git(args, cwd, check=True, input_text=None):
    r = subprocess.run(["git"] + args, cwd=cwd, capture_output=True, text=True, input=input_text)
    if check and r.returncode != 0:
        raise RuntimeError("git %s: %s" % (" ".join(args), r.stderr.strip()))
    return r


def run_tests(cmd, targets, cwd, env_extra):
    """Один прогон pytest со свежим кэшем байткода. Возвращает dict с итогами."""
    cache_dir = tempfile.mkdtemp(prefix="mutpyc-")
    env = dict(os.environ)
    env.update(env_extra)
    env["PYTHONPYCACHEPREFIX"] = cache_dir
    full = cmd + PYTEST_FLAGS + list(targets)
    r = subprocess.run(full, cwd=cwd, capture_output=True, text=True, env=env)
    out = r.stdout + "\n" + r.stderr
    res = {"passed": set(), "failed": set(), "error": set(), "skipped": set(),
           "ran": 0, "rc": r.returncode, "tail": "\n".join(out.strip().splitlines()[-15:])}
    for line in out.splitlines():
        m = SUMMARY_RE.match(line.strip())
        if not m:
            continue
        kind, node = m.group(1), m.group(2)
        key = {"PASSED": "passed", "XPASS": "passed", "FAILED": "failed", "ERROR": "error"}.get(kind, "skipped")
        res[key].add(node)
    counts = {}
    for line in out.splitlines()[::-1]:
        found = COUNT_RE.findall(line)
        if found:
            for n, k in found:
                counts[k.rstrip("s") if k.startswith("error") else k] = int(n)
            break
    res["ran"] = counts.get("passed", 0) + counts.get("failed", 0) + counts.get("xpassed", 0)
    return res


def name_matches(node, expect):
    """expect — полный nodeid, или имя теста (test_x), или Class::test_x."""
    if node == expect:
        return True
    base = node.split("[", 1)[0]
    return base == expect or base.endswith("::" + expect)


def hits(nodes, expect):
    return sorted(n for n in nodes if name_matches(n, expect))


def apply_mutant(m, cwd):
    """Применяет мутант. Возвращает (ok, сообщение)."""
    path = os.path.join(cwd, m["path"])
    if "replace" in m:
        old, new = m["replace"]
        with open(path, encoding="utf-8") as f:
            text = f.read()
        n = text.count(old)
        if n != 1:
            return False, "строка для замены встречается %d раз(а), нужно ровно 1" % n
        with open(path, "w", encoding="utf-8") as f:
            f.write(text.replace(old, new, 1))
        return True, ""
    top = git(["rev-parse", "--show-toplevel"], cwd).stdout.strip()
    rel = os.path.relpath(os.path.abspath(path), top)
    if "revert" in m:
        sha = m["revert"]
        diff = git(["diff", sha + "^", sha, "--", rel], top).stdout
        if not diff.strip():
            return False, "коммит %s не меняет %s" % (sha, rel)
        r = git(["apply", "-R", "--include", rel, "-"], top, check=False, input_text=diff)
    elif "patch" in m:
        with open(os.path.join(cwd, m["patch"]), encoding="utf-8") as f:
            diff = f.read()
        r = git(["apply", "--include", rel, "-"], top, check=False, input_text=diff)
    else:
        return False, "у мутанта нет replace / revert / patch"
    if r.returncode != 0:
        return False, "git apply: " + r.stderr.strip()
    return True, ""


def check_committed(path, cwd):
    r = git(["status", "--porcelain", "--", path], cwd, check=False)
    if r.returncode != 0:
        return "файл не в git-репозитории"
    if r.stdout.strip():
        return "есть незакоммиченные изменения (мутации — только по закоммиченному коду)"
    return None


def evaluate(m, cmd, cwd, env, control_cache, allow_dirty):
    mid = m.get("id", m["path"])
    expects = m["expect"] if isinstance(m["expect"], list) else [m["expect"]]
    targets = tuple(m.get("tests", []))
    row = {"id": mid, "path": m["path"], "expect": expects, "why": m.get("why", ""),
           "failed": [], "verdict": None, "note": ""}

    if not allow_dirty:
        bad = check_committed(m["path"], cwd)
        if bad:
            die("%s: %s: %s" % (mid, m["path"], bad))

    if targets not in control_cache:
        control_cache[targets] = run_tests(cmd, targets, cwd, env)
    ctl = control_cache[targets]
    if ctl["ran"] == 0:
        row["verdict"], row["note"] = "NO_TESTS", "контроль: 0 тестов\n" + ctl["tail"]
        return row
    missing = [e for e in expects if not hits(ctl["passed"], e)]
    if ctl["failed"] or ctl["error"] or missing:
        row["verdict"] = "CONTROL_RED"
        row["note"] = "упали на чистом коде: %s; нет среди прошедших: %s" % (
            sorted(ctl["failed"] | ctl["error"]) or "-", missing or "-")
        return row
    row["control_ran"] = ctl["ran"]

    path = os.path.join(cwd, m["path"])
    with open(path, "rb") as f:
        original = f.read()
    try:
        ok, msg = apply_mutant(m, cwd)
        if not ok:
            row["verdict"], row["note"] = "APPLY_FAILED", msg
            return row
        with open(path, "rb") as f:
            if f.read() == original:
                row["verdict"] = "EMPTY_DIFF"
                return row
        res = run_tests(cmd, targets, cwd, env)
    finally:
        with open(path, "wb") as f:
            f.write(original)

    row["failed"] = sorted(res["failed"])
    killed = [e for e in expects if hits(res["failed"], e)]
    if res["ran"] == 0 and not res["error"]:
        row["verdict"], row["note"] = "NO_TESTS", res["tail"]
    elif len(killed) == len(expects):
        row["verdict"] = "KILLED"
        extra = sorted(set(res["failed"]) - set(sum((hits(res["failed"], e) for e in expects), [])))
        if extra:
            row["note"] = "заодно упали: " + ", ".join(extra)
    elif res["error"] and not res["failed"]:
        row["verdict"], row["note"] = "BROKEN_MUTANT", "ERROR: " + ", ".join(sorted(res["error"]))
    elif res["failed"]:
        row["verdict"] = "WRONG_TEST"
        row["note"] = "не упали ожидаемые: " + ", ".join(e for e in expects if e not in killed)
    else:
        row["verdict"] = "SURVIVED"
    return row


def load_spec(args):
    if args.spec:
        with open(args.spec, encoding="utf-8") as f:
            spec = json.load(f)
        base = os.path.dirname(os.path.abspath(args.spec))
        cwd = spec.get("cwd", ".")
        spec["cwd"] = cwd if os.path.isabs(cwd) else os.path.normpath(os.path.join(base, cwd))
    else:
        if not (args.path and args.expect):
            die("нужен SPEC.json или --path и --expect")
        m = {"id": args.id or "m1", "path": args.path, "expect": args.expect, "tests": args.tests or []}
        if args.replace:
            m["replace"] = args.replace
        elif args.revert:
            m["revert"] = args.revert
        elif args.patch:
            m["patch"] = args.patch
        else:
            die("укажи мутант: --replace OLD NEW, --revert SHA или --patch FILE")
        spec = {"cwd": args.cwd or ".", "mutants": [m]}
    if args.cmd:
        spec["cmd"] = args.cmd
    if args.cwd and args.spec:
        spec["cwd"] = args.cwd
    spec.setdefault("cmd", "python3 -m pytest")
    spec.setdefault("env", {})
    if not spec.get("mutants"):
        die("в спеке нет mutants")
    for m in spec["mutants"]:
        if "path" not in m or "expect" not in m:
            die("у каждого мутанта обязательны path и expect: %r" % m.get("id"))
    return spec


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("spec", nargs="?")
    p.add_argument("--only", nargs="+", help="прогнать только мутанты с этими id")
    p.add_argument("--json-out")
    p.add_argument("--cmd", help='команда pytest, по умолчанию "python3 -m pytest"')
    p.add_argument("--cwd")
    p.add_argument("--allow-dirty", action="store_true", help="не требовать закоммиченного файла")
    p.add_argument("--id")
    p.add_argument("--path")
    p.add_argument("--replace", nargs=2, metavar=("OLD", "NEW"))
    p.add_argument("--revert", metavar="SHA")
    p.add_argument("--patch")
    p.add_argument("--expect", nargs="+")
    p.add_argument("--tests", nargs="+")
    args = p.parse_args()

    spec = load_spec(args)
    cwd = spec["cwd"]
    if not os.path.isdir(cwd):
        die("нет каталога " + cwd)
    cmd = shlex.split(spec["cmd"])
    env = {k: str(v) for k, v in spec["env"].items()}
    mutants = [m for m in spec["mutants"] if not args.only or m.get("id") in args.only]
    if not mutants:
        die("после --only не осталось мутантов")

    control_cache = {}
    rows = []
    for m in mutants:
        row = evaluate(m, cmd, cwd, env, control_cache, args.allow_dirty)
        rows.append(row)
        print("[%s] %s — %s" % (row["verdict"], row["id"], ", ".join(row["failed"]) or "ничего не упало"),
              flush=True)

    # Прогон отката: код возвращён, кэш свежий — всё обязано быть зелёным.
    restore = []
    for targets in control_cache:
        r = run_tests(cmd, targets, cwd, env)
        restore.append({"tests": list(targets) or ["<все>"], "ran": r["ran"],
                        "red": sorted(r["failed"] | r["error"])})
    for m in mutants:
        if not args.allow_dirty and check_committed(m["path"], cwd):
            restore.append({"tests": [m["path"]], "ran": 0, "red": ["файл не совпадает с HEAD после отката"]})

    print("\n| id | ожидаемый тест | упали | вердикт | примечание |")
    print("|---|---|---|---|---|")
    for r in rows:
        note = r["note"].replace("\n", " ")[:200]
        print("| %s | %s | %s | **%s** | %s |" % (r["id"], ", ".join(r["expect"]),
              ", ".join(r["failed"]) or "-", r["verdict"], note))
    ctl = ", ".join("%s: %d" % (" ".join(t) or "<все>", c["ran"]) for t, c in control_cache.items())
    print("\nКонтроль на чистом коде (запущено тестов): " + ctl)
    for r in restore:
        state = "зелёный" if not r["red"] else "КРАСНЫЙ: " + ", ".join(r["red"])
        print("Прогон отката (%s): %d тестов, %s" % (" ".join(r["tests"]), r["ran"], state))
    print("Кэш байткода: свежий PYTHONPYCACHEPREFIX на каждый прогон")
    for v in sorted({r["verdict"] for r in rows} - {"KILLED"}):
        print("  %s — %s" % (v, VERDICT_HELP[v]))

    if args.json_out:
        with open(args.json_out, "w", encoding="utf-8") as f:
            json.dump({"mutants": rows, "control": {" ".join(t): c["ran"] for t, c in control_cache.items()},
                       "restore": restore}, f, ensure_ascii=False, indent=2)

    ok = all(r["verdict"] == "KILLED" for r in rows) and all(not r["red"] for r in restore)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
