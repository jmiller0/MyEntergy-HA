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

# Run data collection with explicit paths
echo "Running data collection..."
if ! python3 /app/entergy_data_collector.py --headless --cookies /app/config/cookies.json --output /app/data; then
    echo ""
    echo "ERROR: Data collection failed"
    echo "Check logs above for details"
    echo "Note: Script will auto re-authenticate if cookies are expired"
    exit 1
fi

echo ""
echo "Data collection complete."
