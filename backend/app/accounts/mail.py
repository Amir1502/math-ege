"""Bounded TLS SMTP delivery. The test transport is injected, never an API mode."""

import smtplib
import ssl
from datetime import datetime
from email.message import EmailMessage
from typing import Protocol

from app.accounts.config import AccountSettings


class MailSender(Protocol):
    def send_login_link(self, email: str, link: str, expires_at: datetime) -> None: ...


class SMTPMailSender:
    def __init__(self, settings: AccountSettings) -> None:
        self.settings = settings

    def send_login_link(self, email: str, link: str, expires_at: datetime) -> None:
        config = self.settings
        message = EmailMessage()
        message["From"] = config.smtp_from
        message["To"] = email
        message["Subject"] = "Вход в ЕГЭ Профиль 2027"
        message.set_content(
            "Откройте ссылку в браузере, где запросили вход, и подтвердите его:\n\n"
            f"{link}\n\nСсылка действует 15 минут и используется один раз. "
            "Если вы не запрашивали вход, проигнорируйте письмо."
        )
        context = ssl.create_default_context()
        if config.smtp_tls == "ssl":
            transport = smtplib.SMTP_SSL(
                config.smtp_host, config.smtp_port, timeout=config.smtp_timeout_seconds,
                context=context,
            )
        else:
            transport = smtplib.SMTP(
                config.smtp_host, config.smtp_port, timeout=config.smtp_timeout_seconds,
            )
        with transport:
            if config.smtp_tls == "starttls":
                transport.ehlo()
                transport.starttls(context=context)
                transport.ehlo()
            transport.login(config.smtp_username, config.smtp_password)
            transport.send_message(message, from_addr=config.smtp_from, to_addrs=[email])
