# Base image with Python 3.11
FROM python:3.11-slim

# Install system dependencies for Playwright, Chromium, etc.
RUN apt-get update && \
    apt-get install -y curl gnupg libnss3 libatk1.0-0 libatk-bridge2.0-0 \
        libdrm2 libxkbcommon0 libxcomposite1 libxdamage1 libxrandr2 \
        libgbm1 libgtk-3-0 libasound2 ca-certificates && \
    rm -rf /var/lib/apt/lists/*

# Set workdir
WORKDIR /app

# Copy requirements and install
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install Playwright browsers
RUN python -m playwright install --with-deps

# Copy source code
COPY . .

# Expose port (Render will provide PORT)
ENV PORT=5000

# Start the app
CMD ["gunicorn", "app:app", "--bind", "0.0.0.0:5000", "--workers", "1"]
