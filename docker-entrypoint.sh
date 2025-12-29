#!/bin/bash
set -e

# Ensure .env file exists in config volume
if [ ! -f /app/config/.env ]; then
    echo "ERROR: .env file not found in /app/config/"
    echo "Please create /app/config/.env with:"
    echo "  MYENTERGY_USERNAME=your_email@example.com"
    echo "  MYENTERGY_PASSWORD=your_password"
    exit 1
fi

# Symlink .env and cookies.json from config volume
# This ensures all reads/writes go directly to the config volume
ln -sf /app/config/.env /app/.env
ln -sf /app/config/cookies.json /app/cookies.json

# Set default collection interval (in minutes)
COLLECTION_INTERVAL=${COLLECTION_INTERVAL:-15}

echo "MyEntergy Data Collector - Docker Container"
echo "==========================================="
echo "Collection interval: every ${COLLECTION_INTERVAL} minutes"
echo "Data output: /app/data (mounted volume)"
echo "Config: /app/config (mounted volume)"
echo ""

# Run initial collection
echo "Running initial data collection..."
if ! python3 /app/entergy_data_collector.py --headless; then
    echo ""
    echo "ERROR: Initial data collection failed"
    echo "Container will exit to prevent API throttling"
    echo "Check your credentials in /app/config/.env and try again"
    exit 1
fi

# Setup cron job (no copy needed - cookies.json writes directly to config via symlink)
echo "*/${COLLECTION_INTERVAL} * * * * cd /app && python3 /app/entergy_data_collector.py --headless >> /var/log/cron.log 2>&1" > /etc/cron.d/myentergy
chmod 0644 /etc/cron.d/myentergy
crontab /etc/cron.d/myentergy

# Create log file
touch /var/log/cron.log

echo ""
echo "Initial collection complete. Starting cron scheduler..."
echo "Logs will be written to /var/log/cron.log"
echo ""

# Start cron in foreground and tail logs
cron && tail -f /var/log/cron.log
