import sys
import time
import random
import os
import json
from modules.browser_manager import BrowserManager
from modules.scraper import LinkedInScraper
from modules.storage_manager import StorageManager
from modules.logger import logger
from job_activity_logger import JobActivityLogger
from modules.bot_reporter import BotReporter
import config

class LinkedInLeadsBot:
    def __init__(self, email=None, password=None, candidate_id=None, keywords=None, chrome_profile=None):
        self.linkedin_email = email or config.LINKEDIN_EMAIL
        self.linkedin_password = password or config.LINKEDIN_PASSWORD
        self.candidate_id = candidate_id
        self.chrome_profile = chrome_profile
        
        self.browser_manager = BrowserManager(chrome_profile=self.chrome_profile)
        self.storage_manager = StorageManager()
        self.activity_logger = JobActivityLogger()
        
        if self.candidate_id:
            self.activity_logger.selected_candidate_id = self.candidate_id
            
        self.scraper = None
        self.keywords = keywords if keywords else []
        self.total_processed = 0
        self.leads_found = 0
        self.leads_extracted_buffer = []
        
    def load_keywords(self):
        if self.keywords:
            logger.info(f"Loaded {len(self.keywords)} keywords from config")
            return True
        try:
            with open('keywords.json', 'r') as f:
                self.keywords = json.load(f)
            logger.info(f"Loaded {len(self.keywords)} keywords from JSON file")
            return True
        except FileNotFoundError:
            logger.warning("keywords.json not found, using default fallback.")
            self.keywords = ["Software Engineer AND open to work"]
            return True
        except Exception as e:
            logger.error(f"Error loading keywords: {e}")
            return False

    def init_driver(self):
        self.browser_manager.init_driver()
        self.scraper = LinkedInScraper(self.browser_manager)

    def process_keyword(self, keyword):
        if self.leads_found >= config.MAX_PROFILES_TO_CHECK:
            return

        self.scraper.search_people(keyword)
        
        page = 1
        # Infinite pagination loop
        while True:
            logger.info(f"--- Keyword: '{keyword}' | Page: {page} ---")
            
            # Step 3.1: Capture raw leads from the search results page
            page_leads = self.scraper.extract_leads_from_page()
            
            if not page_leads:
                if page == 1:
                    logger.warning(f"No results found for '{keyword}'.")
                else:
                    logger.info(f"Reach end of results for '{keyword}'.")
                break

            for lead_data in page_leads:
                if self.leads_found >= config.MAX_PROFILES_TO_CHECK:
                    logger.info(f"Reached MAX_PROFILES_TO_CHECK ({config.MAX_PROFILES_TO_CHECK}). Stopping extraction for this keyword.")
                    break
                
                try:
                    self.total_processed += 1
                    profile_url = lead_data.get("Profile URL")
                    linkedin_id = lead_data.get("LinkedIn ID")

                    # Deduplication check
                    if self.storage_manager.is_processed(linkedin_id):
                        logger.info(f"Skipping {linkedin_id}: Already processed.")
                        continue
                    
                    # Step 3.2: Visit profile to get full details (Name, Headline, Contact Info)
                    logger.info(f"Visiting profile for full extraction: {profile_url}")
                    
                    # Mark as processed immediately so we don't revisit this profile in the future, even if it gets skipped below
                    self.storage_manager.mark_processed(linkedin_id)
                    
                    full_profile_data = self.scraper.scrape_profile(profile_url)
                    if full_profile_data:
                        # Update lead_data with the accurate profile data, preserving existing non-empty values
                        for key, val in full_profile_data.items():
                            if val:
                                lead_data[key] = val
                            elif key not in lead_data:
                                lead_data[key] = val
                    else:
                        logger.warning(f"Failed to scrape profile details or candidate not in USA: {profile_url}")
                        continue
                    
                    # Update metrics and save
                    self.browser_manager.metrics.increment('leads_seen')
                    self.storage_manager.save_lead(lead_data, keyword)
                    self.leads_extracted_buffer.append(lead_data)
                    self.leads_found += 1
                    self.browser_manager.metrics.increment('leads_extracted')
                    
                    logger.info(f"Progress: {self.total_processed} items checked | Leads saved: {self.leads_found}")
                    
                    # Delay between profiles
                    time.sleep(random.uniform(5, 10))
                    
                except Exception as e:
                    logger.error(f"Error processing lead: {e}")
                    self.browser_manager.metrics.track_failure(str(e))
                    continue
                
            if self.leads_found >= config.MAX_PROFILES_TO_CHECK:
                break
                
            if not self.scraper.click_next():
                logger.info(f"No more pages for '{keyword}'.")
                break
            page += 1

    def run(self):
        logger.info("Starting LinkedIn Leads Extractor...")
        sync_results = {}
        try:
            self.load_keywords()
            self.init_driver()
            self.browser_manager.metrics.start_session()
            
            # Step 1: Login
            if not self.scraper.login():
                logger.error("Failed to login. Please check credentials or handle CAPTCHA.")
                time.sleep(30)
                if "feed" not in self.browser_manager.driver.current_url:
                    return {"saved": 0, "synced": 0, "duplicates_sync": 0}

            for idx, keyword in enumerate(self.keywords, 1):
                try:
                    logger.info(f"Starting Keyword {idx}/{len(self.keywords)}: {keyword}")
                    self.process_keyword(keyword)
                except Exception as e:
                    logger.error(f"Error processing keyword '{keyword}': {e}", exc_info=True)
                    continue
                
                if idx < len(self.keywords):
                    sleep_time = random.uniform(10, 20)
                    logger.info(f"Sleeping {sleep_time:.1f}s before next keyword...")
                    time.sleep(sleep_time)

        except KeyboardInterrupt:
            logger.warning("Bot stopped by user.")
        except Exception as e:
            logger.error(f"An unexpected error occurred: {e}", exc_info=True)
        finally:
            if hasattr(self.browser_manager, 'metrics'):
                self.browser_manager.metrics.end_session()
                self.browser_manager.metrics.print_summary()
            
            if self.leads_found > 0:
                logger.info(f"Syncing {self.leads_found} leads to backend...")
                sync_results = self.activity_logger.bulk_save_leads(self.leads_extracted_buffer)
                self.activity_logger.log_activity(self.leads_found, notes=f"Extracted {self.leads_found} leads from people search.")
            
            logger.info("Extraction complete. Closing browser.")
            self.browser_manager.quit()
            
            return {
                "saved": self.leads_found,
                "synced": sync_results.get('inserted', 0),
                "duplicates_sync": sync_results.get('duplicates', 0)
            }


if __name__ == "__main__":
    bot = LinkedInLeadsBot()
    results = bot.run()
    
    try:
        from modules.bot_reporter import BotReporter
        reporter = BotReporter(bot.browser_manager.metrics)
        report_data = {
            'synced': results.get('synced', 0),
            'duplicates_sync': results.get('duplicates_sync', 0)
        }
        reporter.send_run_report(run_results=report_data)
    except Exception as e:
        logger.error(f"Failed to dispatch email report: {e}")
