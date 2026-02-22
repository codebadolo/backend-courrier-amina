# courriers/migrations/0002_add_priority_field.py
from django.db import migrations, models

class Migration(migrations.Migration):
    dependencies = [
        ('courriers', '0001_initial'),
    ]
    
    operations = [
        migrations.AddField(
            model_name='courrier',
            name='priorite',
            field=models.CharField(
                choices=[
                    ('basse', 'Basse'),
                    ('normale', 'Normale'),
                    ('haute', 'Haute'),
                    ('urgente', 'Urgente'),
                ],
                default='normale',
                max_length=20,
            ),
        ),
    ]