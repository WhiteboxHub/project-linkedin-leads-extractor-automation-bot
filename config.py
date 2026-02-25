"""Configuration settings for LinkedIn Leads Extractor."""
import os
import json
from dotenv import load_dotenv

load_dotenv()

# LinkedIn Credentials
LINKEDIN_EMAIL = os.getenv('LINKEDIN_EMAIL')
LINKEDIN_PASSWORD = os.getenv('LINKEDIN_PASSWORD')

# Backend Sync Settings (WBL API)
WBL_API_URL = os.getenv('WBL_API_URL', 'https://api.whitebox-learning.com/api')
WBL_API_TOKEN = os.getenv('WBL_API_TOKEN', '')
WBL_API_EMAIL = os.getenv('WBL_API_EMAIL', '')
WBL_API_PASSWORD = os.getenv('WBL_API_PASSWORD', '')
JOB_UNIQUE_ID = os.getenv('JOB_UNIQUE_ID', 'bot_linkedin_leads_extractor')
EMPLOYEE_ID = os.getenv('EMPLOYEE_ID', '353')
SELECTED_CANDIDATE_ID = os.getenv('SELECTED_CANDIDATE_ID', '0')

# Chrome Profile Settings for persistent login
CHROME_PROFILE_PATH = os.getenv('CHROME_PROFILE_PATH')
CHROME_PROFILE_NAME = os.getenv('CHROME_PROFILE_NAME', 'Default')
CHROME_VERSION = os.getenv('CHROME_VERSION') # Leave empty for auto-detection

# LinkedIn URLs
URLS = {
    "LOGIN": "https://www.linkedin.com/login",
    "MY_NETWORK": "https://www.linkedin.com/mynetwork/",
    "CONNECTIONS": "https://www.linkedin.com/mynetwork/invite-connect/connections/",
}

# Extraction Settings
MAX_PROFILES_TO_CHECK = int(os.getenv('MAX_PROFILES_TO_CHECK', '500'))
MAX_PAGES_PER_KEYWORD = int(os.getenv('MAX_PAGES_PER_KEYWORD', '20'))
LOCATION_FILTER = os.getenv('LOCATION_FILTER', 'United States')
OPEN_TO_WORK_ONLY = os.getenv('OPEN_TO_WORK_ONLY', 'True').lower() == 'true'

# SMTP Email Settings
SMTP_SERVER = os.getenv('SMTP_SERVER')
SMTP_PORT = int(os.getenv('SMTP_PORT', '587'))
SMTP_USERNAME = os.getenv('SMTP_USERNAME')
SMTP_PASSWORD = os.getenv('SMTP_PASSWORD')
EMAIL_FROM = os.getenv('EMAIL_FROM')
EMAIL_TO = os.getenv('EMAIL_TO')

# LinkedIn Selectors - Loaded from JSON
try:
    with open('selectors.json', 'r') as f:
        SELECTORS = json.load(f)
except FileNotFoundError:
    SELECTORS = {}
except json.JSONDecodeError as e:
    print(f"Error parsing selectors.json: {e}")
    SELECTORS = {}
