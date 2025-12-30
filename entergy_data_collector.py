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
        """Load cookies from a JSON file. Creates empty file if missing."""
        if not os.path.exists(filepath):
            print(f"Cookie file not found at {filepath}, will create after authentication")
            return

        try:
            with open(filepath, 'r') as f:
                cookies = json.load(f)
            self._load_cookies_from_list(cookies)
        except (json.JSONDecodeError, ValueError):
            print(f"Cookie file at {filepath} is invalid, will re-authenticate")
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

                            print(f" ✓ Retrieved {len(data_points)} data points")
                else:
                    print(f" ✗ API returned status {response.status_code}")
            except Exception as e:
                print(f" ✗ Error fetching data: {e}")

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
            print(f" ✓ Saved {len(day_records)} records to {filename}")
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
            
            print(f"Fetching XML from: {url}")
            response = self.session.get(url, timeout=30)
            
            if response.status_code == 200:
                # Verify it's valid XML
                if response.text.startswith('<?xml'):
                    print(f"✓ Successfully downloaded {len(response.content)} bytes of XML data")
                    return response.content
                else:
                    print("✗ Error: Response does not appear to be valid XML")
                    return None
            else:
                print(f"✗ Error: HTTP {response.status_code}")
                return None
                
        except Exception as e:
            print(f"✗ Error downloading XML: {e}")
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
            print(f"✓ Successfully saved XML file to {filepath}")
            return filepath
        else:
            print("✗ Failed to download XML data")
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

            print(f"Fetching on-demand read from: {url}")
            response = self.session.get(url, timeout=30)

            if response.status_code == 200:
                data = response.json()
                print(f"✓ Successfully retrieved on-demand read data")
                return data
            else:
                print(f"✗ Error: HTTP {response.status_code}")
                return None

        except Exception as e:
            print(f"✗ Error fetching on-demand read: {e}")
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
            print(f"✓ Successfully saved on-demand read to {filepath}")

            # Print all readings from registers with deltas
            if 'registers' in data and data['registers']:
                print(f"\n  On-Demand Read History:")
                prev_reading = None
                for i, register in enumerate(data['registers']):
                    reading = register.get('odr_amt')
                    timestamp = register.get('last_request_timestamp')

                    delta_str = ""
                    if reading is not None and prev_reading is not None:
                        delta = prev_reading - reading
                        delta_str = f" (Δ {delta:.2f} kWh)"

                    reading_str = f"{reading} kWh" if reading is not None else "null"
                    print(f"    [{i}] {timestamp}: {reading_str}{delta_str}")

                    if reading is not None:
                        prev_reading = reading

            # Print rate level
            if 'rate_level' in data and data['rate_level']:
                print(f"\n  Rate Level: {data['rate_level']}")

            return filepath
        else:
            print("✗ Failed to retrieve on-demand read data")
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
    args = parser.parse_args()

    # Helper function for authentication
    def authenticate():
        """Perform authentication and save cookies."""
        print("Authenticating to MyEntergy...")
        # Load credentials from environment
        load_dotenv()  # No-op if .env doesn't exist (e.g., in Docker)
        username = os.getenv('MYENTERGY_USERNAME')
        password = os.getenv('MYENTERGY_PASSWORD')

        if not username or not password:
            print("Error: MYENTERGY_USERNAME and MYENTERGY_PASSWORD must be set")
            print(" Local: Create .env file with credentials")
            print(" Docker: Ensure config/.env is mounted and loaded via env_file")
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
            print(f"✓ Authentication successful, cookies saved to {args.cookies}\\n")
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

        print("✓ Re-authentication successful\\n")
    else:
        print("✓ Session valid\\n")

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

    print(f"Collecting data from {start_date.date()} to {end_date.date()}\\n")

    # Download based on format selection
    if args.format in ['csv', 'both']:
        # Collect CSV data
        data = collector.get_usage_data(start_date, end_date)
        print(f"\\n✓ Collected {data['total_points']} total data points")

        # Save to CSV
        if data['total_points'] > 0:
            print(f"\\nSaving to CSV files in {args.output}/...")
            files = collector.save_to_csv(data, args.output)
            print(f"\\n✓ Created {len(files)} CSV file(s)")
        else:
            print("\\n✗ No CSV data collected")

    if args.format in ['xml', 'both']:
        # Download and save Green Button XML data
        print(f"\\nDownloading Green Button XML...")
        xml_file = collector.save_green_button_xml(start_date, end_date)

        if not xml_file:
            print("\\n✗ Failed to retrieve Green Button XML data")

    # Fetch on-demand read data
    print(f"\\nFetching on-demand meter read...")
    odr_file = collector.save_on_demand_read()
    if not odr_file:
        print("\\n✗ Failed to retrieve on-demand read data")

    return 0


if __name__ == "__main__":
    exit(main())
