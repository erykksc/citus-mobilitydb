FROM python:3.11-slim

# Install system dependencies for psycopg2
RUN apt-get update && \
    apt-get install -y gcc libpq-dev && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Install required Python libraries
RUN pip install --no-cache-dir psycopg2-binary kubernetes

# Copy the manager script
COPY manager_k8s.py .

# Create directory for healthcheck
RUN mkdir -p /healthcheck

# Set environment variables for healthcheck
ENV PYTHONUNBUFFERED=1
ENV SYNC_INTERVAL_SECONDS=20

# Set entrypoint
ENTRYPOINT ["python", "manager_k8s.py"]

