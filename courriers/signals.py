# courriers/signals.py
from django.db.models.signals import post_save
from django.dispatch import receiver
from courriers.models import Courrier
from ia.tasks import process_courrier_automatique

# @receiver(post_save, sender=Courrier)
# def trigger_ia_workflow(sender, instance, created, **kwargs):
#     if created:
#         process_courrier_automatique(instance)


def handle_courrier_created(sender, instance, **kwargs):
    from ia.tasks import process_courrier_automatique
    process_courrier_automatique(instance)
