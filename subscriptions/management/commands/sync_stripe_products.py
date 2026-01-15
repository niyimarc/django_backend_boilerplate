from django.core.management.base import BaseCommand
from subscriptions.models import Plan
from subscriptions.payment_gateway.sync_stripe import ensure_product_for_plan

class Command(BaseCommand):
    help = "Sync all local Plan objects with Stripe Products via the Stripe gateway."

    def handle(self, *args, **options):
        synced = 0
        reactivated = 0

        for plan in Plan.objects.all():
            self.stdout.write(f"→ Syncing plan: {plan.slug}")
            try:
                product_id = ensure_product_for_plan(plan)
                synced += 1
            except Exception as e:
                self.stderr.write(self.style.ERROR(f"Failed to sync plan '{plan.slug}': {e}"))

        self.stdout.write(self.style.SUCCESS(f"\n✅ Sync complete: {synced} plans processed."))

# run with this command 
# python manage.py sync_stripe_products
