FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1
WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/ /app/
COPY frontend/ /app/frontend/

EXPOSE 8000

# MEDIA_ROOT по умолчанию: /app/media (создастся при старте, volume снаружи лучше подключить в compose)
CMD ["gunicorn", "photo_sort.wsgi:application", "-b", "0.0.0.0:8000", "--workers", "3"]

