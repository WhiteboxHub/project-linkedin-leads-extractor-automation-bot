import requests
import os
import base64
import json
from datetime import date, datetime
from typing import Optional
from modules.logger import logger as bot_logger # Avoid name collision
import config

class JobActivityLogger:    
    def __init__(self):
        self.api_url = config.WBL_API_URL
        self.api_token = config.WBL_API_TOKEN
        self.api_email = os.getenv('WBL_API_EMAIL', '')
        self.api_password = os.getenv('WBL_API_PASSWORD', '')
        self.job_unique_id = config.JOB_UNIQUE_ID
        self.employee_id = int(config.EMPLOYEE_ID)
        self.selected_candidate_id = int(config.SELECTED_CANDIDATE_ID)
        
        self.headers = {
            "Authorization": f"Bearer {self.api_token}",
            "Content-Type": "application/json"
        }
        
        if not self.api_token:
            bot_logger.warning("WBL_API_TOKEN not set. Activity logging will be skipped.")

    def _is_token_expired(self, buffer_seconds=300) -> bool:
        """Decode JWT locally and check if it's expired (or within buffer_seconds of expiry)."""
        try:
            if not self.api_token:
                return True
            parts = self.api_token.split('.')
            if len(parts) != 3:
                return True
            payload_b64 = parts[1]
            payload_b64 += '=' * (-len(payload_b64) % 4)
            payload = json.loads(base64.b64decode(payload_b64))
            exp = payload.get('exp')
            if not exp:
                return True
            return datetime.utcnow().timestamp() >= (exp - buffer_seconds)
        except Exception:
            return True

    def _refresh_token(self) -> bool:
        """Login to WBL API and update the token in memory and in .env file."""
        if not self.api_email or not self.api_password:
            bot_logger.warning("[TOKEN] Cannot auto-refresh: WBL_API_EMAIL or WBL_API_PASSWORD not set in .env")
            return False

        base_url = self.api_url.rstrip('/')
        if '/api' not in base_url:
            base_url = f"{base_url}/api"

        login_url = f"{base_url}/login"
        try:
            bot_logger.info("[TOKEN] Refreshing WBL API token...")
            response = requests.post(
                login_url,
                data={'username': self.api_email, 'password': self.api_password},
                headers={'Content-Type': 'application/x-www-form-urlencoded'},
                timeout=15
            )
            if response.status_code != 200:
                bot_logger.error(f"[TOKEN] Refresh failed: {response.status_code}")
                return False

            data = response.json()
            new_token = data.get('access_token')
            if not new_token:
                return False

            self.api_token = new_token
            self.headers['Authorization'] = f"Bearer {new_token}"

            # Update .env file
            env_path = '.env'
            if os.path.exists(env_path):
                with open(env_path, 'r') as f:
                    lines = f.readlines()
                with open(env_path, 'w') as f:
                    for line in lines:
                        if line.startswith('WBL_API_TOKEN='):
                            f.write(f'WBL_API_TOKEN={new_token}\n')
                        else:
                            f.write(line)
            
            bot_logger.info("[TOKEN] Token refreshed successfully.")
            return True
        except Exception as e:
            bot_logger.error(f"[TOKEN] Refresh error: {e}")
            return False

    def _ensure_valid_token(self):
        """Check token expiry and auto-refresh if needed."""
        if self._is_token_expired():
            self._refresh_token()

    def log_activity(self, activity_count: int, notes: str = "", candidate_id: int = 0) -> bool:
        """Log a summary of the extraction session to the backend."""
        self._ensure_valid_token()
        if not self.api_token:
            return False
            
        activity_date = date.today().isoformat()
        target_candidate_id = candidate_id if candidate_id != 0 else (self.selected_candidate_id if self.selected_candidate_id != 0 else None)
            
        job_type_id = self._get_job_type_id()
        if job_type_id is None:
            bot_logger.error(f"Cannot log activity: Job type '{self.job_unique_id}' not found in backend.")
            return False
        
        payload = {
            "job_id": job_type_id,
            "employee_id": self.employee_id,
            "activity_count": activity_count,
            "candidate_id": target_candidate_id,
            "notes": notes,
            "activity_date": activity_date
        }
        
        base_url = self.api_url.rstrip('/')
        if '/api' not in base_url:
            base_url = f"{base_url}/api"
            
        endpoint = f"{base_url}/job_activity_logs"
        
        try:
            response = requests.post(endpoint, json=payload, headers=self.headers)
            response.raise_for_status()
            result = response.json()
            bot_logger.info(f"Backend activity logged: {activity_count} leads (Log ID: {result.get('id', 'N/A')})")
            return True
        except Exception as e:
            bot_logger.error(f"Failed to log activity to backend: {e}")
            return False

    def bulk_save_leads(self, leads_list: list) -> dict:
        """Sync extracted leads to the potential_leads table using individual requests."""
        self._ensure_valid_token()
        if not self.api_token or not leads_list:
            return {"inserted": 0, "failed": 0, "duplicates": 0, "total": 0}
            
        base_url = self.api_url.rstrip('/')
        if '/api' not in base_url:
            base_url = f"{base_url}/api"
            
        endpoint = f"{base_url}/potential-leads"
        
        inserted_count = 0
        duplicate_count = 0
        failed_count = 0
        
        for lead in leads_list:
            # Prepare payload for PotentialLead
            # Backend expects valid email or None. Empty string "" causes 422 error.
            email = lead.get('Email', '').strip() if lead.get('Email') else None
            phone = lead.get('Phone', '').strip() if lead.get('Phone') else None
            
            # Additional validation for email
            if email and "@" not in email:
                email = None
            
            # Stringify the lead data for the notes field as requested
            notes = lead.get('Notes', '')
            if not notes:
                # Include the raw lead data as JSON in notes
                notes = json.dumps(lead, ensure_ascii=False)

            payload = {
                "full_name": lead.get('Full Name', 'Unknown')[:150],
                "email": email,
                "phone": phone,
                "profession": lead.get('Profession', '')[:150],
                "linkedin_id": lead.get('Profile URL'),
                "internal_linkedin_id": lead.get('LinkedIn ID'),
                "location": lead.get('Location', '')[:150],
                "work_status": lead.get('Work Status')[:50] if lead.get('Work Status') else None,
                "notes": notes
            }
            
            try:
                response = requests.post(endpoint, json=payload, headers=self.headers)
                if response.status_code == 200 or response.status_code == 201:
                    inserted_count += 1
                elif response.status_code == 400: # Assuming backend validation for duplicates
                    duplicate_count += 1
                    bot_logger.debug(f"Duplicate found: {payload.get('full_name')} | Response: {response.text}")
                else:
                    failed_count += 1
                    bot_logger.warning(f"Failed to sync lead {payload.get('full_name')}: Status {response.status_code} | Error: {response.text}")
            except Exception as e:
                bot_logger.error(f"Failed to sync lead {payload.get('full_name')}: {e}")
                failed_count += 1
                
        bot_logger.info(f"Sync complete: {inserted_count} inserted, {duplicate_count} skipped/duplicates, {failed_count} failed out of {len(leads_list)}.")
        return {"inserted": inserted_count, "failed": failed_count, "duplicates": duplicate_count, "total": len(leads_list)}

    def _get_job_type_id(self) -> Optional[int]:
        """Fetch the internal database ID for the given JOB_UNIQUE_ID."""
        self._ensure_valid_token()
        try:
            base_url = self.api_url.rstrip('/')
            if '/api' not in base_url:
                base_url = f"{base_url}/api"
            endpoint = f"{base_url}/job-types"
                
            response = requests.get(endpoint, headers=self.headers)
            response.raise_for_status()
            job_types = response.json()
            
            for job_type in job_types:
                if job_type.get('unique_id') == self.job_unique_id:
                    return job_type.get('id')
            return None
        except Exception as e:
            bot_logger.warning(f"Could not fetch job type ID: {e}")
            return None
