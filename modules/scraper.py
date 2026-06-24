import time
import random
import re
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
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
        # Scroll to load everything on page
        self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(2)
        
        leads = []
        try:
            cards = self.driver.find_elements(By.XPATH, config.SELECTORS['search']['result_card'])
            logger.info(f"Found {len(cards)} result cards using selectors.")
            
            # FALLBACK: If standard cards aren't found, just grab all valid profile links
            if len(cards) == 0:
                logger.info("Falling back to raw link extraction...")
                xpath = "//*[@role='main']//a[contains(@href, '/in/') and not(contains(@href, '/miniProfile')) and not(contains(@href, '/overlay/'))] | //main//a[contains(@href, '/in/') and not(contains(@href, '/miniProfile')) and not(contains(@href, '/overlay/'))] | //div[contains(@class, 'search')]//a[contains(@href, '/in/') and not(contains(@href, '/miniProfile')) and not(contains(@href, '/overlay/'))]"
                links = self.driver.find_elements(By.XPATH, xpath)
                seen_urls = set()
                
                for link in links:
                    try:
                        href = link.get_attribute('href').split('?')[0]
                        if not href or href in seen_urls or "/in/" not in href:
                            continue
                        
                        seen_urls.add(href)
                        profile_id = href.replace("https://www.linkedin.com/in/", "").strip("/")
                        
                        # Skeleton lead (rest will be filled when visiting profile)
                        leads.append({
                            "Full Name": "Pending...",
                            "Location": "",
                            "Profession": "",
                            "LinkedIn ID": profile_id,
                            "Profile URL": href,
                            "Work Status": "Unknown",
                            "Email": "",
                            "Phone": ""
                        })
                    except:
                        pass
                
                logger.info(f"Found {len(leads)} raw profile links via fallback.")
                return leads

            # Standard card extraction
            for card in cards:
                try:
                    # 1. Name and Profile Link
                    name = ""
                    profile_url = ""
                    
                    # Try title link first (most accurate)
                    try:
                        name_elem = card.find_element(By.XPATH, ".//span[contains(@class, 'entity-result__title-text')]//a[contains(@href, '/in/')]")
                        name = name_elem.text.strip().split('\n')[0]
                        profile_url = name_elem.get_attribute('href').split('?')[0]
                    except:
                        pass
                        
                    # Fallback to lockup title
                    if not profile_url:
                        try:
                            name_elem = card.find_element(By.XPATH, ".//a[@data-view-name='search-result-lockup-title']")
                            name = name_elem.text.strip().split('\n')[0]
                            profile_url = name_elem.get_attribute('href').split('?')[0]
                        except:
                            pass
                            
                    # Fallback to any /in/ link inside the card that has text
                    if not profile_url:
                        try:
                            links = card.find_elements(By.XPATH, ".//a[contains(@href, '/in/') and not(contains(@href, '/miniProfile')) and not(contains(@href, '/overlay/'))]")
                            for link in links:
                                if link.text.strip():
                                    name = link.text.strip().split('\n')[0]
                                    profile_url = link.get_attribute('href').split('?')[0]
                                    break
                            # If no text links, just take the first one
                            if not profile_url and links:
                                profile_url = links[0].get_attribute('href').split('?')[0]
                        except:
                            pass
                            
                    if not profile_url:
                        logger.warning("Could not find profile URL in card.")
                        continue
                        
                    profile_id = profile_url.replace("https://www.linkedin.com/in/", "").strip("/")
                    
                    # 3. Headline/Profession & Location
                    headline = ""
                    location = ""
                    try:
                        # Improved extraction by targeting standard classes
                        # 1. Try primary-subtitle for headline
                        try:
                            h_elem = card.find_element(By.XPATH, ".//*[contains(@class, 'primary-subtitle')]")
                            headline = h_elem.text.strip().replace('\n', ' ')
                        except: pass
                        
                        # 2. Try secondary-subtitle for location
                        try:
                            l_elem = card.find_element(By.XPATH, ".//*[contains(@class, 'secondary-subtitle')]")
                            location = l_elem.text.strip().replace('\n', ' ')
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
                    
                    if profile_url:
                        logger.info(f"Captured Profile URL: {profile_url}")
                        leads.append(lead_data)
                    else:
                        logger.debug(f"Skipping incomplete card (no URL found)")
                        
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
        headline = self._safe_get_text(config.SELECTORS['profile']['headline'])
        
        # Broaden USA check to include states and regions since LinkedIn omits "United States" sometimes
        location_lower = location_text.lower()
        usa_identifiers = [
            "united states", "usa", "us", "bay area", "silicon valley", "greater", 
            "alabama", "alaska", "arizona", "arkansas", "california", "colorado", "connecticut", 
            "delaware", "florida", "georgia", "hawaii", "idaho", "illinois", "indiana", "iowa", 
            "kansas", "kentucky", "louisiana", "maine", "maryland", "massachusetts", "michigan", 
            "minnesota", "mississippi", "missouri", "montana", "nebraska", "nevada", "new hampshire", 
            "new jersey", "new mexico", "new york", "north carolina", "north dakota", "ohio", 
            "oklahoma", "oregon", "pennsylvania", "rhode island", "south carolina", "south dakota", 
            "tennessee", "texas", "utah", "vermont", "virginia", "washington", "west virginia", 
            "wisconsin", "wyoming"
        ]
        is_usa = any(loc in location_lower for loc in usa_identifiers)
        
        is_open_to_work_badge = self.bm.find_element(config.SELECTORS['profile']['open_to_work_badge']) is not None
        is_open_to_work = is_open_to_work_badge or ("open to work" in headline.lower()) or ("looking for" in headline.lower())
        
        if config.OPEN_TO_WORK_ONLY and not is_open_to_work:
            logger.debug(f"Skipping profile: Not open to work.")
            return None

        if not is_usa and location_text: # Only skip if location is actually found and not USA
            logger.debug(f"Skipping profile due to location not matching USA criteria: {location_text}")
            return None

        name = self._safe_get_text(config.SELECTORS['profile']['name'])
        if not name:
            try:
                name = self.driver.find_element(By.XPATH, "//h1").text.strip()
            except: pass
            
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
        
        if name:
            lead_data["Full Name"] = name
        if location_text:
            lead_data["Location"] = location_text
        if headline:
            lead_data["Profession"] = headline
            lead_data["Work Status"] = self.processor.extract_work_status(headline)
            
        if contact_info.get('Email'):
            lead_data["Email"] = contact_info['Email']
        if contact_info.get('Phone'):
            lead_data["Phone"] = contact_info['Phone']
            
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
                        email_text = email_elem.text.strip()
                        if not email_text:
                            href = email_elem.get_attribute("href")
                            if href and "mailto:" in href:
                                email_text = href.replace("mailto:", "")
                        data['Email'] = email_text
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
