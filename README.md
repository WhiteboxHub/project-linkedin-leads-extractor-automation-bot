# LinkedIn Leads Extractor Bot

This bot automates the process of extracting potential leads from your LinkedIn connections and syncing them directly to the WBL Lead Management System. It targets profiles that are **"Open to Work"** and located in the **USA**, capturing key contact and professional details.

##  Features

- **Automated Extraction**: Navigates through your LinkedIn connections to identify potential leads.
- **Smart Filtering**:
  - **Open to Work**: Prioritizes candidates explicitly looking for opportunities.
  - **Location**: Filters for candidates based in the USA.
- **Data Capture**: Extracts Name, Headline, Location, Email, Phone, and LinkedIn ID.
- **Work Status Detection**: Attempts to identify visa status (H1B, GC, Citizen, etc.) from profile text.
- **Backend Integration**: Automatically syncs extracted leads to the **Potential Leads** database in the WBL ecosystem.
- **Stealth Mode**: Uses `undetected-chromedriver` and mimics human behavior to avoid detection.
- **Resumable**: Tracks processed profiles to avoid duplicate work.

##  Setup Guide

### 1. Prerequisites
- Python 3.10+
- Google Chrome installed

### 2. Installation
```bash
# Clone the repository
git clone <repository-url>
cd project-linkedin-leads-extractor-automation-bot

# Create virtual environment
python -m venv myenv
# Windows
.\myenv\Scripts\activate
# Mac/Linux
source myenv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### 3. Configuration
The easiest way to configure the bot is using the interactive setup script:

```bash
python setup_production.py
```
This script will:
- Prompt for your WBL credentials.
- Generate a secure API token.
- Validate your Employee ID.
- Create the necessary `.env` file with al your settings.

### 4. Running the Bot
Once configured, simply run:
```bash
python main.py
```

##  Output
- **Console**: Real-time logs of profiles visited and leads found.
- **Database**: Valid leads are synced to the `potential_leads` table and appear in the WBL Dashboard under **Leads > Potential Leads**.
- **CSV Backup**: A local CSV copy is saved in the `output/` directory for your records.
- **Logs**: Detailed execution logs are stored in `logs/` for troubleshooting.

##  Project Structure
- `main.py`: Entry point for the bot.
- `setup_production.py`: Interactive configuration tool.
- `job_activity_logger.py`: Handles API communication with the WBL backend.
- `modules/`:
  - `browser_manager.py`: Manages Chrome instance and stealth settings.
  - `scraper.py`: Core logic for navigating and parsing LinkedIn profiles.
  - `storage_manager.py`: Manages data persistence, DuckDB, CSV and JSON storage.
  - `metrics_manager.py`: Tracks session statistics.
- `selectors.json`: Centralized file for LinkedIn HTML selectors.
