FROM python:3.10-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy project root for editable install (handles sys.path)
COPY pyproject.toml setup.cfg setup.py* ./
COPY processing/ ./processing/
COPY storage/ ./storage/
COPY configs/ ./configs/
COPY api/ ./api/

# Install Python dependencies
RUN pip install --no-cache-dir -r api/requirements.txt \
    && pip install --no-cache-dir -e .

EXPOSE 8000

CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
