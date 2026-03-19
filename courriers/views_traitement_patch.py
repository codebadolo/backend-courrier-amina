# courriers/views_traitement_patch.py
#
# Ce fichier contient les méthodes à REMPLACER dans CourrierViewSet.
# Chaque méthode utilise workflow_traitement.py pour respecter
# le circuit adapté au type du courrier.
#
# INSTRUCTIONS D'INTÉGRATION :
#   1. Ajoute en haut de views.py :
#        from .workflow_traitement import (
#            get_etape_suivante, get_etape_initiale,
#            peut_avancer, progression_pct, build_historique_cloture, ETAPE_LABELS
#        )
#   2. Remplace chaque méthode de CourrierViewSet par celle ci-dessous.
#   3. Ajoute la méthode `historique_cloture` (nouvelle).

from django.utils import timezone
from django.db import transaction
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
import logging

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# 1. prendre_en_charge  (CourrierTraitementViewSet)
# ─────────────────────────────────────────────────────────────────────────────
# REMPLACE : CourrierTraitementViewSet.prendre_en_charge
# URL      : POST /courriers/traitement/{pk}/prendre-en-charge/

def prendre_en_charge(self, request, pk=None):
    """
    Prise en charge d'un courrier.
    Démarre le circuit selon le type : entrant et interne démarrent à
    'prise_en_charge', les sortants démarrent directement à 'redaction'.
    """
    from .workflow_traitement import get_etape_initiale, peut_avancer
    from .models import TraitementEtape, ActionHistorique
    from .serializers import CourrierDetailSerializer

    courrier = self.get_object()
    user     = request.user

    ok, err = peut_avancer(courrier, user)
    if not ok:
        return Response({'error': err}, status=status.HTTP_403_FORBIDDEN)

    if courrier.traitement_statut not in ('prise_en_charge', None, ''):
        return Response(
            {'error': f"Ce courrier est déjà en cours de traitement (statut : {courrier.traitement_statut})"},
            status=status.HTTP_400_BAD_REQUEST
        )

    delai = request.data.get('delai_jours', 5)
    commentaire = request.data.get('commentaire', '')

    with transaction.atomic():
        # Étape initiale selon le type
        etape_initiale = get_etape_initiale(courrier.type)

        courrier.traitement_statut   = etape_initiale
        courrier.agent_traitant      = user
        courrier.responsable_actuel  = user
        courrier.service_actuel      = user.service
        courrier.date_debut_traitement = timezone.now()
        courrier.delai_traitement_jours = int(delai)
        courrier.save()

        TraitementEtape.objects.create(
            courrier=courrier, type_etape=etape_initiale,
            agent=user, description=f"Prise en charge — délai : {delai}j",
            commentaire=commentaire, statut='en_cours',
        )
        ActionHistorique.objects.create(
            courrier=courrier, user=user,
            action='PRISE_EN_CHARGE',
            commentaire=f"Délai : {delai} jours. {commentaire}".strip(),
        )

    return Response({
        'message': 'Courrier pris en charge',
        'etape':   etape_initiale,
        'courrier': CourrierDetailSerializer(courrier, context={'request': request}).data,
    })


# ─────────────────────────────────────────────────────────────────────────────
# 2. demarrer_analyse  (CourrierViewSet)
# ─────────────────────────────────────────────────────────────────────────────
# REMPLACE : CourrierViewSet.demarrer_analyse
# URL      : POST /courriers/courriers/{pk}/demarrer_analyse/

def demarrer_analyse(self, request, pk=None):
    """
    Fait avancer le courrier de 'prise_en_charge' → 'analyse'.
    Uniquement pour les courriers entrants.
    """
    from .workflow_traitement import get_etape_suivante, peut_avancer
    from .models import TraitementEtape, ActionHistorique
    from .serializers import CourrierDetailSerializer

    courrier = self.get_object()
    user     = request.user

    if courrier.type != 'entrant':
        return Response(
            {'error': "L'étape analyse n'existe que pour les courriers entrants."},
            status=400
        )

    ok, err = peut_avancer(courrier, user)
    if not ok:
        return Response({'error': err}, status=403)

    etape_suivante = get_etape_suivante(courrier.type, courrier.traitement_statut)
    if etape_suivante != 'analyse':
        return Response(
            {'error': f"Impossible de démarrer l'analyse depuis l'étape '{courrier.traitement_statut}'."},
            status=400
        )

    with transaction.atomic():
        courrier.traitement_statut = 'analyse'
        courrier.agent_traitant    = user
        courrier.save()

        TraitementEtape.objects.create(
            courrier=courrier, type_etape='analyse',
            agent=user, description="Début de l'analyse", statut='en_cours',
        )
        ActionHistorique.objects.create(
            courrier=courrier, user=user,
            action='DEBUT_ANALYSE', commentaire="Analyse démarrée",
        )

    return Response({
        'message': 'Analyse démarrée',
        'courrier': CourrierDetailSerializer(courrier, context={'request': request}).data,
    })


# ─────────────────────────────────────────────────────────────────────────────
# 3. enregistrer_analyse  (CourrierViewSet)
# ─────────────────────────────────────────────────────────────────────────────
# REMPLACE : CourrierViewSet.enregistrer_analyse
# URL      : POST /courriers/courriers/{pk}/enregistrer_analyse/

def enregistrer_analyse(self, request, pk=None):
    """
    Enregistre les notes d'analyse.
    Si prochaine_etape='instruction' → avance dans le circuit.
    Si prochaine_etape='analyse'    → sauvegarde en brouillon.
    """
    from .workflow_traitement import get_etape_suivante, peut_avancer
    from .models import TraitementEtape, ActionHistorique
    from .serializers import CourrierDetailSerializer

    courrier = self.get_object()
    user     = request.user

    ok, err = peut_avancer(courrier, user)
    if not ok:
        return Response({'error': err}, status=403)

    prochaine = request.data.get('prochaine_etape', 'analyse')

    with transaction.atomic():
        courrier.analyse_notes         = request.data.get('analyse_notes', '')
        courrier.actions_requises      = request.data.get('actions_requises', [])
        courrier.documents_necessaires = request.data.get('documents_necessaires', [])
        courrier.decision_preliminaire = request.data.get('decision_preliminaire', '')

        if prochaine == 'instruction':
            etape_suiv = get_etape_suivante(courrier.type, 'analyse')
            if etape_suiv:
                courrier.traitement_statut = etape_suiv
                TraitementEtape.objects.create(
                    courrier=courrier, type_etape='analyse',
                    agent=user, description="Analyse validée", statut='termine',
                    date_fin=timezone.now(),
                )
                ActionHistorique.objects.create(
                    courrier=courrier, user=user,
                    action='ANALYSE_VALIDEE',
                    commentaire=f"Prochaine étape : {etape_suiv}",
                )
                message = f"Analyse validée — passage à : {etape_suiv}"
            else:
                message = "Analyse enregistrée (circuit terminé)"
        else:
            ActionHistorique.objects.create(
                courrier=courrier, user=user,
                action='ANALYSE_BROUILLON', commentaire="Brouillon sauvegardé",
            )
            message = "Brouillon sauvegardé"

        courrier.save()

    return Response({
        'message': message,
        'courrier': CourrierDetailSerializer(courrier, context={'request': request}).data,
    })


# ─────────────────────────────────────────────────────────────────────────────
# 4. enregistrer_instruction  (CourrierViewSet)
# ─────────────────────────────────────────────────────────────────────────────
# REMPLACE : CourrierViewSet.enregistrer_instruction
# URL      : POST /courriers/courriers/{pk}/enregistrer_instruction/

def enregistrer_instruction(self, request, pk=None):
    """
    Enregistre l'instruction.
    Si statut_instruction='terminee' → avance vers 'redaction'.
    """
    from .workflow_traitement import get_etape_suivante, peut_avancer
    from .models import TraitementEtape, ActionHistorique
    from .serializers import CourrierDetailSerializer

    courrier = self.get_object()
    user     = request.user

    ok, err = peut_avancer(courrier, user)
    if not ok:
        return Response({'error': err}, status=403)

    statut_instruction = request.data.get('statut_instruction', 'en_cours')

    with transaction.atomic():
        courrier.analyse_notes         = request.data.get('notes_instruction', courrier.analyse_notes or '')
        courrier.actions_requises      = request.data.get('actions_requises', courrier.actions_requises or [])
        courrier.documents_necessaires = request.data.get('documents_necessaires', courrier.documents_necessaires or [])

        if statut_instruction == 'terminee':
            etape_suiv = get_etape_suivante(courrier.type, 'instruction')
            if etape_suiv:
                courrier.traitement_statut = etape_suiv
                TraitementEtape.objects.create(
                    courrier=courrier, type_etape='instruction',
                    agent=user, description="Instruction validée", statut='termine',
                    date_fin=timezone.now(),
                )
                ActionHistorique.objects.create(
                    courrier=courrier, user=user,
                    action='INSTRUCTION_VALIDEE',
                    commentaire=f"Passage à : {etape_suiv}",
                )
                message = f"Instruction validée — passage à : {etape_suiv}"
            else:
                message = "Instruction enregistrée"
        else:
            ActionHistorique.objects.create(
                courrier=courrier, user=user, action='INSTRUCTION_BROUILLON',
            )
            message = "Instruction sauvegardée"

        courrier.save()

    return Response({
        'message': message,
        'courrier': CourrierDetailSerializer(courrier, context={'request': request}).data,
    })


# ─────────────────────────────────────────────────────────────────────────────
# 5. soumettre_validation  (CourrierViewSet)
# ─────────────────────────────────────────────────────────────────────────────
# REMPLACE : CourrierViewSet.soumettre_validation
# URL      : POST /courriers/courriers/{pk}/soumettre-validation/

def soumettre_validation(self, request, pk=None):
    """
    Soumet la réponse pour validation.
    Avance de 'redaction' → 'validation' selon le circuit.
    """
    from .workflow_traitement import get_etape_suivante, peut_avancer
    from .models import ValidationCourrier, ActionHistorique
    from .serializers import CourrierDetailSerializer
    from django.db.models import Max

    courrier = self.get_object()
    user     = request.user

    ok, err = peut_avancer(courrier, user)
    if not ok:
        return Response({'error': err}, status=403)

    etape_suiv = get_etape_suivante(courrier.type, 'redaction')
    if not etape_suiv:
        return Response({'error': "Pas d'étape suivante dans le circuit."}, status=400)

    with transaction.atomic():
        courrier.traitement_statut = etape_suiv
        courrier.besoin_validation = True
        courrier.save()

        max_ordre   = courrier.validations.aggregate(Max('ordre'))['ordre__max'] or 0
        validateur  = courrier.service_impute.chef if courrier.service_impute else None

        validation = ValidationCourrier.objects.create(
            courrier=courrier,
            type_validation='hierarchique',
            validateur=validateur,
            ordre=max_ordre + 1,
            statut='en_attente',
            commentaire=request.data.get('commentaire', ''),
        )
        ActionHistorique.objects.create(
            courrier=courrier, user=user,
            action='SOUMIS_VALIDATION',
            commentaire=f"Soumis pour validation — étape : {etape_suiv}",
        )

    return Response({
        'message': 'Courrier soumis pour validation',
        'validation_id': str(validation.id),
        'courrier': CourrierDetailSerializer(courrier, context={'request': request}).data,
    })


# ─────────────────────────────────────────────────────────────────────────────
# 6. valider  (CourrierViewSet)
# ─────────────────────────────────────────────────────────────────────────────
# REMPLACE : CourrierViewSet.valider
# URL      : POST /courriers/courriers/{pk}/valider/

def valider(self, request, pk=None):
    """
    Approuver → avance vers 'signature' selon le circuit.
    Rejeter   → retour à 'redaction'.
    """
    from .workflow_traitement import get_etape_suivante
    from .models import ValidationCourrier, ActionHistorique, TraitementStatus
    from .serializers import CourrierDetailSerializer

    courrier      = self.get_object()
    user          = request.user
    action_val    = request.data.get('action', 'valider')
    commentaire   = request.data.get('commentaire', '')
    validation_id = request.data.get('validation_id')

    # Permission : chef, direction, admin
    if user.role not in ('chef', 'direction', 'admin'):
        return Response({'error': "Vous n'êtes pas autorisé à valider."}, status=403)

    try:
        with transaction.atomic():
            if validation_id:
                validation = ValidationCourrier.objects.get(id=validation_id, courrier=courrier)
                if validation.validateur and validation.validateur != user:
                    return Response({'error': "Vous n'êtes pas le validateur désigné."}, status=403)
                validation.statut     = 'valide' if action_val == 'valider' else 'rejete'
                validation.commentaire = commentaire
                validation.date_action = timezone.now()
                validation.save()

            if action_val == 'valider':
                etape_suiv = get_etape_suivante(courrier.type, 'validation')
                courrier.traitement_statut = etape_suiv or TraitementStatus.SIGNATURE
                msg = "Validation approuvée"
            else:
                courrier.traitement_statut = 'redaction'
                msg = "Validation rejetée — retour à la rédaction"

            courrier.save()
            ActionHistorique.objects.create(
                courrier=courrier, user=user,
                action=f"VALIDATION_{'APPROUVEE' if action_val == 'valider' else 'REJETEE'}",
                commentaire=commentaire,
            )

        return Response({
            'message': msg,
            'courrier': CourrierDetailSerializer(courrier, context={'request': request}).data,
        })

    except ValidationCourrier.DoesNotExist:
        return Response({'error': "Validation non trouvée."}, status=404)
    except Exception as e:
        logger.error(f"Erreur validation: {e}")
        return Response({'error': str(e)}, status=500)


# ─────────────────────────────────────────────────────────────────────────────
# 7. signer  (CourrierViewSet)
# ─────────────────────────────────────────────────────────────────────────────
# REMPLACE : CourrierViewSet.signer
# URL      : POST /courriers/courriers/{pk}/signer/

def signer(self, request, pk=None):
    """
    Signature électronique → avance vers 'envoi' selon le circuit.
    """
    from .workflow_traitement import get_etape_suivante, peut_avancer
    from .models import ValidationCourrier, TraitementEtape, ActionHistorique
    from .serializers import CourrierDetailSerializer
    from django.db.models import Max

    courrier = self.get_object()
    user     = request.user

    ok, err = peut_avancer(courrier, user)
    if not ok:
        return Response({'error': err}, status=403)

    if courrier.traitement_statut not in ('signature', 'validation', 'redaction'):
        return Response(
            {'error': f"Statut actuel '{courrier.traitement_statut}' ne permet pas la signature."},
            status=400
        )

    with transaction.atomic():
        etape_suiv = get_etape_suivante(courrier.type, 'signature')
        max_ordre  = courrier.validations.aggregate(Max('ordre'))['ordre__max'] or 0

        ValidationCourrier.objects.create(
            courrier=courrier, type_validation='signature',
            validateur=user, ordre=max_ordre + 1, statut='signe',
            date_action=timezone.now(),
            signature_data=request.data.get('signature_data', {}),
            commentaire=request.data.get('commentaire', 'Signature électronique'),
        )
        TraitementEtape.objects.create(
            courrier=courrier, type_etape='signature',
            agent=user, description="Signature électronique",
            statut='termine', date_fin=timezone.now(),
        )
        courrier.traitement_statut = etape_suiv or 'envoi'
        courrier.save()

        ActionHistorique.objects.create(
            courrier=courrier, user=user,
            action='SIGNATURE', commentaire="Signé électroniquement",
        )

    return Response({
        'message': 'Courrier signé avec succès',
        'courrier': CourrierDetailSerializer(courrier, context={'request': request}).data,
    })


# ─────────────────────────────────────────────────────────────────────────────
# 8. envoyer  (CourrierViewSet)
# ─────────────────────────────────────────────────────────────────────────────
# REMPLACE : CourrierViewSet.envoyer
# URL      : POST /courriers/courriers/{pk}/envoyer/

def envoyer(self, request, pk=None):
    """
    Confirme l'envoi et clôture le courrier.
    Dernière étape du circuit pour entrant et sortant.
    """
    from .workflow_traitement import peut_avancer
    from .models import TraitementEtape, ActionHistorique
    from .serializers import CourrierDetailSerializer

    courrier = self.get_object()
    user     = request.user

    ok, err = peut_avancer(courrier, user)
    if not ok:
        return Response({'error': err}, status=403)

    with transaction.atomic():
        courrier.traitement_statut   = 'cloture'
        courrier.statut              = 'repondu'
        courrier.date_envoi          = timezone.now().date()
        courrier.date_cloture        = timezone.now().date()
        courrier.date_fin_traitement = timezone.now()
        courrier.save()

        TraitementEtape.objects.create(
            courrier=courrier, type_etape='envoi',
            agent=user, description="Envoi et clôture du traitement",
            statut='termine', date_fin=timezone.now(),
        )
        ActionHistorique.objects.create(
            courrier=courrier, user=user,
            action='ENVOI_ET_CLOTURE', commentaire="Courrier envoyé et traitement clôturé",
        )

    return Response({
        'message': 'Courrier envoyé et clôturé',
        'courrier': CourrierDetailSerializer(courrier, context={'request': request}).data,
    })


# ─────────────────────────────────────────────────────────────────────────────
# 9. transmettre_interne  — NOUVELLE action pour courriers internes
# ─────────────────────────────────────────────────────────────────────────────
# AJOUTER dans CourrierViewSet
# URL : POST /courriers/courriers/{pk}/transmettre-interne/

def transmettre_interne(self, request, pk=None):
    """
    Transmission d'un courrier interne → avance vers 'cloture'.
    """
    from .workflow_traitement import get_etape_suivante, peut_avancer
    from .models import TraitementEtape, ActionHistorique
    from .serializers import CourrierDetailSerializer

    courrier = self.get_object()
    user     = request.user

    if courrier.type != 'interne':
        return Response({'error': "Action réservée aux courriers internes."}, status=400)

    ok, err = peut_avancer(courrier, user)
    if not ok:
        return Response({'error': err}, status=403)

    destinataire_id = request.data.get('destinataire_id')
    commentaire     = request.data.get('commentaire', '')

    with transaction.atomic():
        if destinataire_id:
            from django.contrib.auth import get_user_model
            User = get_user_model()
            try:
                dest = User.objects.get(id=destinataire_id, actif=True)
                courrier.responsable_actuel = dest
                courrier.service_actuel     = dest.service
            except User.DoesNotExist:
                return Response({'error': "Destinataire introuvable."}, status=404)

        etape_suiv = get_etape_suivante(courrier.type, 'transmission') or 'cloture'
        courrier.traitement_statut = etape_suiv
        if etape_suiv == 'cloture':
            courrier.date_cloture        = timezone.now().date()
            courrier.date_fin_traitement = timezone.now()
            courrier.statut              = 'repondu'
        courrier.save()

        TraitementEtape.objects.create(
            courrier=courrier, type_etape='transmission',
            agent=user, description=f"Transmission interne{' → ' + dest.get_full_name() if destinataire_id else ''}",
            commentaire=commentaire, statut='termine', date_fin=timezone.now(),
        )
        ActionHistorique.objects.create(
            courrier=courrier, user=user,
            action='TRANSMISSION_INTERNE', commentaire=commentaire,
        )

    return Response({
        'message': 'Courrier interne transmis',
        'courrier': CourrierDetailSerializer(courrier, context={'request': request}).data,
    })


# ─────────────────────────────────────────────────────────────────────────────
# 10. historique_cloture — NOUVELLE action (GET)
# ─────────────────────────────────────────────────────────────────────────────
# AJOUTER dans CourrierViewSet
# URL : GET /courriers/courriers/{pk}/historique-cloture/

def historique_cloture(self, request, pk=None):
    """
    Retourne le récapitulatif complet du traitement d'un courrier clôturé :
    circuit suivi, étapes réalisées, validations, historique des actions.
    Accessible même si le courrier est archivé.
    """
    from .workflow_traitement import build_historique_cloture, get_circuit, progression_pct
    from .serializers import CourrierDetailSerializer

    # On bypasse get_queryset pour autoriser la lecture même après archivage
    from .models import Courrier
    try:
        courrier = Courrier.objects.get(pk=pk)
    except Courrier.DoesNotExist:
        return Response({'error': "Courrier introuvable."}, status=404)

    # Permission : seul l'agent traitant, chef de service, direction, admin
    user = request.user
    est_implique = (
        courrier.agent_traitant == user or
        courrier.responsable_actuel == user or
        user.role in ('chef', 'direction', 'admin', 'archiviste')
    )
    if not est_implique:
        return Response({'error': "Accès non autorisé."}, status=403)

    recap = build_historique_cloture(courrier)

    # Ajouter données courrier de base
    recap['courrier'] = CourrierDetailSerializer(
        courrier, context={'request': request}
    ).data
    recap['circuit_complet'] = get_circuit(courrier.type)
    recap['progression'] = progression_pct(courrier.type, courrier.traitement_statut)

    return Response(recap)


# ─────────────────────────────────────────────────────────────────────────────
# DÉCORATEURS — à appliquer dans views.py lors de l'intégration
# ─────────────────────────────────────────────────────────────────────────────
#
# Pour chaque méthode remplacée, le décorateur @action reste identique.
# Exemple pour historique_cloture :
#
#   @action(detail=True, methods=['get'], url_path='historique-cloture',
#           permission_classes=[IsAuthenticated])
#   def historique_cloture(self, request, pk=None):
#       ...
#
# Pour transmettre_interne (déjà dans urls.py) :
#   @action(detail=True, methods=['post'], url_path='transmettre-interne',
#           permission_classes=[IsAuthenticated])
#   def transmettre_interne(self, request, pk=None):
#       ...