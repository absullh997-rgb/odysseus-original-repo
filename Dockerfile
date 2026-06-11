# ─────────────────────────────────────────────────────────────────────────────
# Odysseus AI — Optimized for Hugging Face Spaces (16GB RAM free tier)
# Heavy inference is routed to free external APIs (Groq, Cerebras, HF Router)
# ─────────────────────────────────────────────────────────────────────────────
FROM python:3.11-slim

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    curl \
    sqlite3 \
    libsqlite3-dev \
    && rm -rf /var/lib/apt/lists/*

# Set up user with UID 1000 (Hugging Face requirement)
RUN useradd -m -u 1000 user
USER user
ENV HOME=/home/user \
    PATH=/home/user/.local/bin:$PATH \
    # Disable heavy optional features to stay within 16GB RAM
    CHROMADB_HOST="" \
    CHROMADB_PORT="" \
    ODYSSEUS_VECTOR_BACKEND=sqlite \
    # Offload scheduled tasks to GitHub Actions instead of running in-process
    ODYSSEUS_INPROCESS_POLLERS=0 \
    ODYSSEUS_INPROCESS_TASKS=0 \
    # HF Spaces port
    APP_PORT=7860 \
    APP_BIND=0.0.0.0 \
    HF_HUB_DISABLE_SYMLINKS_WARNING=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR $HOME/app

# Copy requirements and install (core only)
COPY --chown=user:user requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt \
    && pip install --no-cache-dir --user httpx[http2] \
    && echo "✅ Core dependencies installed"

# Copy the rest of the application
COPY --chown=user:user . .

# Create necessary directories
RUN mkdir -p data logs services/cache/search research_output

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:7860/api/health 2>/dev/null || exit 1

# Expose Hugging Face default port
EXPOSE 7860

# Command to run the application on port 7860
CMD ["uvicorn", "app:app", \
     "--host", "0.0.0.0", \
     "--port", "7860", \
     "--workers", "1", \
     "--timeout-keep-alive", "30", \
     "--log-level", "info"]
