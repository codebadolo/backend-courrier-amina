from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from django.shortcuts import get_object_or_404

from .models import IAResult
from .serializers import IAResultSerializer
from courriers.models import Courrier
from .tasks import process_courrier_automatique
from django.utils import timezone

class IAResultViewSet(viewsets.ModelViewSet):
    queryset = IAResult.objects.all()
    serializer_class = IAResultSerializer

    @action(detail=True, methods=["post"])
    def process_auto(self, request, pk=None):
        """
        Traite automatiquement un courrier : OCR + NLP + workflow IA
        """
        courrier = get_object_or_404(Courrier, pk=pk)
        ia_result, workflow = process_courrier_automatique(courrier)
        serializer = IAResultSerializer(ia_result)
        return Response(serializer.data, status=status.HTTP_200_OK)

# ia/views.py
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated , AllowAny
from django.utils import timezone
from .services.gemini_service import gemini_service

class TestGeminiAPIView(APIView):
    """
    API pour tester l'API Gemini avec un prompt
    """
    permission_classes = [AllowAny]
    
    def post(self, request):
        # Récupérer le prompt et le modèle
        prompt = request.data.get("prompt", "")
        model_name = request.data.get("model", "gemini-2.5-flash")
        
        if not prompt:
            return Response(
                {"error": "Le champ 'prompt' est requis"},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Validation du prompt (limite de longueur)
        if len(prompt) > 10000:
            return Response(
                {"error": "Le prompt est trop long (max 10000 caractères)"},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Appeler l'API Gemini
        result = gemini_service.generate_content(prompt, model_name)
        
        if result["success"]:
            response_data = {
                "success": True,
                "prompt": prompt,
                "model_used": result.get("model_used", "gemini-2.5-flash"),
                "response": result["text"],
                "finish_reason": result.get("finish_reason"),
                "token_usage": {
                    "prompt_tokens": result.get("prompt_token_count", 0),
                    "candidates_tokens": result.get("candidates_token_count", 0),
                    "total_tokens": result.get("prompt_token_count", 0) + result.get("candidates_token_count", 0)
                },
                "timestamp": timezone.now().isoformat()
            }
            
            # Inclure la réponse brute uniquement si debug est activé
            if request.query_params.get("debug") == "true":
                response_data["raw_response"] = result.get("raw_response")
            
            return Response(response_data)
        else:
            return Response({
                "success": False,
                "prompt": prompt,
                "model_requested": model_name,
                "error": result.get("error", "Erreur inconnue"),
                "status_code": result.get("status_code"),
                "timestamp": timezone.now().isoformat()
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class BatchTestGeminiAPIView(APIView):
    """
    API pour tester plusieurs prompts en batch
    """
    permission_classes = [IsAuthenticated]
    
    def post(self, request):
        prompts = request.data.get("prompts", [])
        model_name = request.data.get("model", "gemini-2.5-flash")
        
        if not prompts or not isinstance(prompts, list):
            return Response(
                {"error": "Le champ 'prompts' est requis et doit être une liste"},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        if len(prompts) > 10:
            return Response(
                {"error": "Maximum 10 prompts en batch"},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        result = gemini_service.batch_generate_content(prompts, model_name)
        
        if result["success"]:
            return Response({
                "success": True,
                "model_used": result.get("model_used"),
                "results": result.get("results", []),
                "timestamp": timezone.now().isoformat()
            })
        else:
            return Response({
                "success": False,
                "error": result.get("error", "Erreur batch inconnue"),
                "timestamp": timezone.now().isoformat()
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        
class AnalyserCourrierAPIView(APIView):
    """
    API pour analyser un courrier spécifique avec Gemini
    """
    permission_classes = [IsAuthenticated]
    
    def post(self, request, courrier_id):
        courrier = get_object_or_404(Courrier, pk=courrier_id)
        prompt = f"Analyser le contenu du courrier suivant : {courrier.content}"
        
        result = gemini_service.generate_content(prompt)
        
        if result["success"]:
            return Response({
                "success": True,
                "courrier_id": courrier_id,
                "analysis": result["text"],
                "timestamp": timezone.now().isoformat()
            })
        else:
            return Response({
                "success": False,
                "courrier_id": courrier_id,
                "error": result.get("error", "Erreur d'analyse inconnue"),
                "timestamp": timezone.now().isoformat()
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class GenererReponseAPIView(APIView):
    """
    API pour générer une réponse à un courrier spécifique avec Gemini
    """
    permission_classes = [IsAuthenticated]
    
    def post(self, request, courrier_id):
        courrier = get_object_or_404(Courrier, pk=courrier_id)
        prompt = f"Générer une réponse professionnelle au courrier suivant : {courrier.content}"
        
        result = gemini_service.generate_content(prompt)
        
        if result["success"]:
            return Response({
                "success": True,
                "courrier_id": courrier_id,
                "response": result["text"],
                "timestamp": timezone.now().isoformat()
            })
        else:
            return Response({
                "success": False,
                "courrier_id": courrier_id,
                "error": result.get("error", "Erreur de génération de réponse inconnue"),
                "timestamp": timezone.now().isoformat()
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        
class BatchAnalyserCourriersAPIView(APIView):
    """
    API pour analyser plusieurs courriers en batch avec Gemini
    """
    permission_classes = [IsAuthenticated]
    
    def post(self, request):
        courrier_ids = request.data.get("courrier_ids", [])
        
        if not courrier_ids or not isinstance(courrier_ids, list):
            return Response(
                {"error": "Le champ 'courrier_ids' est requis et doit être une liste"},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        if len(courrier_ids) > 10:
            return Response(
                {"error": "Maximum 10 courriers en batch"},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        results = []
        for cid in courrier_ids:
            courrier = get_object_or_404(Courrier, pk=cid)
            prompt = f"Analyser le contenu du courrier suivant : {courrier.content}"
            result = gemini_service.generate_content(prompt)
            
            if result["success"]:
                results.append({
                    "courrier_id": cid,
                    "analysis": result["text"]
                })
            else:
                results.append({
                    "courrier_id": cid,
                    "error": result.get("error", "Erreur d'analyse inconnue")
                })
        
        return Response({
            "success": True,
            "results": results,
            "timestamp": timezone.now().isoformat()
        })