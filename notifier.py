import os
import smtplib
import logging
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
import markdown

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger("Notifier")

HTML_TEMPLATE = """<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
    body {{
        font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
        background-color: #0f172a;
        color: #e2e8f0;
        margin: 0;
        padding: 20px;
        line-height: 1.6;
    }}
    .container {{
        max-width: 800px;
        margin: 0 auto;
        background: #1e293b;
        padding: 30px;
        border-radius: 12px;
        box-shadow: 0 10px 25px rgba(0,0,0,0.5);
        border: 1px solid #334155;
    }}
    h1 {{
        color: #38bdf8;
        font-size: 24px;
        border-bottom: 2px solid #334155;
        padding-bottom: 10px;
    }}
    h2 {{
        color: #f43f5e;
        font-size: 20px;
        margin-top: 25px;
    }}
    h3 {{
        color: #fbbf24;
        font-size: 18px;
        margin-bottom: 5px;
    }}
    a {{
        color: #38bdf8;
        text-decoration: none;
    }}
    a:hover {{
        text-decoration: underline;
    }}
    code {{
        background-color: #0f172a;
        color: #a5f3fc;
        padding: 2px 6px;
        border-radius: 4px;
        font-size: 13px;
    }}
    blockquote {{
        background: #0f172a;
        border-left: 4px solid #38bdf8;
        margin: 10px 0;
        padding: 10px 15px;
        color: #94a3b8;
        font-style: italic;
    }}
    hr {{
        border: 0;
        height: 1px;
        background: #334155;
        margin: 20px 0;
    }}
    ul {{
        padding-left: 20px;
    }}
    li {{
        margin-bottom: 6px;
    }}
    .footer {{
        font-size: 12px;
        color: #64748b;
        text-align: center;
        margin-top: 30px;
    }}
</style>
</head>
<body>
<div class="container">
    {content}
</div>
</body>
</html>
"""

class EmailNotifier:
    def __init__(self, smtp_server: str, smtp_port: int, smtp_email: str, smtp_password: str, receiver_email: str):
        self.smtp_server = smtp_server
        self.smtp_port = smtp_port
        self.smtp_email = smtp_email
        self.smtp_password = smtp_password
        self.receiver_email = receiver_email

    def markdown_to_html(self, md_text: str) -> str:
        html_body = markdown.markdown(md_text, extensions=['fenced_code', 'tables', 'nl2br'])
        return HTML_TEMPLATE.format(content=html_body)

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
