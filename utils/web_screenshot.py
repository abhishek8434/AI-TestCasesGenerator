import os
import uuid
import time
import logging
from typing import Optional

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.common.exceptions import WebDriverException

logger = logging.getLogger(__name__)


def capture_url_screenshot(url: str, output_dir: str, filename_prefix: str = "url_screenshot", width: int = 1366, height: int = 768, wait_seconds: float = 2.5) -> Optional[str]:
    """Open the given URL in a headless Chrome browser and capture a PNG screenshot.

    Returns the absolute path to the saved screenshot on success, or None on failure.
    """
    if not url:
        logger.error("capture_url_screenshot called without a URL")
        return None

    os.makedirs(output_dir, exist_ok=True)
    unique_id = f"{filename_prefix}_{uuid.uuid4().hex[:12]}"
    output_path = os.path.join(output_dir, f"{unique_id}.png")

    options = Options()
    # Use new headless mode for modern Chrome
    options.add_argument("--headless=new")
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--window-size={}x{}".format(width, height))
    options.add_argument("--hide-scrollbars")

    driver = None
    try:
        # Selenium Manager will fetch the correct driver automatically (selenium >= 4.6)
        service = Service()
        driver = webdriver.Chrome(service=service, options=options)
        driver.set_page_load_timeout(30)

        logger.info(f"[SCREENSHOT] Navigating to URL: {url}")
        driver.get(url)

        # Simple readiness wait; optionally extend with explicit waits if needed
        try:
            # Small delay to allow late-loading UI elements to render
            time.sleep(wait_seconds)
        except Exception:
            pass

        logger.info(f"[SCREENSHOT] Saving screenshot to: {output_path}")
        driver.save_screenshot(output_path)

        return output_path

    except WebDriverException as e:
        logger.error(f"[SCREENSHOT] WebDriver error: {e}")
        return None
    except Exception as e:
        logger.error(f"[SCREENSHOT] Unexpected error: {e}")
        return None
    finally:
        try:
            if driver:
                driver.quit()
        except Exception:
            pass


