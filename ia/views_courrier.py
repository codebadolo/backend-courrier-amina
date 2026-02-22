# ia/views_courrier.py
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from django.shortcuts import get_object_or_404
from courriers.models import Courrier
from workflow.services.gemini_courrier_service import gemini_courrier_service
import logging

logger = logging.getLogger(__name__)

class AnalyserCourrierAPIView(APIView):
    """
    API pour analyser un courrier existant avec Gemini
    """
    permission_classes = [IsAuthenticated]
    
    def post(self, request, courrier_id):
        courrier = get_object_or_404(Courrier, id=courrier_id)
        
        try:
            # Analyser le courrier
            analyse_data = gemini_courrier_service.analyser_courrier(courrier)
            
            if analyse_data:
                return Response({
                    "success": True,
                    "courrier_id": courrier.id,
                    "reference": courrier.reference,
                    "analyse": analyse_data,
                    "message": "Analyse terminée avec succès"
                })
            else:
                return Response({
                    "success": False,
                    "error": "Échec de l'analyse Gemini",
                    "courrier_id": courrier.id
                }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
                
        except Exception as e:
            logger.error(f"Erreur analyse courrier {courrier_id}: {e}")
            return Response({
                "success": False,
                "error": str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class GenererReponseAPIView(APIView):
    """
    API pour générer une réponse automatique avec Gemini
    """
    permission_classes = [IsAuthenticated]
    
    def post(self, request, courrier_id):
        courrier = get_object_or_404(Courrier, id=courrier_id)
        
        try:
            # Générer la réponse
            result = gemini_courrier_service.suggérer_reponse(courrier)
            
            if result and result["success"]:
                # Mettre à jour le courrier
                courrier.reponse_suggeree = result["reponse"]
                courrier.save(update_fields=['reponse_suggeree'])
                
                return Response({
                    "success": True,
                    "courrier_id": courrier.id,
                    "reponse": result["reponse"],
                    "model_used": result.get("model_used"),
                    "token_usage": result.get("token_usage", {}),
                    "message": "Réponse générée avec succès"
                })
            else:
                return Response({
                    "success": False,
                    "error": result.get("error") if result else "Erreur inconnue",
                    "courrier_id": courrier.id
                }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
                
        except Exception as e:
            logger.error(f"Erreur génération réponse {courrier_id}: {e}")
            return Response({
                "success": False,
                "error": str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class BatchAnalyserCourriersAPIView(APIView):
    """
    API pour analyser plusieurs courriers en batch
    """
    permission_classes = [IsAuthenticated]
    
    def post(self, request):
        courrier_ids = request.data.get("courrier_ids", [])
        limit = request.data.get("limit", 10)
        
        if not courrier_ids:
            # Analyser les courriers non analysés
            courriers = Courrier.objects.filter(
                meta_analyse={},
                contenu_texte__isnull=False
            )[:limit]
            courrier_ids = list(courriers.values_list('id', flat=True))
        
        results = []
        
        for courrier_id in courrier_ids[:limit]:  # Limiter pour éviter la surcharge
            try:
                courrier = Courrier.objects.get(id=courrier_id)
                analyse_data = gemini_courrier_service.analyser_courrier(courrier)
                
                if analyse_data:
                    results.append({
                        "courrier_id": courrier.id,
                        "reference": courrier.reference,
                        "success": True,
                        "categorie": analyse_data.get("classification", {}).get("categorie_suggeree"),
                        "service": analyse_data.get("classification", {}).get("service_suggere")
                    })
                else:
                    results.append({
                        "courrier_id": courrier.id,
                        "success": False,
                        "error": "Échec analyse"
                    })
                    
            except Exception as e:
                results.append({
                    "courrier_id": courrier_id,
                    "success": False,
                    "error": str(e)
                })
        
        return Response({
            "success": True,
            "total": len(results),
            "analyses": results
        })