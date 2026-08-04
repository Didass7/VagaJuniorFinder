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
        # Convert markdown to basic HTML
        raw_html = markdown.markdown(md_text, extensions=['fenced_code', 'tables', 'nl2br'])
        
        # Parse HTML and apply 100% INLINE STYLES to prevent Gmail from stripping styles
        soup = BeautifulSoup(raw_html, "html.parser")
        
        # Inline styling rules map
        for tag in soup.find_all("h1"):
            tag['style'] = "color: #0f172a; font-size: 22px; font-weight: 700; border-bottom: 2px solid #e2e8f0; padding-bottom: 8px; margin-top: 0; margin-bottom: 16px; font-family: sans-serif;"
            
        for tag in soup.find_all("h2"):
            tag['style'] = "color: #1e293b; font-size: 18px; font-weight: 700; border-bottom: 1px solid #e2e8f0; padding-bottom: 6px; margin-top: 28px; margin-bottom: 14px; font-family: sans-serif;"
            
        for tag in soup.find_all("h3"):
            tag['style'] = "color: #1d4ed8; font-size: 16px; font-weight: 600; margin-top: 20px; margin-bottom: 6px; font-family: sans-serif;"
            
        for tag in soup.find_all("p"):
            tag['style'] = "color: #334155; font-size: 14px; line-height: 1.6; margin-bottom: 10px; font-family: sans-serif;"
            
        for tag in soup.find_all("li"):
            tag['style'] = "color: #334155; font-size: 14px; margin-bottom: 6px; font-family: sans-serif;"
            
        for tag in soup.find_all("strong"):
            tag['style'] = "color: #0f172a; font-weight: 700;"
            
        for tag in soup.find_all("a"):
            tag['style'] = "color: #2563eb; font-weight: 600; text-decoration: none;"
            
        for tag in soup.find_all("code"):
            tag['style'] = "background-color: #f1f5f9; color: #0f172a; padding: 2px 6px; border-radius: 4px; font-size: 13px; font-family: monospace; border: 1px solid #cbd5e1;"
            
        for tag in soup.find_all("blockquote"):
            tag['style'] = "background-color: #f8fafc; border-left: 4px solid #3b82f6; margin: 12px 0; padding: 10px 14px; color: #475569; font-style: italic; border-radius: 0 6px 6px 0;"
            
        for tag in soup.find_all("hr"):
            tag['style'] = "border: 0; height: 1px; background-color: #cbd5e1; margin: 24px 0;"

        # Wrap inside clean white container
        full_html = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
</head>
<body style="background-color: #f8fafc; color: #1e293b; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Arial, sans-serif; margin: 0; padding: 20px 10px;">
    <div style="max-width: 720px; margin: 0 auto; background-color: #ffffff; padding: 32px 24px; border-radius: 8px; border: 1px solid #cbd5e1; box-shadow: 0 2px 8px rgba(0,0,0,0.05);">
        {str(soup)}
    </div>
</body>
</html>"""
        return full_html

    def send_email_report(self, md_content: str, md_filepath: str = "") -> bool:
        if not self.smtp_email or not self.smtp_password:
            logger.warning("⚠️ SMTP email or password not configured in .env. Skipping email sending.")
            return False

        subject = f"🎯 [VagaJuniorFinder] Relatório Diário de Vagas — AI & Data Science"
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
