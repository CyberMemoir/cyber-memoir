FROM python:3.12-slim
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg libgomp1 libgl1 && rm -rf /var/lib/apt/lists/*
COPY apps/backend/requirements.lock ./
RUN pip install --no-cache-dir -r requirements.lock
COPY apps/backend/ ./
RUN pip install --no-cache-dir --no-deps .
ARG INSTALL_MODELS=false
RUN if [ "$INSTALL_MODELS" = "true" ]; then pip install --no-cache-dir '.[models]'; fi
RUN useradd --create-home --uid 10001 memoir && mkdir -p /app/.data && chown -R memoir:memoir /app
USER memoir
ENV PYTHONUNBUFFERED=1
EXPOSE 8100
CMD ["uvicorn", "cyber_memoir.api.main:app", "--host", "0.0.0.0", "--port", "8100"]
