from rest_framework import serializers
from .models import RapportStatistique


class RapportStatistiqueSerializer(serializers.ModelSerializer):
    class Meta:
        model = RapportStatistique
        fields = [
            "id",
            "titre",
            "periode_debut",
            "periode_fin",
            "data",
            "created_at",
            "generated_by",
        ]
        read_only_fields = ["created_at"]
