import requests
import json
import os
import time
import csv
from datetime import datetime, timedelta
import argparse
from myentergy_auth import MyEntergyAuth
from dotenv import load_dotenv


class EntergyDataCollector:
    """Collects energy usage data from MyEntergy API."""

    def __init__(self, cookies: list = None, cookies_file: str = None):
        """Initialize the data collector.

        Args:
            cookies: List of cookie dictionaries
            cookies_file: Path to cookies JSON file (alternative to cookies param)
        """
        self.session = requests.Session()
        self.base_url = "https://myentergyadvisor.entergy.com"

        # Set common headers
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "Accept-Language": "en-US,en;q=0.9",
            "X-Requested-With": "XMLHttpRequest",
        })

        # Load cookies
        if cookies:
            self._load_cookies_from_list(cookies)
        elif cookies_file:
            self._load_cookies_from_file(cookies_file)
        else:
            raise ValueError("Either cookies or cookies_file must be provided")

    def _load_cookies_from_list(self, cookies: list) -> None:
        """Load cookies from a list."""
        for cookie in cookies:
            self.session.cookies.set(
                cookie['name'],
                cookie['value'],
                domain=cookie.get('domain', ''),
                path=cookie.get('path', '/'),
                secure=cookie.get('secure', False)
            )

    def _load_cookies_from_file(self, filepath: str) -> None:
        """Load cookies from a JSON file."""
        with open(filepath, 'r') as f:
            cookies = json.load(f)
        self._load_cookies_from_list(cookies)

    def verify_session(self) -> bool:
        """Verify that the session is still valid.

        Returns:
            bool: True if session is valid, False otherwise
        """
        try:
            response = self.session.get(
                f"{self.base_url}/myenergy/usage-history",
                allow_redirects=False
            )
            return response.status_code == 200
        except Exception:
            return False

    def get_usage_data(self, start_date: datetime = None, end_date: datetime = None,
                      fuel_type: str = None, interval: str = "15min") -> dict:
        """Get usage data for the specified date range.

        Args:
            start_date: Start date for data collection (defaults to start of current day)
            end_date: End date for data collection (defaults to now)
            fuel_type: Fuel type identifier from MyEntergy (auto-detected if None)
            interval: Time interval - "15min", "hourly", or "daily"

        Returns:
            dict: Usage data with timestamps and values
        """
        if not end_date:
            end_date = datetime.now()
        if not start_date:
            start_date = end_date.replace(hour=0, minute=0, second=0, microsecond=0)

        all_data = []
        current_time = start_date

        # Process in 3-hour chunks for 15-minute data
        chunk_hours = 3 if interval == "15min" else 24

        while current_time < end_date:
            chunk_end = min(
                current_time + timedelta(hours=chunk_hours),
                end_date
            )

            time_range = f"{current_time.strftime('%H:%M')}-{chunk_end.strftime('%H:%M')}"
            formatted_date = current_time.strftime("%m/%d/%Y")

            print(f"Fetching data for {current_time.strftime('%Y-%m-%d')} {time_range}")

            # API parameters
            params = {
                "date": current_time.strftime("%Y-%m-%d"),
                "usageType": "Q",
                "timePeriod": interval,
                "select-time": time_range,
                "select-date-to": formatted_date,
                "select-date-from": formatted_date,
                "show_demand": "1",
            }

            # Auto-detect fuel type if not provided
            if fuel_type:
                params["fuelType"] = fuel_type

            try:
                response = self.session.get(
                    f"{self.base_url}/myenergy/usage-history-ajax/format/json",
                    params=params
                )

                if response.status_code == 200:
                    data = response.json()

                    if "series_data" in data and len(data["series_data"]) > 0:
                        series = data["series_data"][0]
                        if "data" in series:
                            timestamps = data.get("column_fulldates", [])
                            data_points = series["data"]

                            for ts, dp in zip(timestamps, data_points):
                                try:
                                    ts_str = ts.split(" GMT")[0]
                                    timestamp = datetime.strptime(ts_str, "%Y-%m-%d %H:%M:%S")
                                    all_data.append({
                                        "timestamp": timestamp.isoformat(),
                                        "usage_kwh": dp
                                    })
                                except Exception as e:
                                    print(f"Warning: Error processing timestamp {ts}: {e}")

                            print(f"  ✓ Retrieved {len(data_points)} data points")
                else:
                    print(f"  ✗ API returned status {response.status_code}")

            except Exception as e:
                print(f"  ✗ Error fetching data: {e}")

            current_time = chunk_end
            time.sleep(1)  # Rate limiting

        return {
            "data": all_data,
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "total_points": len(all_data)
        }

    def save_to_csv(self, data: dict, output_dir: str = "data") -> list:
        """Save usage data to CSV files (one per day).

        Args:
            data: Usage data dictionary from get_usage_data()
            output_dir: Directory to save CSV files

        Returns:
            list: Paths to created CSV files
        """
        os.makedirs(output_dir, exist_ok=True)

        # Group data by day
        data_by_day = {}
        for record in data["data"]:
            timestamp = datetime.fromisoformat(record["timestamp"])
            day_key = timestamp.strftime("%Y-%m-%d")

            if day_key not in data_by_day:
                data_by_day[day_key] = []

            data_by_day[day_key].append(record)

        # Save each day to separate CSV
        created_files = []
        for day_key, day_records in data_by_day.items():
            filename = os.path.join(output_dir, f"entergy_usage_{day_key}.csv")

            with open(filename, 'w', newline='') as csvfile:
                fieldnames = ['timestamp', 'usage_kwh']
                writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(day_records)

            print(f"  ✓ Saved {len(day_records)} records to {filename}")
            created_files.append(filename)

        return created_files


def main():
    parser = argparse.ArgumentParser(description='MyEntergy Data Collector')
    parser.add_argument('--cookies', default='cookies.json', help='Path to cookies file')
    parser.add_argument('--output', default='data', help='Output directory for CSV files')
    parser.add_argument('--start-date', help='Start date (YYYY-MM-DD)')
    parser.add_argument('--end-date', help='End date (YYYY-MM-DD)')
    parser.add_argument('--days', type=int, help='Number of days to collect (from today backward)')
    parser.add_argument('--auth', action='store_true', help='Authenticate first and save cookies')
    parser.add_argument('--headless', action='store_true', help='Run authentication in headless mode (no GUI)')
    parser.add_argument('--verbose', action='store_true', help='Enable verbose auth logging')
    parser.add_argument('--manual', action='store_true', help='Pause for manual login button click (debug mode)')
    args = parser.parse_args()

    # Helper function for authentication
    def authenticate():
        """Perform authentication and save cookies."""
        print("Authenticating to MyEntergy...")

        # Load credentials from environment
        load_dotenv()
        username = os.getenv('MYENTERGY_USERNAME')
        password = os.getenv('MYENTERGY_PASSWORD')

        if not username or not password:
            print("Error: MYENTERGY_USERNAME and MYENTERGY_PASSWORD must be set in .env file")
            return False

        auth = MyEntergyAuth(
            username,
            password,
            headless=args.headless,
            verbose=args.verbose,
            manual_mode=args.manual
        )

        try:
            cookies = auth.login()
            auth.save_cookies(args.cookies)
            print(f"✓ Authentication successful, cookies saved to {args.cookies}\n")
            return True
        except Exception as e:
            print(f"✗ Authentication failed: {e}")
            return False

    # Authenticate if requested or cookies missing
    if args.auth or not os.path.exists(args.cookies):
        if not authenticate():
            return 1

    # Verify cookies exist
    if not os.path.exists(args.cookies):
        print(f"Error: Cookies file not found: {args.cookies}")
        print("Run with --auth to authenticate first")
        return 1

    # Initialize collector
    print(f"Loading cookies from {args.cookies}...")
    collector = EntergyDataCollector(cookies_file=args.cookies)

    # Verify session
    print("Verifying session...")
    if not collector.verify_session():
        print("✗ Session invalid or expired - attempting automatic re-authentication...")

        if not authenticate():
            print("✗ Automatic re-authentication failed")
            return 1

        # Reload cookies after successful auth
        print(f"Reloading cookies from {args.cookies}...")
        collector = EntergyDataCollector(cookies_file=args.cookies)

        # Verify again
        if not collector.verify_session():
            print("✗ Session still invalid after re-authentication")
            return 1

        print("✓ Re-authentication successful\n")
    else:
        print("✓ Session valid\n")

    # Determine date range
    if args.start_date and args.end_date:
        start_date = datetime.strptime(args.start_date, '%Y-%m-%d')
        end_date = datetime.strptime(args.end_date, '%Y-%m-%d')
    elif args.days:
        end_date = datetime.now()
        start_date = end_date - timedelta(days=args.days)
    else:
        # Default to current day
        end_date = datetime.now()
        start_date = end_date.replace(hour=0, minute=0, second=0, microsecond=0)

    print(f"Collecting data from {start_date.date()} to {end_date.date()}\n")

    # Collect data
    data = collector.get_usage_data(start_date, end_date)

    print(f"\n✓ Collected {data['total_points']} total data points")

    # Save to CSV
    if data['total_points'] > 0:
        print(f"\nSaving to CSV files in {args.output}/...")
        files = collector.save_to_csv(data, args.output)
        print(f"\n✓ Created {len(files)} CSV file(s)")
    else:
        print("\n✗ No data collected")

    return 0


if __name__ == "__main__":
    exit(main())
