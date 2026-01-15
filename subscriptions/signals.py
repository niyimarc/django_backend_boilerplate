from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone
from subscriptions.models import SubscriptionSetting

@receiver(post_save, sender=SubscriptionSetting)
def update_payment_policy_html(sender, instance, **kwargs):
    """
    Automatically generates a full, well-formatted HTML payment policy
    and stores it in SubscriptionSetting.policy_text whenever admin updates settings.
    """

    updated_on = timezone.now().strftime("%B %d, %Y at %I:%M %p")

    def yes_no(flag):
        return "✅ Yes" if flag else "❌ No"

    html = f"""
    <section style="font-family:Arial, sans-serif; line-height:1.6; color:#222;">
        <h2 style="color:#005ea5;">🧾 Subscription & Payment Policy</h2>
        <p><em>Last updated: {updated_on}</em></p>

        <p>This policy explains how subscriptions, upgrades, downgrades, cancellations,
        renewals, and refunds are handled on our platform. It is automatically kept in sync
        with the administrator’s current settings.</p>

        <hr>

        <h3 style="color:#2b8cc4;">🔼 Plan Upgrades</h3>
        {"<p>Users <strong>can upgrade</strong> their plan at any time.</p>" if instance.allow_upgrade else "<p><strong>Plan upgrades are currently disabled.</strong> Please contact support if you wish to change your plan.</p>"}
    """

    if instance.allow_upgrade:
        html += f"""
        <p>When you upgrade, your access to the new plan’s features will take effect
        <strong>{instance.upgrade_effect.replace('_', ' ')}</strong>.
        For example, if you upgrade from <em>Basic</em> to <em>Pro</em> on the 15th,
        you will immediately gain access to all <em>Pro</em> features if the effect is <strong>immediate</strong>,
        or on your next billing date if it is set to <strong>next cycle</strong>.</p>
        """

    html += f"""
        <h3 style="color:#2b8cc4;">🔽 Plan Downgrades</h3>
        {"<p>Users can downgrade their plan.</p>" if instance.allow_downgrade else "<p><strong>Plan downgrades are currently disabled.</strong></p>"}
    """

    if instance.allow_downgrade:
        effect = "immediately" if instance.downgrade_effect == "immediate" else "after the current billing period ends"
        html += f"""
        <p>When you downgrade, your plan will change <strong>{effect}</strong>.
        Example: If you downgrade from <em>Pro</em> to <em>Basic</em> on the 20th and your billing cycle ends on the 30th,
        you’ll remain on <em>Pro</em> until the 30th, then move to <em>Basic</em>.</p>
        """

    html += f"""
        <h3 style="color:#2b8cc4;">❌ Cancellations</h3>
        {"<p>Users can cancel their subscription.</p>" if instance.can_cancel else "<p><strong>Only administrators</strong> can cancel subscriptions currently.</p>"}
    """

    if instance.can_cancel:
        effect = "immediately" if instance.cancel_effect == "immediate" else "after your current billing period ends"
        html += f"""
        <p>When you cancel, your access will end <strong>{effect}</strong>.
        Example: If your billing period ends on January 31 and you cancel on January 20,
        you’ll still have access until January 31.</p>
        """

    html += "<h3 style='color:#2b8cc4;'>💰 Refund Policy</h3>"
    if instance.refund_policy == "none":
        html += "<p><strong>No refunds</strong> are issued once payment is processed. Please review your plan carefully before purchase.</p>"
    elif instance.refund_policy == "partial":
        html += """
        <p><strong>Partial refunds</strong> are issued proportionally for unused time.
        Example: If you paid $30 for 30 days and cancel after 15 days, you may receive a refund for the remaining half.</p>
        """
    elif instance.refund_policy == "full":
        html += """
        <p><strong>Full refunds</strong> are available for cancellations made during your active billing period.
        Example: If you cancel your plan at any time within your billing month, you’ll receive a full refund of your last payment.</p>
        """

    html += f"""
        <h3 style="color:#2b8cc4;">🔁 Automatic Renewal</h3>
        {"<p>Your subscription will automatically renew using your saved payment method. Cancel before renewal to avoid charges.</p>" if instance.auto_charge_on_renewal else "<p>Your subscription will not renew automatically. You’ll need to manually renew it when it expires.</p>"}

        <h3 style="color:#2b8cc4;">💳 Payment Gateway</h3>
        <p>All payments are securely processed via <strong>{instance.default_provider.title()}</strong>.
        We do not store your card details. If your card expires or is replaced, you can update your payment method in your account settings.</p>

        <h3 style="color:#2b8cc4;">🆓 Free Plan Usage</h3>
        {"<p>Each user can use the <strong>Free Plan</strong> only once.</p>" if not instance.allow_free_plan_reuse else "<p>You can switch back to the <strong>Free Plan</strong> anytime if available.</p>"}

        <hr>
        <p>For further assistance, contact our support team. This policy is automatically generated to reflect the current system configuration.</p>
    </section>
    """
    sender.objects.filter(pk=instance.pk).update(policy_text=html)

    # print("[Subscription Policy Updated] HTML policy regenerated successfully.")