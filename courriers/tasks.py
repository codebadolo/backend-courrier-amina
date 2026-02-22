# courriers/tasks.py
from celery import shared_task
from django.core.mail import send_mail
from django.utils import timezone
from django.db.models import Q
from .models import Courrier, IAResult
from .services.ocr_service import OCRService
from .services.classification_service import ClassificationService


@shared_task
def process_courrier_async(courrier_id):
    """Traitement asynchrone d'un courrier"""
    try:
        courrier = Courrier.objects.get(id=courrier_id)
        
        # OCR
        ocr_service = OCRService()
        text = ocr_service.extract_text(courrier)
        
        # Classification IA
        ia_service = ClassificationService()
        predictions = ia_service.predict_all(text)
        
        # Mise à jour
        courrier.contenu_texte = text
        courrier.save()
        
        # Créer résultat IA
        IAResult.objects.create(
            courrier=courrier,
            texte_extrait=text,
            categorie_predite=predictions.get('category'),
            service_suggere=predictions.get('service'),
            fiabilite=predictions.get('confidence', 0.0)
        )
        
        return f"Courrier {courrier_id} traité avec succès"
        
    except Courrier.DoesNotExist:
        return f"Courrier {courrier_id} non trouvé"
    except Exception as e:
        return f"Erreur lors du traitement du courrier {courrier_id}: {str(e)}"


@shared_task
def send_notifications():
    """Envoi des notifications de rappel"""
    courriers_en_retard = Courrier.objects.filter(
        statut='traitement',
        date_echeance__lt=timezone.now()
    ).exclude(
        Q(responsable_actuel__isnull=True) | Q(responsable_actuel__email='')
    )
    
    notifications_sent = 0
    for courrier in courriers_en_retard:
        try:
            if courrier.responsable_actuel and courrier.responsable_actuel.email:
                send_mail(
                    subject=f"Courrier en retard: {courrier.reference}",
                    message=f"Le courrier '{courrier.objet}' est en retard depuis le {courrier.date_echeance}.",
                    from_email='system@entreprise.com',
                    recipient_list=[courrier.responsable_actuel.email],
                    fail_silently=True,
                )
                notifications_sent += 1
        except Exception as e:
            print(f"Erreur envoi notification pour courrier {courrier.id}: {e}")
    
    return f"{notifications_sent} notifications envoyées"


@shared_task
def process_batch_courriers(courrier_ids):
    """Traite plusieurs courriers en batch"""
    results = []
    for courrier_id in courrier_ids:
        result = process_courrier_async.delay(courrier_id)
        results.append(result)
    return results


@shared_task
def daily_maintenance():
    """Tâches de maintenance quotidienne"""
    # 1. Nettoyage des anciens fichiers temporaires
    # 2. Archivage automatique des courriers clos
    # 3. Mise à jour des statistiques
    # 4. Backup des données
    from datetime import timedelta
    from django.utils import timezone
    
    # Exemple: Archiver les courriers clos depuis plus de 30 jours
    date_limite = timezone.now() - timedelta(days=30)
    courriers_a_archiver = Courrier.objects.filter(
        statut='repondu',
        date_cloture__lt=date_limite,
        archived=False
    )
    
    for courrier in courriers_a_archiver:
        courrier.archived = True
        courrier.date_archivage = timezone.now()
        courrier.save()
    
    return f"{courriers_a_archiver.count()} courriers archivés"