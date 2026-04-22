# Miner with local OpenFly VLM (CUDA + OpenFly-Platform/train deps). Code under /app; OpenFly-Platform and
# model weights are bind-mounted at runtime (see docker-compose.miner.yml).
#
#   docker compose -f docker-compose.miner.yml build

FROM nvidia/cuda:12.4.1-cudnn-runtime-ubuntu22.04
ARG PIP_EXTRA_INDEX_URL=https://pypi.org/simple

ENV DEBIAN_FRONTEND=noninteractive \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONUNBUFFERED=1 \
    PIP_ROOT_USER_ACTION=ignore

RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 \
    python3-pip \
    ca-certificates \
    curl \
    libglib2.0-0 \
    libgl1 \
    libegl1 \
    libsm6 \
    libxext6 \
    libxrender1 \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

RUN python3 -m pip install --upgrade pip setuptools wheel

COPY OpenFly-Platform/requirements.txt /tmp/openfly-platform-requirements.txt
COPY docker/subnet-miner/requirements-extras.txt /tmp/requirements-extras.txt

RUN python3 -m pip install --extra-index-url "${PIP_EXTRA_INDEX_URL}" "numpy>=1.26.0,<2.0" "msgpack-rpc-python" \
    && python3 -m pip install --extra-index-url "${PIP_EXTRA_INDEX_URL}" --no-build-isolation "airsim==1.7.0" \
    && awk '!/^airsim$/ {print}' /tmp/openfly-platform-requirements.txt > /tmp/openfly-platform-without-airsim.txt \
    && python3 -m pip install --extra-index-url "${PIP_EXTRA_INDEX_URL}" -r /tmp/openfly-platform-without-airsim.txt \
    && python3 -m pip install --extra-index-url "${PIP_EXTRA_INDEX_URL}" -r /tmp/requirements-extras.txt \
    && python3 -c "import torch, cv2, transformers, unrealcv, airsim; print('miner vlm imports ok', torch.__version__)"

WORKDIR /app

COPY requirements.txt setup.py README.md ./
COPY template ./template
COPY neurons ./neurons
COPY scripts ./scripts

RUN python3 -m pip install --no-cache-dir --extra-index-url "${PIP_EXTRA_INDEX_URL}" -r requirements.txt \
    && python3 -m pip install --no-cache-dir --extra-index-url "${PIP_EXTRA_INDEX_URL}" -e .

CMD ["python3", "neurons/miner.py", "--help"]
