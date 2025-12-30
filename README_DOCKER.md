# Docker Deployment

One-shot container for MyEntergy data collection.

## Quick Start

### Build Image
```bash
docker build -t myentergy-collector .
```

### Run with Docker Compose
Uses `config/.env` for credentials and `config/cookies.json` for session:

```bash
docker-compose up
```

### Run Docker Directly (Uses Local Files)
Equivalent to running `python3 entergy_data_collector.py --headless`:

```bash
./run-docker.sh
```

Or manually:
```bash
docker run --rm \
  --env-file config/.env \
  -v $(pwd)/config:/app/config \
  -v $(pwd)/data:/app/data \
  --shm-size=2g \
  --security-opt seccomp:unconfined \
  myentergy-collector
```

This uses your local `config/` and `data/` directories.

## How It Works

- Validates environment variables on startup
- Auto-authenticates if cookies missing/expired
- Saves cookies to `/app/config/cookies.json` (persists between runs)
- Writes CSV to `/app/data/`
- Container exits when complete

## Volumes

- `./config:/app/config` - Credentials (.env) and session cookies
- `./data:/app/data` - CSV output files

## Troubleshooting

**Container exits with error:**
- Check logs: `docker-compose logs`
- Verify credentials in `config/.env`
- Delete `config/cookies.json` to force re-auth

**Chrome issues:**
- Requires `--shm-size=2g` (Chrome needs shared memory)
- Requires `--security-opt seccomp:unconfined` (for sandboxing)

## Security

- Never commit `config/.env` to git
- Chrome runs with `--no-sandbox` (Docker compatibility)
