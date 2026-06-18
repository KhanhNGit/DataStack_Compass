FROM python:3.10-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc curl \
    && rm -rf /var/lib/apt/lists/*

# Copy application modules
COPY processing/ ./processing/
COPY storage/ ./storage/
COPY configs/ ./configs/
COPY api/ ./api/

# Set PYTHONPATH so absolute imports work without editable install
ENV PYTHONPATH=/app

# Install Python dependencies
RUN pip install --no-cache-dir -r api/requirements.txt

EXPOSE 8000

CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
