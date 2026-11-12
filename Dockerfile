FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Collect static files into the image. Debug is switched on only for this
# build step so that no secret key is needed at build time.
RUN DJANGO_DEBUG=1 python manage.py collectstatic --noinput

RUN useradd --create-home app && chown -R app /app
USER app

EXPOSE 8000
CMD ["sh", "docker-entrypoint.sh"]
