import os
import csv
import json
import duckdb
from datetime import datetime
from modules.logger import logger

class StorageManager:
    """
    Manages data persistence including DuckDB for deduplication, 
    date-wise CSV exports, and structured JSON storage for leads.
    """
    def __init__(self):
        self.current_date_str = datetime.now().strftime('%Y-%m-%d')
        
        # Structure for RAW leads
        self.base_raw_dir = "data/raw_leads"
        self.current_raw_dir = os.path.join(self.base_raw_dir, self.current_date_str)
        
        if not os.path.exists(self.current_raw_dir):
            os.makedirs(self.current_raw_dir)
            
        # Output directory for CSVs (date based)
        self.base_output_dir = "data/output"
        self.current_output_dir = os.path.join(self.base_output_dir, self.current_date_str)
        if not os.path.exists(self.current_output_dir):
            os.makedirs(self.current_output_dir)
            
        self.processed_ids = set()
        self.db_file = 'leads_data.db'
        
        # Headers for CSV
        self.csv_headers = [
            "Full Name", "Location", "Profession", "LinkedIn ID", 
            "Email", "Phone", "Work Status", "Description", "Profile URL", "Extraction Date"
        ]
        
        self.load_processed_ids()

    def _ensure_db_schema(self, con):
        """Create the leads table if it doesn't exist."""
        con.execute("""
            CREATE TABLE IF NOT EXISTS leads (
                linkedin_id VARCHAR PRIMARY KEY,
                full_name VARCHAR,
                email VARCHAR,
                phone VARCHAR,
                profession VARCHAR,
                location VARCHAR,
                work_status VARCHAR,
                description VARCHAR,
                profile_url VARCHAR,
                extraction_date TIMESTAMP
            )
        """)
        try:
            con.execute("ALTER TABLE leads ADD COLUMN description VARCHAR")
        except: pass

    def load_processed_ids(self):
        """Load previously processed LinkedIn IDs from DuckDB."""
        try:
            con = duckdb.connect(self.db_file)
            self._ensure_db_schema(con)
            
            results = con.execute("SELECT linkedin_id FROM leads").fetchall()
            for row in results:
                self.processed_ids.add(row[0])
            
            logger.info(f"Loaded {len(self.processed_ids)} previously processed IDs from DuckDB ({self.db_file})")
            con.close()
        except Exception as e:
            logger.error(f"Could not load processed IDs from DuckDB: {e}")
            self.processed_ids = set()

    def is_processed(self, linkedin_id):
        """Check if a lead has already been processed."""
        return linkedin_id in self.processed_ids

    def save_lead(self, lead_data, keyword):
        """Save lead data to DuckDB, JSON, and CSV."""
        linkedin_id = lead_data.get("LinkedIn ID")
        if not linkedin_id:
            logger.warning("Attempted to save lead without LinkedIn ID")
            return False

        try:
            # 1. Save to DuckDB (Deduplication layer)
            self._save_to_db(lead_data)
            self.processed_ids.add(linkedin_id)

            # 2. Save to JSON (Structured format)
            self._save_to_json(lead_data, keyword)

            # 3. Save to CSV (Export format)
            self._save_to_csv(lead_data)

            # 4. Save to JSON in output folder (Consolidated)
            self._save_to_output_json(lead_data)

            return True
        except Exception as e:
            logger.error(f"Error saving lead {linkedin_id}: {e}")
            return False

    def _save_to_db(self, lead_data):
        con = duckdb.connect(self.db_file)
        self._ensure_db_schema(con)
        
        con.execute("""
            INSERT OR REPLACE INTO leads 
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            lead_data.get("LinkedIn ID"),
            lead_data.get("Full Name"),
            lead_data.get("Email"),
            lead_data.get("Phone"),
            lead_data.get("Profession"),
            lead_data.get("Location"),
            lead_data.get("Work Status"),
            lead_data.get("Description"),
            lead_data.get("Profile URL"),
            datetime.now()
        ))
        con.close()

    def _save_to_json(self, lead_data, keyword):
        safe_keyword = keyword.replace(' ', '_').replace('/', '_')
        filename = f"{safe_keyword}_leads.json"
        filepath = os.path.join(self.current_raw_dir, filename)
        
        leads_list = []
        if os.path.exists(filepath):
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    leads_list = json.load(f)
            except:
                leads_list = []

        # Avoid duplicates in the same day's JSON file
        if not any(l.get("LinkedIn ID") == lead_data.get("LinkedIn ID") for l in leads_list):
            leads_list.append({
                **lead_data,
                "search_keyword": keyword,
                "extraction_timestamp": datetime.now().isoformat()
            })
            
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(leads_list, f, indent=2, ensure_ascii=False)

    def _save_to_output_json(self, lead_data):
        """Save to a consolidated JSON file in the output directory."""
        filepath = os.path.join(self.current_output_dir, 'leads.json')
        leads_list = []
        if os.path.exists(filepath):
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    leads_list = json.load(f)
            except:
                leads_list = []
        
        # Add extraction date if not present
        if "Extraction Date" not in lead_data:
            lead_data["Extraction Date"] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        # Check for duplicates in the consolidated file
        if not any(l.get("LinkedIn ID") == lead_data.get("LinkedIn ID") for l in leads_list):
            leads_list.append(lead_data)
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(leads_list, f, indent=2, ensure_ascii=False)

    def _save_to_csv(self, lead_data):
        filepath = os.path.join(self.current_output_dir, 'leads.csv')
        file_exists = os.path.exists(filepath)
        
        # Add extraction date if not present
        if "Extraction Date" not in lead_data:
            lead_data["Extraction Date"] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        with open(filepath, mode='a', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=self.csv_headers, extrasaction='ignore')
            if not file_exists:
                writer.writeheader()
            writer.writerow(lead_data)
