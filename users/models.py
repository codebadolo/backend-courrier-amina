from django.db import models
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from core.models import Service


class Role(models.Model):
    nom = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'users_role'
        verbose_name = "Rôle"
        verbose_name_plural = "Rôles"

    def __str__(self):
        return self.nom


class Permission(models.Model):
    nom = models.CharField(max_length=100, unique=True)
    code = models.CharField(max_length=100, unique=True)  # ex: can_validate_document
    description = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'users_permission'
        verbose_name = "Permission"
        verbose_name_plural = "Permissions"

    def __str__(self):
        return f"{self.nom} ({self.code})"


class RolePermission(models.Model):
    role = models.ForeignKey(Role, on_delete=models.CASCADE, related_name="permissions")
    permission = models.ForeignKey(Permission, on_delete=models.CASCADE)

    class Meta:
        db_table = 'users_role_permission'
        unique_together = ('role', 'permission')

    def __str__(self):
        return f"{self.role.nom} -> {self.permission.code}"


# -------------------------
# Custom User
# -------------------------
class UserManager(BaseUserManager):
    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError("L'email est requis")
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        if password:
            user.set_password(password)
        else:
            user.set_unusable_password()
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("actif", True)

        if extra_fields.get("is_staff") is not True:
            raise ValueError("Superuser must have is_staff=True.")
        if extra_fields.get("is_superuser") is not True:
            raise ValueError("Superuser must have is_superuser=True.")

        return self.create_user(email, password, **extra_fields)


class User(AbstractBaseUser, PermissionsMixin):
    ROLE_CHOICES = (
        ('admin', 'Administrateur'),
        ('direction', 'Direction'),
        ('chef', 'Chef de service'),
        ('collaborateur', 'Collaborateur'),
        ('agent_courrier', 'Agent courrier'),
        ('archiviste', 'Archiviste'),
       ('agent_service', 'Agent de service')
    )

    email = models.EmailField(max_length=191, unique=True)
    nom = models.CharField(max_length=100)
    prenom = models.CharField(max_length=100)

    role = models.CharField(max_length=30, choices=ROLE_CHOICES, default='collaborateur')
    service = models.ForeignKey(Service, on_delete=models.SET_NULL, null=True, blank=True, related_name='membres')

    actif = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # keep Django's groups & permissions relations but avoid naming conflicts with related_name
    groups = models.ManyToManyField('auth.Group', related_name='custom_users', blank=True)
    user_permissions = models.ManyToManyField('auth.Permission', related_name='custom_user_permissions', blank=True)

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['nom', 'prenom']

    objects = UserManager()

    class Meta:
        db_table = 'users_user'
        verbose_name = "Utilisateur"
        verbose_name_plural = "Utilisateurs"
        indexes = [
            models.Index(fields=['email']),
            models.Index(fields=['role']),
        ]

    def __str__(self):
        return f"{self.prenom} {self.nom} <{self.email}>"

    @property
    def is_agent_service(self):
        return self.role == 'agent_service'
    
