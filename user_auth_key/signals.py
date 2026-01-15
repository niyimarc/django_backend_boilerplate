import secrets
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.contrib.auth.models import User
from .models import UserKeyPair, KeyRegenerationLog

@receiver(post_save, sender=User)
def create_user_key_pair(sender, instance, created, **kwargs):
    if created:
        private_key = f"private_{secrets.token_hex(32)}"
        UserKeyPair.objects.create(user=instance, private_key=private_key)

@receiver(post_save, sender=UserKeyPair)
def log_key_regeneration(sender, instance, created, **kwargs):
    # Log regeneration only when the private key changes (not on initial create).
    if not created:  # avoid logging the initial key at user creation
        KeyRegenerationLog.objects.create(user=instance.user)