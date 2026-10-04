# Dockerfile — mwtn backend + static frontend
#
# Build:   docker build -t mwtn .
# Run:     docker run -p 8000:8000 -v ./data:/app/backend/data mwtn
#
# The data volume is the only thing you need to persist between runs.
# Mount your Colab output ZIPs or extract them there:
#   docker run ... -v /your/local/data:/app/backend/data mwtn
#
# NOTE: torch and demucs are NOT included — this image is for the
# backend API + frontend serving only. ML processing runs on Colab.
# If you want local separation, see the "Local path" section in SETUP.md.

FROM python:3.11-slim

# System deps: ffmpeg for audio export, curl for healthcheck
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    curl \
  && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python deps first (layer caching)
COPY backend/requirements.txt ./backend/requirements.txt
RUN pip install --no-cache-dir --upgrade pip \
 && pip install --no-cache-dir -r backend/requirements.txt

# Copy backend source
COPY backend/ ./backend/

# Copy static frontend (pre-built, no Node.js needed)
COPY frontend/static/ ./frontend/static/

# Runtime data directory (override with -v)
RUN mkdir -p ./backend/data ./backend/_cache ./backend/_import_tmp

EXPOSE 8000

# Healthcheck — /api/songs returns [] when healthy
HEALTHCHECK --interval=15s --timeout=5s --start-period=10s --retries=3 \
  CMD curl -sf http://localhost:8000/api/songs || exit 1

# Run as non-root
RUN useradd -m -u 1000 mwtn && chown -R mwtn:mwtn /app
USER mwtn

WORKDIR /app/backend
CMD ["uvicorn", "main:app", \
     "--host", "0.0.0.0", \
     "--port", "8000", \
     "--workers", "2"]
