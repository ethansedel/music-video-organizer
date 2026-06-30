FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    HOME=/tmp

RUN apt-get update \
    && apt-get install --yes --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY pyproject.toml README.md ./
COPY src ./src

RUN python -m pip install --no-cache-dir . \
    && useradd --system --uid 1000 --no-create-home liner-notes

USER 1000:1000

EXPOSE 8765

ENTRYPOINT ["liner-notes"]
CMD ["/library", "--review", "--no-open", "--review-host", "0.0.0.0", "--review-port", "8765"]
