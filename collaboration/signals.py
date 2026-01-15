from django.db.models.signals import pre_save, post_save, post_delete
from django.dispatch import receiver
from django.contrib.contenttypes.models import ContentType
from .models import ActivityLog


@receiver(pre_save)
def capture_old_values(sender, instance, **kwargs):
    """
    Temporarily attach old values to instance before save.
    """
    if not hasattr(instance, "user"):
        return
    if not instance.pk:
        return  # New object

    try:
        old_instance = sender.objects.get(pk=instance.pk)
        instance._old_values = {
            f.name: getattr(old_instance, f.name)
            for f in instance._meta.fields
        }
    except sender.DoesNotExist:
        pass


@receiver(post_save)
def track_save_action(sender, instance, created, **kwargs):
    """
    Create ActivityLog automatically after model save.
    """
    if not hasattr(instance, "user"):
        return
    if sender.__name__ in ["ActivityLog", "AccountAccess", "Invitation"]:
        return  # Avoid recursion

    actor = getattr(instance, "_actor", None)
    if not actor:
        return

    # Compute diff for updates
    diff = {}
    if not created and hasattr(instance, "_old_values"):
        for field in instance._meta.fields:
            name = field.name
            old_val = instance._old_values.get(name)
            new_val = getattr(instance, name)
            if old_val != new_val:
                diff[name] = [old_val, new_val]

    ActivityLog.objects.create(
        owner=instance.owner,
        actor=actor,
        action="created" if created else "updated",
        content_type=ContentType.objects.get_for_model(sender),
        object_id=instance.pk,
        changes=diff or {},
    )


@receiver(post_delete)
def track_delete_action(sender, instance, **kwargs):
    """
    Track deletions.
    """
    if not hasattr(instance, "user"):
        return
    if sender.__name__ in ["ActivityLog", "AccountAccess", "Invitation"]:
        return

    actor = getattr(instance, "_actor", None)
    if not actor:
        return

    ActivityLog.objects.create(
        owner=instance.owner,
        actor=actor,
        action="deleted",
        content_type=ContentType.objects.get_for_model(sender),
        object_id=instance.pk,
        changes=None,
    )
