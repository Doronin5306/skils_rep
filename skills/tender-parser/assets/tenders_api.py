#!/usr/bin/env python3
# -*- coding: utf-8 -*-

# Отправка процедур в tenders-api (общая БД tenders) и чтение .env.
# Запись идемпотентна (upsert по platform + item_id), повторная отправка безопасна.
# Шаблон из rosatom/tenders_api.py - без pydantic, только requests.

import os
import re

import requests


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TIMEOUT = 30
BATCH_SIZE = 50


def load_env(path=os.path.join(BASE_DIR, '.env')):
    # Простой .env: строки KEY=VALUE, пустые и начинающиеся с # пропускаются.
    # Переменные, уже заданные в окружении, не перезаписываются (cron/CI важнее файла).
    if not os.path.exists(path):
        return
    with open(path, encoding='utf-8') as file:
        for line in file:
            line = line.strip()
            if not line or line.startswith('#') or '=' not in line:
                continue
            key, value = line.split('=', 1)
            os.environ.setdefault(key.strip(), value.strip())


load_env()


def clean(text):
    # \x00 API отклоняет с 422; пробелы и переносы из вёрстки схлопываем
    return re.sub(r'\s+', ' ', str(text).replace('\x00', '')).strip()


def post(path, payload, key):
    # Ключ разрешает запись только для своей platform: у парсеров разных площадок ключи разные
    response = requests.post(
        os.environ['TENDERS_API_URL'].rstrip('/') + path,
        json=payload,
        headers={'X-API-Key': key},
        timeout=TIMEOUT,
    )
    if not response.ok:
        raise RuntimeError(f'HTTP {response.status_code}: {response.text[:300]}')
    return response.json()
