# users/permissions.py
from rest_framework import permissions


class IsServiceChiefOrAdmin(permissions.BasePermission):
    """
    Permission pour vérifier si l'utilisateur est chef de service ou admin
    """
    
    def has_permission(self, request, view):
        return request.user and request.user.is_authenticated
    
    def has_object_permission(self, request, view, obj):
        # Pour les objets Service
        if hasattr(obj, 'chef'):
            return (
                request.user.is_superuser or
                request.user.role == 'admin' or
                obj.chef == request.user
            )
        return False


class CanManageServiceAgents(permissions.BasePermission):
    """
    Permission pour gérer les agents d'un service
    """
    
    def has_permission(self, request, view):
        # Seuls les admins, direction et chefs de service peuvent gérer
        allowed_roles = ['admin', 'direction', 'chef']
        return (
            request.user and
            request.user.is_authenticated and
            request.user.role in allowed_roles
        )


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