# -*- coding: utf-8 -*-
"""
LifeOS Cloud Mailer Engine
===========================
Поддерживает:
1. Стандартный SMTP (Яндекс, Gmail, Mail.ru, Brevo, SendGrid и др.)
2. Resend API (HTTP) если передан RESEND_API_KEY
3. Dev/Safe Mode: если почта еще не подключена, выводит код в консоль сервера,
   чтобы тестирование регистрации и сброса паролей никогда не блокировалось.
"""
import os
import smtplib
import urllib.request
import json
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

SMTP_HOST = os.environ.get("SMTP_HOST", "").strip()
SMTP_PORT = int(os.environ.get("SMTP_PORT", 465))
SMTP_USER = os.environ.get("SMTP_USER", "").strip()
SMTP_PASS = os.environ.get("SMTP_PASS", "").strip()
SMTP_FROM = os.environ.get("SMTP_FROM", "").strip() or SMTP_USER or "LifeOS Cloud <no-reply@lifeos.app>"
RESEND_API_KEY = os.environ.get("RESEND_API_KEY", "").strip()

def render_html_email(title: str, code: str, subtitle: str, instruction: str) -> str:
    """Generates an AuraGlass dark neon HTML email template."""
    return f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{title}</title>
</head>
<body style="margin: 0; padding: 0; background-color: #060d13; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; color: #e2e8f0;">
  <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="background-color: #060d13; padding: 40px 15px;">
    <tr>
      <td align="center">
        <table role="presentation" width="100%" style="max-width: 520px; background: radial-gradient(circle at 50% 20%, #0d222e 0%, #060d13 100%); border: 1px solid rgba(0, 255, 136, 0.35); border-radius: 20px; box-shadow: 0 20px 60px rgba(0,0,0,0.8), 0 0 35px rgba(0,255,136,0.12); padding: 36px 30px; text-align: center;">
          <!-- Logo Badge -->
          <tr>
            <td align="center" style="padding-bottom: 20px;">
              <div style="display: inline-block; width: 56px; height: 56px; line-height: 56px; border-radius: 16px; background: rgba(0,255,136,0.12); border: 1px solid rgba(0,255,136,0.4); box-shadow: 0 0 25px rgba(0,255,136,0.25); text-align: center; font-size: 26px;">
                ⚡
              </div>
            </td>
          </tr>
          <!-- Header -->
          <tr>
            <td align="center">
              <span style="font-family: monospace; font-size: 11px; font-weight: 800; color: #00ff88; letter-spacing: 2.5px; text-transform: uppercase;">LIFE OS · CLOUD AUTH</span>
              <h1 style="color: #ffffff; font-size: 24px; font-weight: 800; margin: 8px 0 10px 0;">{title}</h1>
              <p style="color: #94a3b8; font-size: 14px; line-height: 1.5; margin: 0 0 24px 0;">{subtitle}</p>
            </td>
          </tr>
          <!-- OTP Code Box -->
          <tr>
            <td align="center" style="padding: 10px 0 25px 0;">
              <div style="display: inline-block; background: rgba(0, 0, 0, 0.55); border: 1px solid rgba(0, 255, 136, 0.5); border-radius: 14px; padding: 16px 28px; box-shadow: 0 0 30px rgba(0,255,136,0.18);">
                <span style="font-family: monospace; font-size: 34px; font-weight: 900; letter-spacing: 9px; color: #00ff88;">{code}</span>
              </div>
            </td>
          </tr>
          <!-- Instructions -->
          <tr>
            <td align="center">
              <p style="color: #cbd5e1; font-size: 13px; line-height: 1.6; margin: 0 0 20px 0;">
                {instruction}
              </p>
              <div style="border-top: 1px solid rgba(255,255,255,0.08); padding-top: 18px; margin-top: 10px;">
                <p style="color: #64748b; font-size: 11.5px; line-height: 1.45; margin: 0;">
                  ⏱ Код действителен в течение <b>15 минут</b>.<br>
                  Если вы не запрашивали данный код, просто проигнорируйте это письмо.
                </p>
              </div>
            </td>
          </tr>
        </table>
      </td>
    </tr>
  </table>
</body>
</html>"""

def send_verification_email(to_email: str, code: str, display_name: str) -> dict:
    title = "Подтверждение регистрации"
    subtitle = f"Здравствуйте, {display_name}! Введите этот 6-значный код в приложении для активации вашего аккаунта LifeOS:"
    instruction = "После ввода кода ваше изолированное пространство будет активировано, и запустится интерактивный тур по всем сферам платформы."
    subject = f"Код подтверждения регистрации: {code}"
    
    html = render_html_email(title, code, subtitle, instruction)
    text = f"Здравствуйте, {display_name}!\n\nВаш код подтверждения регистрации в LifeOS: {code}\nКод действителен 15 минут."
    return send_email(to_email, subject, text, html, code)

def send_password_reset_email(to_email: str, code: str) -> dict:
    title = "Сброс пароля"
    subtitle = "Был получен запрос на восстановление доступа к вашему аккаунту LifeOS Cloud."
    instruction = "Введите этот 6-значный код на странице восстановления и задайте новый надежный пароль."
    subject = f"Код сброса пароля: {code}"
    
    html = render_html_email(title, code, subtitle, instruction)
    text = f"Ваш код для сброса пароля в LifeOS: {code}\nКод действителен 15 минут.\nЕсли вы не запрашивали сброс пароля, проигнорируйте это письмо."
    return send_email(to_email, subject, text, html, code)

def send_email(to_email: str, subject: str, body_text: str, body_html: str, code: str = "") -> dict:
    # 1. Resend API mode
    if RESEND_API_KEY:
        try:
            url = "https://api.resend.com/emails"
            payload = {
                "from": SMTP_FROM or "LifeOS <onboarding@resend.dev>",
                "to": [to_email],
                "subject": subject,
                "html": body_html,
                "text": body_text
            }
            req = urllib.request.Request(
                url,
                data=json.dumps(payload).encode('utf-8'),
                headers={
                    "Authorization": f"Bearer {RESEND_API_KEY}",
                    "Content-Type": "application/json"
                },
                method="POST"
            )
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read().decode('utf-8'))
                print(f"[Mailer:Resend] Email sent to {to_email}: {data}")
                return {"success": True, "provider": "resend", "id": data.get("id")}
        except Exception as e:
            print(f"[Mailer:Resend Error] {e}")

    # 2. Standard SMTP mode
    if SMTP_HOST and SMTP_USER and SMTP_PASS:
        try:
            msg = MIMEMultipart("alternative")
            msg["Subject"] = subject
            msg["From"] = SMTP_FROM
            msg["To"] = to_email
            
            part1 = MIMEText(body_text, "plain", "utf-8")
            part2 = MIMEText(body_html, "html", "utf-8")
            msg.attach(part1)
            msg.attach(part2)

            if SMTP_PORT == 465:
                # SSL
                with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, timeout=15) as server:
                    server.login(SMTP_USER, SMTP_PASS)
                    server.sendmail(SMTP_FROM, [to_email], msg.as_string())
            else:
                # STARTTLS (e.g. 587)
                with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=15) as server:
                    server.starttls()
                    server.login(SMTP_USER, SMTP_PASS)
                    server.sendmail(SMTP_FROM, [to_email], msg.as_string())
                    
            print(f"[Mailer:SMTP] Email sent to {to_email} via {SMTP_HOST}")
            return {"success": True, "provider": "smtp"}
        except Exception as e:
            print(f"[Mailer:SMTP Error] Failed to send to {to_email}: {e}")

    # 3. Dev / Safe Mode fallback
    print("=" * 60)
    print(f"[Mailer:DevMode] To: {to_email} | Subject: {subject}")
    if code:
        print(f"[Mailer:DevMode] >>> 6-DIGIT OTP CODE: {code} <<<")
    print(f"[Mailer:DevMode] Note: Set SMTP_HOST/USER/PASS or RESEND_API_KEY in environment for live email delivery.")
    print("=" * 60)
    return {"success": True, "provider": "dev_mode", "code": code}
