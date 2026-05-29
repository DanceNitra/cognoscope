FROM python:3.12-slim

WORKDIR /app

# Minimal system deps
RUN apt-get update -qq && \
    apt-get install -y -qq --no-install-recommends \
        git \
    && rm -rf /var/lib/apt/lists/*

# Copy dependency manifest first for layer caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy cognoscope
COPY . .

# Default command: show status dashboard
CMD ["python", "cli.py", "status"]
