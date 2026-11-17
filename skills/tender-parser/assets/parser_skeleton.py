#!/usr/bin/env python3
# -*- coding: utf-8 -*-

# Каркас парсера площадки по схеме портфеля (образец - rosatom/rosatom_parser.py).
# Площадко-зависимое помечено TODO: URL, поиск по дате, разбор списка и карточки, вход.
# Если нужен браузер - вход и/или страницы через Selenium (references/patterns.md),
# а скачивание и отправка остаются такими же.
#
# Сбор: процедуры, опубликованные за день -> карточка -> файлы. По каждой процедуре в архив
# кладутся index.html, files/, documents.json и info.json (строка списка; пишется последним -
# признак, что процедура собрана), и процедура сразу отправляется в tenders-api.
#
# Запуск:
#     parser.py                        процедуры, опубликованные сегодня
#     parser.py --date 2026-10-29      процедуры за день (добор вчерашних после полуночи)
#     parser.py --limit 5              не больше 5 новых процедур (отладка)
#     parser.py --files                докачать нескачанные файлы за FILES_DAYS дней
#     parser.py --resend --date ...    только отправить архив в tenders-api (--since, --dry-run)

import argparse
import json
import logging
import os
import re
import sys
import time
from datetime import date, datetime, timedelta, timezone
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

import tenders_api
from tenders_api import clean

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
NAME = 'myparser'                                          # TODO: имя парсера (каталог архива, логи)
SITE_URL = 'https://example-platform.ru'                   # TODO
PLATFORM = os.environ.get('MYPARSER_PLATFORM', 'example-platform.ru')   # TODO: platform в tenders-api
ARCHIVE_ROOT = os.environ.get('ARCHIVE_ROOT', '/archive/selenium')       # корень веб-архива, от него local_path
ARCHIVE_DIR = os.path.join(ARCHIVE_ROOT, NAME)
LOG_DIR = os.path.join(BASE_DIR, 'logs')
LOG_KEEP_DAYS = 62
USER_AGENT = ('Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 '
              '(KHTML, like Gecko) Chrome/151.0.0.0 Safari/537.36')
# Пауза между любыми запросами к площадке. Подбирается разведкой: превышение = капча/бан по IP
REQUEST_INTERVAL = float(os.environ.get('MYPARSER_REQUEST_INTERVAL', '3'))
RETRY_STATUSES = (429, 500, 502, 503, 504)
PAGE_SIZE = 20                                             # TODO: строк на странице списка
TIMEOUT = 60
FILE_TIMEOUT = 300
FILE_ATTEMPTS = 3
FILES_DAYS = 30
MAX_NAME_BYTES = 200                                       # ext4: 255 байт на имя, кириллица - 2 байта
MSK = timezone(timedelta(hours=3))
CANONICAL_FIELDS = (
    'Наименование процедуры', 'Наименование организации', 'ИНН организации',
    'Статус процедуры', 'Способ процедуры', 'Дата и время публикации процедуры',
)


class Captcha(Exception):
    """Площадка не пускает (капча, бан по IP): прогон останавливается, остальное - следующим cron."""


class Site:
    """Запросы к площадке с cookies, паузой между запросами и ретраями."""

    def __init__(self, session=None, login=None, password=None):
        self.session = session or requests.Session()
        self.session.headers['User-Agent'] = USER_AGENT
        self.login_name, self.password = login, password
        self.logged_in = False
        self.last_request = 0

    def request(self, method, path, timeout=TIMEOUT, **kwargs):
        url = urljoin(SITE_URL, path)
        for attempt in range(5):
            time.sleep(max(0, self.last_request + REQUEST_INTERVAL - time.time()))
            self.last_request = time.time()
            try:
                response = self.session.request(method, url, timeout=timeout, **kwargs)
            except (requests.ConnectionError, requests.Timeout):
                if attempt == 4:
                    raise
                time.sleep(30 * (attempt + 1))
                continue
            if '/captcha' in response.url:                 # TODO: признак бана этой площадки
                # запросы во время бана могут его продлевать - сразу стоп
                raise Captcha('площадка перенаправляет на капчу')
            if response.status_code not in RETRY_STATUSES:
                break
            time.sleep(retry_after(response, 30 * (attempt + 1)))
        response.raise_for_status()
        return response

    def get(self, path):
        # кодировку задаём явно: response.text угадывает её по заголовкам и ошибается
        return self.request('GET', path).content.decode('utf-8', 'replace')

    def login(self):
        """Войти; без учётных данных - работать гостем. TODO: вход этой площадки."""
        if not (self.login_name and self.password):
            return False
        raise NotImplementedError('вход на площадку')
        # Пример (B2B-Center): взять все input формы (CSRF), добавить логин/пароль, POST
        # с X-Requested-With, проверить ответ; признак успеха проверять явно.
        # self.logged_in = True
        # return True

    def download(self, url):
        response = self.request('GET', url, timeout=FILE_TIMEOUT)
        if 'text/html' in response.headers.get('Content-Type', ''):
            # вместо файла - страница ошибки или истекшей сессии
            raise RuntimeError(f'вместо файла страница HTML (HTTP {response.status_code})')
        return response.content

    def search(self, day, start):
        """(всего процедур или None, строки страницы) - опубликованные в день day. TODO."""
        raise NotImplementedError('поиск по дате публикации')


def retry_after(response, default):
    try:
        return int(response.headers.get('Retry-After')) + 1
    except (TypeError, ValueError):
        return default


def parse_search(html):
    """Строки списка: [{'id', 'url', 'published', ...}]. TODO: селекторы списка."""
    raise NotImplementedError('TODO: разбор списка (parse_search)')


def parse_card(html):
    """{'fields': {подпись: значение}, 'documents': [{'name', 'url'}]}. TODO: селекторы карточки.

    fields - сырые пары со всей карточки, повтор подписи -> «Подпись (2)».
    """
    soup = BeautifulSoup(html, 'html.parser')
    fields, documents = {}, []
    raise NotImplementedError('TODO: разбор карточки (parse_card)')
    return {'fields': fields, 'documents': documents}


def strip_noise(html):
    soup = BeautifulSoup(html, 'html.parser')
    for tag in soup.find_all(['script', 'noscript']):
        tag.decompose()
    return str(soup)


def shorten(text, max_bytes):
    return text.encode('utf-8')[:max_bytes].decode('utf-8', 'ignore').rstrip()


def safe_name(name, used):
    name = re.sub(r'[\x00/\\:*?"<>|]', '_', name).strip() or 'document'
    base, ext = os.path.splitext(name)
    if len(ext.encode('utf-8')) > 20:
        base, ext = name, ''
    base = shorten(base, MAX_NAME_BYTES - len(ext.encode('utf-8')) - 6) or 'document'   # запас под « (N)»
    candidate, n = base + ext, 1
    while candidate in used:
        n += 1
        candidate = f'{base} ({n}){ext}'
    used.add(candidate)
    return candidate


def write_json(path, data):
    # через временный файл: прерванная запись не оставит битый json
    with open(path + '.tmp', 'w', encoding='utf-8') as file:
        json.dump(data, file, ensure_ascii=False)
    os.replace(path + '.tmp', path)


def read_json(path, default=None):
    if not os.path.exists(path):
        return default
    with open(path, encoding='utf-8') as file:
        return json.load(file)


def download_documents(site, item_dir, documents):
    """Скачать нескачанные файлы. Возвращает (скачано сейчас, ошибок). Ошибка файла не роняет процедуру."""
    downloaded = failed = 0
    for doc in documents:
        if doc.get('downloaded') or doc.get('attempts', 0) >= FILE_ATTEMPTS:
            continue
        try:
            content = site.download(doc['url'])
        except Captcha:
            write_json(os.path.join(item_dir, 'documents.json'), documents)
            raise
        except Exception as error:
            failed += 1
            doc['attempts'] = doc.get('attempts', 0) + 1
            doc['error'] = str(error)[:300]
            logging.warning('Файл %s процедуры %s не скачан: %s', doc['name'], os.path.basename(item_dir), error)
            continue
        os.makedirs(os.path.join(item_dir, 'files'), exist_ok=True)
        with open(os.path.join(item_dir, 'files', doc['name']), 'wb') as file:
            file.write(content)
        doc['downloaded'] = True
        doc.pop('error', None)
        downloaded += 1
    write_json(os.path.join(item_dir, 'documents.json'), documents)
    return downloaded, failed


def save_item(site, item, day_dir):
    """Собрать процедуру в каталог. Возвращает каталог или None, если она уже собрана."""
    item_dir = os.path.join(day_dir, item['id'])
    if os.path.exists(os.path.join(item_dir, 'info.json')):
        return None
    html = site.get(item['url'])
    card = parse_card(html)
    if not card['fields']:
        # страница ошибки/заглушка вместо карточки: не сохранять, следующий прогон попробует снова
        raise RuntimeError('на карточке нет полей')
    os.makedirs(item_dir, exist_ok=True)
    with open(os.path.join(item_dir, 'index.html'), 'w', encoding='utf-8') as file:
        file.write(strip_noise(html))
    used = set()
    documents = [dict(doc, name=safe_name(doc['name'], used), downloaded=False) for doc in card['documents']]
    download_documents(site, item_dir, documents)
    # info.json последним: по нему следующий прогон понимает, что процедура собрана целиком
    write_json(os.path.join(item_dir, 'info.json'), dict(item, collected_at=datetime.now(timezone.utc).isoformat()))
    return item_dir


def build_fields(item, card):
    fields = dict(card['fields'])
    # TODO: канонические поля, если площадка называет их иначе; время публикации - из списка,
    # если на карточке его нет (иначе tenders-api поставит полночь МСК)
    fields.setdefault('Дата и время публикации процедуры', item.get('published'))
    return {key: clean(text) for key, text in fields.items() if text not in (None, '')}


def build_item(item_dir, scraped_at=None):
    """Тело POST /v1/tenders из каталога архива - один код и для сбора, и для --resend."""
    item = read_json(os.path.join(item_dir, 'info.json'))
    with open(os.path.join(item_dir, 'index.html'), encoding='utf-8') as file:
        card = parse_card(file.read())
    if scraped_at is None:
        scraped_at = datetime.fromisoformat(item['collected_at'])
    return {
        'platform': PLATFORM,
        'item_id': item['id'],
        'source_url': item['url'],
        'fields': build_fields(item, card),
        'documents': [{
            'name': doc['name'],
            'url': doc.get('url'),
            # относительно корня веб-архива, только для реально скачанных файлов
            'local_path': os.path.relpath(os.path.join(item_dir, 'files', doc['name']), ARCHIVE_ROOT).replace(os.sep, '/')
            if doc.get('downloaded') else None,
        } for doc in read_json(os.path.join(item_dir, 'documents.json'), [])],
        'scraped_at': scraped_at.isoformat(),
    }


def api_key():
    return os.environ.get('MYPARSER_TENDERS_API_KEY')     # TODO: свой ключ на platform


_not_configured_logged = False


def is_configured():
    global _not_configured_logged
    if os.environ.get('TENDERS_API_URL') and api_key():
        return True
    if not _not_configured_logged:
        logging.warning('TENDERS_API_URL / ключ не заданы (.env) - процедуры в tenders-api не отправляются')
        _not_configured_logged = True
    return False


def new_site():
    site = Site(login=os.environ.get('LOGIN'), password=os.environ.get('PASSWORD'))
    if not site.login():
        logging.warning('LOGIN / PASSWORD не заданы (.env) - работаем гостем')
    return site


def collect(day, limit=0, site=None):
    day_dir = os.path.join(ARCHIVE_DIR, day.isoformat())
    os.makedirs(day_dir, exist_ok=True)
    logging.info('Старт прогона за %s', day.isoformat())
    saved = skipped = errors = sent = send_errors = 0
    count, items, start = None, {}, 0
    site = site or new_site()
    try:
        # Сначала весь список дня, потом карточки: пока идёт сбор, новые публикации сдвигают
        # страницы; что сдвинулось за край, доберёт следующий прогон
        while True:
            total, rows = site.search(day, start)
            if count is None:
                count = total
                logging.info('Найдено процедур: %s', count)
            for row in rows:
                items.setdefault(row['id'], row)
            start += PAGE_SIZE
            if len(rows) < PAGE_SIZE or (count is not None and start >= count):
                break
    except Captcha as error:
        logging.warning('Список, позиция %s: %s - собираем найденное', start, error)
    for item in items.values():
        if limit and saved >= limit:
            break
        try:
            item_dir = save_item(site, item, day_dir)
        except Captcha as error:
            logging.warning('Процедура %s: %s - прогон остановлен', item['id'], error)
            break
        except Exception as error:
            errors += 1
            logging.warning('Процедура %s не собрана: %s', item['id'], error)
            continue
        if item_dir is None:
            skipped += 1
            continue
        saved += 1
        if is_configured():
            try:
                tenders_api.post('/v1/tenders', build_item(item_dir, datetime.now(timezone.utc)), key=api_key())
                sent += 1
            except Exception as error:
                # best-effort: процедура в архиве, дошлёт --resend
                send_errors += 1
                logging.warning('Процедура %s не отправлена в tenders-api: %s', item['id'], error)
    logging.info('Итог: найдено %s, в списке %s, новых %s, уже были %s, ошибок сбора %s, отправлено %s, ошибок отправки %s',
                 count, len(items), saved, skipped, errors, sent, send_errors)
    # ошибки отдельных карточек - норма (доберёт следующий прогон); провал прогона - это исключение
    return True


def item_dirs(day=None, since=None):
    if not os.path.isdir(ARCHIVE_DIR):
        return
    for name in sorted(os.listdir(ARCHIVE_DIR)):
        try:
            current = date.fromisoformat(name)
        except ValueError:
            continue
        if (day and current != day) or (since and current < since):
            continue
        for number in sorted(os.listdir(os.path.join(ARCHIVE_DIR, name))):
            item_dir = os.path.join(ARCHIVE_DIR, name, number)
            if os.path.exists(os.path.join(item_dir, 'info.json')):
                yield item_dir


def download_files(day=None, since=None, site=None):
    """Докачать файлы, не скачанные при сборе, и дослать процедуры с новыми файлами."""
    if day is None and since is None:
        since = datetime.now(MSK).date() - timedelta(days=FILES_DAYS)
    site = site or new_site()
    items = downloaded = failed = 0
    for item_dir in item_dirs(day, since):
        documents = read_json(os.path.join(item_dir, 'documents.json'), [])
        if all(doc.get('downloaded') or doc.get('attempts', 0) >= FILE_ATTEMPTS for doc in documents):
            continue
        try:
            count, errors = download_documents(site, item_dir, documents)
        except Captcha as error:
            logging.warning('%s - докачка остановлена', error)
            break
        downloaded += count
        failed += errors
        if count:
            items += 1
            if is_configured():
                try:
                    tenders_api.post('/v1/tenders', build_item(item_dir), key=api_key())
                except Exception as error:
                    logging.warning('Процедура %s не отправлена в tenders-api: %s', os.path.basename(item_dir), error)
    logging.info('Итог докачки: процедур %s, файлов %s, ошибок %s', items, downloaded, failed)


def resend(day=None, since=None, dry_run=False):
    """Дозаливка архива в tenders-api пачками; повтор безопасен (upsert)."""
    found = sent = 0
    errors, batch = [], []

    def flush():
        nonlocal sent
        if not batch:
            return
        try:
            results = tenders_api.post('/v1/tenders/batch', {'items': batch}, key=api_key())
            errors.extend(f"{item['item_id']}: {result.get('error')}" for item, result in zip(batch, results) if not result.get('ok'))
            sent += sum(1 for result in results if result.get('ok'))
        except Exception as error:
            errors.append(f'пачка из {len(batch)} процедур не отправлена: {error}')
        batch.clear()

    for item_dir in item_dirs(day, since):
        found += 1
        try:
            item = build_item(item_dir)
        except Exception as error:
            errors.append(f'{item_dir}: не удалось разобрать: {error}')
            continue
        if dry_run:
            canonical = {key: item['fields'][key] for key in CANONICAL_FIELDS if key in item['fields']}
            print(item['item_id'], canonical, 'полей:', len(item['fields']), 'документов:', len(item['documents']))
            continue
        batch.append(item)
        if len(batch) >= tenders_api.BATCH_SIZE:
            flush()
    flush()
    for error in errors:
        print('ОШИБКА', error)
    print(f'Найдено процедур: {found}, {"разобрано" if dry_run else "отправлено"}: '
          f'{found - len(errors) if dry_run else sent}, ошибок: {len(errors)}')
    return not errors


def setup_logging(prefix=NAME):
    # файл на день; старше LOG_KEEP_DAYS удаляются; в консоль - только при ручном запуске
    os.makedirs(LOG_DIR, exist_ok=True)
    for name in os.listdir(LOG_DIR):
        path = os.path.join(LOG_DIR, name)
        if name.startswith(f'{prefix}_') and name.endswith('.log') and os.path.getmtime(path) < time.time() - LOG_KEEP_DAYS * 86400:
            os.remove(path)
    handlers = [logging.FileHandler(os.path.join(LOG_DIR, f'{prefix}_{datetime.now():%Y-%m-%d}.log'), encoding='utf-8')]
    if sys.stdout.isatty():
        handlers.append(logging.StreamHandler())
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s', handlers=handlers)


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=f'Парсер {SITE_URL}')
    day = date.fromisoformat
    period = parser.add_mutually_exclusive_group()
    period.add_argument('--date', type=day, help='процедуры, опубликованные в этот день ГГГГ-ММ-ДД (по умолчанию - сегодня)')
    period.add_argument('--since', type=day, help='с --resend и --files: архив с дня ГГГГ-ММ-ДД')
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--resend', action='store_true', help='не собирать, а отправить архив в tenders-api')
    mode.add_argument('--files', action='store_true', help=f'докачать нескачанные файлы (по умолчанию за {FILES_DAYS} дней)')
    parser.add_argument('--dry-run', action='store_true', help='с --resend: только разобрать и показать')
    parser.add_argument('--limit', type=int, default=0, help='собрать не больше N новых процедур (отладка)')
    args = parser.parse_args(argv)
    if args.dry_run and not args.resend:
        parser.error('--dry-run работает только с --resend')
    if args.since and not (args.resend or args.files):
        parser.error('--since работает только с --resend и --files')
    return args


if __name__ == '__main__':
    args = parse_args()
    if args.resend:
        logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
        if not args.dry_run and not is_configured():
            sys.exit(1)
        sys.exit(0 if resend(args.date, args.since, args.dry_run) else 1)
    setup_logging(f'{NAME}_files' if args.files else NAME)
    try:
        if args.files:
            download_files(args.date, args.since)
            ok = True
        else:
            ok = collect(args.date or datetime.now(MSK).date(), args.limit)
    except Exception:
        logging.exception('Прогон завершился с ошибкой')
        raise
    # ненулевой код при сбое - иначе cron/docker видят «успех»
    sys.exit(0 if ok else 1)
