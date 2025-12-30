import requests
import json
import os
import time
import csv
import logging
from datetime import datetime, timedelta
import argparse
from myentergy_auth import MyEntergyAuth
from dotenv import load_dotenv

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)


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
        """Load cookies from a JSON file. Creates empty file if missing."""
        if not os.path.exists(filepath):
            logging.warning(f"Cookie file not found at {filepath}, will create after authentication")
            return

        try:
            with open(filepath, 'r') as f:
                cookies = json.load(f)
            self._load_cookies_from_list(cookies)
        except (json.JSONDecodeError, ValueError):
            logging.warning(f"Cookie file at {filepath} is invalid, will re-authenticate")
            return

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

            logging.info(f"Fetching data for {current_time.strftime('%Y-%m-%d')} {time_range}")

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
                                    logging.warning(f" Error processing timestamp {ts}: {e}")

                            logging.info(f"✓ Retrieved {len(data_points)} data points")
                else:
                    logging.error(f"✗ API returned status {response.status_code}")
            except Exception as e:
                logging.error(f"✗ Error fetching data: {e}")

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
            logging.info(f"✓ Saved {len(day_records)} records to {filename}")
            created_files.append(filename)

        return created_files

    def get_green_button_xml(self, start_date, end_date, fuel_type='E', interval_length='MONTHLY'):
        """
        Download Green Button XML data from Entergy.
        
        Args:
            start_date: Start date as string in YYYY-MM-DD format or datetime object
            end_date: End date as string in YYYY-MM-DD format or datetime object
            fuel_type: 'E' for electricity, 'G' for gas (default: 'E')
            interval_length: 'MONTHLY' or 'DAILY' (default: 'MONTHLY')
        
        Returns:
            bytes: XML content if successful, None if failed
        """
        try:
            from datetime import datetime
            
            # Convert dates to MM-DD-YYYY format if they're not already strings
            if hasattr(start_date, 'strftime'):  # datetime object
                start_date_str = start_date.strftime('%m-%d-%Y')
            else:  # string in YYYY-MM-DD format
                date_obj = datetime.strptime(str(start_date).split()[0], '%Y-%m-%d')
                start_date_str = date_obj.strftime('%m-%d-%Y')
            
            if hasattr(end_date, 'strftime'):  # datetime object
                end_date_str = end_date.strftime('%m-%d-%Y')
            else:  # string in YYYY-MM-DD format
                date_obj = datetime.strptime(str(end_date).split()[0], '%Y-%m-%d')
                end_date_str = date_obj.strftime('%m-%d-%Y')
            
            # Use the meter ID - you may need to extract this from the page dynamically
            backup_meter_id_owh = "METER_ID_REMOVED"
            
            # Build the endpoint URL with properly formatted dates
            url = (
                f"https://myentergyadvisor.entergy.com/cassandra/getfile/"
                f"period/custom/"
                f"start_date/{start_date_str}/"
                f"to_date/{end_date_str}/"
                f"format/xml/"
                f"fuel_type/{fuel_type}/"
                f"backup_meter_id_owh/{backup_meter_id_owh}/"
                f"from_usage/1/"
                f"interval_length/{interval_length}"
            )
            
            logging.info(f"Fetching XML from: {url}")
            response = self.session.get(url, timeout=30)
            
            if response.status_code == 200:
                # Verify it's valid XML
                if response.text.startswith('<?xml'):
                    logging.info(f"✓ Successfully downloaded {len(response.content)} bytes of XML data")
                    return response.content
                else:
                    logging.error("✗ Error: Response does not appear to be valid XML")
                    return None
            else:
                logging.error(f"✗ Error: HTTP {response.status_code}")
                return None
                
        except Exception as e:
            logging.error(f"✗ Error downloading XML: {e}")
            return None

    def save_green_button_xml(self, start_date, end_date, filename=None, fuel_type='E', interval_length='MONTHLY'):
        """
        Download and save Green Button XML data.
        
        Args:
            start_date: Start date as string in YYYY-MM-DD format or datetime object
            end_date: End date as string in YYYY-MM-DD format or datetime object
            filename: Output filename (default: greenbutton_{start_date}_{end_date}.xml)
            fuel_type: 'E' for electricity, 'G' for gas (default: 'E')
            interval_length: 'MONTHLY' or 'DAILY' (default: 'MONTHLY')
        """
        from datetime import datetime
        import os
        
        xml_data = self.get_green_button_xml(start_date, end_date, fuel_type, interval_length)
        
        if xml_data:
            if filename is None:
                # Convert dates to clean format for filename
                if hasattr(start_date, 'strftime'):  # datetime object
                    start_str = start_date.strftime('%Y-%m-%d')
                else:  # string
                    start_str = str(start_date).split()[0]  # Get just the date part
                
                if hasattr(end_date, 'strftime'):  # datetime object
                    end_str = end_date.strftime('%Y-%m-%d')
                else:  # string
                    end_str = str(end_date).split()[0]  # Get just the date part
                
                filename = f"{start_str}_{end_str}.xml"
            
            # Create data directory if it doesn't exist
            os.makedirs('data', exist_ok=True)
            filepath = os.path.join('data', filename)
            
            with open(filepath, 'wb') as f:
                f.write(xml_data)
            logging.info(f"✓ Successfully saved XML file to {filepath}")
            return filepath
        else:
            logging.error("✗ Failed to download XML data")
            return None

    def get_on_demand_read(self, cust_id=None, meter_id=None):
        """
        Get on-demand meter read data from Entergy.

        Args:
            cust_id: Customer ID (uses hardcoded default if None)
            meter_id: Meter ID (uses hardcoded default if None)

        Returns:
            dict: JSON response if successful, None if failed
        """
        try:
            # Default values
            if not cust_id:
                cust_id = "CUSTOMER_ID_REMOVED"
            if not meter_id:
                meter_id = "METER_ID_REMOVED"

            now = datetime.now()
            today = now.strftime('%Y-%m-%d')
            today_formatted = now.strftime('%m%%2F%d%%2F%Y')
            first_of_month = now.replace(day=1).strftime('%m%%2F%d%%2F%Y')

            url = (
                f"https://myentergyadvisor.entergy.com/myenergy/odr-ajax"
                f"?date={today}"
                f"&custId={cust_id}"
                f"&countHourly=1"
                f"&useselectric=NO"
                f"&usesgas=NO"
                f"&usespropane=NO"
                f"&useswater=NO"
                f"&usesreclaim=NO"
                f"&usesirrigation=NO"
                f"&usesktg=NO"
                f"&usesvoltage=NO"
                f"&fuelType=E-AM12380287-{meter_id}"
                f"&usageType=Q"
                f"&timePeriod=MONTHLY"
                f"&overlay_with=weather"
                f"&select-time=00%3A00-02%3A59"
                f"&select-date-to={today_formatted}"
                f"&select-date-from={first_of_month}"
                f"&show_demand=1"
                f"&get_on_demand_read=1"
            )

            logging.info(f"Fetching on-demand read from: {url}")
            response = self.session.get(url, timeout=30)

            if response.status_code == 200:
                data = response.json()
                logging.info(f"✓ Successfully retrieved on-demand read data")
                return data
            else:
                logging.error(f"✗ Error: HTTP {response.status_code}")
                return None

        except Exception as e:
            logging.error(f"✗ Error fetching on-demand read: {e}")
            return None

    def save_on_demand_read(self, cust_id=None, meter_id=None, filename=None):
        """
        Download and save on-demand read data.

        Args:
            cust_id: Customer ID (uses hardcoded default if None)
            meter_id: Meter ID (uses hardcoded default if None)
            filename: Output filename (default: on_demand_YYYYMMDD_HHMMSS.json)
        """
        data = self.get_on_demand_read(cust_id, meter_id)

        if data:
            if filename is None:
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                filename = f"on_demand_{timestamp}.json"

            os.makedirs('data', exist_ok=True)
            filepath = os.path.join('data', filename)

            with open(filepath, 'w') as f:
                json.dump(data, f, indent=2)
            logging.info(f"✓ Successfully saved on-demand read to {filepath}")

            # Log all readings from registers with deltas
            if 'registers' in data and data['registers']:
                logging.info("On-Demand Read History:")
                prev_reading = None
                for i, register in enumerate(data['registers']):
                    reading = register.get('odr_amt')
                    timestamp = register.get('last_request_timestamp')

                    delta_str = ""
                    if reading is not None and prev_reading is not None:
                        delta = prev_reading - reading
                        delta_str = f" (Δ {delta:.2f} kWh)"

                    reading_str = f"{reading} kWh" if reading is not None else "null"
                    logging.info(f"  [{i}] {timestamp}: {reading_str}{delta_str}")

                    if reading is not None:
                        prev_reading = reading

            # Log rate level
            if 'rate_level' in data and data['rate_level']:
                logging.info(f"Rate Level: {data['rate_level']}")

            return filepath
        else:
            logging.error("✗ Failed to retrieve on-demand read data")
            return None

def main():
    parser = argparse.ArgumentParser(description='MyEntergy Data Collector')
    parser.add_argument('--cookies', default='cookies.json', help='Path to cookies file')
    parser.add_argument('--output', default='data', help='Output directory for files')
    parser.add_argument('--start-date', help='Start date (YYYY-MM-DD)')
    parser.add_argument('--end-date', help='End date (YYYY-MM-DD)')
    parser.add_argument('--days', type=int, help='Number of days to collect (from today backward)')
    parser.add_argument('--format', choices=['csv', 'xml', 'both'], default='xml',
                       help='Download format: csv, xml, or both (default: xml)')
    parser.add_argument('--auth', action='store_true', help='Authenticate first and save cookies')
    parser.add_argument('--headless', action='store_true', help='Run authentication in headless mode (no GUI)')
    parser.add_argument('--verbose', action='store_true', help='Enable verbose auth logging')
    parser.add_argument('--manual', action='store_true', help='Pause for manual login button click (debug mode)')
    parser.add_argument('--poll', type=int, nargs='?', const=5, metavar='MINUTES', help='Poll every N minutes (runs forever, default: 5)')
    args = parser.parse_args()

    # Adjust log level for verbose mode
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    # Helper function for authentication
    def authenticate():
        """Perform authentication and save cookies."""
        logging.info("Authenticating to MyEntergy...")
        # Load credentials from environment
        load_dotenv()  # No-op if .env doesn't exist (e.g., in Docker)
        username = os.getenv('MYENTERGY_USERNAME')
        password = os.getenv('MYENTERGY_PASSWORD')

        if not username or not password:
            logging.error("Error: MYENTERGY_USERNAME and MYENTERGY_PASSWORD must be set")
            logging.error(" Local: Create .env file with credentials")
            logging.error(" Docker: Ensure config/.env is mounted and loaded via env_file")
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
            logging.info(f"✓ Authentication successful, cookies saved to {args.cookies}")
            return True
        except Exception as e:
            logging.error(f"✗ Authentication failed: {e}")
            return False

    # Helper function to calculate next scheduled run time
    def get_next_scheduled_time(poll_interval):
        """Calculate the next scheduled run time based on poll interval."""
        now = datetime.now()
        current_minute = now.minute
        next_minute = ((current_minute // poll_interval) + 1) * poll_interval

        if next_minute >= 60:
            next_minute = 0
            next_run = now.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
        else:
            next_run = now.replace(minute=next_minute, second=0, microsecond=0)

        return next_run

    # Helper function for data collection (extracted for polling loop)
    def collect_data(collector):
        """Perform a single data collection cycle."""
        # Verify session
        logging.info("Verifying session...")
        if not collector.verify_session():
            logging.error("✗ Session invalid or expired - attempting automatic re-authentication...")
            if not authenticate():
                logging.error("✗ Automatic re-authentication failed")
                return None

            # Reload cookies after successful auth
            logging.info(f"Reloading cookies from {args.cookies}...")
            collector = EntergyDataCollector(cookies_file=args.cookies)

            # Verify again
            if not collector.verify_session():
                logging.error("✗ Session still invalid after re-authentication")
                return None

            logging.info("✓ Re-authentication successful")
        else:
            logging.info("✓ Session valid")

        # Determine date range
        if args.start_date and args.end_date:
            start_date = datetime.strptime(args.start_date, '%Y-%m-%d')
            end_date = datetime.strptime(args.end_date, '%Y-%m-%d')
            # Ensure end_date is end of day
            end_date = end_date.replace(hour=23, minute=59, second=59, microsecond=999999)
        elif args.days:
            end_date = datetime.now().replace(hour=23, minute=59, second=59, microsecond=999999)
            start_date = (end_date - timedelta(days=args.days)).replace(hour=0, minute=0, second=0, microsecond=0)
        else:
            # Default to current full day (midnight to current time or end of day)
            now = datetime.now()
            start_date = now.replace(hour=0, minute=0, second=0, microsecond=0)
            end_date = now.replace(hour=23, minute=59, second=59, microsecond=999999)

        logging.info(f"Collecting data from {start_date.date()} to {end_date.date()}")

        # Download based on format selection
        if args.format in ['csv', 'both']:
            # Collect CSV data
            data = collector.get_usage_data(start_date, end_date)
            logging.info(f"✓ Collected {data['total_points']} total data points")

            # Save to CSV
            if data['total_points'] > 0:
                logging.info(f"Saving to CSV files in {args.output}/...")
                files = collector.save_to_csv(data, args.output)
                logging.info(f"✓ Created {len(files)} CSV file(s)")
            else:
                logging.error("✗ No CSV data collected")

        if args.format in ['xml', 'both']:
            # Download and save Green Button XML data
            logging.info("Downloading Green Button XML...")
            xml_file = collector.save_green_button_xml(start_date, end_date)

            if not xml_file:
                logging.error("✗ Failed to retrieve Green Button XML data")

        # Fetch on-demand read data
        logging.info("Fetching on-demand meter read...")
        odr_file = collector.save_on_demand_read()
        if not odr_file:
            logging.error("✗ Failed to retrieve on-demand read data")

        return collector

    # Authenticate if requested or cookies missing
    if args.auth or not os.path.exists(args.cookies):
        if not authenticate():
            return 1

    # Verify cookies exist
    if not os.path.exists(args.cookies):
        logging.error(f"Error: Cookies file not found: {args.cookies}")
        logging.error("Run with --auth to authenticate first")
        return 1

    # Initialize collector
    logging.info(f"Loading cookies from {args.cookies}...")
    collector = EntergyDataCollector(cookies_file=args.cookies)

    # Handle polling mode
    if args.poll is not None:
        poll_interval = args.poll if args.poll > 0 else 5
        logging.info(f"Starting polling mode: collecting data every {poll_interval} minute(s)")
        logging.info(f"Scheduled times: :{':'.join([f'{m:02d}' for m in range(0, 60, poll_interval)])}")
        logging.info("Press Ctrl+C to stop")

        iteration = 0
        try:
            # Handle initial sync to schedule
            now = datetime.now()
            current_minute = now.minute
            current_second = now.second

            # Check if we should run immediately or wait
            if current_minute % poll_interval == 0 and current_second < 5:
                # We're within 5 seconds of a valid minute mark, run immediately
                logging.info("Starting immediately (on schedule)")
            else:
                # Sleep until next scheduled time
                next_run = get_next_scheduled_time(poll_interval)
                sleep_seconds = (next_run - now).total_seconds()
                logging.info(f"First run will be at {next_run.strftime('%H:%M:%S')}")
                logging.info(f"Sleeping for {sleep_seconds:.0f} seconds...")
                time.sleep(sleep_seconds)

            while True:
                iteration += 1
                logging.info("=" * 60)
                logging.info(f"Poll iteration #{iteration} - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
                logging.info("=" * 60)

                collector = collect_data(collector)
                if collector is None:
                    logging.error("✗ Collection failed, will retry on next poll")

                # Calculate exact sleep time to next scheduled run (accounts for execution time)
                next_run = get_next_scheduled_time(poll_interval)
                sleep_seconds = (next_run - datetime.now()).total_seconds()

                # If we're behind schedule (collection took too long), keep advancing until positive
                while sleep_seconds < 0:
                    logging.warning(f"Collection took longer than poll interval, advancing to next scheduled time")
                    # Manually advance to next interval since we're already past next_run
                    current_minute = datetime.now().minute
                    next_minute = ((current_minute // poll_interval) + 1) * poll_interval
                    if next_minute >= 60:
                        next_run = datetime.now().replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
                    else:
                        next_run = datetime.now().replace(minute=next_minute, second=0, microsecond=0)
                    sleep_seconds = (next_run - datetime.now()).total_seconds()

                logging.info("=" * 60)
                logging.info(f"Next run at {next_run.strftime('%H:%M:%S')} (sleeping {sleep_seconds:.0f}s)")
                logging.info("=" * 60)
                time.sleep(sleep_seconds)
        except KeyboardInterrupt:
            logging.info("Polling stopped by user")
            return 0
    else:
        # Single run mode (original behavior)
        collector = collect_data(collector)
        if collector is None:
            return 1

    return 0


if __name__ == "__main__":
    exit(main())
