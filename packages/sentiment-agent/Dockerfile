FROM python:3.12-slim

WORKDIR /app
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_SYSTEM_PYTHON=1

RUN pip install --no-cache-dir uv

COPY packages/shared /app/packages/shared
COPY packages/sentiment-agent /app/packages/sentiment-agent

RUN uv pip install --no-cache \
    /app/packages/shared \
    /app/packages/sentiment-agent

CMD ["python", "-m", "sentiment_agent.main"]
