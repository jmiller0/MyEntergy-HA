# MyEntergy Data Collector - Docker Deployment

Automated data collection running in a Docker container with scheduled cron jobs.

## Quick Start

### 1. Setup Configuration

Create a `config` directory and add your credentials:

```bash
mkdir -p config
cat > config/.env << EOF
MYENTERGY_USERNAME=your_email@example.com
MYENTERGY_PASSWORD=your_password
EOF
```

### 2. Build and Run

Using Docker Compose (recommended):

```bash
docker-compose up -d
```

Or using Docker directly:

```bash
# Build image
docker build -t myentergy-collector .

# Run container
docker run -d \
  --name myentergy-collector \
  --restart unless-stopped \
  -v $(pwd)/data:/app/data \
  -v $(pwd)/config:/app/config \
  -e COLLECTION_INTERVAL=15 \
  --shm-size=2g \
  --security-opt seccomp:unconfined \
  myentergy-collector
```

### 3. Monitor Logs

```bash
# Docker Compose
docker-compose logs -f

# Docker
docker logs -f myentergy-collector
```

## Configuration

### Environment Variables

- `COLLECTION_INTERVAL`: Data collection interval in minutes (default: 15)

Set in `docker-compose.yml`:

```yaml
environment:
  - COLLECTION_INTERVAL=15
```

Or with Docker run:

```bash
docker run -e COLLECTION_INTERVAL=30 ...
```

### Volume Mounts

**Required volumes:**

- `./config:/app/config` - Credentials (.env) and session cookies
- `./data:/app/data` - CSV output files

## How It Works

1. **Initial startup:**
   - Validates `.env` file exists in `/app/config`
   - Runs initial data collection with auto-authentication
   - Saves session cookies to `/app/config/cookies.json`

2. **Scheduled collection:**
   - Cron job runs every `COLLECTION_INTERVAL` minutes
   - Uses existing cookies (auto re-authenticates if expired)
   - Appends data to CSV files in `/app/data`
   - Persists cookies back to `/app/config`

3. **Self-healing:**
   - Automatically re-authenticates when session expires (~24 hours)
   - No manual intervention required

## Maintenance

### View cron logs

```bash
docker exec myentergy-collector tail -f /var/log/cron.log
```

### Force re-authentication

```bash
docker exec myentergy-collector rm /app/config/cookies.json
docker restart myentergy-collector
```

### Change collection interval

Edit `docker-compose.yml`, then:

```bash
docker-compose down
docker-compose up -d
```

### Backup data

CSV files are in `./data/`:

```bash
tar -czf myentergy-backup-$(date +%Y%m%d).tar.gz data/
```

## Troubleshooting

### Container exits immediately

Check logs for missing .env file:

```bash
docker logs myentergy-collector
```

Ensure `config/.env` exists with valid credentials.

### Authentication failures

Check credentials in `config/.env`:

```bash
cat config/.env
```

View detailed logs:

```bash
docker logs -f myentergy-collector
```

### No data being collected

Check cron logs:

```bash
docker exec myentergy-collector tail -100 /var/log/cron.log
```

Verify cron is running:

```bash
docker exec myentergy-collector ps aux | grep cron
```

### Chrome/browser issues

The container includes Chrome with headless mode. If browser issues occur:

1. Check shared memory size (should be 2GB): `--shm-size=2g`
2. Verify security options: `--security-opt seccomp:unconfined`

## System Requirements

- **Docker**: 20.10+
- **Docker Compose**: 1.29+ (optional but recommended)
- **Disk space**: ~500MB for image, ~1MB per day of data
- **Memory**: 2GB minimum (for Chrome headless)

## Security Notes

- Never commit `config/.env` to version control
- `config/` directory is in `.gitignore` and `.dockerignore`
- Container runs Chrome in sandbox mode with `--no-sandbox` for compatibility
- Session cookies are stored in `config/cookies.json` (auto-generated)
