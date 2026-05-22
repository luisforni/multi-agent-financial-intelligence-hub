FROM python:3.12-slim

WORKDIR /app
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_SYSTEM_PYTHON=1 \
    MPLBACKEND=Agg

RUN pip install --no-cache-dir uv

COPY packages/shared /app/packages/shared
COPY packages/chart-vision-agent /app/packages/chart-vision-agent

RUN uv pip install --no-cache \
    /app/packages/shared \
    /app/packages/chart-vision-agent

CMD ["python", "-m", "chart_vision_agent.main"]
