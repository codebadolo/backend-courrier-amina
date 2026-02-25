from rest_framework import viewsets, status, permissions
from rest_framework.response import Response
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated, AllowAny
from django.contrib.auth import get_user_model, authenticate
from rest_framework.authtoken.models import Token
from rest_framework import serializers

from rest_framework.decorators import api_view
from rest_framework.response import Response
from users.models import User
from .models import Role, Permission, RolePermission
from .serializers import (
    LoginSerializer,
    UserDetailSerializer,
    UserListSerializer,
    UserCreateSerializer,
    UserUpdateSerializer,
    ChangePasswordSerializer,
    RoleSerializer,
    PermissionSerializer,
    RolePermissionSerializer,
)

from .serializers import UserSerializer
User = get_user_model()


# -------------------------
# Auth ViewSet
# -------------------------
class AuthViewSet(viewsets.ViewSet):
    permission_classes = [AllowAny]

    @action(detail=False, methods=["post"])
    def login(self, request):
        email = request.data.get("email")
        password = request.data.get("password")

        if not email or not password:
            return Response(
                {"detail": "Email et mot de passe requis"},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            # 1. Chercher l'utilisateur par email
            user = User.objects.get(email=email)
            
            # 2. Vérifier si l'utilisateur est actif
            if not user.actif:
                return Response(
                    {"detail": "Compte désactivé"},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # 3. Vérifier le mot de passe
            if user.check_password(password):
                # 4. Créer ou récupérer le token
                token, created = Token.objects.get_or_create(user=user)
                
                # 5. Préparer les données de réponse
                from .serializers import UserDetailSerializer
                user_data = UserDetailSerializer(user).data
                
                return Response({
                    "token": token.key,
                    "user": user_data
                })
            else:
                return Response(
                    {"detail": "Identifiants incorrects"},
                    status=status.HTTP_400_BAD_REQUEST
                )
                
        except User.DoesNotExist:
            return Response(
                {"detail": "Identifiants incorrects"},
                status=status.HTTP_400_BAD_REQUEST
            )
        except Exception as e:
            print(f"Erreur lors de la connexion: {str(e)}")
            return Response(
                {"detail": "Erreur serveur"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
# -------------------------
# User ViewSet
# -------------------------
class UserViewSet(viewsets.ModelViewSet):
    queryset = User.objects.all()
    permission_classes = [IsAuthenticated]

    def get_serializer_class(self):
        """
        Retourne le serializer approprié selon l'action
        """
        if self.action == "list":
            return UserListSerializer
        elif self.action == "create":
            return UserCreateSerializer
        elif self.action in ["update", "partial_update"]:
            return UserUpdateSerializer
        return UserDetailSerializer

    @action(detail=True, methods=["post"])
    def activate(self, request, pk=None):
        user = self.get_object()
        user.actif = True
        user.save()
        return Response({"detail": "Utilisateur activé"})

    @action(detail=True, methods=["post"])
    def deactivate(self, request, pk=None):
        user = self.get_object()
        user.actif = False
        user.save()
        return Response({"detail": "Utilisateur désactivé"})

    @action(detail=False, methods=["post"], permission_classes=[IsAuthenticated])
    def change_password(self, request):
        serializer = ChangePasswordSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = request.user
        if not user.check_password(serializer.validated_data["old_password"]):
            return Response({"detail": "Ancien mot de passe incorrect"}, status=400)
        user.set_password(serializer.validated_data["new_password"])
        user.save()
        return Response({"detail": "Mot de passe modifié"})
    @action(detail=False, methods=['get'], url_path='par-service')
    def get_users_by_service(self, request):
        """Retourne les utilisateurs d'un service (filtrage optionnel par rôle)"""
        service_id = request.query_params.get('service')
        roles = request.query_params.getlist('role')  # ex: ?role=agent_service&role=collaborateur

        if not service_id:
            return Response(
                {"error": "Le paramètre 'service' est requis"},
                status=status.HTTP_400_BAD_REQUEST
            )

        queryset = User.objects.filter(service_id=service_id, is_active=True)
        if roles:
            queryset = queryset.filter(role__in=roles)

        data = [{
            'id': user.id,
            'username': user.username,
            'full_name': user.get_full_name() or user.username,
            'email': user.email,
            'role': user.role,
            'role_display': user.get_role_display()
        } for user in queryset]

        return Response(data)

    @action(detail=False, methods=['get'])
    def par_service(self, request):
        service_id = request.query_params.get('service')
        roles = request.query_params.getlist('role')
        if not service_id:
            return Response({"error": "Le paramètre 'service' est requis."}, status=400)
        queryset = User.objects.filter(service_id=service_id, actif=True)
        if roles:
            queryset = queryset.filter(role__in=roles)
        serializer = UserSerializer(queryset, many=True)
        return Response(serializer.data)
    
@api_view(['GET'])
def get_role_choices(request):
    roles = [
        {"value": "admin", "label": "Administrateur"},
        {"value": "direction", "label": "Direction"},
        {"value": "chef", "label": "Chef de service"},
        {"value": "collaborateur", "label": "Collaborateur"},
        {"value": "agent_courrier", "label": "Agent courrier"},
        {"value": "archiviste", "label": "Archiviste"},
        {"value": "agent_service", "label": "Agent de service"},
    ]
    return Response(roles)
    
@api_view(['GET'])
def get_current_user(request):
    """Retourne les informations de l'utilisateur connecté"""
    serializer = UserSerializer(request.user)
    return Response(serializer.data)

# Role, Permission & RolePermission
# -------------------------
class RoleViewSet(viewsets.ModelViewSet):
    queryset = Role.objects.all()
    serializer_class = RoleSerializer
    permission_classes = [IsAuthenticated]


class PermissionViewSet(viewsets.ModelViewSet):
    queryset = Permission.objects.all()
    serializer_class = PermissionSerializer
    permission_classes = [IsAuthenticated]


class RolePermissionViewSet(viewsets.ModelViewSet):
    queryset = RolePermission.objects.all()
    serializer_class = RolePermissionSerializer
    permission_classes = [IsAuthenticated]

# users/views.py - Ajouter cette classe
class ServiceMembersViewSet(viewsets.ViewSet):
    """
    Gestion des membres d'un service
    """
    permission_classes = [IsAuthenticated]
    
    @action(detail=True, methods=['get'], url_path='membres')
    def list_members(self, request, pk=None):
        """
        Lister tous les membres d'un service
        """
        try:
            from core.models import Service
            service = Service.objects.get(pk=pk)
            
            # Vérifier si l'utilisateur a le droit de voir les membres
            if not (request.user.is_superuser or 
                    request.user == service.chef or
                    request.user.role in ['admin', 'direction']):
                return Response(
                    {"error": "Vous n'avez pas la permission de voir les membres de ce service"},
                    status=status.HTTP_403_FORBIDDEN
                )
            
            # Récupérer tous les membres du service
            membres = User.objects.filter(service=service).exclude(role='chef')
            
            serializer = UserListSerializer(membres, many=True)
            return Response(serializer.data)
            
        except Service.DoesNotExist:
            return Response(
                {"error": "Service non trouvé"},
                status=status.HTTP_404_NOT_FOUND
            )
    
    @action(detail=True, methods=['post'], url_path='ajouter-membre')
    def add_member(self, request, pk=None):
        """
        Ajouter un utilisateur comme membre d'un service
        """
        try:
            service = Service.objects.get(pk=pk)
            user_id = request.data.get('user_id')
            
            # Vérifier les permissions
            if not (request.user.is_superuser or 
                    request.user == service.chef or
                    request.user.role == 'admin'):
                return Response(
                    {"error": "Vous n'avez pas la permission d'ajouter des membres à ce service"},
                    status=status.HTTP_403_FORBIDDEN
                )
            
            # Trouver l'utilisateur
            user = User.objects.get(pk=user_id)
            
            # Vérifier que l'utilisateur n'est pas déjà chef d'un autre service
            if user.role == 'chef' and Service.objects.filter(chef=user).exists():
                return Response(
                    {"error": "Cet utilisateur est déjà chef d'un service"},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Affecter l'utilisateur au service
            user.service = service
            # Si c'est un agent de service, s'assurer que son rôle est correct
            if request.data.get('role') == 'agent_service':
                user.role = 'agent_service'
            user.save()
            
            # Journaliser l'action
            from core.models import AuditLog
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
            
        except Service.DoesNotExist:
            return Response(
                {"error": "Service non trouvé"},
                status=status.HTTP_404_NOT_FOUND
            )
        except User.DoesNotExist:
            return Response(
                {"error": "Utilisateur non trouvé"},
                status=status.HTTP_404_NOT_FOUND
            )
    
    @action(detail=True, methods=['post'], url_path='retirer-membre')
    def remove_member(self, request, pk=None):
        """
        Retirer un utilisateur d'un service
        """
        try:
            service = Service.objects.get(pk=pk)
            user_id = request.data.get('user_id')
            
            # Vérifier les permissions
            if not (request.user.is_superuser or 
                    request.user == service.chef or
                    request.user.role == 'admin'):
                return Response(
                    {"error": "Vous n'avez pas la permission de retirer des membres de ce service"},
                    status=status.HTTP_403_FORBIDDEN
                )
            
            # Trouver l'utilisateur
            user = User.objects.get(pk=user_id)
            
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
            from core.models import AuditLog
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
            
        except Service.DoesNotExist:
            return Response(
                {"error": "Service non trouvé"},
                status=status.HTTP_404_NOT_FOUND
            )
        except User.DoesNotExist:
            return Response(
                {"error": "Utilisateur non trouvé"},
                status=status.HTTP_404_NOT_FOUND
            )