"""
邮差精灵 (IMAP/SMTP)
"""
import re
from html.parser import HTMLParser
from fr_cli.lang.i18n import T

class _HTMLTextExtractor(HTMLParser):
    """将 HTML 提取为纯文本 —— 去除标签，保留换行"""
    def __init__(self):
        super().__init__()
        self.text = []
        self.skip_tags = {"script", "style", "head", "title", "meta", "link"}
        self._skip_depth = 0

    def handle_starttag(self, tag, attrs):
        if tag in self.skip_tags:
            self._skip_depth += 1
        elif tag in ("br", "p", "div", "h1", "h2", "h3", "h4", "h5", "h6", "li", "tr"):
            self.text.append("\n")

    def handle_endtag(self, tag):
        if tag in self.skip_tags:
            self._skip_depth = max(0, self._skip_depth - 1)
        elif tag in ("p", "div", "h1", "h2", "h3", "h4", "h5", "h6", "li", "tr", "td"):
            self.text.append("\n")

    def handle_data(self, data):
        if self._skip_depth == 0:
            self.text.append(data)

    def get_text(self):
        raw = "".join(self.text)
        # 合并多个连续换行
        return re.sub(r"\n{3,}", "\n\n", raw).strip()


def _html_to_text(html):
    """HTML → 纯文本"""
    try:
        parser = _HTMLTextExtractor()
        parser.feed(html)
        return parser.get_text()
    except Exception:
        # 兜底：正则去标签
        return re.sub(r"<[^>]+>", "", html).strip()

class MailClient:
    def __init__(self, cfg):
        self.imap_server = cfg.get("imap_server", "")
        self.smtp_server = cfg.get("smtp_server", "")
        self.email = cfg.get("email", "")
        self.password = cfg.get("password", "")
        self.connected = False
        
        # 尝试连接（可选依赖检查）
        try:
            import imaplib
            import smtplib
            import email
            from email.mime.text import MIMEText
            from email.mime.multipart import MIMEMultipart
            from email.header import decode_header
            self.imap = imaplib
            self.smtp = smtplib
            self.email_module = email
            self.mime_text = MIMEText
            self.mime_multipart = MIMEMultipart
            self.decode_header = decode_header
            self.connected = True
        except ImportError:
            self.connected = False

    def inbox(self, lang):
        """获取收件箱列表"""
        if not self.connected:
            return None, T("mail_no_cfg", lang)
        if not self.imap_server or not self.email or not self.password:
            return None, T("mail_no_cfg", lang)
        
        try:
            mail = self.imap.IMAP4_SSL(self.imap_server)
            mail.login(self.email, self.password)
            mail.select('inbox')
            
            _, data = mail.search(None, 'ALL')
            mail_ids = data[0].split()
            
            mails = []
            for mail_id in mail_ids[-10:]:  # 只取最近10封
                _, msg_data = mail.fetch(mail_id, '(RFC822)')
                raw_email = msg_data[0][1]
                email_message = self.email_module.message_from_bytes(raw_email)
                
                subject = ""
                for part in self.decode_header(email_message['Subject']):
                    if isinstance(part[0], bytes):
                        subject += part[0].decode(part[1] or 'utf-8', errors='ignore')
                    else:
                        subject += part[0]
                
                from_addr = email_message['From'] or "Unknown"
                
                mails.append({
                    "id": mail_id.decode(),
                    "sub": subject[:50],
                    "from": from_addr[:30]
                })
            
            mail.close()
            mail.logout()
            return mails, None
        except Exception as e:
            return None, f"{T('mail_err', lang)} {e}"

    def read(self, mail_id, lang):
        """读取指定邮件"""
        if not self.connected:
            return None, T("mail_no_cfg", lang)
        
        try:
            mail = self.imap.IMAP4_SSL(self.imap_server)
            mail.login(self.email, self.password)
            mail.select('inbox')
            
            _, msg_data = mail.fetch(mail_id, '(RFC822)')
            raw_email = msg_data[0][1]
            email_message = self.email_module.message_from_bytes(raw_email)
            
            subject = ""
            for part in self.decode_header(email_message['Subject']):
                if isinstance(part[0], bytes):
                    subject += part[0].decode(part[1] or 'utf-8', errors='ignore')
                else:
                    subject += part[0]
            
            from_addr = email_message['From'] or "Unknown"
            date = email_message['Date'] or ""
            
            body = ""
            html_body = ""
            if email_message.is_multipart():
                for part in email_message.walk():
                    ctype = part.get_content_type()
                    if ctype == "text/plain":
                        try:
                            body = part.get_payload(decode=True).decode('utf-8', errors='ignore')
                        except Exception:
                            body = str(part.get_payload())
                        break
                    elif ctype == "text/html" and not html_body:
                        try:
                            html_body = part.get_payload(decode=True).decode('utf-8', errors='ignore')
                        except Exception:
                            html_body = str(part.get_payload())
                # 如果没有纯文本，从 HTML 中提取
                if not body and html_body:
                    body = _html_to_text(html_body)
            else:
                ctype = email_message.get_content_type()
                try:
                    raw = email_message.get_payload(decode=True).decode('utf-8', errors='ignore')
                except Exception:
                    raw = str(email_message.get_payload())
                if ctype == "text/html":
                    body = _html_to_text(raw)
                else:
                    body = raw
            
            mail.close()
            mail.logout()
            
            return {
                "sub": subject,
                "from": from_addr,
                "date": date,
                "body": body
            }, None
        except Exception as e:
            return None, f"{T('mail_err', lang)} {e}"

    def send(self, to, subject, body, lang):
        """发送邮件"""
        if not self.connected:
            return False, T("mail_no_cfg", lang)
        if not self.smtp_server or not self.email or not self.password:
            return False, T("mail_no_cfg", lang)

        # 安全校验：防止邮件头注入
        import email.utils
        if '\n' in to or '\r' in to or '\n' in subject or '\r' in subject:
            return False, "❌ 邮件地址或主题包含非法字符"
        parsed = email.utils.parseaddr(to)
        if not parsed[1] or '@' not in parsed[1]:
            return False, "❌ 收件人地址格式无效"

        try:
            msg = self.mime_multipart()
            msg['From'] = self.email
            msg['To'] = to
            msg['Subject'] = subject

            msg.attach(self.mime_text(body, 'plain', 'utf-8'))

            server = self.smtp.SMTP_SSL(self.smtp_server, 465)
            server.login(self.email, self.password)
            server.send_message(msg)
            server.quit()

            return True, None
        except Exception as e:
            return False, f"{T('mail_err', lang)} {e}"