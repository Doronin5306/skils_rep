import os
import sys

# Тесты не должны требовать .env, сеть, браузер или tenders-api. Конфиг читает переменные
# при импорте - подставляем фиктивные ДО первого импорта модулей парсера.
# Реальные значения, если заданы, не перезаписываются. В CI фиктивные значения задаются
# на уровне джобы, а не проекта, чтобы не перекрыть настоящие секреты деплоя.
_FAKE_ENV = {
    'LOGIN': 'test-login',
    'PASSWORD': 'test-pass',
    'TENDERS_API_URL': 'http://tenders_api.test',
    'MYPARSER_TENDERS_API_KEY': 'test-api-key',   # TODO: имя ключа парсера
    'ARCHIVE_ROOT': os.path.join(os.path.dirname(__file__), '.test_archive'),
    'PROXY_API_TOKEN': 'test-token',
    'PROXY_HOST': '127.0.0.1',
    'PROXY_PORT': '8080',
    'PROXY_USER': 'test-proxy-user',
    'PROXY_PASS': 'test-proxy-pass',
}

for _key, _value in _FAKE_ENV.items():
    os.environ.setdefault(_key, _value)

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Реальные страницы площадки - в tests/fixtures/*.html (персональные данные вычищены).
FIXTURES = os.path.join(os.path.dirname(__file__), 'fixtures')


def fixture(name):
    with open(os.path.join(FIXTURES, name), encoding='utf-8') as file:
        return file.read()
