# Time-Machine Chess — Railway/anywhere deployment.
# Model weights are pulled from the GitHub release (they're gitignored).
FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

# CPU wheel index primary, PyPI as fallback, and maia2 resolved in the SAME
# pip invocation as torch. Installing maia2 separately makes pip re-resolve
# torch from PyPI (maia2 wants torch<2.9,>=2.8.0) and quietly swap the CPU
# build for the CUDA one, adding ~2.5GB of nvidia_* wheels this server can
# never use. Found while deploying the Lichess bot; the same bug was here.
RUN pip install --no-cache-dir \
    --index-url https://download.pytorch.org/whl/cpu \
    --extra-index-url https://pypi.org/simple \
    torch maia2 fastapi uvicorn python-chess pyyaml pillow

RUN if pip list --format=freeze | grep -qi '^nvidia-'; then \
      echo "ERROR: CUDA wheels leaked into the image - check the torch/maia2 resolution"; \
      pip list --format=freeze | grep -i '^nvidia-'; \
      exit 1; \
    fi; \
    python -c "import torch; print('torch', torch.__version__, '| cuda:', torch.version.cuda)"

# Era checkpoints + Maia-2 pretrained base from the GitHub release
ARG WEIGHTS_BASE=https://github.com/nickjlamb/time-machine-chess/releases/download/weights-v1
RUN mkdir -p models maia2_models \
    && curl -fL -o models/romantic.pt   ${WEIGHTS_BASE}/romantic.pt \
    && curl -fL -o models/classical.pt  ${WEIGHTS_BASE}/classical.pt \
    && curl -fL -o models/soviet.pt     ${WEIGHTS_BASE}/soviet.pt \
    && curl -fL -o maia2_models/rapid_model.pt ${WEIGHTS_BASE}/rapid_model.pt \
    && { curl -fL -o models/digital.pt  ${WEIGHTS_BASE}/digital.pt \
         || { rm -f models/digital.pt; echo "digital.pt not in the release yet — era falls back to heuristic"; }; } \
    && { curl -fL -o models/modern.pt   ${WEIGHTS_BASE}/modern.pt \
         || { rm -f models/modern.pt; echo "modern.pt not in the release yet — era falls back to heuristic"; }; }

COPY backend ./backend
COPY frontend ./frontend
COPY config ./config
# All committed validation receipts (self-play baselines, classifier confusion
# matrix, measured Elo) — the pages and /api read these. validation/selfplay/
# stays out via .dockerignore.
COPY validation/*.json ./validation/

# Keep RAM ~1GB on small instances: one era model resident, LRU-swapped (~10s on era switch)
ENV MAX_LOADED_MODELS=1

CMD ["sh", "-c", "uvicorn backend.app:app --host 0.0.0.0 --port ${PORT:-8000} --workers 1"]
