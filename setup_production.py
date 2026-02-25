
import requests
import json
import os
import re
from pathlib import Path


DEFAULT_API_URL = "http://localhost:8000"
JOB_UNIQUE_ID = "bot_linkedin_leads_extractor"
ENV_FILE = ".env"

def setup_api_connection():
    print("=" * 70)
    print(" WBL JOB ACTIVITY LOGGER SETUP (LEADS EXTRACTOR)")
    print("=" * 70)
    print("\nThis script will configure the bot with your personal credentials.")
    print("=" * 70)

    # Step 1: Configuration Choice
    print("\n Step 1: Select Environment")
    print("-" * 70)
    print(f"1. Local (Default: {DEFAULT_API_URL})")
    print("2. Production (https://api.whitebox-learning.com/api)")
    choice = input("\nSelect environment [1/2, default: 2]: ").strip() or "1"
    
    if choice == "2":
        api_url = "https://api.whitebox-learning.com/api"
    else:
        api_url = input(f"Enter API URL [default: {DEFAULT_API_URL}]: ").strip() or DEFAULT_API_URL

    print("\n Step 2: Your Credentials")
    print("-" * 70)
    email = input("Enter your WBL email: ")
    password = input("Enter your WBL password: ")
    employee_id = input("Enter your Employee ID (e.g., 353): ").strip()
    
    while not employee_id:
        employee_id = input("Employee ID is required. Please enter it: ").strip()

    print("\n Step 2.5: Chrome Profile (Optional)")
    print("-" * 70)
    print("Providing a Chrome profile allows the bot to stay logged in.")
    print("Example Path: C:\\Users\\YourName\\AppData\\Local\\Google\\Chrome\\User Data")
    chrome_path = input("Enter Chrome User Data Path (Enter to skip): ").strip()
    chrome_profile = "Default"
    if chrome_path:
        chrome_profile = input("Enter Profile Name [default: Default]: ").strip() or "Default"

  
    print("\n Step 3: Getting JWT Token")
    print("-" * 70)
  
    login_url = f"{api_url}/login"
    if "localhost" in api_url and not api_url.endswith("/api"):
        login_url = f"{api_url}/api/login"

    try:
       
        response = requests.post(
            login_url,
            data={
                "username": email,
                "password": password
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"}
        )
        response.raise_for_status()
        data = response.json()
        token = data.get("access_token")
        
        if not token:
            print(" ERROR: No access_token in response")
            return
        
        print(f" Token received: {token[:20]}...{token[-20:]}")
        
    except Exception as e:
        print(f" Login failed: {e}")
        if hasattr(e, 'response') and e.response is not None:
             print(f"   Response: {e.response.text}")
        return

    print("\n Step 3.5: Verifying Token and Employee ID")
    print("-" * 70)
    
    # Use an employee-specific endpoint to verify both the token and the ID
    emp_verify_url = f"{api_url}/employees/{employee_id}/candidates"
    if "localhost" in api_url and not api_url.endswith("/api"):
        emp_verify_url = f"{api_url}/api/employees/{employee_id}/candidates"
    
    try:
        print(f" Verifying Employee ID {employee_id}...")
        response = requests.get(emp_verify_url, headers={"Authorization": f"Bearer {token}"})
        
        if response.status_code == 401:
            print(" ERROR: Token rejected by API. Access denied. Please check your credentials.")
            return
        elif response.status_code == 404:
            print(f" ERROR: Employee ID {employee_id} not found in the database.")
            print(" Please check your ID and try again.")
            return
            
        response.raise_for_status()
        print(f"   [✓] Token Valid")
        print(f"   [✓] Employee ID {employee_id} verified")
        
    except Exception as e:
        print(f" ERROR: Validation failed: {e}")
        if hasattr(e, 'response') and e.response is not None:
             print(f"   Response: {e.response.text}")
        return

    selected_candidate_id = "0"
 
    print("\n Step 4: Updating .env File")
    print("-" * 70)

    try:
        env_content = ""
        if os.path.exists(ENV_FILE):
            with open(ENV_FILE, 'r') as f:
                env_content = f.read()
        elif os.path.exists('.env.example'):
            with open('.env.example', 'r') as f:
                env_content = f.read()
        else:
            
            env_content = (
                "LINKEDIN_EMAIL=\n"
                "LINKEDIN_PASSWORD=\n"
                "WBL_API_URL=\n"
                "WBL_API_TOKEN=\n"
                "JOB_UNIQUE_ID=bot_linkedin_leads_extractor\n"
                "EMPLOYEE_ID=\n"
                "SELECTED_CANDIDATE_ID=0\n"
                "CHROME_PROFILE_PATH=\n"
                "CHROME_PROFILE_NAME=Default\n"
                "MAX_PROFILES_TO_CHECK=500\n"
                "LOCATION_FILTER=United States\n"
                "OPEN_TO_WORK_ONLY=True\n"
            )

     
        def update_key(content, key, value):
            # Escape backslashes for the replacement string in re.sub
            escaped_value = value.replace('\\', '\\\\')
            if f"{key}=" in content:
                return re.sub(rf'^{key}=.*', f'{key}={escaped_value}', content, flags=re.MULTILINE)
            else:
                return content.rstrip() + f"\n{key}={value}\n"

        env_content = update_key(env_content, "WBL_API_URL", api_url)
        env_content = update_key(env_content, "WBL_API_TOKEN", token)
        env_content = update_key(env_content, "JOB_UNIQUE_ID", JOB_UNIQUE_ID)
        env_content = update_key(env_content, "EMPLOYEE_ID", employee_id)
        env_content = update_key(env_content, "SELECTED_CANDIDATE_ID", selected_candidate_id)
        if chrome_path:
            env_content = update_key(env_content, "CHROME_PROFILE_PATH", chrome_path)
            env_content = update_key(env_content, "CHROME_PROFILE_NAME", chrome_profile)

        with open(ENV_FILE, 'w') as f:
            f.write(env_content)
        
        print(f" Updated {ENV_FILE} with your personal configuration.")
        
    except Exception as e:
        print(f" Failed to update .env: {e}")
        return

   
    print("\n  Step 5: Verifying Job Type in Database")
    print("-" * 70)

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }

   
    types_url = f"{api_url}/job-types"
    if "localhost" in api_url and not api_url.endswith("/api"):
        types_url = f"{api_url}/api/job-types"

    try:
        response = requests.get(types_url, headers=headers)
        response.raise_for_status()
        existing_jobs = response.json()
        
        job_exists = False
        for job in existing_jobs:
            if job.get('unique_id') == JOB_UNIQUE_ID:
                print(f" Job type already exists (ID: {job.get('id')})")
                job_exists = True
                break
        
        if not job_exists:
            print("Creating missing job type...")
            job_type_data = {
                "unique_id": JOB_UNIQUE_ID,
                "name": "LinkedIn Leads Extractor Bot",
                "job_owner_id": int(employee_id),
                "description": "Extracts potential leads from LinkedIn connections.",
                "notes": "Automated bot that processes LinkedIn connections and extracts potential leads."
            }
            response = requests.post(types_url, json=job_type_data, headers=headers)
            response.raise_for_status()
            print(f" Job type created successfully.")
            
    except Exception as e:
        print(f"  Note: Could not verify/create job type via API: {e}")
        print("   If you have already run the SQL setup script, this is fine.")

    print("\n" + "=" * 70)
    print(" PERSONAL SETUP COMPLETE!")
    print("=" * 70)
    print("\nYour bot is now configured for your account.")
    print(f"Linked to Employee ID: {employee_id}")
    print("\nNext step: Run 'python main.py'")
    print("=" * 70)

def main():
    while True:
        print("\n" + "="*60)
        print(" LINKEDIN BOT SETUP MENU")
        print("="*60)
        print(" 1. Setup API Connection (.env)")
        print(" 0. Exit")
        
        choice = input("\n Enter choice: ").strip()
        
        if choice == '1':
            setup_api_connection()
        elif choice == '0':
            print(" Exiting.")
            break
        else:
            print(" Invalid choice.")

if __name__ == "__main__":
    main()
