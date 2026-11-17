# Парсеры портфеля — карточки

Все проекты лежат в `/Users/b2b-connect/Doronin/<проект>`. Полные факты — в `KNOWLEDGE.md` каждого проекта (у rts_tender — `kb/wiki/`). Здесь — выжимка, чтобы выбрать ближайший образец.

## Сводная таблица

| Проект | Площадка | Доступ | Вход | Документы | Деплой |
|---|---|---|---|---|---|
| gz_spb `main.py` | estore.gz-spb.ru (госзакупки СПб) | Selenium | ЭЦП, КриптоПро, сертификат по имени организации | с карточки | venv, ВМ selenium |
| gz_spb `rts_parser.py` | app.rts-tender.ru (44-ФЗ, кабинет поставщика) | Selenium для входа → JSON API через requests | ЭЦП, сертификат по ФИО владельца | из ЕИС, отдельный режим `--files` | venv, ВМ selenium |
| utp_sberbank | utp.sberbank-ast.ru, 14 торговых секций | Selenium (headless) | логин/пароль | 5 способов + «Скачать все» zip | venv, ВМ selenium |
| rosatom | www.rosatom.rts-tender.ru (движок B2B-Center) | только requests | логин/пароль POST формы | только после входа, `--files` | venv, ВМ selenium |
| rts_market | ~34 витрины *.rts-tender.ru (market) | Selenium, Xvfb | SSO 223.rts-tender.ru, тенант, роль | кликом в браузере | Docker, 9 воркеров на pp/dp1/dp2 |
| rts_tender | 223.rts-tender.ru (223-ФЗ, коммерческие, ПП 615) | Selenium, Xvfb | логин/пароль | requests через прокси-мост | Docker, pp.trade.su |
| rts_selenium | www.rts-tender.ru (только 44-ФЗ) | Selenium, Xvfb | email + код из почты (IMAP) | из публичного ЕИС по рег. номеру | Docker |

Прокси (`proxy_config.py`, мост pproxy) есть у rts_market, rts_tender, rts_selenium и у `gz_spb/rts_parser.py`. У utp_sberbank, rosatom и `gz_spb/main.py` прокси нет.

## gz_spb

Два парсера в одном репозитории (`git@gitlab.trade.su:www/gz_spb.git`).

**main.py — estore.gz-spb.ru.** Вход на `account.gz-spb.ru/login-ecp` по сертификату: select2 со списком сертификатов, выбор по части имени организации (`GZ_SPB_CERT`). Затем `estore.gz-spb.ru/electronicshop/catalog/procedure/`, расширенный поиск по `publication_date_time-from`/`-to` (обе = искомый день, иначе «по» захватывает будущие даты), 50 карточек на страницу, `index.html` + `information.json`. С 2026-10-27 сайт включил HSTS, сертификат выпущен УЦ Минцифры → `site_key_pin()` (см. patterns.md).

**rts_parser.py — app.rts-tender.ru, 44-ФЗ.** Selenium только для входа: SSO `auth/sso/login`, строка таблицы сертификатов по ФИО владельца (`RTS_CERT_OWNER`), закрыть popup «Установите сертификат Минцифры» в shadow DOM, «Войти», дождаться Anti-DDoS. Дальше `requests.Session` с cookies браузера: `POST /supplier/lk/api/auction/search` (фильтр publicationDate в UTC от полуночи МСК), `GET /supplier/lk/api/{PurchaseMethod}/procedure/model`. Поля модели обёрнуты в `{"CurrentValue", "PreviousValue"}`. Архив `/archive/selenium/rts_44/<день>/<номер>/`: `search.json`, `model.json` (признак «собрано»), `documents.json`, `files/`. Документы — со страницы документов извещения в ЕИС (`EisDocumentUrl`), т.к. площадка отвечает 429/503 на каждый файл. Сессия пересоздаётся раз в сутки (`fresh_login`, очистка cookies через CDP): после суток работы старая получает 429/503 на поиск с любого IP.

Cron: gz_spb каждые 2 ч; rts — сбор каждые 2 ч со сдвигом :30, добор вчера 00:50, `--files` каждые 15 мин со своим lock.

## utp_sberbank

Логин на `login.sberbank-ast.ru` (`#mainContent_txtLoginName`, `#btnSignInLogin`, ждать ухода с login-хоста; `PdnConsent` в URL — только warning). 14 секций в `settings.SECTIONS`, каждая `…/{Секция}/List/PurchaseList` (или `BidList`). Фильтр `#PublicDateMin`/`#PublicDateMax` + `applyMainFilters()`, до 50 страниц.

Особенности:
- 3 вида вёрстки карточки: старая таблица `tr` из 2 ячеек; Vue-1 `div.a-text > .a-text__label + .a-text__row`; Vue-2 `div.table-element > p.label-text`. Повторы подписи → `"Подпись (2)"`.
- Время публикации есть только в списке → state-файл `published_at.json`; без него tenders-api ставит полночь МСК и процедура «уезжает» на прошлый день в UTC.
- `information.json` — это `repr()` питоновского списка, не JSON: формат зафиксирован внешним потребителем, менять нельзя.
- `platform` = `utp.sberbank-ast.ru/<Секция>` (хост + секция).
- Площадка иногда не применяет фильтр даты и отдаёт счётчик всего реестра → если счётчик > 5000, переприменить до 3 раз, иначе `FilterNotApplied`.
- Карточка Vue иногда не отрисовывается → до 3 попыток через разные прогоны, на последней сохраняется с пометкой.
- tenders-api недоступен 3 раза подряд → дальше в прогоне сразу в очередь `tenders_api_pending.json`, досылка в конце и в следующих прогонах (старше 7 дней — выбрасывать).
- chromedriver в своей группе процессов, при закрытии `os.killpg(SIGKILL)`; `healthcheck.py` считает зомби и осиротевшие Chrome.
- Алерты: Telegram и/или почта, дедупликация по ключу не чаще раза в 6 ч.

Cron: каждые 2 ч под `timeout -k 120 105m`, `--yesterday` в 00:40, healthcheck ежечасно.

## rosatom

B2B-Center под белой этикеткой: серверный HTML, UTF-8. Корень `/` — JS-челлендж, но `/market/` и карточки проходятся `requests` с cookie jar (первый заход — 3 редиректа через b2b-center.ru для синхронизации кук).

- Список без входа: `/market/?show=all&trade=all&date=1&date_start_dmy=DD.MM.YYYY&date_end_dmy=DD.MM.YYYY&from=N`, шаг 20, строки `table.search-results tbody tr`. Глубина `from` ограничена (~5000), с дневным фильтром не мешает.
- Карточка одна на все типы: `tr > td.fname` (метка с «:») + соседний `td`. Метку брать до вложенной подсказки.
- Лоты — отдельные страницы `tender-<id+N>`, ссылки в поле «Лоты:».
- Вход: GET страницы с формой `/auth/credentials_ajax_login.html` → все `input` формы (CSRFToken и т.п.) + логин/пароль → POST с `X-Requested-With: XMLHttpRequest` → `{"reload": "True"}`. Гость узнаётся по `data-is-guest="1"`.
- Документация: форма «Скачать документацию» (`<input type=submit>`, не `<a>` — поиск ссылок её не видит!) → `/market/view.html?id=<id>&action=register` → `div.file_download_link > a[href*="download.html?checksum="]`, имя файла в `<b>` (Content-Disposition в кракозябрах). Файл отдаётся только с сессией → в tenders-api `local_path`.
- Документацию выкладывают позже («Не загружена») → `--files` перечитывает такие карточки (`RECHECK_HOURS=3`, `RECHECK_DAYS=3`).
- **Лимит скорости**: ~150–180 запросов с паузой 0.5 с → капча по IP на 40+ мин. Пауза 6 с (`ROSATOM_REQUEST_INTERVAL`) капчи не даёт. При капче прогон сразу останавливается (`Captcha`), запросы во время бана могут его продлевать. Сбор и `--files` под общим lock — с одного IP.
- Список сдвигается, пока его листаешь (новое сверху) — выпавшую строку подберёт следующий прогон.

## rts_market

~34 витрины `*.rts-tender.ru` (из них активны 26, см. `deploy/domains.csv`). Один процесс = один Chrome = свой подсписок доменов (`MARKET_DOMAINS`), параллелизм — 9 контейнеров на pp/dp1/dp2, раскладка LPT-упаковкой по весу домена (`deploy/balance.py`).

- Вход через SSO 223.rts-tender.ru: «ВХОД» → «223» → (вкладка «Учётная запись» есть не у всех тенантов) → `#Login`/`#Password` → видимая `button.marketSignIn` или `input#submitSignin` → выбор тенанта → выбор роли. SSO общая: на втором домене прогона форма логина пропускается. Неверный пароль не меняет URL — проверять, что ушли с `223.rts-tender.ru`/`authorization`.
- Роль площадка сбрасывает — переизбирать до 3 раз.
- Список: `article.catalog__strip[id="position<id>"]`, пагинация кликом `button.p-paginator-next` (PrimeNG). Карточка: `li.list__item > .list__key + .list__value`. Карточка заказчика `/company/<id>/info` → блок `customer`.
- Порядок доменов сдвигается на 1 каждый прогон, чтобы тяжёлые домены в начале не копили отставание.
- `platform` = реальный домен заявки → в ключе tenders-api `allowed_platforms` должны быть ВСЕ домены.
- Все домены провалились → повтор прогона со свежим прокси-IP (выданный IP бывает уже забанен).

## rts_tender (rts_tender_full)

223.rts-tender.ru, ASP.NET WebForms. Самая подробная база знаний — `kb/wiki/` (инциденты, runbook).

- Логин `MainContent_txtUserName`/`txtUserPassword`/`btnLogin`; провал = форма осталась на экране.
- Поиск `Trade/Search.aspx`, jqGrid `BaseMainContent_MainContent_jqgTrade`. Фильтр «опубликовано от» = сегодня (или `FILTER_DATE_FROM`), размер страницы 100 (необязательно), **сортировка по возрастанию даты**.
- **Чекбоксы типа закупки не трогать**: они значат «только отмеченные», даже все шесть отсекают закупки без типа (~1.3% в день).
- Пейджер «из 9 900» — заглушка, реальный итог только на последней странице.
- Карточка `<fieldset><label>…</label><span>…</span></fieldset>`, документы только из jqGrid `…jqgTradeDocs` (`a[href*="FileDownloadHandler"]`). Папка дня — по списку подписей даты публикации (зависит от вида закупки).
- Две вкладки: грид (не перезагружать — потеряешь позицию) и вкладка карточек.
- Дедупликация — `logs/processed_items.txt` (append-only, необратимо).
- Время в контейнере UTC, на сервере МСК.

## rts_selenium

www.rts-tender.ru, только 44-ФЗ (223 и market вынесены в отдельные проекты). Карточки «Извещение на площадке» с других ЭТП пропускаются, это не ошибка.

- Вход на passport.rts-tender.ru: email → «по паролю» → код подтверждения из письма (IMAP Яндекса, тема «Код подтверждения», последнее непрочитанное) → Anti-DDoS → настройки фильтров кликами.
- Документы: прямые ссылки app.rts-tender.ru отдают 404 даже с сессией → публичный ЕИС `zakupki.gov.ru/epz/order/notice/zk20/view/documents.html` по регистрационному номеру.
- Временный 503 у площадки → переоткрыть ссылку до 3 раз с растущей паузой (это не Anti-DDoS, ждать readyState бесполезно).
- `MAX_CONSECUTIVE_ITEM_FAILURES = 15` — сессия тихо разлогинилась, без предохранителя контейнер висел 6+ часов.
- При сбое логина — скриншот + HTML в `logs/` (`save_failure_diagnostics`).
