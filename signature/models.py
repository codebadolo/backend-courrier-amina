from django.db import models

# Create your models here.
# créer signature/models.py

class Signature(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    courrier = models.ForeignKey(Courrier, on_delete=models.CASCADE, related_name='signatures')
    type_signature = models.CharField(max_length=20, choices=[
        ('simple', 'Signature simple'),
        ('qualifiee', 'Signature qualifiée'),
        ('timestamp', 'Horodatage'),
    ])
    fichier_signature = models.FileField(upload_to='signatures/')
    certificat_info = models.JSONField(default=dict, blank=True)
    signe_le = models.DateTimeField(auto_now_add=True)
    valide_jusquau = models.DateField(null=True, blank=True)
    
    class Meta:
        db_table = 'signature_signature'
