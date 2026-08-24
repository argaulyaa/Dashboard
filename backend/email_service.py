from __future__ import annotations

import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText


def _smtp_config() -> dict | None:
    host = os.environ.get('SMTP_HOST', '').strip()
    if not host:
        return None
    return {
        'host': host,
        'port': int(os.environ.get('SMTP_PORT', '587')),
        'user': os.environ.get('SMTP_USER', ''),
        'password': os.environ.get('SMTP_PASSWORD', ''),
        'from': os.environ.get('SMTP_FROM', '') or os.environ.get('SMTP_USER', 'no-reply@oran-dashboard.local'),
    }


def send_verification_email(to_email: str, otp_code: str, username: str = '') -> bool:
    """Kirim OTP via SMTP. FAIL-CLOSED: kalau SMTP tidak dikonfigurasi atau
    pengiriman gagal, raise RuntimeError('email_service_unavailable') — OTP
    TIDAK PERNAH dicetak/di-log dalam bentuk apa pun. Return True hanya jika
    email benar-benar terkirim."""
    cfg = _smtp_config()
    if cfg is None:
        # SMTP belum dikonfigurasi -> jangan pernah cetak OTP ke log.
        raise RuntimeError('email_service_unavailable')
    subject = 'Your O-RAN Dashboard Verification Code'
    body_html = f'''
    <div style="font-family: sans-serif; max-width: 480px; margin: auto;">
      <h2 style="color: #1a1a2e;">O-RAN Control Panel</h2>
      <p>Hello{' <strong>' + username + '</strong>' if username else ''},</p>
      <p>Your account verification code is:</p>
      <div style="background: #f0f4ff; border-radius: 8px; padding: 20px; text-align: center; margin: 20px 0;">
        <span style="font-size: 36px; font-weight: bold; letter-spacing: 10px; color: #2563eb;">{otp_code}</span>
      </div>
      <p style="color: #6b7280; font-size: 13px;">
        This code is valid for <strong>10 minutes</strong>.<br>
        If you did not request this, please ignore this email.
      </p>
    </div>'''
    body_plain = f'Your O-RAN Dashboard verification code is: {otp_code}\nValid for 10 minutes.'
    msg = MIMEMultipart('alternative')
    msg['Subject'] = subject
    msg['From'] = cfg['from']
    msg['To'] = to_email
    msg.attach(MIMEText(body_plain, 'plain'))
    msg.attach(MIMEText(body_html, 'html'))
    try:
        with smtplib.SMTP(cfg['host'], cfg['port'], timeout=10) as server:
            server.ehlo()
            server.starttls()
            if cfg['user'] and cfg['password']:
                server.login(cfg['user'], cfg['password'])
            server.sendmail(cfg['from'], [to_email], msg.as_string())
        return True
    except Exception:
        # Gagal kirim -> fail-closed, jangan pernah cetak OTP ke log.
        raise RuntimeError('email_service_unavailable') from None


def send_password_reset_email(to_email: str, otp_code: str, username: str = '') -> bool:
    """Kirim OTP reset password via SMTP. Sama fail-closed dgn
    send_verification_email: SMTP tidak siap / gagal kirim ->
    RuntimeError('email_service_unavailable'), OTP tidak pernah dicetak ke log.
    Return True hanya jika email benar-benar terkirim."""
    cfg = _smtp_config()
    if cfg is None:
        raise RuntimeError('email_service_unavailable')
    subject = 'Your O-RAN Dashboard Password Reset Code'
    body_html = f'''
    <div style="font-family: sans-serif; max-width: 480px; margin: auto;">
      <h2 style="color: #1a1a2e;">O-RAN Control Panel</h2>
      <p>Hello{' <strong>' + username + '</strong>' if username else ''},</p>
      <p>We received a request to reset your password. Your password reset code is:</p>
      <div style="background: #f0f4ff; border-radius: 8px; padding: 20px; text-align: center; margin: 20px 0;">
        <span style="font-size: 36px; font-weight: bold; letter-spacing: 10px; color: #2563eb;">{otp_code}</span>
      </div>
      <p style="color: #6b7280; font-size: 13px;">
        This code is valid for <strong>10 minutes</strong> and can be used once.<br>
        If you did not request a password reset, you can safely ignore this email —
        your password will not change.
      </p>
    </div>'''
    body_plain = (
        f'We received a request to reset your O-RAN Dashboard password.\n'
        f'Your password reset code is: {otp_code}\n'
        f'Valid for 10 minutes. If you did not request this, ignore this email.'
    )
    msg = MIMEMultipart('alternative')
    msg['Subject'] = subject
    msg['From'] = cfg['from']
    msg['To'] = to_email
    msg.attach(MIMEText(body_plain, 'plain'))
    msg.attach(MIMEText(body_html, 'html'))
    try:
        with smtplib.SMTP(cfg['host'], cfg['port'], timeout=10) as server:
            server.ehlo()
            server.starttls()
            if cfg['user'] and cfg['password']:
                server.login(cfg['user'], cfg['password'])
            server.sendmail(cfg['from'], [to_email], msg.as_string())
        return True
    except Exception:
        # Gagal kirim -> fail-closed, jangan pernah cetak OTP ke log.
        raise RuntimeError('email_service_unavailable') from None
