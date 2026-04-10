import time
import random
import re
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException
from modules.logger import logger
from modules.processor import ProcessorModule
import config

class LinkedInScraper:
    def __init__(self, browser_manager):
        self.bm = browser_manager
        self.driver = self.bm.driver
        self.processor = ProcessorModule()
        self.metrics = self.bm.metrics

    def login(self):
        """Perform login if necessary."""
        self.bm.navigate(config.URLS['LOGIN'])
        time.sleep(2)
        
        # Check if already logged in (look for search bar or feed indicators)
        if "feed" in self.driver.current_url:
            logger.info("Already logged in.")
            return True

        if not config.LINKEDIN_EMAIL or not config.LINKEDIN_PASSWORD:
            logger.error("LinkedIn credentials missing in .env")
            return False

        logger.info(f"Attempting login as {config.LINKEDIN_EMAIL}...")
        try:
            user_field = self.bm.find_element(config.SELECTORS['login']['username'], By.ID)
            pass_field = self.bm.find_element(config.SELECTORS['login']['password'], By.ID)
            
            if user_field and pass_field:
                user_field.send_keys(config.LINKEDIN_EMAIL)
                time.sleep(random.uniform(1, 2))
                pass_field.send_keys(config.LINKEDIN_PASSWORD)
                time.sleep(random.uniform(1, 2))
                pass_field.submit()
                time.sleep(5)
                return "feed" in self.driver.current_url
        except Exception as e:
            logger.error(f"Login error: {e}")
        return False

    def search_people(self, keywords):
        """Perform search for people with keywords and location filter."""
        import urllib.parse
        encoded_keywords = urllib.parse.quote(keywords)
        # geoUrn=103644278 is USA
        search_url = f"https://www.linkedin.com/search/results/people/?keywords={encoded_keywords}&origin=FACETED_SEARCH&geoUrn=%5B%22103644278%22%5D"
        
        logger.info(f"Searching for: {keywords}")
        self.bm.navigate(search_url)
        time.sleep(5)
        return True

    def extract_leads_from_page(self):
        """Extract lead data directly from search result cards (raw leads)."""
        # 1. Immediate small scroll to trigger LinkedIn's lazy-loading
        self.driver.execute_script("window.scrollTo(0, 400);")
        time.sleep(1)
        
        # 2. Wait for at least one card to be present
        card_selector = config.SELECTORS['search']['result_card']
        try:
            WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.XPATH, card_selector))
            )
        except TimeoutException:
            # Diagnostic info
            curr_url = self.driver.current_url
            all_links = self.driver.find_elements(By.XPATH, "//a[contains(@href, '/in/')]")
            logger.warning(f"Timed out waiting for search result cards. URL: {curr_url} | Profile links found: {len(all_links)}")
            
            # FALLBACK: If we find profile links but the "card" selector is failing, use the links as "cards"
            if len(all_links) > 0:
                logger.info("Using detected profile links as extraction points (Fallback Mode).")
                # We filter to unique profile paths and use their parents as cards
                filtered_links = []
                seen_hrefs = set()
                for lnk in all_links:
                    href = lnk.get_attribute('href')
                    if href and "/in/" in href and "miniProfile" not in href:
                        base_href = href.split('?')[0]
                        if base_href not in seen_hrefs:
                            seen_hrefs.add(base_href)
                            filtered_links.append(lnk)
                
                # Use the parent/ancestor of the link as our 'card' so we can find sub-elements
                cards = []
                for lnk in filtered_links:
                    try:
                        # Try to find a reasonably sized parent container (li or div)
                        parent = lnk.find_element(By.XPATH, "./ancestor::li[1] | ./ancestor::div[contains(@class, 'result') or contains(@class, 'item')][1] | ./following-sibling::* | ./..")
                        cards.append(parent)
                    except:
                        cards.append(lnk) # Absolute fallback
                
                if not cards:
                    return []
                logger.info(f"Fallback Mode: Processing {len(cards)} profile containers.")
            else:
                return []
        else:
            # Standard path: cards were found
            cards = self.driver.find_elements(By.XPATH, card_selector)
            logger.info(f"Found {len(cards)} result cards on page.")

        # 3. Final Scroll to ensure bottom results are loaded
        self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(2)
        
        leads = []
        try:
            for card in cards:
                try:
                    # 1. Profile Link & ID
                    try:
                        # Find all links and pick the first one that points to a profile
                        links = card.find_elements(By.XPATH, ".//a[contains(@href, '/in/')]")
                        profile_url = ""
                        for lnk in links:
                            href = lnk.get_attribute('href')
                            if href and "/in/" in href and "miniProfile" not in href:
                                profile_url = href.split('?')[0]
                                break
                        
                        if not profile_url:
                            continue # Skip if no profile URL found
                    except:
                        continue
                    
                    profile_id = profile_url.replace("https://www.linkedin.com/in/", "").strip("/")
                    
                    # 2. Name
                    name = ""
                    try:
                        name_elem = card.find_element(By.XPATH, config.SELECTORS['search']['name'])
                        name = name_elem.text.strip().split('\n')[0]
                    except:
                        # Fallback: Use the text of the profile link itself
                        try:
                            name = card.find_element(By.XPATH, ".//span[contains(@class, 'entity-result__title-text')]").text.strip().split('\n')[0]
                        except:
                            try:
                                name = card.find_element(By.XPATH, ".//a[contains(@href, '/in/')]").text.strip().split('\n')[0]
                            except: pass
                    
                    # CLEAN NAME: Remove connectivity indicators like "• 3rd+" or "• 2nd"
                    if name:
                        name = re.sub(r'\s*•\s*\d*(?:st|nd|rd|th)?\+?\s*$', '', name).strip()
                        name = name.replace('•', '').strip()

                    # 3. Headline/Profession & Location
                    headline = ""
                    location = ""
                    try:
                        # Improved extraction by targeting standard classes
                        # 1. Try primary-subtitle for headline
                        try:
                            h_elements = card.find_elements(By.XPATH, ".//*[contains(@class, 'primary-subtitle')] | .//*[contains(@class, 'entity-result__primary-subtitle')]")
                            for h in h_elements:
                                txt = h.text.strip()
                                if txt and len(txt) > 5:
                                    headline = txt.replace('\n', ' ')
                                    break
                        except: pass
                        
                        # 2. Try secondary-subtitle for location
                        try:
                            l_elements = card.find_elements(By.XPATH, ".//*[contains(@class, 'secondary-subtitle')] | .//*[contains(@class, 'entity-result__secondary-subtitle')]")
                            for l in l_elements:
                                txt = l.text.strip()
                                # Validation: Real locations are usually short, NOT technical titles, and NOT the candidate's name
                                if txt and len(txt) < 60 and not any(word in txt.lower() for word in ['certified', 'specialist', 'expert', 'engineer', 'developer']):
                                    if name and txt.lower() == name.lower():
                                        continue
                                    location = txt.replace('\n', ' ')
                                    break
                        except: pass

                        # Fallback: Search for any text containing "Area" or "United States"
                        if not location:
                            try:
                                possible_locs = card.find_elements(By.XPATH, ".//div | .//span | .//p")
                                for loc in possible_locs:
                                    t = loc.text.strip()
                                    if any(key in t for key in ['Area', 'Region', 'United States', 'India', 'Canada', 'UK']):
                                        if len(t) < 50:
                                            location = t
                                            break
                            except: pass

                        # Fallback: Find all p tags inside the info div if classes failed
                        if not headline or not location:
                            p_tags = card.find_elements(By.XPATH, ".//p")
                            for p in p_tags:
                                txt = p.text.strip().replace('\n', ' ')
                                if not txt or name.lower() in txt.lower() or txt.lower() in name.lower():
                                    continue
                                
                                # Use class-based logic if available
                                parent_div = p.find_element(By.XPATH, "..")
                                p_class = parent_div.get_attribute("class") or ""
                                
                                if "_50aa6142" in p_class or "secondary-subtitle" in p_class:
                                    if not location: location = txt
                                elif not headline:
                                    headline = txt
                    except: pass
                    
                    # Final Fallbacks from config selectors
                    if not headline:
                        try:
                            h_elem = card.find_element(By.XPATH, config.SELECTORS['search']['headline'])
                            headline = h_elem.text.strip().replace('\n', ' ')
                        except: pass

                    if not location:
                        try:
                            l_elem = card.find_element(By.XPATH, config.SELECTORS['search']['location'])
                            location = l_elem.text.strip().replace('\n', ' ')
                        except: pass
                    
                    # Clean up: Ensure headline doesn't contain the name accidentally
                    if headline and name and (name.lower() in headline.lower() and len(headline) < len(name) + 5):
                        headline = ""

                    # 4. Fallback: Parse location from headline if empty
                    if not location and headline:
                        # Look for "City, ST" or common patterns
                        city_match = re.search(r'([A-Z][a-z]+(?: [A-Z][a-z]+)*),? ([A-Z]{2})', headline)
                        if city_match:
                            location = city_match.group(0)
                        elif " - " in headline:
                            # Many people put their location after a dash
                            parts = [p.strip() for p in headline.split(" - ")]
                            if len(parts) > 1 and len(parts[-1]) < 30:
                                location = parts[-1]

                    # 5. Partial Data Object
                    lead_data = {
                        "Full Name": name,
                        "Location": location,
                        "Profession": headline,
                        "LinkedIn ID": profile_id,
                        "Profile URL": profile_url,
                        "Work Status": self.processor.extract_work_status(headline),
                        "Email": "", 
                        "Phone": ""  
                    }
                    
                    if name and profile_url:
                        logger.info(f"Captured: {name} | Location: {location} | Profession: {headline}")
                        leads.append(lead_data)
                    else:
                        logger.debug(f"Skipping incomplete card: Name={name}, URL={profile_url}")
                        
                except Exception as e:
                    logger.debug(f"Error parsing result card: {e}")
                    continue
        except Exception as e:
            logger.error(f"Error extracting leads from page: {e}")
            
        return leads


    def click_next(self):
        """Click the 'Next' button to go to the next page of results."""
        try:
            # 1. Look for the button
            next_button = self.bm.find_element(config.SELECTORS['search']['next_button'], timeout=10)
            
            if not next_button:
                # Fallback: try finding by text directly if XPATH failed
                try:
                    next_button = self.driver.find_element(By.XPATH, "//button[contains(., 'Next')]")
                except: pass

            if next_button:
                # Check if button is actually disabled (LinkedIn does this on last page)
                is_disabled = next_button.get_attribute("disabled")
                if is_disabled == "true" or "disabled" in (next_button.get_attribute("class") or "").lower():
                    logger.info("Next button is disabled. Reached end of results.")
                    return False

                # 2. Strategic Scrolling
                # Scroll to button and a bit more to ensure it's not covered by footer
                self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", next_button)
                time.sleep(1.5)
                
                # 3. Try standard click first
                try:
                    next_button.click()
                except:
                    # 4. Fallback to Javascript click (more reliable for overlapping elements)
                    self.driver.execute_script("arguments[0].click();", next_button)
                
                logger.info("Successfully clicked Next page.")
                time.sleep(5) # Wait for page to load
                return True
            else:
                logger.warning("Next button not found on page.")
                return False
        except Exception as e:
            logger.error(f"Error in click_next: {e}")
            return False

    def _get_contact_info_from_profile(self, profile_url):
        """Navigate to profile and extract contact information."""
        logger.info(f"Visiting profile for contact info: {profile_url}")
        self.bm.navigate(profile_url)
        time.sleep(random.uniform(3, 5))
        return self._get_contact_info()

    def scrape_profile(self, profile_url):
        """Full profile extraction (Legacy/Fallback)."""
        self.metrics.increment('leads_seen')
        self.bm.navigate(profile_url)
        time.sleep(random.uniform(3, 5))

        # Basic data extraction
        location_text = self._safe_get_text(config.SELECTORS['profile']['location'])
        is_usa = "united states" in location_text.lower() or "usa" in location_text.lower()
        is_open_to_work = self.bm.find_element(config.SELECTORS['profile']['open_to_work_badge']) is not None
        
        if config.OPEN_TO_WORK_ONLY and not is_open_to_work:
            return None

        if not is_usa:
            return None

        name = self._safe_get_text(config.SELECTORS['profile']['name'])
        headline = self._safe_get_text(config.SELECTORS['profile']['headline'])
        linkedin_id = profile_url.replace("https://www.linkedin.com/in/", "").strip("/")
        
        contact_info = self._get_contact_info()
        
        lead_data = {
            "Full Name": name,
            "Location": location_text,
            "Profession": headline,
            "LinkedIn ID": linkedin_id,
            "Email": contact_info.get('Email', ''),
            "Phone": contact_info.get('Phone', ''),
            "Work Status": self.processor.extract_work_status(headline),
            "Profile URL": profile_url
        }
        
        return lead_data

    def _safe_get_text(self, xpath):
        try:
            elem = self.bm.find_element(xpath)
            return elem.text.strip() if elem else ""
        except:
            return ""

    def _get_contact_info(self):
        """Click 'Contact info' and extract data."""
        data = {'Email': '', 'Phone': ''}
        try:
            # 1. Click the link
            contact_link = self.bm.find_element(config.SELECTORS['profile']['contact_info_link'])
            if contact_link:
                contact_link.click()
                time.sleep(3)  # Wait for modal animation
                
                # 2. Extract Email
                try:
                    email_elem = self.bm.find_element(config.SELECTORS['contact_info']['email'], timeout=5)
                    if email_elem:
                        data['Email'] = email_elem.text.strip()
                except: pass

                # 3. Extract Phone
                try:
                    phone_elem = self.bm.find_element(config.SELECTORS['contact_info']['phone'], timeout=5)
                    if phone_elem:
                        data['Phone'] = phone_elem.text.strip()
                except: pass
                
                # 4. Close modal
                try:
                    # Generic dismiss button or escape
                    self.driver.find_element(By.TAG_NAME, 'body').send_keys(Keys.ESCAPE)
                except:
                    pass
                
                time.sleep(1)
        except Exception as e:
            logger.warning(f"Error extracting contact info: {e}")
            try: 
                self.driver.find_element(By.TAG_NAME, 'body').send_keys(Keys.ESCAPE)
            except: pass
            
        return data

    def _extract_work_status(self, text):
        """Attempt to find work status keywords."""
        status = self.processor.extract_work_status(text)
        
        # Also check "About" section if headline doesn't have it
        if status == "Unknown / N/A":
            try:
                about_section = self.bm.find_element("//div[@id='about']//following-sibling::div")
                if about_section:
                    status = self.processor.extract_work_status(about_section.text)
            except: pass
            
        return status
