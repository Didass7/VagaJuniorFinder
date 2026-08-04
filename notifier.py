import os
import smtplib
import logging
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
import markdown
from bs4 import BeautifulSoup

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger("Notifier")

class EmailNotifier:
    def __init__(self, smtp_server: str, smtp_port: int, smtp_email: str, smtp_password: str, receiver_email: str):
        self.smtp_server = smtp_server
        self.smtp_port = smtp_port
        self.smtp_email = smtp_email
        self.smtp_password = smtp_password
        self.receiver_email = receiver_email

    def markdown_to_html(self, md_text: str) -> str:
        raw_html = markdown.markdown(md_text, extensions=['fenced_code', 'tables', 'nl2br'])
        soup = BeautifulSoup(raw_html, "html.parser")
        
        # Apply 100% INLINE STYLES with zero fluff / clean modern corporate design
        for tag in soup.find_all("h1"):
            tag['style'] = "color: #111827; font-size: 20px; font-weight: 700; border-bottom: 2px solid #e5e7eb; padding-bottom: 8px; margin-top: 0; margin-bottom: 12px; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;"
            
        for tag in soup.find_all("h2"):
            tag['style'] = "color: #1f2937; font-size: 16px; font-weight: 700; border-bottom: 1px solid #e5e7eb; padding-bottom: 4px; margin-top: 24px; margin-bottom: 12px; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;"
            
        for tag in soup.find_all("h3"):
            tag['style'] = "color: #2563eb; font-size: 15px; font-weight: 600; margin-top: 16px; margin-bottom: 4px; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;"
            
        for tag in soup.find_all("p"):
            tag['style'] = "color: #374151; font-size: 13px; line-height: 1.5; margin-bottom: 8px; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;"
            
        for tag in soup.find_all("li"):
            tag['style'] = "color: #374151; font-size: 13px; margin-bottom: 4px; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;"
            
        for tag in soup.find_all("strong"):
            tag['style'] = "color: #111827; font-weight: 600;"
            
        for tag in soup.find_all("a"):
            tag['style'] = "color: #2563eb; font-weight: 600; text-decoration: none;"
            
        for tag in soup.find_all("code"):
            tag['style'] = "background-color: #f3f4f6; color: #1f2937; padding: 2px 5px; border-radius: 3px; font-size: 12px; font-family: SFMono-Regular, Consolas, monospace; border: 1px solid #e5e7eb;"
            
        for tag in soup.find_all("blockquote"):
            tag['style'] = "background-color: #f9fafb; border-left: 3px solid #2563eb; margin: 8px 0; padding: 8px 12px; color: #4b5563; font-style: italic; border-radius: 0 4px 4px 0; font-size: 13px;"
            
        for tag in soup.find_all("hr"):
            tag['style'] = "border: 0; height: 1px; background-color: #e5e7eb; margin: 20px 0;"

        full_html = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
</head>
<body style="background-color: #f9fafb; color: #374151; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; margin: 0; padding: 20px 10px;">
    <div style="max-width: 700px; margin: 0 auto; background-color: #ffffff; padding: 28px 24px; border-radius: 6px; border: 1px solid #e5e7eb; box-shadow: 0 1px 3px rgba(0,0,0,0.05);">
        {str(soup)}
    </div>
</body>
</html>"""
        return full_html

    def send_email_report(self, md_content: str, md_filepath: str = "") -> bool:
        if not self.smtp_email or not self.smtp_password:
            logger.warning("⚠️ SMTP email or password not configured in .env. Skipping email sending.")
            return False

        subject = f"Relatório Diário de Vagas — AI & Data Science"
        html_content = self.markdown_to_html(md_content)

        msg = MIMEMultipart("mixed")
        msg["Subject"] = subject
        msg["From"] = f"VagaJuniorFinder <{self.smtp_email}>"
        msg["To"] = self.receiver_email

        # Attach HTML body
        msg_alternative = MIMEMultipart("alternative")
        html_part = MIMEText(html_content, "html", "utf-8")
        msg_alternative.attach(html_part)
        msg.attach(msg_alternative)

        # Attach raw Markdown file if available
        if md_filepath and os.path.exists(md_filepath):
            try:
                with open(md_filepath, "rb") as f:
                    part = MIMEBase("application", "octet-stream")
                    part.set_payload(f.read())
                encoders.encode_base64(part)
                filename = os.path.basename(md_filepath)
                part.add_header("Content-Disposition", f"attachment; filename= {filename}")
                msg.attach(part)
            except Exception as attachment_err:
                logger.error(f"Error attaching Markdown file: {attachment_err}")

        # Send via SMTP
        try:
            logger.info(f"📧 Connecting to SMTP server {self.smtp_server}:{self.smtp_port}...")
            if self.smtp_port == 465:
                server = smtplib.SMTP_SSL(self.smtp_server, self.smtp_port, timeout=15)
            else:
                server = smtplib.SMTP(self.smtp_server, self.smtp_port, timeout=15)
                server.starttls()

            server.login(self.smtp_email, self.smtp_password)
            server.sendmail(self.smtp_email, [self.receiver_email], msg.as_string())
            server.quit()
            logger.info(f"✅ Daily report email successfully sent to {self.receiver_email}!")
            return True
        except Exception as e:
            logger.error(f"❌ Failed to send email via SMTP: {e}")
            return False
