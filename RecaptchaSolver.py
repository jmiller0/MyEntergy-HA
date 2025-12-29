import os
import urllib.request
import random
import pydub
import speech_recognition
import time
from typing import Optional
from DrissionPage import ChromiumPage


class RecaptchaSolver:
    """A class to solve reCAPTCHA challenges using audio recognition."""

    # Constants
    TEMP_DIR = os.getenv("TEMP") if os.name == "nt" else "/tmp"
    TIMEOUT_STANDARD = 7
    TIMEOUT_SHORT = 1
    TIMEOUT_DETECTION = 0.05

    def __init__(self, driver: ChromiumPage, verbose: bool = False) -> None:
        """Initialize the solver with a ChromiumPage driver.

        Args:
            driver: ChromiumPage instance for browser interaction
            verbose: Enable verbose logging
        """
        self.driver = driver
        self.verbose = verbose

    def _log(self, message: str) -> None:
        """Log message if verbose mode is enabled."""
        if self.verbose:
            print(message)

    def solveCaptcha(self) -> None:
        """Attempt to solve the reCAPTCHA challenge.

        Raises:
            Exception: If captcha solving fails or bot is detected
        """

        # Handle main reCAPTCHA iframe
        self._log("Waiting for reCAPTCHA iframe...")
        self.driver.wait.ele_displayed(
            "@title=reCAPTCHA", timeout=self.TIMEOUT_STANDARD
        )
        time.sleep(0.1)
        self._log("Found reCAPTCHA iframe")
        iframe_inner = self.driver("@title=reCAPTCHA")

        # Click the checkbox
        self._log("Waiting for checkbox...")
        iframe_inner.wait.ele_displayed(
            ".rc-anchor-content", timeout=self.TIMEOUT_STANDARD
        )
        self._log("Clicking checkbox...")
        iframe_inner(".rc-anchor-content", timeout=self.TIMEOUT_SHORT).click()

        # Wait for reCAPTCHA to process
        time.sleep(2)

        # Check if solved by just clicking
        self._log("Checking if solved by checkbox click...")
        if self.is_solved():
            self._log("Captcha solved by checkbox click (checkmark detected)!")
            return

        # Also check if login form appeared (alternative success indicator)
        self._log("Checking if login form appeared...")
        if self.login_form_visible():
            self._log("Captcha solved by checkbox click (login form appeared)!")
            return

        # Neither worked - proceed to audio challenge
        self._log("Checkbox click insufficient - proceeding to audio challenge...")
        self._log("Looking for audio challenge iframe...")
        iframe = self.driver("xpath://iframe[contains(@title, 'recaptcha')]")
        self._log("Waiting for audio button...")
        iframe.wait.ele_displayed(
            "#recaptcha-audio-button", timeout=self.TIMEOUT_STANDARD
        )
        self._log("Clicking audio button...")
        iframe("#recaptcha-audio-button", timeout=self.TIMEOUT_SHORT).click()
        time.sleep(0.3)

        self._log("Checking for bot detection...")
        if self.is_detected():
            raise Exception("Captcha detected bot behavior")

        # Download and process audio
        self._log("Waiting for audio source...")
        iframe.wait.ele_displayed("#audio-source", timeout=self.TIMEOUT_STANDARD)
        src = iframe("#audio-source").attrs["src"]
        self._log(f"Audio source found: {src[:50]}...")

        try:
            self._log("Processing audio challenge...")
            text_response = self._process_audio_challenge(src)
            self._log(f"Recognized text: {text_response}")
            iframe("#audio-response").input(text_response.lower())
            self._log("Clicking verify button...")
            iframe("#recaptcha-verify-button").click()
            time.sleep(2.0)

            self._log("Checking if captcha is solved...")
            solved = self.is_solved()
            if not solved:
                raise Exception("Failed to solve the captcha")
            self._log("Captcha solved successfully!")

        except Exception as e:
            raise Exception(f"Audio challenge failed: {str(e)}")

    def _process_audio_challenge(self, audio_url: str) -> str:
        """Process the audio challenge and return the recognized text.

        Args:
            audio_url: URL of the audio file to process

        Returns:
            str: Recognized text from the audio file
        """
        mp3_path = os.path.join(self.TEMP_DIR, f"{random.randrange(1,1000)}.mp3")
        wav_path = os.path.join(self.TEMP_DIR, f"{random.randrange(1,1000)}.wav")

        try:
            urllib.request.urlretrieve(audio_url, mp3_path)
            sound = pydub.AudioSegment.from_mp3(mp3_path)
            sound.export(wav_path, format="wav")

            recognizer = speech_recognition.Recognizer()
            with speech_recognition.AudioFile(wav_path) as source:
                audio = recognizer.record(source)

            return recognizer.recognize_google(audio)

        finally:
            for path in (mp3_path, wav_path):
                if os.path.exists(path):
                    try:
                        os.remove(path)
                    except OSError:
                        pass

    def is_solved(self) -> bool:
        """Check if the captcha has been solved successfully."""
        try:
            # Check inside the reCAPTCHA iframe
            iframe_inner = self.driver("@title=reCAPTCHA", timeout=self.TIMEOUT_SHORT)
            elem = iframe_inner.ele(".recaptcha-checkbox-checkmark", timeout=self.TIMEOUT_SHORT)
            attrs = elem.attrs
            has_style = "style" in attrs
            if self.verbose:
                self._log(f"Checkmark element attrs: {attrs}")
                self._log(f"Has style attribute: {has_style}")
            return has_style
        except Exception as e:
            if self.verbose:
                self._log(f"is_solved() exception: {e}")
            return False

    def login_form_visible(self) -> bool:
        """Check if the login form (username/password fields) is visible.

        This indicates reCAPTCHA was solved and form was revealed.
        """
        try:
            # Look for password input field outside the iframe
            # Using main driver, not iframe
            # Also verify it's actually visible (not hidden or in an iframe)
            password_fields = self.driver.eles('tag:input@type=password', timeout=1)
            for field in password_fields:
                # Check if field is actually displayed (not hidden, not in iframe)
                if field.states.is_displayed and field.states.is_alive:
                    if self.verbose:
                        self._log(f"Found visible password field: {field.attr('name')}")
                    return True
            return False
        except Exception as e:
            if self.verbose:
                self._log(f"login_form_visible() exception: {e}")
            return False

    def is_detected(self) -> bool:
        """Check if the bot has been detected."""
        try:
            return (
                self.driver.ele("Try again later", timeout=self.TIMEOUT_DETECTION)
                .states()
                .is_displayed
            )
        except Exception:
            return False

    def get_token(self) -> Optional[str]:
        """Get the reCAPTCHA token if available."""
        try:
            return self.driver.ele("#recaptcha-token").attrs["value"]
        except Exception:
            return None