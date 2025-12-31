#!/bin/bash
set -e

# Validate required environment variables (loaded via env_file in docker-compose.yml)
if [ -z "$MYENTERGY_USERNAME" ] || [ -z "$MYENTERGY_PASSWORD" ]; then
    echo "ERROR: Required environment variables not set"
    echo "Please ensure /app/config/.env contains:"
    echo "  MYENTERGY_USERNAME=your_email@example.com"
    echo "  MYENTERGY_PASSWORD=your_password"
    exit 1
fi

echo "MyEntergy Data Collector - Docker Container"
echo "==========================================="
echo "Data output: /app/data (mounted volume)"
echo "Config: /app/config (mounted volume)"
echo ""

# Run data collection with explicit paths in polling mode
# Use POLL_INTERVAL_MINUTES from .env or default to 60
POLL_INTERVAL=${POLL_INTERVAL_MINUTES:-60}
echo "Starting polling mode (every ${POLL_INTERVAL} minutes)..."
echo "Press Ctrl+C to stop"
echo ""
exec python3 /app/entergy_data_collector.py --headless --cookies /app/config/cookies.json --output /app/data --poll ${POLL_INTERVAL}
