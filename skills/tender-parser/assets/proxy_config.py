#!/usr/bin/env python3
# -*- coding: utf-8 -*-

# Локальный прокси-мост без авторизации поверх российского прокси с логином.
# Chrome не умеет --proxy-server с логином/паролем, поэтому поднимаем pproxy на
# 127.0.0.1 и направляем в него и Selenium, и requests (документы).
# Шаблон из rts_tender/proxy_config.py, переменные - из окружения (tenders_api.load_env).
#
#   proxy = None if DISABLE_PROXY else start_local_proxy_bridge()
#   if proxy and not wait_port(LOCAL_HOST, LOCAL_PORT): raise RuntimeError(...)
#   ...
#   finally: proxy.terminate(); proxy.wait(timeout=5)

import os
import socket
import subprocess
import sys
import time

import requests
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

PROXY_SCHEME = os.getenv('PROXY_SCHEME', 'http')          # http или socks5
PROXY_API_URL = 'https://edo.k-zakupki.ru/get_random_proxy/'
LOCAL_HOST = '127.0.0.1'
LOCAL_PORT = int(os.getenv('LOCAL_PROXY_PORT', '18080'))   # свой порт на парсер, если на машине их несколько
# Переключатель, а не удаление кода: прокси возвращается одной переменной без деплоя
DISABLE_PROXY = os.getenv('DISABLE_PROXY', '0') == '1'


def fetch_proxy_credentials():
    # Каждый вызов может вернуть другой прокси. verify=False - у API самоподписанный сертификат.
    response = requests.post(PROXY_API_URL, json={'token': os.environ['PROXY_API_TOKEN']}, timeout=15, verify=False)
    if response.status_code == 403:
        # IP не в whitelist API (машина разработчика) - резервный прокси из .env
        print('API get_random_proxy вернул 403, использую резервный прокси из .env.')
        return (os.environ['PROXY_HOST'], int(os.environ['PROXY_PORT']),
                os.environ['PROXY_USER'], os.environ['PROXY_PASS'])
    response.raise_for_status()
    proxies = response.json()
    if not proxies:
        raise RuntimeError('API get_random_proxy вернул пустой список прокси.')
    host, port, user, password = proxies[0]
    return host, int(port), user, password


def build_upstream_proxy_uri(host, port, user, password):
    # pproxy разбирает user:pass@ как cipher:key Shadowsocks и падает с "existing ciphers" -
    # учётные данные upstream передаются во fragment после #
    return f'{PROXY_SCHEME}://{host}:{port}#{user}:{password}'


def wait_port(host, port, timeout=15.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with socket.create_connection((host, port), timeout=1):
                return True
        except OSError:
            time.sleep(0.2)
    return False


def start_local_proxy_bridge():
    host, port, user, password = fetch_proxy_credentials()
    # не печатать upstream целиком: в нём логин и пароль прокси
    print(f'Upstream proxy: {PROXY_SCHEME}://{host}:{port}')
    cmd = [sys.executable, '-m', 'pproxy', '-l', f'http://{LOCAL_HOST}:{LOCAL_PORT}',
           '-r', build_upstream_proxy_uri(host, port, user, password)]
    # stdout/stderr наследуются - ошибки pproxy (занятый порт, неверный upstream) видны в логе
    return subprocess.Popen(cmd)


def requests_proxies():
    """proxies= для requests: через тот же мост, что и браузер (или напрямую при DISABLE_PROXY)."""
    if DISABLE_PROXY:
        return None
    url = f'http://{LOCAL_HOST}:{LOCAL_PORT}'
    return {'http': url, 'https': url}
