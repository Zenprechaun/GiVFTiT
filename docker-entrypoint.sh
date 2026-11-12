#!/bin/sh
# Start-up for the web container: bring the database up to date, then serve.
set -e
python manage.py migrate --noinput
python manage.py seed_categories
exec gunicorn config.wsgi --bind 0.0.0.0:8000 --workers 3
