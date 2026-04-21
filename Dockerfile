# Validator (and optional CPU-only tooling): slim image with bittensor only.
# **Miner** compose uses `docker/subnet-miner/Dockerfile` (CUDA + OpenFly VLM deps).
FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt setup.py README.md ./
COPY template ./template
COPY neurons ./neurons
COPY scripts ./scripts

RUN pip install --no-cache-dir -r requirements.txt \
    && pip install --no-cache-dir -e .

ENV PYTHONUNBUFFERED=1

CMD ["python", "neurons/validator.py", "--help"]
