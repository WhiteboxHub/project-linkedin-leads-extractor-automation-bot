import sys
import time
import random
from modules.browser_manager import BrowserManager
from modules.scraper import LinkedInScraper
from modules.storage_manager import StorageManager
from modules.logger import logger
from job_activity_logger import JobActivityLogger
from modules.bot_reporter import BotReporter
import config

def main():
    leads_found = 0
    logger.info("Starting LinkedIn Leads Extractor...")
    
    # Initialize components
    try:
        bm = BrowserManager().init_driver()
        bm.metrics.start_session()
        sm = StorageManager()
        scraper = LinkedInScraper(bm) 
        activity_logger = JobActivityLogger()
        leads_extracted_buffer = []
    except Exception as e:
        logger.critical(f"Initialization failed: {e}")
        return

    try:
        # Step 1: Login
        if not scraper.login():
            logger.error("Failed to login. Please check credentials or handle CAPTCHA.")
            time.sleep(30)
            if "feed" not in bm.driver.current_url:
                bm.quit()
                return

        # Step 2: Load Keywords
        import json
        try:
            with open('keywords.json', 'r') as f:
                keywords_list = json.load(f)
        except:
            keywords_list = ["Software Engineer AND open to work"]

        leads_found = 0
        total_processed = 0

        for keywords in keywords_list:
            if leads_found >= config.MAX_PROFILES_TO_CHECK:
                break
                
            scraper.search_people(keywords)
            
            page = 1
            while page <= config.MAX_PAGES_PER_KEYWORD: # Use custom max pages from .env
                logger.info(f"--- Keyword: '{keywords}' | Page: {page} ---")
                
                # Step 3.1: Capture raw leads from the search results page
                page_leads = scraper.extract_leads_from_page()
                
                if not page_leads:
                    if page == 1:
                        logger.warning(f"No results found for '{keywords}'.")
                    else:
                        logger.info(f"Reach end of results for '{keywords}'.")
                    break

                for lead_data in page_leads:
                    if leads_found >= config.MAX_PROFILES_TO_CHECK:
                        break
                    
                    try:
                        total_processed += 1
                        profile_url = lead_data.get("Profile URL")
                        linkedin_id = lead_data.get("LinkedIn ID")

                        # Deduplication check
                        if sm.is_processed(linkedin_id):
                            logger.info(f"Skipping {linkedin_id}: Already processed.")
                            continue
                        
                        # Step 3.2: Visit profile to get Contact Info (Email/Phone)
                        logger.info(f"Processing candidate: {lead_data['Full Name']} ({profile_url})")
                        
                        # Visit profile for deeper extraction (Contact Info)
                        contact_info = scraper._get_contact_info_from_profile(profile_url)
                        if contact_info:
                            lead_data.update(contact_info)
                        
                        # Update metrics and save
                        bm.metrics.increment('leads_seen')
                        sm.save_lead(lead_data, keywords)
                        leads_extracted_buffer.append(lead_data)
                        leads_found += 1
                        bm.metrics.increment('leads_extracted')
                        
                        logger.info(f"Progress: {total_processed} items checked | Leads saved: {leads_found}")
                        
                        # Delay between profiles
                        time.sleep(random.uniform(5, 10))
                        
                    except Exception as e:
                        logger.error(f"Error processing lead: {e}")
                        bm.metrics.track_failure(str(e))
                        continue
                
                if leads_found >= config.MAX_PROFILES_TO_CHECK:
                    break
                    
                if not scraper.click_next():
                    logger.info(f"No more pages for '{keywords}'.")
                    break
                page += 1

    except KeyboardInterrupt:
        logger.warning("Bot stopped by user.")
    except Exception as e:
        logger.error(f"An unexpected error occurred: {e}")
    finally:
        bm.metrics.end_session()
        bm.metrics.print_summary()
        
        # Final Backend Sync & Reporting
        sync_results = {}
        if leads_found > 0:
            logger.info(f"Syncing {leads_found} leads to backend...")
            sync_results = activity_logger.bulk_save_leads(leads_extracted_buffer)
            activity_logger.log_activity(leads_found, notes=f"Extracted {leads_found} leads from people search.")
        
        # Dispatch Email Report
        try:
            reporter = BotReporter(bm.metrics)
            # Pass sync results to reporter for a more complete email
            report_data = {
                'synced': sync_results.get('inserted', 0),
                'duplicates_sync': sync_results.get('duplicates', 0)
            }
            reporter.send_run_report(run_results=report_data)
        except Exception as e:
            logger.error(f"Failed to dispatch email report: {e}")
        
        logger.info("Extraction complete. Closing browser.")
        bm.quit()

if __name__ == "__main__":
    main()
