import re
import config

class ProcessorModule:
    @staticmethod
    def extract_email(text):
        """Extract valid business emails, skipping personal ones like gmail."""
        if not text:
            return None
            
        email_pattern = r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}'
        image_extensions = {'.png', '.jpg', '.jpeg', '.gif', '.svg', '.webp'}
        
        emails = re.findall(email_pattern, text)
        valid_emails = []
        
        for email in emails:
            if len(email) < 5 or len(email) > 100:
                continue
            
            is_image = any(email.lower().endswith(ext) for ext in image_extensions)
            if is_image:
                continue
                
            valid_emails.append(email)
            
        return list(set(valid_emails)) if valid_emails else None
    
    @staticmethod
    def extract_phone(text):
        if not text:
            return None
        patterns = [
            r'\b\+?\d{1,3}[-.\s]\(?\d{3}\)?[-.\s]\d{3}[-.\s]\d{4}\b', 
            r'\b\(\d{3}\)\s?\d{3}[-.\s]?\d{4}\b',
            r'\b\d{10}\b', 
        ]
        matches = []
        for pattern in patterns:
            found = re.findall(pattern, text)
            matches.extend(found)
        return list(set(matches)) if matches else None

    @staticmethod
    def extract_work_status(text):
        """Extract work status keywords like H1B, GC, Citizen."""
        if not text:
            return "Unknown / N/A"
        keywords = ["H1B", "GC", "Citizen", "Green Card", "EAD", "OPT", "CPT", "US Citizen"]
        text_lower = text.lower()
        found = [kw for kw in keywords if kw.lower() in text_lower]
        return ", ".join(set(found)) if found else "Unknown / N/A"
