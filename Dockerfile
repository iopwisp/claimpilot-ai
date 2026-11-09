FROM python:3.11-slim
WORKDIR /srv
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
RUN apt-get update && apt-get install -y --no-install-recommends tesseract-ocr tesseract-ocr-rus && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app app
COPY migrations migrations
COPY alembic.ini .
COPY evaluation evaluation
COPY demo demo
RUN useradd -u 10001 -m pilot && mkdir -p /srv/state && chown pilot /srv/state
USER pilot
CMD ["uvicorn","app.main:app","--host","0.0.0.0","--port","8000"]
