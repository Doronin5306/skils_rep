# Проверенные фрагменты кода

Каждый фрагмент взят из рабочего парсера и уже пережил прод. Источник указан — при сомнении открой оригинал.

## Содержание
1. Chrome для Selenium (Xvfb, прокси, Docker)
2. Chrome с КриптоПро (вход по ЭЦП)
3. Сертификаты УЦ Минцифры
4. Ожидания: readyState, Anti-DDoS, 503, клик
5. Вход: ретраи, код из почты, диагностика
6. Selenium → requests (перенос cookies)
7. HTTP-клиент с темпом и ретраями
8. Имена файлов документов
9. Скачивание документов
10. Дедупликация и статус прогона
11. Предохранители основного цикла
12. Алерты
13. Логи

## 1. Chrome для Selenium — `rts_tender/main.py: build_chrome_options`

```python
options = webdriver.ChromeOptions()
if not DISABLE_PROXY:
    options.add_argument(f"--proxy-server={LOCAL_HOST}:{LOCAL_PORT}")   # мост pproxy, см. assets/proxy_config.py
options.set_capability('pageLoadStrategy', 'eager')
options.add_argument("--ignore-certificate-errors")
options.add_argument("--no-sandbox")
options.add_argument("--disable-dev-shm-usage")
options.add_argument("--disable-blink-features=AutomationControlled")
options.add_argument("--window-size=1920,1080")   # НЕ driver.maximize_window(): под Xvfb в Docker падает "unknown command: Runtime.evaluate"
if os.getenv("HEADLESS", "0") == "1":
    options.add_argument("--headless=new")        # только осознанно: Anti-DDoS rts-tender ловит headless-отпечаток
if os.getenv("CHROME_BINARY_PATH"):
    options.binary_location = os.getenv("CHROME_BINARY_PATH")
service = ChromeService(executable_path=os.getenv("CHROMEDRIVER_PATH")) if os.getenv("CHROMEDRIVER_PATH") else None
```

- Для *.rts-tender.ru — реальный Chrome под Xvfb (`docker-entrypoint.sh`: `Xvfb "$DISPLAY" -screen 0 1920x1080x24 -nolisten tcp & sleep 2; exec python main.py`). utp_sberbank работает headless без проблем.
- Chrome не умеет `--proxy-server` с логином/паролем → нужен локальный мост без авторизации (`assets/proxy_config.py`).
- Зомби Chrome (utp_sberbank `browser.py`): `Service(..., popen_kw={'start_new_session': True})`, при закрытии `driver.quit()`, затем `os.killpg(pgid, SIGKILL)` и `service.process.wait()`.

## 2. Chrome с КриптоПро — `gz_spb/main.py: get_driver`

Обычный Chrome ≥137 не даёт Selenium грузить расширения → используется **Chrome for Testing** (версия зафиксирована в `gz_spb/install_browser.py`, ставится в `./browser/`). Расширение `extension_1_3_17_0.crx`, ID `pfhgbfnnjiafkhfdkmpiflachepdcjod`. Системный манифест нативного хоста не знает ID расширения под MV3 → пишем свой в профиль:

```python
hosts_dir = os.path.join(profile_dir, 'NativeMessagingHosts')
os.makedirs(hosts_dir, exist_ok=True)
json.dump({'name': 'ru.cryptopro.nmcades', 'description': 'Chrome Native Messaging Host for CAdES Browser plug-in',
           'path': '/opt/cprocsp/bin/amd64/nmcades', 'type': 'stdio',
           'allowed_origins': [f'chrome-extension://{CADES_EXTENSION_ID}/']},
          open(os.path.join(hosts_dir, 'ru.cryptopro.nmcades.json'), 'w', encoding='utf-8'))
options.binary_location = CHROME_BINARY
options.add_extension(CADES_EXTENSION)
options.add_argument(f'--user-data-dir={profile_dir}')   # свой профиль на парсер: сессия переживает прогоны
```

- Запуск не headless, нужен `DISPLAY` (ВМ selenium, пользователь `cryptopro` — владелец сертификатов).
- Новый сайт должен быть в TrustedSites плагина: `/var/opt/cprocsp/users/cryptopro/local.ini`, секция `[Software\"Crypto Pro"\CAdESplugin]`. Иначе окно «Загрузка сертификатов» висит бесконечно (плагин ждёт подтверждения). Правит пользователь.
- Выбор сертификата: gz-spb — select2 по имени организации; SSO rts-tender — `//tr[@data-hash][td[normalize-space()="<ФИО>"]]`; B2B-Center — `//tr[td/div[contains(., "<ОРГАНИЗАЦИЯ>,")]]//button[contains(@class,"js-trigger-ecp-toSign")]`. Имя — из env, не хардкодом.
- Popup «Установите сертификат Минцифры» на SSO rts-tender появляется с задержкой и перехватывает клик — закрыть JS-ом в shadow DOM (`rts_parser.CLOSE_POPUP_JS`) прямо перед кликом.
- Сначала проверить, не активна ли сессия из профиля (нет редиректа на `auth/sso/login`) — тогда вход не нужен.
- «Сертификат не зарегистрирован в Системе» — проблема привязки сертификата к учётке на площадке, не кода. Сообщи пользователю.

## 3. Сертификаты УЦ Минцифры

Сайты госсектора (ЕИС, gz-spb, rts-tender) выпущены УЦ Минцифры — certifi их не знает.

- requests: собрать bundle certifi + `certs/*.pem` (`rts_parser.ca_bundle()`) и передать в `session.verify`. Для urllib — `ssl_context.load_verify_locations(RU_CA_FILE)` (utp_sberbank).
- Chrome доверяет только пину ключа конечного сертификата: `--ignore-certificate-errors-spki-list=<base64 sha256 SPKI>`. Пин меняется при перевыпуске → вычислять при каждом запуске, проверив цепочку по `certs/*.pem` (`gz_spb/main.py: site_key_pin`).

## 4. Ожидания

```python
def wait_page_ready(driver, timeout=30):
    WebDriverWait(driver, timeout).until(lambda d: d.execute_script("return document.readyState") == "complete")
    wait_out_anti_ddos(driver)

def wait_out_anti_ddos(driver, timeout=35):
    # первый визит на любой *.rts-tender.ru: промежуточная страница "Anti-DDoS" в title,
    # реальный браузер сам проходит JS-челлендж - просто ждать
    deadline = time.time() + timeout
    while time.time() < deadline and "Anti-DDoS" in driver.title:
        time.sleep(2)

def safe_click(driver, element):
    # чаты/баннеры перекрывают элемент - скролл в центр, при перехвате клик через JS
    driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", element)
    time.sleep(0.3)
    try:
        element.click()
    except ElementClickInterceptedException:
        driver.execute_script("arguments[0].click();", element)
```

- Anti-DDoS может прилететь и **после** логина/кода — ждать его перед поиском следующего элемента (rts_selenium падал 2 дня подряд на этом шаге).
- Страница «503 Сервис недоступен» отдаётся мгновенно — переоткрывать ссылку с паузой `20 * attempt`, до 3 раз (rts_selenium `wait_out_503`).
- jqGrid (rts_tender `wait_for_grid_reload`): до 3 с ловить появление спиннера, затем ждать его исчезновения И (строка `tr.jqgrow` ИЛИ текст «Нет записей для просмотра»). Сравнение «отпечатка» грида до/после не работает — грид на миг пустеет.
- Элементы после перерисовки бывают stale → собрать ссылки страницы целиком заново (до 3 раз).
- Vue-карточка (utp_sberbank): ждать JS-условие отрисовки (`CARD_RENDERED_JS`, есть ли `a-text__label`/`label-text`), а не readyState.
- В тестах с `MagicMock`-драйвером мокать `wait_page_ready`, иначе настоящий `WebDriverWait` ждёт полные 30 с.

## 5. Вход

**Ретраи** (`rts_tender: login_with_retries`): `TimeoutException` до формы (сеть, прокси, Anti-DDoS) — пересоздать драйвер и повторить до 3 раз с паузой 60 с. Форма осталась на экране после отправки — это неверные данные: не повторять, сразу алерт.

**Признак успеха** — ушли со страницы логина (`until_not(presence_of_element_located(поле логина))`, URL больше не содержит login-хост). Неверный пароль часто не бросает ошибок и не меняет URL.

**Код из почты** (rts_selenium `get_autorization_key`): IMAP `imap.yandex.com:993`, `UNSEEN SUBJECT "Код подтверждения"` с `CHARSET UTF-8`, взять **последний** UID (могли накопиться старые), опрос ~7 раз по 2 с; не пришло — нажать «отправить код ещё раз» и повторить.

**Диагностика** при сбое входа: `driver.save_screenshot` + `page_source` в `logs/<label>_<stamp>.png/.html` — чтобы не гадать при следующем сбое.

**Свежая сессия раз в сутки** (rts_parser `fresh_login`): долгоживущая сессия начинает получать 429/503 — очистить cookies через CDP (`Network.clearBrowserCookies`) и войти заново.

## 6. Selenium → requests — `gz_spb/rts_parser.py: Api`

```python
session = requests.Session()
session.verify = ca_bundle()
session.headers.update({'User-Agent': driver.execute_script('return navigator.userAgent'),
                        'X-Requested-With': 'XMLHttpRequest'})
for c in driver.get_cookies():
    session.cookies.set(c['name'], c['value'], domain=c['domain'], path=c.get('path', '/'))
```

Истечение сессии в requests: 401 или 301/302 с `Location` на `auth/sso/login` → `SessionExpired`, перелогин браузером. Запросы с `allow_redirects=False`, чтобы это увидеть.

Для документов внешних хостов (ЕИС) cookie площадки не слать (utp_sberbank `fetch_file`: только если хост оканчивается на домен площадки).

## 7. HTTP-клиент с темпом — `rosatom/rosatom_parser.py: Site`, `rts_parser.Api`

```python
RETRY_STATUSES = (429, 500, 502, 503, 504)

def request(self, method, path, **kwargs):
    for attempt in range(5):
        time.sleep(max(0, self.last_request + REQUEST_INTERVAL - time.time()))   # темп между ЛЮБЫМИ запросами
        self.last_request = time.time()
        try:
            response = self.session.request(method, urljoin(SITE_URL, path), timeout=TIMEOUT, **kwargs)
        except (requests.ConnectionError, requests.Timeout):
            if attempt == 4: raise
            time.sleep(30 * (attempt + 1)); continue
        if '/captcha/' in response.url:
            raise Captcha('площадка перенаправляет на капчу')   # стоп прогона: запросы во время бана его продлевают
        if response.status_code not in RETRY_STATUSES: break
        time.sleep(retry_after(response, 30 * (attempt + 1)))  # уважать Retry-After
    response.raise_for_status()
    return response
```

- Темп — параметр из env (`ROSATOM_REQUEST_INTERVAL=6`, `REQUEST_INTERVAL=2.0` у rts_parser, `FILES_INTERVAL=2.7` для ЕИС ≈ 22 файла/мин).
- **ЕИС 403** — блок всего ЕИС на минуты, а не конкретного файла: паузы `(60, 180, 300, 600)` с, не расходуя попытки документа; исчерпали — `EisBlocked`, прогон останавливается, доест следующий cron.
- «Файл» с `Content-Type: text/html` — это страница ошибки/логина, не файл → исключение.
- Кодировку декодировать явно (`content.decode('utf-8', 'replace')`), не доверять `response.text`.

## 8. Имена файлов документов — `rts_parser.safe_name`

```python
MAX_NAME_BYTES = 200   # ext4: 255 БАЙТ на имя, кириллица - 2 байта; на Windows/NTFS не проявляется

def shorten(text, max_bytes):
    return text.encode('utf-8')[:max_bytes].decode('utf-8', 'ignore').rstrip()

def safe_name(name, used):
    name = re.sub(r'[\x00/\\]', '_', name).strip() or 'document'   # для Windows-совместимости ещё [:*?"<>|]
    base, ext = os.path.splitext(name)
    if len(ext.encode('utf-8')) > 20:        # "расширение" из точки в середине названия
        base, ext = name, ''
    base = shorten(base, MAX_NAME_BYTES - len(ext.encode('utf-8')) - 6) or 'document'   # запас под " (N)"
    candidate, n = base + ext, 1
    while candidate in used:                 # одинаковые имена в одной процедуре
        n += 1
        candidate = f'{base} ({n}){ext}'
    used.add(candidate)
    return candidate
```

Реальное имя на диске сохранять в `documents.json` — оно уходит в tenders-api как `local_path`.

## 9. Скачивание документов

Порядок предпочтения:
1. Публичный ЕИС по номеру извещения (rts_selenium, rts_parser: `.blockFilesTabDocs a[href*="filestore"]`) — не нагружает площадку.
2. `requests` с cookies сессии и через тот же прокси-мост, что и браузер (rts_tender: напрямую TLS к `FileDownloadHandler` обрывается).
3. Клик в браузере с `Browser.setDownloadBehavior` и ожиданием нового файла в каталоге (rts_market, utp_sberbank, zakupki.rosatom.ru) — когда у кнопки нет href.
4. «Скачать все» zip → распаковать, пропустить служебные (`Passport_*`).

Ошибка одного документа — только в лог, процедура сохраняется. Нескачанные отмечать в `documents.json` (`downloaded: false`) и докачивать отдельным режимом `--files` за последние `FILES_DAYS=30` дней (`FILE_ATTEMPTS=3`). Отдельный процесс позволяет качать файлы в своём темпе и не тормозить сбор карточек.

## 10. Дедупликация и статус прогона

Два подхода, оба рабочие:
- **Признак в архиве** (rosatom, rts_parser): процедура собрана, если есть файл, который пишется последним (`info.json` / `model.json`). Пишется через временный файл + `os.replace`. Не нужен отдельный state.
- **`logs/processed_items.txt`** (rts_tender, rts_selenium, rts_market): append-only, по id в строке, в смонтированном томе. Пометка **необратима** → ставить только после реально полученной карточки.

`logs/last_run_status.json`: `{status, finished_at, items_processed, error?}` — для healthcheck и разборов.

## 11. Предохранители основного цикла

- `InvalidSessionIdException` — браузер умер, пробросить сразу (каждая следующая карточка упадёт так же вхолостую).
- N ошибок карточек подряд (`MAX_CONSECUTIVE_ITEM_FAILURES = 15`) — сессия тихо разлогинилась, прервать прогон.
- `MAX_CONSECUTIVE_ALREADY_PROCESSED = 30`, `MAX_PAGES_PER_RUN = 15` (rts_market) — когда список не фильтруется по дате, остановиться на старом.
- Внешний таймаут: `timeout -k 120 105m` (utp_sberbank), `timeout 3h` в run.sh (rts_market, после 6-часового зависания rts_selenium).
- Необязательная оптимизация (размер страницы 100) при неудаче — warning и дальше, а не падение.
- SIGTERM-обработчик, чтобы при таймауте закрыть браузер и записать статус.

## 12. Алерты

- Письмо на **любой** сбой прогона, не только на логин (38 ч простоя без писем — rts_tender 2026-08-22).
- Алерт живёт **снаружи** того, за чем следит: `run.sh` шлёт письмо сам, если `docker pull` не прошёл (`deploy/send_alert.py`, только stdlib).
- Повторяющиеся ошибки — `error_state.json` с счётчиком дней подряд, письмо с N-го дня (`RECURRING_ERROR_THRESHOLD_DAYS = 2`, rts_market/rts_selenium).
- Дедупликация по ключу, не чаще раза в `ALERT_REPEAT_MINUTES=360` (utp_sberbank `notify.py`, Telegram + SMTP). `alert()` никогда не бросает исключений.
- Healthcheck по расписанию (utp_sberbank `healthcheck.py`): последний прогон старше N часов; нет новых процедур в рабочие часы будней; зомби/осиротевшие Chrome в `/proc`.
- В cron-парсерах без своей рассылки traceback упавшего прогона уходит на `MAILTO` (rosatom).

## 13. Логи

- Файл на день `logs/<prefix>_YYYY-MM-DD.log`, удаление старше `LOG_KEEP_DAYS = 62` при запуске; в консоль — только если `sys.stdout.isatty()` (rosatom, gz_spb).
- Или `TimedRotatingFileHandler` в полночь, 60 дней, уровень ERROR (rts_tender).
- В конце прогона — строка итога: собрано / пропущено / документов / ошибок / отправлено.
