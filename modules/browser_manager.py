import time
import os
import psutil
import random
import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import StaleElementReferenceException, TimeoutException
from selenium_stealth import stealth
import config
from modules.logger import logger
from modules.metrics_manager import MetricsTracker

class BrowserManager:
    """Manages the Chrome Browser instance using undetected_chromedriver."""
    
    def __init__(self, chrome_profile=None):
        self.driver = None
        self.chrome_profile_name = config.CHROME_PROFILE_NAME
        raw_profile = chrome_profile if chrome_profile else config.CHROME_PROFILE_PATH
        self.chrome_profile = os.path.abspath(raw_profile) if raw_profile else None
        self.metrics = MetricsTracker()
        self.use_uc = getattr(config, 'USE_UC', True)
        
    def is_chrome_running_with_profile(self):
        """Check if Chrome is already running with the configured profile."""
        if not self.chrome_profile:
            return False
            
        try:
            target_path = os.path.normpath(self.chrome_profile).lower()
            for proc in psutil.process_iter(['name', 'cmdline']):
                try:
                    name = proc.info.get('name')
                    if name and 'chrome' in name.lower():
                        cmdline = proc.info.get('cmdline')
                        if cmdline:
                            for arg in cmdline:
                                if arg.lower().startswith('--user-data-dir='):
                                    profile_in_arg = os.path.normpath(arg.split('=', 1)[1]).lower()
                                    if target_path == profile_in_arg:
                                        return True
                except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                    continue
        except Exception as e:
            logger.warning(f"Error checking for running Chrome: {e}")
            
        return False

    def init_driver(self):
        logger.info("Initializing Browser...")
        
        # 1. Try Undetected Chromedriver if enabled
        if self.use_uc:
            try:
                logger.info("Attempting to launch with Undetected Chromedriver...")
                chrome_options = uc.ChromeOptions()
                self._configure_options(chrome_options)
                
                # Check for existing instance
                if self.chrome_profile and self.is_chrome_running_with_profile():
                    logger.error("ALREADY RUNNING: Chrome is already using the selected profile. Please CLOSE ALL Chrome windows.")
                    import sys
                    sys.exit(1)

                version = int(config.CHROME_VERSION) if config.CHROME_VERSION else None
                self.driver = uc.Chrome(options=chrome_options, version_main=version, use_subprocess=True)
                self._apply_stealth()
                logger.info("Undetected Chrome launched successfully!")
                return self
                
            except Exception as e:
                logger.warning(f"Undetected Chromedriver failed: {e}")
                logger.info("Falling back to standard Selenium ChromeDriver...")

        # 2. Fallback to Standard Selenium
        try:
            from selenium import webdriver
            from selenium.webdriver.chrome.service import Service as ChromeService
            from webdriver_manager.chrome import ChromeDriverManager
            
            options = webdriver.ChromeOptions()
            self._configure_options(options)
            
            # Standard selenium requires some extra flags to mimic real user better if UC failed
            options.add_argument("--disable-blink-features=AutomationControlled")
            options.add_experimental_option("excludeSwitches", ["enable-automation"])
            options.add_experimental_option("useAutomationExtension", False)

            self.driver = webdriver.Chrome(
                service=ChromeService(ChromeDriverManager().install()),
                options=options
            )
            self._apply_stealth()
            logger.info("Standard Chrome launched successfully!")
            return self
            
        except Exception as e:
            logger.critical(f"FATAL: Could not initialize any Chrome driver: {e}")
            raise e

    def _configure_options(self, options):
        """Configure common Chrome options."""
        options.add_argument("--start-maximized")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--ignore-certificate-errors")
        options.add_argument("--disable-popup-blocking")
        
        if self.chrome_profile:
            abs_profile_path = os.path.abspath(self.chrome_profile)
            logger.info(f"Using Chrome profile: {self.chrome_profile_name} at {abs_profile_path}")
            options.add_argument(f"--user-data-dir={abs_profile_path}")
            options.add_argument(f"--profile-directory={self.chrome_profile_name}")

    def _apply_stealth(self):
        """Apply selenium-stealth to the current driver."""
        try:
            stealth(self.driver,
                languages=["en-US", "en"],
                vendor="Google Inc.",
                platform="Win32",
                webgl_vendor="Intel Inc.",
                renderer="Intel Iris OpenGL Engine",
                fix_hairline=True,
            )
        except Exception as e:
            logger.warning(f"Failed to apply stealth: {e}")

    def get_driver(self):
        """Expose the underlying driver object."""
        return self.driver

    def navigate(self, url, retries=3):
        logger.info(f"Navigating to: {url}")
        for i in range(retries):
            try:
                self.driver.get(url)
                return True
            except Exception as e:
                logger.warning(f"Navigation failed ({i+1}/{retries}): {e}")
                time.sleep(5)
        return False

    def find_element(self, selector, by=By.XPATH, timeout=10):
        try:
            return WebDriverWait(self.driver, timeout).until(
                EC.presence_of_element_located((by, selector))
            )
        except TimeoutException:
            return None

    def wait_click(self, selector, by=By.XPATH, timeout=10):
        try:
            element = WebDriverWait(self.driver, timeout).until(
                EC.element_to_be_clickable((by, selector))
            )
            element.click()
            return True
        except Exception as e:
            logger.warning(f"Click failed for {selector}: {e}")
            return False

    def human_scroll(self, limit_range=(800, 1200)):
        """
        Scrolls the page like a human: varying speeds, small pauses, and random distances.
        """
        if not self.driver: return

        try:
            scroll_amount = random.randint(*limit_range)
            current_pos = self.driver.execute_script("return window.pageYOffset;")
            target_pos = current_pos + scroll_amount
            
            # Break scroll into chunks
            while current_pos < target_pos:
                step = random.randint(50, 150)
                current_pos += step
                if current_pos > target_pos: current_pos = target_pos
                
                self.driver.execute_script(f"window.scrollTo(0, {current_pos});")
                
                # Tiny sleep between steps for smooth scroll effect
                time.sleep(random.uniform(0.01, 0.05))
                
                # Occasionally pause briefly
                if random.random() < 0.1:
                    time.sleep(random.uniform(0.1, 0.3))
            
            time.sleep(random.uniform(0.5, 1.5))
        except Exception as e:
            logger.debug(f"Human scroll failed: {e}")

    def human_mouse_move(self):
        """Simulate human mouse movements/hovers on the page."""
        if not self.driver: return

        try:
            from selenium.webdriver.common.action_chains import ActionChains
            
            # Move to random visible elements (headers, buttons, texts)
            possible_targets = self.driver.find_elements(By.CSS_SELECTOR, "h1, h2, span, p, a")
            if possible_targets:
                target = random.choice(possible_targets[:20]) 
                if target.is_displayed():
                    ActionChains(self.driver).move_to_element(target).perform()
                    time.sleep(random.uniform(0.2, 0.7))
        except Exception as e:
            logger.debug(f"Human mouse move failed: {e}")

    def quit(self):
        if self.driver:
            self.driver.quit()
