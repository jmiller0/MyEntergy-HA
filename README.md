# MyEntergy Data Collector

Clean, minimal implementation for authenticating to MyEntergy and downloading energy usage data.

## Features

- Automated reCAPTCHA solving using audio recognition
- Secure cookie-based session management
- 15-minute interval energy usage data collection
- CSV export organized by day

## Setup

1. Install dependencies:
```bash
uv pip install -r requirements.txt
```

2. Create `.env` file with your credentials:
```bash
cp .env.example .env
```

Then edit `.env` and add your credentials:
```
MYENTERGY_USERNAME=your_email@example.com
MYENTERGY_PASSWORD=your_password
```

## Usage

### Collect today's data (with automatic authentication):
```bash
python entergy_data_collector.py --auth
```

### Collect data for last N days:
```bash
python entergy_data_collector.py --auth --days 7
```

### Collect specific date range:
```bash
python entergy_data_collector.py --auth --start-date 2025-01-01 --end-date 2025-01-31
```

### Use existing cookies (skip authentication):
```bash
python entergy_data_collector.py --cookies cookies.json
```

### Verbose mode (show authentication details):
```bash
python entergy_data_collector.py --auth --verbose
```

## Files

- `myentergy_auth.py` - Authentication handler with reCAPTCHA solver
- `RecaptchaSolver.py` - Audio-based reCAPTCHA solving
- `entergy_data_collector.py` - Data collection and CSV export
- `.env` - Your credentials (not in git)
- `.env.example` - Template for credentials file
- `cookies.json` - Session cookies (auto-generated)
- `data/` - Output directory for CSV files

## Output

Data is saved to `data/entergy_usage_YYYY-MM-DD.csv` with columns:
- `timestamp` - ISO format timestamp
- `usage_kwh` - Energy usage in kWh for that 15-minute interval

## Notes

- First run requires browser automation (not headless) to solve reCAPTCHA
- Cookies are saved and reused for subsequent runs
- If session expires, re-run with `--auth` flag
