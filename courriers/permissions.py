# courriers/permissions.py
from rest_framework import permissions
from django.db.models import Q


class CourrierPermissions(permissions.BasePermission):
    """
    Permissions personnalisées pour les courriers
    """
    
    def has_permission(self, request, view):
        """Autorisation générale pour la vue"""
        if request.user.is_authenticated:
            return True
        return False
    
    def has_object_permission(self, request, view, obj):
        """
        Vérifie si l'utilisateur a accès à un courrier spécifique
        """
        # 0. Vérifier si l'utilisateur est authentifié
        if not request.user.is_authenticated:
            return False
        
        # 1. Administrateur système - accès total
        if request.user.role == 'admin' or request.user.is_superuser:
            return True
        
        # 2. Direction - peut voir tous les courriers non confidentiels
        if request.user.role == 'direction':
            if obj.confidentialite in ['normale', 'restreinte']:
                return True
        
        # 3. Archiviste - peut voir tous les courriers archivés
        if request.user.role == 'archiviste':
            if obj.archived:
                return True
        
        # 4. Le courrier est imputé au service de l'utilisateur
        if obj.service_actuel == request.user.service:
            return True
        
        # 5. L'utilisateur est responsable du service imputé
        if (obj.service_actuel and 
            obj.service_actuel.chef and 
            request.user == obj.service_actuel.chef):
            return True
        
        # 6. L'utilisateur est responsable actuel du courrier
        if obj.responsable_actuel == request.user:
            return True
        
        # 7. Le courrier n'est pas confidentiel ET l'utilisateur est dans un service concerné
        if obj.confidentialite == 'normale':
            # Vérifier si l'utilisateur fait partie des services concernés
            # (nécessite d'implémenter services_concernes() dans le modèle)
            services_concernes = obj.services_concernes() if hasattr(obj, 'services_concernes') else []
            if request.user.service in services_concernes:
                return True
        
        # 8. L'utilisateur a créé le courrier
        if obj.created_by == request.user:
            return True
        
        # 9. Accès en lecture seule pour certains rôles
        if request.method in permissions.SAFE_METHODS:  # GET, HEAD, OPTIONS
            # Secrétariat/Guichet peut voir tous les courriers en lecture
            if request.user.role == 'agent_courrier':
                return True
        
        return False


class CourrierCreatePermissions(permissions.BasePermission):
    """Permissions pour la création de courriers"""
    
    def has_permission(self, request, view):
        if view.action == 'create':
            # Qui peut créer des courriers ?
            allowed_roles = ['admin', 'agent_courrier', 'chef', 'collaborateur']
            return request.user.is_authenticated and request.user.role in allowed_roles
        return True


class CourrierUpdatePermissions(permissions.BasePermission):
    """Permissions pour la modification de courriers"""
    
    def has_object_permission(self, request, view, obj):
        if request.method in ['PUT', 'PATCH']:
            # Qui peut modifier ?
            if request.user.role == 'admin':
                return True
            if obj.created_by == request.user and obj.statut == 'recu':
                return True  # Le créateur peut modifier tant que c'est en statut "Reçu"
            if obj.responsable_actuel == request.user:
                return True
            if obj.service_actuel and obj.service_actuel.chef == request.user:
                return True
            return False
        return True


class CourrierDeletePermissions(permissions.BasePermission):
    """Permissions pour la suppression de courriers"""
    
    def has_object_permission(self, request, view, obj):
        if request.method == 'DELETE':
            # Seuls les admins peuvent supprimer définitivement
            return request.user.role == 'admin' or request.user.is_superuser
        return True


class ConfidentialitePermissions(permissions.BasePermission):
    """Permissions basées sur le niveau de confidentialité"""
    
    def has_object_permission(self, request, view, obj):
        if obj.confidentialite == 'confidentielle':
            # Accès restreint aux courriers confidentiels
            allowed_users = ['admin', 'direction']
            if request.user.role in allowed_users:
                return True
            if obj.service_actuel and obj.service_actuel.chef == request.user:
                return True
            if obj.responsable_actuel == request.user:
                return True
            return False
        
        elif obj.confidentialite == 'restreinte':
            # Accès modéré
            if request.user.role in ['admin', 'direction', 'chef']:
                return True
            if obj.service_actuel == request.user.service:
                return True
            return False
        
        # 'normale' - accessible selon les règles générales
        return True


class WorkflowPermissions(permissions.BasePermission):
    """Permissions pour les actions de workflow"""
    
    def has_object_permission(self, request, view, obj):
        # Permissions spécifiques pour les actions de workflow
        if view.action in ['validate', 'reject', 'forward']:
            # Vérifier si l'utilisateur est un validateur dans le workflow
            from workflow.models import WorkflowStep
            try:
                workflow = obj.workflow
                current_step = workflow.steps.filter(
                    statut='en_attente',
                    validator=request.user
                ).first()
                if current_step:
                    return True
            except:
                pass
            
            # Les chefs de service peuvent valider pour leur service
            if obj.service_actuel and obj.service_actuel.chef == request.user:
                return True
            
            return False
        
        return True
    

class IsChefOfService(permissions.BasePermission):
    """Vérifie si l'utilisateur est le chef du service actuel du courrier"""
    
    def has_object_permission(self, request, view, obj):
        if obj.service_actuel and obj.service_actuel.chef == request.user:
            return True
        return False    
   
# courriers/permissions.py - Ajouter cette classe
class IsAgentService(permissions.BasePermission):
    """
    Permission pour vérifier si l'utilisateur est un agent de service
    """
    
    def has_permission(self, request, view):
        return (
            request.user and
            request.user.is_authenticated and
            request.user.role == 'agent_service'
        )
    
    def has_object_permission(self, request, view, obj):
        # Pour les courriers, vérifie si l'utilisateur est agent du service
        if hasattr(obj, 'service_actuel'):
            return obj.service_actuel == request.user.service
        return False