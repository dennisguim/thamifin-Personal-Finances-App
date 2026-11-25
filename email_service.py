import smtplib
import os
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

ADMIN_NOTIFICATION_EMAIL = "drinaldim@gmail.com"

def send_confirmation_code(user_name: str, user_email: str, code: str) -> dict:
    """
    Envia o código de confirmação para o email drinaldim@gmail.com
    para liberação do novo acesso na plataforma.
    """
    recipient = ADMIN_NOTIFICATION_EMAIL
    subject = f"[ThamiFin] Código de Confirmação para Novo Usuário: {code}"
    
    body_text = f"""Olá!

Uma nova solicitação de criação de conta foi realizada na plataforma ThamiFin:

- Nome do Solicitante: {user_name}
- Email da Nova Conta: {user_email}
- Código de Confirmação: {code}

Para autorizar a criação da conta, informe o código acima ao solicitante.
Este código expira em 15 minutos.

Atenciosamente,
Equipe ThamiFin
"""

    body_html = f"""
    <div style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; background-color: #f6f8fb; padding: 24px; color: #0f172a;">
        <div style="max-width: 520px; margin: 0 auto; background: #ffffff; border-radius: 16px; border: 1px solid #e2e8f0; padding: 32px; box-shadow: 0 4px 12px rgba(0,0,0,0.05);">
            <div style="display: flex; align-items: center; gap: 8px; margin-bottom: 20px;">
                <h2 style="color: #48b9c7; margin: 0; font-size: 24px;">ThamiFin</h2>
            </div>
            <h3 style="margin-top: 0; color: #0f172a; font-size: 18px;">Solicitação de Novo Acesso</h3>
            <p style="color: #475569; font-size: 14px; line-height: 1.6;">
                Um novo usuário solicitou a criação de acesso na plataforma ThamiFin:
            </p>
            <div style="background-color: #f1f5f9; border-radius: 12px; padding: 16px; margin: 20px 0;">
                <p style="margin: 4px 0; font-size: 14px;"><b>Nome:</b> {user_name}</p>
                <p style="margin: 4px 0; font-size: 14px;"><b>Email:</b> {user_email}</p>
            </div>
            <p style="color: #475569; font-size: 14px;">Código de autorização para liberar o acesso:</p>
            <div style="text-align: center; margin: 24px 0;">
                <span style="display: inline-block; background: #e0f7fa; color: #008080; border: 2px dashed #48b9c7; font-size: 32px; font-weight: 700; letter-spacing: 6px; padding: 12px 28px; border-radius: 12px;">
                    {code}
                </span>
            </div>
            <p style="color: #64748b; font-size: 12px; text-align: center;">
                Este código expira em 15 minutos.
            </p>
        </div>
    </div>
    """

    print("\n" + "=" * 65)
    print(f"📧 [THAMIFIN] CÓDIGO DE CONFIRMAÇÃO DE ACESSO ENVIADO:")
    print(f"Destinatário: {recipient}")
    print(f"Código Gerado: {code}")
    print(f"Solicitante: {user_name} ({user_email})")
    print("=" * 65 + "\n")

    smtp_host = os.getenv("SMTP_HOST", "smtp.gmail.com")
    smtp_port = int(os.getenv("SMTP_PORT", "587"))
    smtp_user = os.getenv("SMTP_USER", "")
    smtp_pass = os.getenv("SMTP_PASSWORD", "")
    smtp_from = os.getenv("SMTP_FROM", smtp_user or "noreply@thamifin.com")

    if smtp_user and smtp_pass:
        try:
            msg = MIMEMultipart("alternative")
            msg["From"] = smtp_from
            msg["To"] = recipient
            msg["Subject"] = subject
            msg.attach(MIMEText(body_text, "plain", "utf-8"))
            msg.attach(MIMEText(body_html, "html", "utf-8"))

            with smtplib.SMTP(smtp_host, smtp_port, timeout=10) as server:
                server.starttls()
                server.login(smtp_user, smtp_pass)
                server.send_message(msg)
            print(f"E-mail enviado com sucesso via SMTP para {recipient}!")
            return {"sent": True, "method": "smtp", "recipient": recipient}
        except Exception as e:
            print(f"Aviso de Envio: Falha ao enviar via servidor SMTP ({e}). O código está registrado no console do servidor.")
            return {"sent": False, "method": "console_fallback", "recipient": recipient, "error": str(e)}
    else:
        return {"sent": True, "method": "console_log", "recipient": recipient}
