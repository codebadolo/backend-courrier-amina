import logging
from datetime import timedelta
from django.utils import timezone
from django.db import transaction
from courriers.models import (
    TraitementStatus, TraitementEtape, ValidationCourrier
)
from core.models import Service
from users.models import User

logger = logging.getLogger(__name__)


class TraitementCourrierService:
    """Service pour la gestion du traitement des courriers"""
    
    @staticmethod
    def creer_workflow_validation(courrier):
        """
        Crée un workflow de validation automatique basé sur le type et le service
        """
        try:
            from courriers.models_traitement import WorkflowValidation
            
            # Chercher un workflow existant
            workflow = WorkflowValidation.objects.filter(
                type_courrier=courrier.type,
                service_associe=courrier.service_actuel,
                actif=True
            ).first()
            
            if not workflow:
                # Créer un workflow par défaut
                workflow = TraitementCourrierService._creer_workflow_defaut(courrier)
            
            courrier.workflow_validation = workflow
            courrier.save()
            
            # Créer les validations initiales
            TraitementCourrierService._creer_validations_initiales(courrier, workflow)
            
            return workflow
            
        except Exception as e:
            logger.error(f"Erreur création workflow: {str(e)}")
            return None
    
    @staticmethod
    def _creer_workflow_defaut(courrier):
        """Crée un workflow par défaut selon le type de courrier"""
        from courriers.models_traitement import WorkflowValidation
        
        etapes = []
        
        if courrier.type == 'entrant':
            etapes = [
                {'role': 'chef', 'type': 'hierarchique', 'ordre': 1, 'obligatoire': True},
                {'role': 'direction', 'type': 'finale', 'ordre': 2, 'obligatoire': courrier.priorite in ['haute', 'urgente']},
            ]
        elif courrier.type == 'sortant':
            etapes = [
                {'role': 'chef', 'type': 'hierarchique', 'ordre': 1, 'obligatoire': True},
                {'role': 'juridique', 'type': 'juridique', 'ordre': 2, 'obligatoire': courrier.category and 'juridique' in courrier.category.name.lower()},
                {'role': 'direction', 'type': 'signature', 'ordre': 3, 'obligatoire': True},
            ]
        elif courrier.type == 'interne':
            etapes = [
                {'role': 'chef', 'type': 'hierarchique', 'ordre': 1, 'obligatoire': True},
            ]
        
        workflow = WorkflowValidation.objects.create(
            nom=f"Workflow {courrier.type} - {courrier.service_actuel.nom if courrier.service_actuel else 'Général'}",
            type_courrier=courrier.type,
            service_associe=courrier.service_actuel,
            etapes_validation=etapes,
            actif=True
        )
        
        return workflow
    
    @staticmethod
    def _creer_validations_initiales(courrier, workflow):
        """Crée les validations initiales basées sur le workflow"""
        from courriers.models_traitement import ValidationCourrier
        
        for etape in workflow.etapes_validation:
            # Trouver le validateur approprié
            validateur = TraitementCourrierService._trouver_validateur(
                courrier.service_actuel, 
                etape['role']
            )
            
            if validateur or not etape.get('obligatoire', True):
                ValidationCourrier.objects.create(
                    courrier=courrier,
                    type_validation=etape['type'],
                    validateur=validateur,
                    ordre=etape['ordre'],
                    statut='en_attente' if validateur else 'valide'  # Auto-validé si pas de validateur
                )
    
    @staticmethod
    def _trouver_validateur(service, role):
        """Trouve le validateur approprié pour un rôle donné"""
        if role == 'chef':
            return service.chef if service and service.chef else None
        elif role == 'direction':
            # Trouver un utilisateur avec rôle direction
            return User.objects.filter(role='direction').first()
        elif role == 'juridique':
            # Trouver un utilisateur du service juridique
            service_juridique = Service.objects.filter(nom__icontains='juridique').first()
            if service_juridique:
                return service_juridique.chef
        return None
    
    @staticmethod
    def prendre_en_charge_courrier(courrier, agent, commentaire=""):
        """Prend en charge un courrier pour traitement"""
        with transaction.atomic():
            courrier.responsable_actuel = agent
            courrier.agent_traitant = agent
            courrier.traitement_statut = TraitementStatus.ANALYSE
            courrier.date_debut_traitement = timezone.now()
            courrier.save()
            
            # Créer l'étape de prise en charge
            TraitementEtape.objects.create(
                courrier=courrier,
                type_etape='prise_en_charge',
                agent=agent,
                description=f"Prise en charge par {agent.get_full_name()}",
                commentaire=commentaire,
                statut='termine',
                date_fin=timezone.now()
            )
            
            # Journaliser
            from courriers.models import ActionHistorique
            ActionHistorique.objects.create(
                courrier=courrier,
                user=agent,
                action="PRISE_EN_CHARGE",
                commentaire=f"Courrier pris en charge par {agent.get_full_name()}"
            )
            
            return courrier
    
    @staticmethod
    def rediger_reponse(courrier, redacteur, donnees_reponse):
        """Rédige une réponse pour un courrier"""
        from courriers.models_traitement import CourrierReponse
        
        with transaction.atomic():
            # Créer la réponse
            reponse = CourrierReponse.objects.create(
                courrier_origine=courrier,
                type_reponse=donnees_reponse['type_reponse'],
                objet=donnees_reponse['objet'],
                contenu=donnees_reponse['contenu'],
                destinataires=donnees_reponse['destinataires'],
                copies=donnees_reponse.get('copies', []),
                canal_envoi=donnees_reponse.get('canal_envoi', 'email'),
                redacteur=redacteur,
                statut='brouillon'
            )
            
            # Mettre à jour le statut du traitement
            courrier.traitement_statut = TraitementStatus.REDACTION
            courrier.reponse_associee = reponse
            courrier.save()
            
            # Créer l'étape de rédaction
            TraitementEtape.objects.create(
                courrier=courrier,
                type_etape='redaction',
                agent=redacteur,
                description="Rédaction de la réponse",
                commentaire=f"Type: {donnees_reponse['type_reponse']}",
                statut='termine',
                date_fin=timezone.now()
            )
            
            return reponse
    
    @staticmethod
    def soumettre_pour_validation(courrier, soumetteur):
        """Soumet un courrier pour validation"""
        with transaction.atomic():
            # Mettre à jour le statut
            courrier.traitement_statut = TraitementStatus.VALIDATION
            courrier.besoin_validation = True
            
            if courrier.reponse_associee:
                courrier.reponse_associee.statut = 'a_valider'
                courrier.reponse_associee.save()
            
            courrier.save()
            
            # Créer l'étape de soumission
            TraitementEtape.objects.create(
                courrier=courrier,
                type_etape='validation',
                agent=soumetteur,
                description="Soumis pour validation",
                statut='en_attente'
            )
            
            # Notifier les validateurs
            TraitementCourrierService._notifier_validateurs(courrier)
            
            return courrier
    
    @staticmethod
    def _notifier_validateurs(courrier):
        """Notifie les validateurs d'une demande de validation"""
        # Implémentation des notifications (email, notifications internes, etc.)
        pass
    
    @staticmethod
    def valider_courrier(validation, validateur, action, commentaire=""):
        """Valide ou rejette une validation"""
        with transaction.atomic():
            # Mettre à jour la validation
            validation.statut = action
            validation.commentaire = commentaire
            validation.date_action = timezone.now()
            validation.save()
            
            # Mettre à jour le courrier si nécessaire
            courrier = validation.courrier
            
            if action == 'valide':
                courrier.niveau_validation_atteint = max(
                    courrier.niveau_validation_atteint,
                    validation.ordre
                )
                
                # Vérifier si toutes les validations sont faites
                if courrier.niveau_validation_atteint >= courrier.niveau_validation_requis:
                    courrier.traitement_statut = TraitementStatus.SIGNATURE
                    
                    if courrier.reponse_associee:
                        courrier.reponse_associee.statut = 'a_signature'
                        courrier.reponse_associee.validateur = validateur
                        courrier.reponse_associee.date_validation = timezone.now()
                        courrier.reponse_associee.save()
            
            elif action == 'rejete':
                courrier.traitement_statut = TraitementStatus.REDACTION
                
                if courrier.reponse_associee:
                    courrier.reponse_associee.statut = 'a_corriger'
                    courrier.reponse_associee.save()
            
            courrier.save()
            
            # Créer l'étape de validation
            TraitementEtape.objects.create(
                courrier=courrier,
                type_etape='validation',
                agent=validateur,
                description=f"Validation {action}ée",
                commentaire=commentaire,
                statut='termine',
                date_fin=timezone.now()
            )
            
            return validation
    
    @staticmethod
    def signer_courrier(courrier, signataire, signature_data):
        """Signe électroniquement un courrier"""
        with transaction.atomic():
            # Créer la validation de signature
            validation = ValidationCourrier.objects.create(
                courrier=courrier,
                type_validation='signature',
                validateur=signataire,
                statut='signe',
                date_action=timezone.now(),
                signature_data=signature_data.get('signature_data'),
                signature_image=signature_data.get('signature_image'),
                certificat_info=signature_data.get('certificat_info'),
                commentaire=signature_data.get('commentaire', '')
            )
            
            # Mettre à jour le statut
            courrier.traitement_statut = TraitementStatus.ENVOI
            
            if courrier.reponse_associee:
                courrier.reponse_associee.statut = 'a_envoyer'
                courrier.reponse_associee.signataire = signataire
                courrier.reponse_associee.date_signature = timezone.now()
                courrier.reponse_associee.save()
            
            courrier.save()
            
            # Créer l'étape de signature
            TraitementEtape.objects.create(
                courrier=courrier,
                type_etape='signature',
                agent=signataire,
                description="Signature électronique",
                statut='termine',
                date_fin=timezone.now()
            )
            
            return validation
    
    @staticmethod
    def envoyer_reponse(courrier, envoyeur):
        """Envoie la réponse finale"""
        with transaction.atomic():
            reponse = courrier.reponse_associee
            
            if not reponse:
                raise ValueError("Aucune réponse à envoyer")
            
            # Mettre à jour la réponse
            reponse.date_envoi = timezone.now()
            reponse.statut = 'envoye'
            reponse.save()
            
            # Mettre à jour le courrier
            courrier.traitement_statut = TraitementStatus.CLOTURE
            courrier.statut = 'repondu'
            courrier.date_fin_traitement = timezone.now()
            courrier.date_cloture = timezone.now().date()
            courrier.save()
            
            # Envoyer physiquement (à implémenter selon le canal)
            TraitementCourrierService._effectuer_envoi(reponse)
            
            # Créer l'étape d'envoi
            TraitementEtape.objects.create(
                courrier=courrier,
                type_etape='envoi',
                agent=envoyeur,
                description=f"Réponse envoyée par {reponse.canal_envoi}",
                statut='termine',
                date_fin=timezone.now()
            )
            
            # Journaliser
            from courriers.models import ActionHistorique
            ActionHistorique.objects.create(
                courrier=courrier,
                user=envoyeur,
                action="REPONSE_ENVOYEE",
                commentaire=f"Réponse {reponse.reference} envoyée"
            )
            
            return reponse
    
    @staticmethod
    def _effectuer_envoi(reponse):
        """Effectue l'envoi physique selon le canal"""
        # Implémentation spécifique selon le canal d'envoi
        if reponse.canal_envoi == 'email':
            TraitementCourrierService._envoyer_email(reponse)
        elif reponse.canal_envoi == 'courrier':
            TraitementCourrierService._generer_pdf_pour_poste(reponse)
        # etc.
    
    @staticmethod
    def _envoyer_email(reponse):
        """Envoie la réponse par email"""
        # Implémentation de l'envoi d'email
        pass
    
    @staticmethod
    def _generer_pdf_pour_poste(reponse):
        """Génère un PDF pour envoi postal"""
        # Implémentation de la génération PDF
        pass
    
    @staticmethod
    def get_timeline_traitement(courrier):
        """Récupère la timeline du traitement d'un courrier"""
        timeline = []
        
        # Étape de réception
        if courrier.date_reception:
            timeline.append({
                'type': 'reception',
                'date': courrier.date_reception,
                'titre': 'Réception',
                'description': f'Reçu de {courrier.expediteur_nom}',
                'auteur': courrier.created_by.get_full_name() if courrier.created_by else 'Système'
            })
        
        # Imputations
        for imputation in courrier.imputations.all():
            timeline.append({
                'type': 'imputation',
                'date': imputation.date_imputation,
                'titre': 'Imputation',
                'description': f'Vers {imputation.service.nom if imputation.service else "N/A"}',
                'auteur': imputation.responsable.get_full_name() if imputation.responsable else 'Système'
            })
        
        # Étapes de traitement
        for etape in courrier.traitement_etapes.all():
            timeline.append({
                'type': 'traitement',
                'date': etape.date_debut,
                'titre': etape.get_type_etape_display(),
                'description': etape.description,
                'auteur': etape.agent.get_full_name() if etape.agent else 'Système',
                'statut': etape.get_statut_display()
            })
        
        # Validations
        for validation in courrier.validations.all():
            timeline.append({
                'type': 'validation',
                'date': validation.date_action or validation.date_demande,
                'titre': f'Validation {validation.get_type_validation_display()}',
                'description': validation.commentaire or f'Statut: {validation.get_statut_display()}',
                'auteur': validation.validateur.get_full_name() if validation.validateur else 'En attente',
                'statut': validation.get_statut_display()
            })
        
        # Trier par date
        timeline.sort(key=lambda x: x['date'])
        
        return timeline


traitement_service = TraitementCourrierService()