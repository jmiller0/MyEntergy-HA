import json
import os
import time
from DrissionPage import ChromiumPage, ChromiumOptions
from RecaptchaSolver import RecaptchaSolver
from dotenv import load_dotenv


CHROME_ARGUMENTS = [
    "-no-first-run",
    "-force-color-profile=srgb",
    "-metrics-recording-only",
    "-password-store=basic",
    "-use-mock-keychain",
    "-export-tagged-pdf",
    "-no-default-browser-check",
    "-disable-background-mode",
    "-enable-features=NetworkService,NetworkServiceInProcess",
    "-disable-features=FlashDeprecationWarning",
    "-deny-permission-prompts",
    "-disable-gpu",
    "-accept-lang=en-US",
    "--disable-usage-stats",
    "--disable-crash-reporter",
    "--no-sandbox"
]


class MyEntergyAuth:
    """Handles authentication for MyEntergy website."""

    def __init__(self, username: str, password: str, headless: bool = False, verbose: bool = False, manual_mode: bool = False):
        """Initialize the auth handler.

        Args:
            username: MyEntergy username/email
            password: MyEntergy password
            headless: Run browser in headless mode
            verbose: Enable verbose logging and screenshots
            manual_mode: Pause after filling credentials for manual login button click (debug only)
        """
        self.username = username
        self.password = password
        self.headless = headless
        self.verbose = verbose
        self.manual_mode = manual_mode
        self.driver = None
        self.cookies = None

    def _log(self, message: str) -> None:
        """Log message if verbose mode is enabled."""
        if self.verbose:
            print(message)

    def _take_screenshot(self, name: str) -> None:
        """Take a screenshot for debugging (verbose mode only)."""
        if self.driver and self.verbose:
            try:
                filename = f"debug_{name}.png"
                self.driver.get_screenshot(path=filename)
                self._log(f"Screenshot saved: {filename}")
            except Exception as e:
                self._log(f"Failed to take screenshot: {e}")

    def _log_page_state(self, label: str) -> None:
        """Log current page state for debugging (verbose mode only)."""
        if self.driver and self.verbose:
            try:
                url = self.driver.url
                title = self.driver.title
                self._log(f"[{label}] URL: {url}")
                self._log(f"[{label}] Title: {title}")
            except Exception as e:
                self._log(f"Failed to log page state: {e}")

    def _get_button_state(self) -> dict:
        """Get current state of Login button (verbose mode only)."""
        if not self.verbose:
            return {}

        return self.driver.run_js("""
            const btn = document.querySelector('button');
            if (!btn) return {error: 'Button not found'};
            const styles = window.getComputedStyle(btn);
            return {
                disabled: btn.disabled,
                backgroundColor: styles.backgroundColor,
                display: styles.display,
                visibility: styles.visibility
            };
        """)

    def login(self) -> dict:
        """Perform login and return session cookies.

        Returns:
            dict: Session cookies that can be used for API requests

        Raises:
            Exception: If login fails
        """
        self._log("Initializing browser...")

        # Configure Chrome options
        options = ChromiumOptions()
        for argument in CHROME_ARGUMENTS:
            options.set_argument(argument)

        if self.headless:
            options.set_argument("--headless=new")

        # Create browser instance
        self.driver = ChromiumPage(addr_or_opts=options)

        try:
            # Navigate to login page
            self._log("Navigating to MyEntergy login page...")
            self.driver.get("https://www.myentergy.com/s/login/")
            time.sleep(2)
            self._log_page_state("After navigation")
            self._take_screenshot("01_after_navigation")

            # Solve reCAPTCHA
            self._log("Solving reCAPTCHA...")
            recaptcha_solver = RecaptchaSolver(self.driver, verbose=self.verbose)
            recaptcha_solver.solveCaptcha()
            time.sleep(2)
            self._log_page_state("After captcha")
            self._take_screenshot("02_after_captcha")

            # Find form input fields - filter by type to avoid hidden fields
            self._log("Finding input fields...")
            all_inputs = self.driver.eles('tag:input', timeout=10)

            # Filter to visible text/password fields only
            visible_inputs = []
            for inp in all_inputs:
                inp_type = inp.attr('type') or 'text'
                if inp_type in ('text', 'password', 'email'):
                    visible_inputs.append(inp)

            if len(visible_inputs) < 2:
                raise Exception(f"Expected at least 2 visible input fields, found {len(visible_inputs)}")

            self._log(f"Found {len(all_inputs)} total input fields, {len(visible_inputs)} visible")

            # Log field details in verbose mode
            if self.verbose:
                for i, inp in enumerate(all_inputs):
                    try:
                        inp_type = inp.attr('type') or 'text'
                        inp_name = inp.attr('name') or 'no-name'
                        self._log(f"  Input {i}: type={inp_type}, name={inp_name}")
                    except:
                        pass

            # Fill username (first visible field)
            self._log("Entering username...")
            username_field = visible_inputs[0]
            username_field.input(self.username)
            time.sleep(0.5)
            self._take_screenshot("03_after_username")

            # Fill password (second visible field)
            self._log("Entering password...")
            password_field = visible_inputs[1]
            password_field.input(self.password)
            time.sleep(0.5)
            self._take_screenshot("04_after_password")

            # Blur password field to enable Login button
            # The form is a Salesforce Lightning Web Component with Shadow DOM
            # Button remains disabled until password field loses focus
            self._log("Blurring password field to enable Login button...")

            if self.verbose:
                button_state_before = self._get_button_state()
                self._log(f"Button state BEFORE blur: disabled={button_state_before.get('disabled')}, color={button_state_before.get('backgroundColor')}")

            # Trigger blur using DrissionPage element reference (works in Shadow DOM)
            password_field.run_js('this.blur();')
            self._log("Password field blurred")
            time.sleep(1)  # Wait for blur event handlers to enable button

            if self.verbose:
                button_state_after = self._get_button_state()
                self._log(f"Button state AFTER blur: disabled={button_state_after.get('disabled')}, color={button_state_after.get('backgroundColor')}")

                if button_state_after.get('disabled'):
                    self._log("WARNING: Button still disabled after blur - click may fail")
                else:
                    self._log("SUCCESS: Button enabled after blur (disabled=False)")

            self._take_screenshot("04b_after_blur")

            # Manual mode - pause for user to click login button (debug only)
            if self.manual_mode:
                self._log("\n" + "="*70)
                self._log("MANUAL MODE: Credentials filled, waiting for manual click")
                self._log("="*70)
                print("\n>>> PLEASE CLICK THE LOGIN BUTTON NOW <<<")
                print()

                url_before = self.driver.url
                self._log(f"URL before manual click: {url_before}")

                # Monitor for URL change
                print("Waiting for login button click (monitoring URL changes)...")
                for i in range(60):
                    time.sleep(1)
                    current_url = self.driver.url
                    if current_url != url_before:
                        self._log(f"URL CHANGED after {i+1} seconds!")
                        self._log(f"  From: {url_before}")
                        self._log(f"  To:   {current_url}")

                        # Monitor for additional redirects
                        print("Login detected! Monitoring for 10 more seconds...")
                        url_before = current_url
                        for j in range(10):
                            time.sleep(1)
                            new_url = self.driver.url
                            if new_url != url_before:
                                self._log(f"URL changed again after {j+1} more seconds:")
                                self._log(f"  From: {url_before}")
                                self._log(f"  To:   {new_url}")
                                url_before = new_url
                        break
                    elif i % 5 == 0 and i > 0:
                        print(f"Still waiting... ({i} seconds elapsed)")

                self._log_page_state("After manual login")
                self._take_screenshot("05_after_manual_login")
                current_url = self.driver.url

            else:
                # Automated login - click the Login button
                self._log("Clicking login button...")

                # Find Login button
                buttons = self.driver.eles('tag:button')
                login_button = None

                for i, btn in enumerate(buttons):
                    try:
                        btn_text = btn.text.strip()
                        self._log(f"Found button {i}: '{btn_text}'")
                        if btn_text == 'Login':
                            login_button = btn
                            self._log(f"Found Login button at index {i}")
                            break
                    except:
                        pass

                if not login_button:
                    raise Exception("Could not find Login button")

                # Click the button
                url_before_click = self.driver.url
                self._log(f"URL before click: {url_before_click}")

                login_button.click()
                self._log("Click completed")
                time.sleep(0.5)

                # Verify URL changed (indicates successful form submission)
                url_after_click = self.driver.url
                if url_after_click != url_before_click:
                    self._log(f"SUCCESS: URL changed after click!")
                    self._log(f"  From: {url_before_click}")
                    self._log(f"  To:   {url_after_click}")
                else:
                    self._log(f"WARNING: URL unchanged - click may have failed")
                    self._log(f"  Still at: {url_after_click}")

                current_url = url_after_click

            # Wait for login to complete
            time.sleep(1)
            self._take_screenshot("05_after_button_click")

            # Wait for redirects to complete
            self._log("Waiting for login to complete...")
            time.sleep(3)
            self._log_page_state("3 seconds after click")
            time.sleep(3)
            self._log_page_state("6 seconds after click")
            self._take_screenshot("06_after_wait")

            # Verify login succeeded
            current_url = self.driver.url
            if '/login' in current_url.lower():
                self._log("Still on login page - login failed")
                self._take_screenshot("07_login_failed")
                raise Exception(f"Login failed - still on login page. URL: {current_url}")

            if 'myentergyadvisor.entergy.com' in current_url or 'myentergy.com/s/' in current_url:
                self._log(f"Login successful! Current URL: {current_url}")
            else:
                self._log(f"Warning: Unexpected URL after login: {current_url}")

            # Navigate to advisor page to get session cookies
            self._log("Navigating to MyEntergy Advisor to establish session...")
            self.driver.get("https://myentergyadvisor.entergy.com/myenergy/usage-history")
            time.sleep(3)
            self._log_page_state("After advisor navigation")
            self._take_screenshot("08_advisor_page")

            # Extract cookies
            self._log("Extracting session cookies...")
            self.cookies = self._get_cookies()
            self._log(f"Successfully extracted {len(self.cookies)} cookies")

            return self.cookies

        finally:
            if self.driver:
                self._log("Closing browser...")
                self.driver.close()

    def _get_cookies(self) -> list:
        """Extract cookies from the browser session.

        Returns:
            list: List of cookie dictionaries
        """
        if not self.driver:
            return []

        all_cookies = []
        try:
            cookies = self.driver.cookies()
            if isinstance(cookies, list):
                all_cookies.extend(cookies)
            elif isinstance(cookies, dict):
                # Convert single cookie dict to list format
                for name, value in cookies.items():
                    all_cookies.append({
                        'name': name,
                        'value': value,
                        'domain': '.entergy.com'
                    })
        except Exception as e:
            self._log(f"Warning: Could not extract cookies: {e}")

        return all_cookies

    def save_cookies(self, filepath: str) -> None:
        """Save cookies to a JSON file.

        Args:
            filepath: Path to save cookies file
        """
        if not self.cookies:
            raise Exception("No cookies available. Run login() first.")

        with open(filepath, 'w') as f:
            json.dump(self.cookies, f, indent=2)

        self._log(f"Cookies saved to {filepath}")

    @staticmethod
    def load_cookies(filepath: str) -> list:
        """Load cookies from a JSON file.

        Args:
            filepath: Path to cookies file

        Returns:
            list: List of cookie dictionaries
        """
        with open(filepath, 'r') as f:
            return json.load(f)


def main():
    """Example usage of MyEntergyAuth."""
    import argparse

    parser = argparse.ArgumentParser(description='MyEntergy Authentication')
    parser.add_argument('--username', help='MyEntergy username (or use .env)')
    parser.add_argument('--password', help='MyEntergy password (or use .env)')
    parser.add_argument('--headless', action='store_true', help='Run in headless mode')
    parser.add_argument('--verbose', action='store_true', help='Enable verbose logging')
    parser.add_argument('--output', default='cookies.json', help='Output file for cookies')
    args = parser.parse_args()

    # Load environment variables
    load_dotenv()

    # Load credentials from .env if not provided via command line
    if not args.username or not args.password:
        username = os.getenv('MYENTERGY_USERNAME')
        password = os.getenv('MYENTERGY_PASSWORD')

        if not username or not password:
            print("Error: Please provide --username and --password or set MYENTERGY_USERNAME and MYENTERGY_PASSWORD in .env")
            return 1
    else:
        username = args.username
        password = args.password

    # Perform authentication
    auth = MyEntergyAuth(username, password, headless=args.headless, verbose=args.verbose)

    try:
        cookies = auth.login()
        auth.save_cookies(args.output)
        print(f"\n✓ Authentication successful!")
        print(f"✓ Cookies saved to {args.output}")
        print(f"✓ {len(cookies)} cookies extracted")
        return 0
    except Exception as e:
        print(f"\n✗ Authentication failed: {e}")
        return 1


if __name__ == "__main__":
    exit(main())
