# Time-Machine Chess — Railway/anywhere deployment.
# Model weights are pulled from the GitHub release (they're gitignored).
FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

# CPU-only torch keeps the image ~1.5GB smaller than the default wheel
RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu \
    && pip install --no-cache-dir fastapi uvicorn python-chess pyyaml maia2

# Era checkpoints + Maia-2 pretrained base from the GitHub release
ARG WEIGHTS_BASE=https://github.com/nickjlamb/time-machine-chess/releases/download/weights-v1
RUN mkdir -p models maia2_models \
    && curl -fL -o models/romantic.pt   ${WEIGHTS_BASE}/romantic.pt \
    && curl -fL -o models/classical.pt  ${WEIGHTS_BASE}/classical.pt \
    && curl -fL -o models/soviet.pt     ${WEIGHTS_BASE}/soviet.pt \
    && curl -fL -o maia2_models/rapid_model.pt ${WEIGHTS_BASE}/rapid_model.pt \
    && { curl -fL -o models/digital.pt  ${WEIGHTS_BASE}/digital.pt \
         || { rm -f models/digital.pt; echo "digital.pt not in the release yet — era falls back to heuristic"; }; }

COPY backend ./backend
COPY frontend ./frontend
COPY config ./config
COPY validation/results.json ./validation/results.json

# Keep RAM ~1GB on small instances: one era model resident, LRU-swapped (~10s on era switch)
ENV MAX_LOADED_MODELS=1

CMD ["sh", "-c", "uvicorn backend.app:app --host 0.0.0.0 --port ${PORT:-8000} --workers 1"]
