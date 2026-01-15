from django.core.mail import send_mail
from django.conf import settings

business_name = settings.BUSINESS_NAME
business_logo = settings.BUSINESS_LOGO
contact_email = settings.CONTACT_EMAIL
from_email = settings.FROM_EMAIL


def _accept_url(token: str) -> str:
    base = getattr(settings, "FRONTEND_BASE_URL", "http://127.0.0.1:8001").rstrip("/")
    return f"{base}/collaboration/accept/?token={token}"

def send_invitation_email(invitation):
    """
    Send an invitation email with a token link.
    """
    accept_url = _accept_url(str(invitation.token))

    subject = "You have been invited to collaborate!"
    message = f"""
    Hi,

    {invitation.inviter.username} has invited you to collaborate on their account as a {invitation.role}.
    
    Please click the link below to accept:
    {accept_url}

    If you don’t have an account, sign up first then use the link.
    """

    send_mail(
        subject,
        message,
        from_email,
        [invitation.email],
        fail_silently=False,
    )
