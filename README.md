# MyEntergy Data Collector

Automated collection of 15-minute interval electricity usage data from MyEntergy.

## Features

- Automated login with reCAPTCHA solving
- 15-minute interval energy usage data
- CSV export organized by day

## Requirements

- Python 3.9+
- Chromium/Chrome browser
- FFmpeg

## Setup

1. Install dependencies:
```bash
pip install -r requirements.txt
```

2. Create `.env` file:
```bash
cp .env.example .env
```

3. Edit `.env` with your MyEntergy credentials:
```
MYENTERGY_USERNAME=your_email@example.com
MYENTERGY_PASSWORD=your_password
```

## Usage

Collect today's data:
```bash
python entergy_data_collector.py --auth
```

Collect last 7 days:
```bash
python entergy_data_collector.py --auth --days 7
```

Collect specific date range:
```bash
python entergy_data_collector.py --auth --start-date 2025-01-01 --end-date 2025-01-31
```

## Options

- `--auth` - Authenticate and save session cookies
- `--headless` - Run browser in headless mode
- `--verbose` - Show detailed authentication logs
- `--days N` - Collect last N days of data
- `--start-date / --end-date` - Collect specific date range

## Output

CSV files saved to `data/entergy_usage_YYYY-MM-DD.csv`:
- `timestamp` - ISO format timestamp
- `usage_kwh` - Energy usage in kWh (15-minute intervals)

## Notes

Session cookies are saved to `cookies.json` and reused automatically. If expired, the script re-authenticates.
