FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg fonts-noto-cjk ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY clipper_pipeline ./clipper_pipeline
COPY web ./web

RUN mkdir -p /app/runs /app/exports

ENV HOST=0.0.0.0
ENV PORT=8080
ENV CLIPPER_RUNS_DIR=/app/runs
ENV CLIPPER_EXPORTS_DIR=/app/exports

CMD ["python", "-m", "clipper_pipeline.server"]
