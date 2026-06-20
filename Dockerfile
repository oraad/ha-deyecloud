# syntax=docker/dockerfile:1

FROM mcr.microsoft.com/devcontainers/python:3.14

# ffmpeg omitted — not needed for this integration's tests; avoids a large apt tree.
RUN for attempt in 1 2 3; do \
        apt-get update \
        && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
            libturbojpeg0 \
            libpcap-dev \
            libcairo2 \
            libcairo2-dev \
            libffi-dev \
        && break; \
        echo "apt install failed (attempt ${attempt}), retrying..." >&2; \
        sleep 15; \
    done \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /workspace

COPY requirements.txt requirements_test.txt ./
RUN python3 -m pip install --no-cache-dir --upgrade pip \
    && python3 -m pip install --no-cache-dir -r requirements_test.txt

COPY . .

ENV PYTHONPATH=/workspace/custom_components

CMD ["sleep", "infinity"]
