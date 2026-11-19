#!/bin/sh
set -eu
python manage.py migrate --noinput
exec gunicorn config.wsgi:application --bind "0.0.0.0:${PORT:-10000}" --workers 1 --threads 2 --timeout 90 --limit-request-field_size 20000 --access-logfile - --access-logformat '%(h)s %(m)s %(U)s %(s)s' --error-logfile -
