# core/views.py - Version complète et propre
from rest_framework import viewsets, filters, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response
from django.shortcuts import get_object_or_404
import logging

from .models import Service, Category, ClassificationRule, AuditLog
from .serializers import (
    ServiceSerializer,
    CategorySerializer,
    ClassificationRuleSerializer,
    AuditLogSerializer
)
from users.models import User
from users.serializers import UserListSerializer

logger = logging.getLogger(__name__)


class ServiceViewSet(viewsets.ModelViewSet):
    queryset = Service.objects.all().order_by("nom")
    serializer_class = ServiceSerializer
    permission_classes = [permissions.AllowAny]
    filter_backends = [filters.SearchFilter]
    search_fields = ["nom", "description"]
    
    @action(detail=True, methods=['get'])
    def membres(self, request, pk=None):
        """
        Lister tous les membres d'un service
        GET /api/services/{id}/membres/
        """
        try:
            service = self.get_object()
            
            # Vérifier les permissions
            if not self._can_view_members(request.user, service):
                return Response(
                    {"error": "Vous n'avez pas la permission de voir les membres de ce service"},
                    status=status.HTTP_403_FORBIDDEN
                )
            
            # Récupérer tous les membres du service
            membres = User.objects.filter(service=service)
            
            serializer = UserListSerializer(membres, many=True, context={'request': request})
            return Response(serializer.data)
            
        except Exception as e:
            logger.error(f"Erreur liste membres: {e}")
            return Response(
                {"error": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=True, methods=['post'])
    def ajouter_membre(self, request, pk=None):
        """
        Ajouter un utilisateur comme membre d'un service
        POST /api/services/{id}/ajouter_membre/
        Body: {"user_id": 123}
        """
        try:
            service = self.get_object()
            user_id = request.data.get('user_id')
            
            if not user_id:
                return Response(
                    {"error": "Le champ 'user_id' est requis"},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Vérifier les permissions
            if not self._can_manage_members(request.user, service):
                return Response(
                    {"error": "Vous n'avez pas la permission d'ajouter des membres à ce service"},
                    status=status.HTTP_403_FORBIDDEN
                )
            
            # Trouver l'utilisateur
            user = get_object_or_404(User, pk=user_id)
            
            # Vérifier que l'utilisateur n'est pas déjà chef d'un autre service
            if user.role == 'chef' and user.services_diriges.exists():
                return Response(
                    {"error": "Cet utilisateur est déjà chef d'un service"},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Affecter l'utilisateur au service
            user.service = service
            user.save()
            
            # Journaliser l'action
            AuditLog.objects.create(
                user=request.user,
                action="ADD_SERVICE_MEMBER",
                metadata={
                    "service_id": service.id,
                    "service_nom": service.nom,
                    "user_id": user.id,
                    "user_email": user.email
                }
            )
            
            return Response(
                {"message": f"Utilisateur {user.email} ajouté au service {service.nom}"},
                status=status.HTTP_200_OK
            )
            
        except Exception as e:
            logger.error(f"Erreur ajout membre: {e}")
            return Response(
                {"error": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=True, methods=['post'])
    def retirer_membre(self, request, pk=None):
        """
        Retirer un utilisateur d'un service
        POST /api/services/{id}/retirer_membre/
        Body: {"user_id": 123}
        """
        try:
            service = self.get_object()
            user_id = request.data.get('user_id')
            
            if not user_id:
                return Response(
                    {"error": "Le champ 'user_id' est requis"},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Vérifier les permissions
            if not self._can_manage_members(request.user, service):
                return Response(
                    {"error": "Vous n'avez pas la permission de retirer des membres de ce service"},
                    status=status.HTTP_403_FORBIDDEN
                )
            
            # Trouver l'utilisateur
            user = get_object_or_404(User, pk=user_id)
            
            # Vérifier que l'utilisateur est bien membre du service
            if user.service != service:
                return Response(
                    {"error": "Cet utilisateur n'est pas membre de ce service"},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Retirer l'utilisateur du service
            user.service = None
            user.save()
            
            # Journaliser
            AuditLog.objects.create(
                user=request.user,
                action="REMOVE_SERVICE_MEMBER",
                metadata={
                    "service_id": service.id,
                    "service_nom": service.nom,
                    "user_id": user.id,
                    "user_email": user.email
                }
            )
            
            return Response(
                {"message": f"Utilisateur {user.email} retiré du service {service.nom}"},
                status=status.HTTP_200_OK
            )
            
        except Exception as e:
            logger.error(f"Erreur retrait membre: {e}")
            return Response(
                {"error": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=True, methods=['get'])
    def statistiques(self, request, pk=None):
        """
        Récupérer les statistiques d'un service
        GET /api/services/{id}/statistiques/
        """
        try:
            service = self.get_object()
            
            # Vérifier les permissions
            if not self._can_view_members(request.user, service):
                return Response(
                    {"error": "Vous n'avez pas la permission de voir les statistiques de ce service"},
                    status=status.HTTP_403_FORBIDDEN
                )
            
            # Utiliser le serializer de statistiques
            from .serializers import ServiceStatsSerializer
            serializer = ServiceStatsSerializer(service, context={'request': request})
            return Response(serializer.data)
            
        except Exception as e:
            logger.error(f"Erreur statistiques service: {e}")
            return Response(
                {"error": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    def _can_view_members(self, user, service):
        """Vérifie si l'utilisateur peut voir les membres du service"""
        return (
            user.is_superuser or 
            user.role in ['admin', 'direction'] or
            service.chef == user
        )
    
    def _can_manage_members(self, user, service):
        """Vérifie si l'utilisateur peut gérer les membres du service"""
        return (
            user.is_superuser or 
            user.role == 'admin' or
            service.chef == user
        )
    
    @action(detail=True, methods=['get'], url_path='validateurs')
    def get_validateurs(self, request, pk=None):
        """Retourne les utilisateurs du service qui peuvent valider (chef, direction, admin)"""
        service = self.get_object()
        validateurs = User.objects.filter(
            service=service,
            role__in=['chef', 'direction', 'admin']
        ).values('id', 'username', 'first_name', 'last_name', 'email', 'role')
        
        # Format attendu par le frontend
        data = [{
            'id': v['id'],
            'nom': f"{v['first_name']} {v['last_name']}".strip() or v['username'],
            'email': v['email'],
            'role': v['role'],
            'role_display': dict(User.ROLE_CHOICES).get(v['role'], v['role']),
            'service_nom': service.nom
        } for v in validateurs]
        
        return Response(data)

class CategoryViewSet(viewsets.ModelViewSet):
    queryset = Category.objects.all().order_by("name")
    serializer_class = CategorySerializer
    permission_classes = [permissions.AllowAny]
    filter_backends = [filters.SearchFilter]
    search_fields = ["name", "description"]


class ClassificationRuleViewSet(viewsets.ModelViewSet):
    queryset = ClassificationRule.objects.all().order_by("priority")
    serializer_class = ClassificationRuleSerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ["keyword"]
    ordering_fields = ["priority"]


class AuditLogViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = AuditLog.objects.all()
    serializer_class = AuditLogSerializer
    permission_classes = [permissions.IsAdminUser]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ["action", "user__email"]
    ordering_fields = ["timestamp"]