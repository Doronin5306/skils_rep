#!/bin/bash
# Прогон парсера из cron (вариант venv на ВМ selenium):
#   run.sh            процедуры за сегодня
#   run.sh yesterday  добор вчерашних, опубликованных после последнего прогона дня
#   run.sh files      докачка нескачанных файлов
# Блокировка общая, если сбор и докачка ходят на площадку с одного IP (вместе превысят
# лимит скорости). Если файлы идут с другого хоста (ЕИС) - дайте files свой lock-файл.
# timeout: SIGTERM на 105-й минуте (парсер закрывает браузер и пишет итог), SIGKILL через 2 мин.
# Для Selenium с окном раскомментируйте DISPLAY.
# export DISPLAY=${DISPLAY:-:0}
NAME=myparser                                   # TODO: имя парсера
cd "/home/cryptopro/Work/$NAME" || exit 1
LOCK="/tmp/$NAME.lock"
RUN="timeout -k 120 105m ./venv/bin/python3 parser.py"
case "$1" in
    yesterday) exec flock -n "$LOCK" $RUN --date "$(date -d yesterday +%F)" ;;
    files) exec flock -n "$LOCK" $RUN --files ;;
    *) exec flock -n "$LOCK" $RUN "$@" ;;
esac
