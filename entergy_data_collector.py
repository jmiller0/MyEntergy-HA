import requests
import json
import os
import time
import csv
import logging
import re
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from pathlib import Path
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

        # Load account IDs (cust_id, meter_id)
        self.cust_id = None
        self.meter_id = None
        self._load_account_ids()

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

    def _load_account_ids(self) -> None:
        """Load customer ID and meter ID using fallback chain:
        1. Try loading from .entergy_config.json (cached)
        2. Try extracting from authenticated session
        3. Try loading from environment variables
        4. Fail with helpful error
        """
        # Try config directory first (Docker mount), fallback to current dir
        config_dir = Path('config')
        if config_dir.exists() and config_dir.is_dir():
            config_path = config_dir / '.entergy_config.json'
        else:
            config_path = Path('.entergy_config.json')

        # Step 1: Try cached config file
        if config_path.exists():
            try:
                with open(config_path, 'r') as f:
                    config = json.load(f)
                self.cust_id = config.get('cust_id')
                self.meter_id = config.get('meter_id')
                if self.cust_id and self.meter_id:
                    logging.info(f"✓ Loaded account IDs from {config_path}")
                    return
            except (json.JSONDecodeError, ValueError) as e:
                logging.warning(f"Failed to load {config_path}: {e}")

        # Step 2: Try extracting from session
        logging.info("Extracting account IDs from MyEntergy session...")
        extracted = self._extract_account_ids()
        if extracted and extracted.get('cust_id') and extracted.get('meter_id'):
            self.cust_id = extracted['cust_id']
            self.meter_id = extracted['meter_id']
            # Save for future use
            try:
                with open(config_path, 'w') as f:
                    json.dump(extracted, f, indent=2)
                logging.info(f"✓ Account IDs extracted and saved to {config_path}")
            except Exception as e:
                logging.warning(f"Failed to save config: {e}")
            return

        # Step 3: Try environment variables
        self.cust_id = os.getenv('MYENTERGY_CUSTOMER_ID')
        self.meter_id = os.getenv('MYENTERGY_METER_ID')
        if self.cust_id and self.meter_id:
            logging.info("✓ Loaded account IDs from environment variables")
            return

        # Step 4: Fail with helpful error
        raise ValueError(
            "Could not load account IDs. Please either:\n"
            "  1. Ensure you have a valid authenticated session (cookies), or\n"
            "  2. Set MYENTERGY_CUSTOMER_ID and MYENTERGY_METER_ID in .env file"
        )

    def _extract_account_ids(self) -> dict:
        """Extract custId and meterId from the MyEntergy usage history page.

        Returns:
            dict: Contains 'cust_id' and 'meter_id' if successful, None otherwise
        """
        try:
            response = self.session.get(
                f"{self.base_url}/myenergy/usage-history",
                timeout=30
            )

            if response.status_code != 200:
                logging.warning(f"Could not access usage history page: HTTP {response.status_code}")
                return None

            html = response.text

            # Extract custId from hidden input field
            # <input type="hidden" name="custId" value="CUSTOMER_ID_REMOVED"/>
            cust_id_match = re.search(r'name="custId"\s+value="(\d{8})"', html)
            if not cust_id_match:
                # Fallback: JavaScript variable
                cust_id_match = re.search(r'var premises = \[(\d{8})\]', html)

            if not cust_id_match:
                logging.warning("Could not find custId in page")
                return None

            cust_id = cust_id_match.group(1)

            # Extract meterId from fuelType hidden input
            meter_id_match = re.search(r'name="fuelType"[^>]+value="E-[A-Z0-9]+-([a-f0-9]{40})"', html)
            if not meter_id_match:
                # Fallback: JavaScript amiDates object
                meter_id_match = re.search(r'var amiDates = \{"([a-f0-9]{40})"', html)

            if not meter_id_match:
                logging.warning("Could not find meterId in page")
                return None

            meter_id = meter_id_match.group(1)

            return {
                'cust_id': cust_id,
                'meter_id': meter_id
            }

        except Exception as e:
            logging.warning(f"Error extracting account IDs: {e}")
            return None

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
            
            # Build the endpoint URL with properly formatted dates
            url = (
                f"https://myentergyadvisor.entergy.com/cassandra/getfile/"
                f"period/custom/"
                f"start_date/{start_date_str}/"
                f"to_date/{end_date_str}/"
                f"format/xml/"
                f"fuel_type/{fuel_type}/"
                f"backup_meter_id_owh/{self.meter_id}/"
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

    def get_on_demand_read(self, cust_id=None, meter_id=None, date=None, trigger_read=False):
        """
        Get on-demand meter read data from Entergy.

        Args:
            cust_id: Customer ID (uses instance attribute if None)
            meter_id: Meter ID (uses instance attribute if None)
            date: Date to fetch readings for (datetime object, defaults to today)
            trigger_read: If True, trigger new meter read (get_on_demand_read=1),
                         else read existing history only (get_on_demand_read=0, default)

        Returns:
            dict: JSON response if successful, None if failed
        """
        try:
            # Use instance attributes if not provided
            if not cust_id:
                cust_id = self.cust_id
            if not meter_id:
                meter_id = self.meter_id

            # Use provided date or default to today in Central Time (Entergy's timezone)
            # This ensures correct day boundaries regardless of system timezone
            if date is None:
                central_tz = ZoneInfo('America/Chicago')
                date = datetime.now(central_tz)

            date_str = date.strftime('%Y-%m-%d')
            date_formatted = date.strftime('%m%%2F%d%%2F%Y')
            odr_flag = "1" if trigger_read else "0"

            url = (
                f"https://myentergyadvisor.entergy.com/myenergy/odr-ajax"
                f"?date={date_str}"
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
                f"&timePeriod=DAILY"
                f"&overlay_with=weather"
                f"&select-time=00%3A00-02%3A59"
                f"&select-date-to={date_formatted}"
                f"&select-date-from={date_formatted}"
                f"&show_demand=1"
                f"&get_on_demand_read={odr_flag}"
            )

            logging.info(f"Fetching on-demand read from: {url}")
            response = self.session.get(url, timeout=30)

            if response.status_code == 200:
                data = response.json()

                # The API ignores all date parameters and always returns full history
                # Filter client-side to only include readings from the requested date
                if 'registers' in data and data['registers']:
                    date_str_match = date.strftime('%m/%d/%Y')  # Format: 12/31/2025
                    filtered_registers = []

                    for register in data['registers']:
                        timestamp = register.get('last_request_timestamp', '')
                        # Only include registers from the requested date
                        if timestamp.startswith(date_str_match):
                            filtered_registers.append(register)

                    original_count = len(data['registers'])
                    data['registers'] = filtered_registers
                    logging.info(f"✓ Successfully retrieved on-demand read data ({len(filtered_registers)} of {original_count} registers from {date_str_match})")
                else:
                    logging.info(f"✓ Successfully retrieved on-demand read data")

                return data
            else:
                logging.error(f"✗ Error: HTTP {response.status_code}")
                return None

        except Exception as e:
            logging.error(f"✗ Error fetching on-demand read: {e}")
            return None

    def save_on_demand_read(self, cust_id=None, meter_id=None, filename=None, date=None, trigger_read=False):
        """
        Download and save on-demand read data.

        Args:
            cust_id: Customer ID (uses instance attribute if None)
            meter_id: Meter ID (uses instance attribute if None)
            filename: Output filename (default: on_demand_YYYYMMDD.json)
            date: Date to fetch readings for (datetime object, defaults to today)
            trigger_read: If True, trigger new meter read (passed to get_on_demand_read)
        """
        data = self.get_on_demand_read(cust_id, meter_id, date, trigger_read)

        if data:
            if filename is None:
                # Use the date parameter if provided, otherwise use today in Central Time
                if date is None:
                    central_tz = ZoneInfo('America/Chicago')
                    date_for_filename = datetime.now(central_tz)
                else:
                    date_for_filename = date
                date_str = date_for_filename.strftime('%Y%m%d')
                filename = f"on_demand_{date_str}.json"

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
                    # Only process numeric readings (skip "error" strings)
                    if isinstance(reading, (int, float)) and prev_reading is not None:
                        delta = prev_reading - reading
                        delta_str = f" (Δ {delta:.2f} kWh)"

                    reading_str = f"{reading} kWh" if isinstance(reading, (int, float)) else str(reading)
                    logging.info(f"  [{i}] {timestamp}: {reading_str}{delta_str}")

                    if isinstance(reading, (int, float)):
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
    parser.add_argument('--poll', type=int, nargs='?', const=-1, metavar='MINUTES', help='Poll every N minutes (runs forever, default: from POLL_INTERVAL_MINUTES env var or 60)')
    args = parser.parse_args()

    # Load environment variables from .env file
    load_dotenv()

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
    def collect_data(collector, mqtt_publisher=None):
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

        # Determine date range (using Central Time for Entergy API compatibility)
        central_tz = ZoneInfo('America/Chicago')

        if args.start_date and args.end_date:
            # Parse dates as Central Time
            start_date = datetime.strptime(args.start_date, '%Y-%m-%d').replace(tzinfo=central_tz)
            end_date = datetime.strptime(args.end_date, '%Y-%m-%d').replace(tzinfo=central_tz)
            # Ensure end_date is end of day
            end_date = end_date.replace(hour=23, minute=59, second=59, microsecond=999999)
        elif args.days:
            end_date = datetime.now(central_tz).replace(hour=23, minute=59, second=59, microsecond=999999)
            start_date = (end_date - timedelta(days=args.days)).replace(hour=0, minute=0, second=0, microsecond=0)
        else:
            # Default to current full day in Central Time (midnight to current time or end of day)
            now = datetime.now(central_tz)
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

        # Fetch on-demand read data for the current day
        logging.info("Fetching on-demand meter read...")
        odr_file = collector.save_on_demand_read(date=start_date, trigger_read=True)
        if not odr_file:
            logging.error("✗ Failed to retrieve on-demand read data")
        elif mqtt_publisher:
            # Publish to MQTT if configured
            try:
                odr_data = collector.get_on_demand_read(date=start_date, trigger_read=True)
                if odr_data and 'registers' in odr_data and len(odr_data['registers']) > 0:
                    # Get most recent reading with valid odr_amt
                    for register in odr_data['registers']:
                        if register.get('odr_amt') is not None:
                            odr_amt = register['odr_amt']
                            # Use Unix timestamp from API (timezone-agnostic)
                            unix_ts = register['last_request_unix_timestamp']
                            timestamp = datetime.fromtimestamp(unix_ts, tz=timezone.utc)
                            mqtt_publisher.publish_meter_reading(odr_amt, timestamp)
                            break
                    else:
                        logging.warning("No valid meter reading found in registers")
                else:
                    logging.warning("No on-demand read data available for MQTT publish")
            except Exception as e:
                logging.error(f"✗ MQTT publish failed: {e}")

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

    # Initialize MQTT publisher if enabled
    mqtt_publisher = None
    mqtt_enabled = os.getenv('MQTT_ENABLED', 'false').lower() == 'true'
    if mqtt_enabled:
        logging.info("=" * 60)
        logging.info("MQTT Integration: ENABLED")
        logging.info("=" * 60)
        mqtt_host = os.getenv('MQTT_HOST')
        if mqtt_host:
            mqtt_port = int(os.getenv('MQTT_PORT', '1883'))
            mqtt_username = os.getenv('MQTT_USERNAME') or None
            mqtt_password = os.getenv('MQTT_PASSWORD') or None

            logging.info(f"Connecting to MQTT broker at {mqtt_host}:{mqtt_port}...")
            try:
                from mqtt_publisher import MQTTPublisher
                mqtt_publisher = MQTTPublisher(
                    host=mqtt_host,
                    port=mqtt_port,
                    username=mqtt_username,
                    password=mqtt_password,
                    meter_id=collector.meter_id
                )
                logging.info("=" * 60)
            except Exception as e:
                logging.error("=" * 60)
                logging.error(f"✗ FAILED to connect to MQTT broker: {e}")
                logging.error("Cannot continue with MQTT integration disabled")
                logging.error("Please check:")
                logging.error(f"  - MQTT broker is running at {mqtt_host}:{mqtt_port}")
                logging.error("  - Firewall/network allows connection")
                logging.error("  - MQTT credentials are correct (if authentication enabled)")
                logging.error("=" * 60)
                return 1
        else:
            logging.error("✗ MQTT_ENABLED=true but MQTT_HOST not set")
            logging.error("Please set MQTT_HOST in .env file")
            return 1
    else:
        logging.info("MQTT Integration: Disabled")

    # Handle polling mode
    if args.poll is not None:
        # Determine polling interval: CLI arg > env var > default (60 minutes)
        if args.poll == -1:
            # --poll flag used without value, check env var or use default
            poll_interval = int(os.getenv('POLL_INTERVAL_MINUTES', '60'))
        elif args.poll > 0:
            # Explicit positive value provided via CLI
            poll_interval = args.poll
        else:
            # Invalid value (0 or negative), use env var or default
            logging.warning(f"Invalid poll interval {args.poll}, using POLL_INTERVAL_MINUTES or default (60)")
            poll_interval = int(os.getenv('POLL_INTERVAL_MINUTES', '60'))

        logging.info(f"Starting polling mode: collecting data every {poll_interval} minute(s)")

        # Display scheduled times (handle intervals > 60 minutes)
        if poll_interval <= 60:
            scheduled_minutes = [f'{m:02d}' for m in range(0, 60, poll_interval)]
            logging.info(f"Scheduled times: :{':'.join(scheduled_minutes)}")
        else:
            logging.info(f"Scheduled time: :00 every {poll_interval} minutes")

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

                collector = collect_data(collector, mqtt_publisher)
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
        collector = collect_data(collector, mqtt_publisher)
        if collector is None:
            return 1

    # Cleanup MQTT connection
    if mqtt_publisher:
        mqtt_publisher.close()

    return 0


if __name__ == "__main__":
    exit(main())
