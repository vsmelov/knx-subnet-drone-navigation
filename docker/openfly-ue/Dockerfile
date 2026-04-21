# Минимальный образ только для City Sample + UnrealCV (без Python/torch).
# Сцена и бинарники — bind-mount: ./OpenFly-Platform:/app/OpenFly-Platform
#
#   docker compose build openfly-ue

FROM nvidia/cuda:12.4.1-runtime-ubuntu22.04

ENV DEBIAN_FRONTEND=noninteractive \
    NVIDIA_DRIVER_CAPABILITIES=all \
    NVIDIA_VISIBLE_DEVICES=all

RUN apt-get update && apt-get install -y --no-install-recommends \
    bash \
    ca-certificates \
    curl \
    xvfb \
    procps \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender1 \
    libgomp1 \
    libnss3 \
    libasound2 \
    libpulse0 \
    libxrandr2 \
    libxi6 \
    libxcursor1 \
    libvulkan1 \
    libgl1 \
    libegl1 \
    libfontconfig1 \
    netcat-openbsd \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# NVIDIA Container Toolkit подкладывает libGLX_nvidia.so.* в рантайме, но JSON ICD часто отсутствует — без него Vulkan не стартует.
RUN mkdir -p /usr/share/vulkan/icd.d
COPY docker/openfly-ue/nvidia_icd.json /usr/share/vulkan/icd.d/nvidia_icd.json

COPY docker/openfly-ue/entrypoint-ue.sh /app/entrypoint-ue.sh
RUN chmod +x /app/entrypoint-ue.sh

EXPOSE 9030

ENTRYPOINT ["/bin/bash", "/app/entrypoint-ue.sh"]
