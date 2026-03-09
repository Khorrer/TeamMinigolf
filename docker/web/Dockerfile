FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
  PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt-get update && \
  apt-get install -y --no-install-recommends \
  gcc \
  default-libmysqlclient-dev \
  pkg-config \
  && rm -rf /var/lib/apt/lists/*

COPY app/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app/ .
COPY docker/web/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

RUN python manage.py collectstatic --noinput 2>/dev/null || true

EXPOSE 8000

ENTRYPOINT ["/entrypoint.sh"]
CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "2", "--timeout", "120"]
