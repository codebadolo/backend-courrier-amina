import logging
from django.core.mail import send_mail
from django.conf import settings

logger = logging.getLogger(__name__)

def send_accuse_reception_email(courrier):
    """
    Envoie un accusé de réception par email à l'expéditeur
    """
    try:
        if not courrier.expediteur_email:
            logger.warning("Pas d'email expéditeur pour l'accusé de réception")
            return False
        
        subject = f"Accusé de réception - Courrier {courrier.reference}"
        
        message = f"""
        Madame, Monsieur,
        
        Nous accusons réception de votre courrier qui nous est parvenu le {courrier.date_reception}.
        
        Détails du courrier :
        - Référence : {courrier.reference}
        - Objet : {courrier.objet}
        - Date de réception : {courrier.date_reception}
        
        Votre courrier a été enregistré dans notre système de gestion et sera traité 
        par le service compétent dans les meilleurs délais.
        
        Vous serez informé(e) de l'avancement du traitement.
        
        Cordialement,
        Le Service de Gestion du Courrier
        {settings.COMPANY_NAME if hasattr(settings, 'COMPANY_NAME') else 'Votre Organisation'}
        """
        
        # Envoi de l'email
        send_mail(
            subject=subject,
            message=message.strip(),
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[courrier.expediteur_email],
            fail_silently=False,
        )
        
        logger.info(f"Accusé de réception envoyé à {courrier.expediteur_email}")
        return True
        
    except Exception as e:
        logger.error(f"Erreur envoi accusé de réception: {e}")
        return False