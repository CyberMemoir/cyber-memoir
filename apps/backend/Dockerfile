FROM python:3.12-slim
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg libgomp1 libgl1 && rm -rf /var/lib/apt/lists/*
COPY apps/backend/requirements.lock ./
RUN pip install --no-cache-dir -r requirements.lock
ARG INSTALL_MODELS=false
ARG MODEL_EXTRAS=models
# Model deps resolve from pyproject alone and install before the source copy, so editing
# code does not invalidate this layer and reinstall torch on every build. CPU-only torch:
# the default wheel bundles CUDA, ~2GB larger for no benefit on this stack.
COPY apps/backend/pyproject.toml ./
RUN if [ "$INSTALL_MODELS" = "true" ]; then \
      case "$MODEL_EXTRAS" in \
        *embeddings*|*models*) pip install --no-cache-dir --index-url https://download.pytorch.org/whl/cpu torch ;; \
      esac; \
      python -c "import tomllib, os; extras = tomllib.load(open('pyproject.toml','rb'))['project']['optional-dependencies']; print('\n'.join(spec for name in os.environ['MODEL_EXTRAS'].split(',') for spec in extras.get(name.strip(), [])))" > /tmp/extras.txt && \
      cat /tmp/extras.txt && \
      pip install --no-cache-dir -r /tmp/extras.txt; \
    fi
COPY apps/backend/ ./
RUN pip install --no-cache-dir --no-deps .
# /app/.models exists so a volume mounted there inherits memoir's ownership; created
# by docker it would be root's and the download would fail as this unprivileged user.
RUN useradd --create-home --uid 10001 memoir && mkdir -p /app/.data /app/.models && chown -R memoir:memoir /app
USER memoir
ENV PYTHONUNBUFFERED=1
EXPOSE 8100
CMD ["uvicorn", "cyber_memoir.api.main:app", "--host", "0.0.0.0", "--port", "8100"]
