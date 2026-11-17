# Деплой и запуск

Парсер — не сервис, а cron-джоба: прогон раз в N часов, lock от параллельного запуска, внешний таймаут. Есть два способа, выбирай по тому, нужен ли КриптоПро.

| | Docker (pp.trade.su, dp1, dp2) | venv (ВМ selenium 192.168.0.228) |
|---|---|---|
| Кто | rts_tender, rts_market, rts_selenium | gz_spb, utp_sberbank, rosatom |
| Когда | Chrome без ЭЦП, нужен прокси/масштаб | вход по ЭЦП (КриптоПро, сертификаты пользователя `cryptopro`), или просто requests |
| Браузер | `chromium` + `chromium-driver` + `xvfb` из apt | Chrome for Testing в `./browser/` (gz_spb) или Selenium Manager |
| Обновление | push в master → CI собирает образ `gitlab.trade.su:5050/parsers/<проект>:latest`, `run.sh` делает `docker pull` перед каждым прогоном | CI-джоба `deploy` на shell-раннере ВМ: `git reset --hard $SHA`, `pip install`, sanity-импорт |
| Откат | revert + push | Retry deploy-джобы старого пайплайна |

## Docker

**Dockerfile** (`rts_tender/Dockerfile`): `python:3.11-slim-bookworm`, `ENV PYTHONUNBUFFERED=1 CHROME_BINARY_PATH=/usr/bin/chromium CHROMEDRIVER_PATH=/usr/bin/chromedriver DISPLAY=:99`, apt `chromium chromium-driver xvfb fonts-liberation`, `ENTRYPOINT ["./docker-entrypoint.sh"]` (Xvfb → `exec python main.py`; почистить `/tmp/.X99-lock` от прошлого аварийного выхода).

Грабля: `COPY` перечисляет файлы поимённо — **новый модуль добавить в COPY** (ломалось дважды). Или копировать `*.py`.

**run.sh на сервере** (копия — `rts_tender/kb/raw/server/run.sh`):
- `PATH=...` явно (у cron урезанный, `docker` не найдётся);
- `exec 200>run.lock; flock -n 200 || exit 0` — пропуск, если прошлый прогон идёт;
- `docker pull`; не прошёл → письмо с хоста (`send_alert.py`, только stdlib) и `exit 1` — алерты внутри контейнера тут не сработают;
- `docker run --rm --network tenders_net --env-file .env -v logs:/app/logs -v /archive/...:/archive/...` (+ `--memory`/`--cpus` у rts_market);
- `timeout 3h`; коды 124 и 137 — оба «превышен лимит», удалить осиротевший контейнер.

`logs/` и архив монтируются снаружи — иначе дедупликация и статус не переживут `--rm`.

**CI** (`.gitlab-ci.yml`): `test` (образ python:3.11-slim, тег `docker`, фиктивные env на уровне джобы — не проекта, чтобы не перекрыть реальные секреты деплоя) → `docker-build` (push `:latest` и `:$CI_COMMIT_SHORT_SHA`) → у rts_market ещё `deploy` (`deploy/deploy.py`: scp/ssh на dp1/dp2, запись в примонтированный каталог на pp — ssh из docker-раннера до самого pp не работает, hairpin NAT).

Разовая диагностика в контейнере: `docker run --rm --network tenders_net --env-file .env -e DISABLE_PROXY=1 -v $PWD/diag.py:/app/diag.py --entrypoint sh <образ> -c "Xvfb :99 >/dev/null 2>&1 & sleep 1; python diag.py"`. `DISABLE_PROXY=1` обязателен, если скрипт зовёт функции в обход `main()` (моста нет → `ERR_PROXY_CONNECTION_FAILED`). Скрипт потом удалить, вывод — в базу знаний. Проверять, идёт ли прогон, через `docker ps`, не `pgrep -f` по ssh (найдёт сам себя).

## venv на ВМ selenium

- Каталог `/home/cryptopro/Work/<проект>`, владелец `cryptopro` (у него cron, сертификаты КриптоПро, SSH-ключ к GitLab). Историческое имя каталога может не совпадать с проектом (utp_sberbank → `selen`).
- `run.sh` — шаблон в `assets/run.sh`: подкоманды `yesterday` / `files`, `flock -n /tmp/<парсер>.lock`, `./venv/bin/python3`. Для Selenium с окном — `export DISPLAY=${DISPLAY:-:0}`. Внешний таймаут: `timeout -k 120 105m` (SIGTERM, через 2 мин SIGKILL).
- **Общий lock** для сбора и `--files`, если оба ходят на площадку с одного IP и вместе превысят лимит (rosatom). **Отдельный lock**, если файлы идут с другого хоста (ЕИС у rts_parser).
- `deploy/update.sh`: `set -eu`, `git fetch && git reset --hard $SHA` (`.env`, `venv/`, `logs/`, `browser/`, профили — в .gitignore), `pip install -r requirements.txt`, sanity `python -c "import <модули>"`, проверка, что в `.env` заданы обязательные переменные.
- `.gitlab-ci.yml`: `test` на том же shell-раннере (тег `rnis`) в своём `.ci-venv` + `py_compile` + `pytest` + `sh -n`/`bash -n` скриптов; `deploy` — `sudo su - cryptopro -c "sh -s $CI_COMMIT_SHA" < deploy/update.sh` (именно `su -`: у gitlab-runner без пароля только root; скрипт через stdin — каталог сборки раннера cryptopro не читает), `resource_group: production`.
- `deploy/crontab` — **для справки**, деплой его не ставит: crontab `cryptopro` общий с другими проектами. Строки добавляет пользователь вручную.

## Расписание

Типовое: сбор за сегодня каждые 2 часа; **добор вчерашнего** после полуночи (`--date вчера`) — иначе процедуры, опубликованные после последнего дневного прогона, теряются; докачка файлов каждые 15–60 минут. Сдвигай минуты относительно соседних парсеров на той же машине (gz_spb :00, rts_44 :30, rosatom :45).

## Переменные окружения

Имена — в `.env.example` (значения не коммитятся). Типовой набор: учётка площадки, `TENDERS_API_URL`, `<ПАРСЕР>_TENDERS_API_KEY`, `ARCHIVE_ROOT`/`DOWNLOAD_DIR`, прокси (`PROXY_API_TOKEN`, резерв `PROXY_HOST/PORT/USER/PASS`, `DISABLE_PROXY`, `LOCAL_PROXY_PORT`), почта для алертов/кода. Без pydantic — stdlib-парсер `.env` (не перезаписывает уже заданные переменные), см. `assets/tenders_api.py`.
