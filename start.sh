#!/usr/bin/env bash
# Install Playwright browsers
playwright install --with-deps

# Start Flask with Gunicorn
exec gunicorn app:app --bind 0.0.0.0:$PORT --workers 1
