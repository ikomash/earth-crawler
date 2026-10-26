FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1
RUN apt-get update && apt-get install -y --no-install-recommends \
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
RUN useradd -m earth_crawler
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY --chown=earth_crawler:earth_crawler . .
USER earth_crawler
ENTRYPOINT ["python", "./src/earth_crawler.py"]