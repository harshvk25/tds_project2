# Use official Playwright base image with all dependencies
FROM mcr.microsoft.com/playwright/python:v1.48.0-jammy

# Prevent Python from writing .pyc files
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Set work directory
WORKDIR /app

# Install Python deps
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy project files
COPY . /app

# Expose port for Render
EXPOSE 5000

# Start the app
CMD ["gunicorn", "-b", "0.0.0.0:5000", "app:app"]
