ROLE_CHOICES = [
        ('viewer', 'Viewer'),
        ('editor', 'Editor'),
        ('admin', 'Admin'),
    ]

# Define role hierarchy (higher roles inherit lower roles)
ROLE_HIERARCHY = {
    "viewer": ["viewer"],
    "editor": ["editor", "viewer"],
    "admin": ["admin", "editor", "viewer"],
}

ACCESS_STATUS_CHOICES = [
    ("pending", "Pending"),
    ("active", "Active"),
    ("revoked", "Revoked"),
    ("expired", "Expired"),
]
