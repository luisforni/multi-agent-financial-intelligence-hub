FROM python:3.12-slim

WORKDIR /app
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_SYSTEM_PYTHON=1

RUN pip install --no-cache-dir uv

COPY packages/shared /app/packages/shared
COPY packages/market-data-agent /app/packages/market-data-agent
COPY packages/sentiment-agent /app/packages/sentiment-agent
COPY packages/risk-agent /app/packages/risk-agent
COPY packages/chart-vision-agent /app/packages/chart-vision-agent
COPY packages/orchestrator /app/packages/orchestrator

RUN uv pip install --no-cache \
    /app/packages/shared \
    /app/packages/market-data-agent \
    /app/packages/sentiment-agent \
    /app/packages/risk-agent \
    /app/packages/chart-vision-agent \
    /app/packages/orchestrator

EXPOSE 8000

CMD ["python", "-m", "orchestrator.main"]
