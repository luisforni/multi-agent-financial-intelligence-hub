FROM python:3.12-slim

WORKDIR /app
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_SYSTEM_PYTHON=1

RUN pip install --no-cache-dir uv

COPY packages/shared /app/packages/shared
COPY packages/market-data-agent /app/packages/market-data-agent

RUN uv pip install --no-cache \
    /app/packages/shared \
    /app/packages/market-data-agent

CMD ["python", "-m", "market_data_agent.main"]
