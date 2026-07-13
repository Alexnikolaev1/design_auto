FROM python:3.11-slim

# Системные зависимости:
#  - fonts-liberation / fonts-dejavu-core: fallback-шрифты для Pillow-рендера
#    превью и для INX-генератора, если пользователь не положил PT Serif/PT
#    Sans/Montserrat в папку fonts/ (см. README.md).
#  - libjpeg62-turbo / zlib1g: нужны Pillow для JPEG/PNG.
RUN apt-get update && apt-get install -y --no-install-recommends \
    fonts-liberation \
    fonts-dejavu-core \
    libjpeg62-turbo \
    zlib1g \
    libreoffice-writer \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /srv/app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY fonts ./fonts

ENV LG_JOBS_DIR=/tmp/layoutgenius_jobs
ENV PYTHONUNBUFFERED=1

EXPOSE 8000

# Railway пробрасывает порт через переменную PORT — используем её,
# с фолбэком на 8000 для локального запуска.
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --proxy-headers --forwarded-allow-ips='*' --access-log --log-level info"]
