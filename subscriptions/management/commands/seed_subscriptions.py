from django.core.management.base import BaseCommand, CommandError
from django.utils.text import slugify
from pathlib import Path
import json
try:
    import yaml
except Exception:
    yaml = None

from subscriptions.models import Plan, PlanPrice, Entitlement

class Command(BaseCommand):
    help = "Seed plans, prices, and entitlements from a JSON or YAML file"

    def add_arguments(self, parser):
        parser.add_argument("file_path", type=str, help="Path to JSON/YAML config")

    def handle(self, *args, **opts):
        p = Path(opts["file_path"])
        if not p.exists():
            raise CommandError(f"File not found: {p}")

        if p.suffix.lower() in [".yaml", ".yml"]:
            if not yaml:
                raise CommandError("pyyaml not installed; use JSON or `pip install pyyaml`.")
            data = yaml.safe_load(p.read_text(encoding="utf-8"))
        else:
            data = json.loads(p.read_text(encoding="utf-8"))

        for cfg in data:
            slug = cfg.get("slug") or slugify(cfg["name"])
            plan, _ = Plan.objects.update_or_create(
                slug=slug,
                defaults={
                    "name": cfg["name"],
                    "description": cfg.get("description", ""),
                    "interval": cfg.get("interval", "monthly"),
                    "is_active": cfg.get("is_active", True),
                    "sort_order": cfg.get("sort_order", 0),
                    "metadata": cfg.get("metadata", None),
                },
            )

            # Prices
            prices = cfg.get("prices", [])
            for pr in prices:
                PlanPrice.objects.update_or_create(
                    plan=plan,
                    currency=pr["currency"],
                    defaults={
                        "amount": pr["amount"],
                        "is_default": bool(pr.get("is_default", False)),
                    },
                )

            # Entitlements
            ents = cfg.get("entitlements", [])
            for ent in ents:
                Entitlement.objects.update_or_create(
                    plan=plan,
                    key=ent["key"],
                    defaults={
                        "enabled": bool(ent.get("enabled", False)),
                        "limit_int": ent.get("limit_int"),
                        "limit_str": ent.get("limit_str"),
                        "note": ent.get("note", ""),
                    },
                )

        self.stdout.write(self.style.SUCCESS("Seeded subscriptions data."))


# Run the seeder:

# python manage.py seed_subscriptions config/pricing/plans.prod.json


# If you use YAML:

# python manage.py seed_subscriptions config/pricing/plans.yaml
# Requires pyyaml; if missing, install: pip install pyyaml