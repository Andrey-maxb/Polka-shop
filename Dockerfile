FROM python:3.12-slim

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PORT=8000 \
    DB_PATH=/app/data/shop.db

COPY app.py config.py ./
COPY integrations ./integrations
COPY static ./static
COPY data ./data

RUN mkdir -p /app/data

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s \
    CMD python3 -c "import urllib.request;urllib.request.urlopen('http://127.0.0.1:8000/api/health',timeout=3)"

# база хранится в /app/data — подключите volume, чтобы данные не терялись
CMD ["python3", "app.py"]
