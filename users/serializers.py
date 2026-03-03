from rest_framework import serializers
from .models import User, Role, Permission, RolePermission, Service
from rest_framework.permissions import IsAuthenticated
from core.models import Service 

from rest_framework import serializers
from django.contrib.auth import authenticate
from .models import User

class UserSerializer(serializers.ModelSerializer):
    service = serializers.CharField(source='service.nom', read_only=True)
    permission_classes = [IsAuthenticated]

    class Meta:
        model = User
        fields = [
            "id",
            "email",
            "nom",
            "prenom",
            "role",
            "service",
            "actif",
        ]

    def get_serializer_class(self):
        if self.action == "list":
            return UserListSerializer
        elif self.action == "create":
            return UserCreateSerializer
        elif self.action in ["update", "partial_update"]:
            return UserUpdateSerializer
        elif self.action == "retrieve":
            return UserDetailSerializer
        return UserSerializer

    # Optionnel : forcer la liste pour être sûr
    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        serializer = UserListSerializer(queryset, many=True)
        return Response(serializer.data)

class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True)

    def validate(self, attrs):
        email = attrs.get("email")
        password = attrs.get("password")

        if email and password:
            user = authenticate(email=email, password=password)
            if not user:
                raise serializers.ValidationError("Email ou mot de passe incorrect")
            attrs["user"] = user
            return attrs
        raise serializers.ValidationError("Email et mot de passe sont requis")

# -------------------------
# User serializers
# -------------------------
class UserListSerializer(serializers.ModelSerializer):
    role_display = serializers.CharField(source="get_role_display", read_only=True)
    service_name = serializers.CharField(source="service.nom", read_only=True)
    full_name = serializers.SerializerMethodField()
    last_login = serializers.DateTimeField(
        read_only=True, 
        format='%d/%m/%Y %H:%M', 
        allow_null=True
    )
    created_at = serializers.DateTimeField(
        format='%d/%m/%Y %H:%M', 
        read_only=True
    )

    class Meta:
        model = User
        fields = [
            "id",
            "prenom",
            "nom",
            "full_name",
            "email",
            "role",
            "role_display",
            "service_name",
            "actif",
            "is_staff",
            "created_at",
            "updated_at",
            "last_login",
        ]
    
    def get_full_name(self, obj):
        return f"{obj.prenom} {obj.nom}"

class UserDetailSerializer(serializers.ModelSerializer):
    role_display = serializers.CharField(source="get_role_display", read_only=True)
    service_name = serializers.CharField(source="service.nom", read_only=True)
    full_name = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            "id",
            "prenom",
            "nom",
            "full_name",
            "email",
            "role",
            "role_display",
            "service",
            "service_name",
            "actif",
            "is_staff",
            "is_superuser",
            "groups",
            "user_permissions",
            "created_at",
            "updated_at",
        ]
    
    def get_full_name(self, obj):
        return f"{obj.prenom} {obj.nom}"

class UserCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ["email", "prenom", "nom", "role", "service", "password"]

    def create(self, validated_data):
        password = validated_data.pop("password", None)
        user = super().create(validated_data)
        if password:
            user.set_password(password)
            user.save()
        return user

# users/serializers.py
class UserUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['email', 'prenom', 'nom', 'role', 'service', 'actif']


class ChangePasswordSerializer(serializers.Serializer):
    old_password = serializers.CharField(write_only=True)
    new_password = serializers.CharField(write_only=True)
    confirm_password = serializers.CharField(write_only=True)

    def validate(self, data):
        if data["new_password"] != data["confirm_password"]:
            raise serializers.ValidationError("Les mots de passe ne correspondent pas.")
        return data

# -------------------------
# Roles & permissions
# -------------------------
class PermissionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Permission
        fields = "__all__"

class RoleSerializer(serializers.ModelSerializer):
    permissions = serializers.SerializerMethodField()

    class Meta:
        model = Role
        fields = ["id", "nom", "description", "created_at", "permissions"]

    def get_permissions(self, obj):
        perms = Permission.objects.filter(rolepermission__role=obj)
        return PermissionSerializer(perms, many=True).data

class RolePermissionSerializer(serializers.ModelSerializer):
    class Meta:
        model = RolePermission
        fields = "__all__"

# users/serializers.py - Ajouter cette classe
class ServiceAgentAssignmentSerializer(serializers.ModelSerializer):
    """
    Serializer pour l'affectation des agents de service
    """
    service_membres = serializers.SerializerMethodField()
    available_agents = serializers.SerializerMethodField()
    
    class Meta:
        model = Service
        fields = [
            'id', 'nom', 'chef', 'chef_detail',
            'description', 'service_membres', 'available_agents'
        ]
    
    def get_service_membres(self, obj):
        """Récupère tous les membres du service (excluant le chef)"""
        membres = obj.membres.exclude(id=obj.chef.id if obj.chef else None)
        return UserListSerializer(membres, many=True).data
    
    def get_available_agents(self, obj):
        """Récupère les utilisateurs disponibles pour être affectés au service"""
        # Utilisateurs sans service OU déjà membres d'autres services
        from .models import User
        available = User.objects.filter(
            Q(service__isnull=True) | Q(service=obj),
            role__in=['collaborateur', 'agent_service'],
            actif=True
        ).exclude(id=obj.chef.id if obj.chef else None)
        
        return UserListSerializer(available, many=True).data


class AgentAssignmentSerializer(serializers.Serializer):
    """
    Serializer pour l'affectation d'un agent à un service
    """
    user_id = serializers.IntegerField(required=True)
    role = serializers.ChoiceField(
        choices=['agent_service', 'collaborateur'],
        default='agent_service'
    )