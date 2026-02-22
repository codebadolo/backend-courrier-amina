from rest_framework import serializers
from core.serializers import ServiceSerializer, CategorySerializer
from .models import IAResult


class IAResultSerializer(serializers.ModelSerializer):
    categorie_predite = CategorySerializer(read_only=True)
    service_suggere = ServiceSerializer(read_only=True)

    class Meta:
        model = IAResult
        fields = "__all__"
