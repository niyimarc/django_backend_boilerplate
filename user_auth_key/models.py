import secrets
import hashlib
from django.db import models
from django.contrib.auth.models import User
from .constants import ACTION_CHOICES

class KeyRegenerationLog(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    timestamp = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Key regeneration for {self.user.username} at {self.timestamp}"

class UserKeyPair(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='key_pair')
    private_key = models.CharField(max_length=128, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    revoked = models.BooleanField(default=False)

    @property
    def public_key(self):
        """
        One-way deterministic conversion from private key
        """
        hash_bytes = hashlib.sha256(self.private_key.encode()).hexdigest()
        return f"public_{hash_bytes}"
    
    
    @property
    def masked_private_key(self):
        prefix = "private_"
        if self.private_key.startswith(prefix):
            visible_part = self.private_key[len(prefix):len(prefix)+6]  # take next 6 chars
            return f"{prefix}{visible_part}{'*'*10}{self.private_key[-4:]}"
        return f"{self.private_key[:6]}{'*'*10}{self.private_key[-4:]}"

    
    def regenerate_keys(self, limit=3, period_hours=24):
        from .utils import too_many_regenerations

        exceeded, message = too_many_regenerations(self.user)
        if exceeded:
            raise ValueError(message)

        # Otherwise regenerate
        self.private_key = f"private_{secrets.token_hex(32)}"
        self.revoked = False
        self.save()
        return self.public_key

    
    def show_private_key(self):
        """Return the full private key (e.g., when user explicitly requests it)."""
        return self.private_key
    
class PrivateKeyAccessLog(models.Model):
    user = models.ForeignKey("auth.User", on_delete=models.CASCADE)
    success = models.BooleanField(default=False)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True)
    action = models.CharField(max_length=50, choices=ACTION_CHOICES)
    timestamp = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.user} - {self.action} - {'Success' if self.success else 'Failed'}"
