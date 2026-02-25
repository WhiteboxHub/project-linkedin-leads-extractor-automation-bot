"""Complete email reporting module for LinkedIn Leads Extractor - handles generation AND sending."""
import smtplib
import config
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
from modules.logger import logger

class BotReporter:
    """Handles complete email reporting for bot execution - generation and sending."""
    def __init__(self, metrics_tracker):
        self.metrics_tracker = metrics_tracker
        self.metrics = metrics_tracker.metrics
        self.server = config.SMTP_SERVER
        self.port = config.SMTP_PORT
        self.username = config.SMTP_USERNAME
        self.password = config.SMTP_PASSWORD
        self.email_from = config.EMAIL_FROM
        
        # Support multiple recipients (comma-separated)
        if config.EMAIL_TO:
            self.email_to = [email.strip() for email in config.EMAIL_TO.split(',')]
        else:
            self.email_to = []
    
    def _is_configured(self):
        return all([self.server, self.port, self.username, self.password, self.email_from, self.email_to])
    
    def send_run_report(self, run_results=None):
        """
        Generates and sends the HTML report.
        run_results: Optional dictionary containing summary counts if available
        """
        try:
            subject, html_body = self._generate_html_report(run_results)
            
            if not subject or not html_body:
                logger.warning("Failed to generate report content", extra={"step_name": "BotReporter"})
                return False
            
            return self._send_email(subject, html_body)
                
        except Exception as e:
            logger.error(f"Failed to generate/send email report: {e}", extra={"step_name": "BotReporter"}, exc_info=True)
            return False
    
    def _send_email(self, subject, html_body):
        if not self._is_configured():
            logger.warning("SMTP not configured. Skipping email report.", extra={"step_name": "BotReporter"})
            # Log a snippet for debugging if SMTP is missing
            logger.info(f"--- EMAIL REPORT (DRY RUN) ---\nSubject: {subject}\nBody (HTML length): {len(html_body)} chars\n-----------------------------", extra={"step_name": "BotReporter"})
            return True
            
        msg = MIMEMultipart()
        msg['From'] = self.email_from
        msg['To'] = ', '.join(self.email_to)
        msg['Subject'] = subject
        
        msg.attach(MIMEText(html_body, 'html'))
        
        try:
            logger.info(f"Connecting to SMTP server at {self.server}:{self.port}...", extra={"step_name": "BotReporter"})
            with smtplib.SMTP(self.server, self.port) as server:
                server.starttls()
                server.login(self.username, self.password)
                text = msg.as_string()
                server.sendmail(self.email_from, self.email_to, text)
                logger.info(f"Email report sent successfully to {len(self.email_to)} recipient(s).", extra={"step_name": "BotReporter"})
                return True
        except Exception as e:
            logger.error(f"Failed to send email report: {e}", extra={"step_name": "BotReporter"}, exc_info=True)
            return False
    
    def _generate_html_report(self, run_results=None):
        try:
            start_t = self.metrics.get('start_time')
            end_t = self.metrics.get('end_time')
            duration = str(end_t - start_t) if start_t and end_t else "In Progress..."
            
            final_metrics = {
                "Total Profiles Seen": self.metrics.get('leads_seen', 0),
                "Profiles Attempted": self.metrics.get('leads_attempted', 0),
                "Successfully Extracted": self.metrics.get('leads_extracted', 0),
                "Skipped (Deduplication/Filters)": self.metrics.get('leads_skipped', 0),
                "Failed Extractions": self.metrics.get('leads_failed', 0),
                "Duration": duration
            }

            # If external results provided (like sync counts)
            if run_results:
                if 'synced' in run_results:
                    final_metrics["Synced to Backend"] = run_results['synced']
                if 'duplicates_sync' in run_results:
                    final_metrics["Sync Duplicates"] = run_results['duplicates_sync']

            html_rows = ""
            for k, v in final_metrics.items():
                bg_color = "#ffffff"
                if "Failed" in k and v > 0: bg_color = "#fff3f3"
                if "Successfully" in k: bg_color = "#f3fff3"
                
                html_rows += f"<tr style='background-color: {bg_color};'><td style='padding: 8px; border: 1px solid #ddd;'>{k}</td><td style='padding: 8px; border: 1px solid #ddd;'>{v}</td></tr>"

            # 3. Create failure/skip reason lists
            reason_sections = ""
            
            skipped = self.metrics.get('skipped_reasons', {})
            if skipped:
                skip_rows = "".join([f"<li>{r}: {c}</li>" for r, c in skipped.items()])
                reason_sections += f"<h3>Skipped Reasons</h3><ul>{skip_rows}</ul>"

            failed = self.metrics.get('failed_reasons', {})
            if failed:
                fail_rows = "".join([f"<li>{r}: {c}</li>" for r, c in failed.items()])
                reason_sections += f"<h3>Failure Reasons</h3><ul>{fail_rows}</ul>"

            # 4. Build complete HTML body
            email_body = f"""
            <html>
            <body style="font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; color: #333; line-height: 1.6;">
                <div style="max-width: 600px; margin: 0 auto; border: 1px solid #eee; padding: 20px; border-radius: 8px;">
                    <h2 style="color: #0073b1; border-bottom: 2px solid #0073b1; padding-bottom: 10px;">LinkedIn Leads Extractor - Run Report</h2>
                    <p><strong>Date:</strong> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
                    <p><strong>Job Type:</strong> {config.JOB_UNIQUE_ID}</p>
                    <p><strong>Employee ID:</strong> {config.EMPLOYEE_ID}</p>
                    
                    <h3 style="margin-top: 25px;">Session Metrics</h3>
                    <table style="border-collapse: collapse; width: 100%; box-shadow: 0 1px 3px rgba(0,0,0,0.1);">
                        <tr style="background-color: #f2f2f2; text-align: left;">
                            <th style="padding: 12px; border: 1px solid #ddd;">Metric</th>
                            <th style="padding: 12px; border: 1px solid #ddd;">Value</th>
                        </tr>
                        {html_rows}
                    </table>

                    {reason_sections}
                    
                    <div style="margin-top: 30px; padding: 15px; background-color: #f9f9f9; border-radius: 5px; font-size: 0.9em; color: #666;">
                        <p style="margin: 0;"><strong>Settings used:</strong></p>
                        <ul style="margin: 5px 0;">
                            <li>Max Profiles: {config.MAX_PROFILES_TO_CHECK}</li>
                            <li>Open To Work Only: {config.OPEN_TO_WORK_ONLY}</li>
                            <li>Location Filter: {config.LOCATION_FILTER}</li>
                        </ul>
                    </div>
                    
                    <p style="font-size: 0.8em; color: #999; margin-top: 30px; text-align: center; border-top: 1px solid #eee; padding-top: 15px;">
                        <em>This is an automated report generated by the LinkedIn Leads Extractor Bot.</em>
                    </p>
                </div>
            </body>
            </html>
            """
            
            subject = f"LinkedIn Leads Extractor Report: {final_metrics['Successfully Extracted']} Found - {datetime.now().strftime('%Y-%m-%d')}"
            
            return subject, email_body
            
        except Exception as e:
            logger.error(f"Failed to generate report HTML: {e}", extra={"step_name": "BotReporter"}, exc_info=True)
            return None, None
