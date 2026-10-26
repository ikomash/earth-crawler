
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    binutils \
    patchelf \
    libgssapi-krb5-2 \
    libgl1 \
    libglib2.0-0 \
    libxkbcommon0 \
    libxcb-icccm4 \
    libxcb-image0 \
    libxcb-keysyms1 \
    libxcb-randr0 \
    libxcb-render-util0 \
    libxcb-shape0 \
    libxcb-xinerama0 \
    libxcb-xkb1 \
    libxkbcommon-x11-0 \
    libxcb-cursor0 \
    libegl1 \
    fontconfig \
    libdbus-1-3 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt ./requirements.txt
COPY requirements-build.txt ./requirements-build.txt

RUN pip install --no-cache-dir -r requirements.txt \
    && pip install --no-cache-dir -r requirements-build.txt

COPY . .

CMD ["python", "scripts/build_with_pyinstaller.py", "--platform", "linux"]
