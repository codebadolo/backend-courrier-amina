# ia/services/gemini_service.py
import requests
import json
from django.conf import settings
import logging
from typing import Dict, Optional

logger = logging.getLogger(__name__)

class GeminiService:
    def __init__(self):
        self.api_key = settings.GEMINI_API_KEY
        # Utilisez le modèle que vous avez trouvé
        self.default_model = "gemini-2.5-flash"
        self.api_base_url = "https://generativelanguage.googleapis.com/v1beta/models"
    
    def generate_content(self, prompt: str, model_name: Optional[str] = None) -> Dict:
        """
        Envoie un prompt à l'API Gemini
        """
        model = model_name or self.default_model
        
        try:
            # URL complète avec le modèle
            url = f"{self.api_base_url}/{model}:generateContent?key={self.api_key}"
            
            # Structure de la requête Gemini
            payload = {
                "contents": [{
                    "parts": [{
                        "text": prompt
                    }]
                }],
                "generationConfig": {
                    "temperature": 0.7,
                    "topP": 0.8,
                    "topK": 40,
                    "maxOutputTokens": 2048,
                },
                "safetySettings": [
                    {
                        "category": "HARM_CATEGORY_HARASSMENT",
                        "threshold": "BLOCK_MEDIUM_AND_ABOVE"
                    },
                    {
                        "category": "HARM_CATEGORY_HATE_SPEECH", 
                        "threshold": "BLOCK_MEDIUM_AND_ABOVE"
                    },
                    {
                        "category": "HARM_CATEGORY_SEXUALLY_EXPLICIT",
                        "threshold": "BLOCK_MEDIUM_AND_ABOVE"
                    },
                    {
                        "category": "HARM_CATEGORY_DANGEROUS_CONTENT",
                        "threshold": "BLOCK_MEDIUM_AND_ABOVE"
                    }
                ]
            }
            
            # En-têtes
            headers = {
                "Content-Type": "application/json"
            }
            
            logger.info(f"Appel Gemini avec modèle: {model}")
            logger.debug(f"Prompt: {prompt}")
            
            # Envoi de la requête
            response = requests.post(
                url, 
                headers=headers, 
                data=json.dumps(payload),
                timeout=30
            )
            
            # Journaliser la réponse brute (pour débogage)
            logger.debug(f"Statut Gemini: {response.status_code}")
            
            # Vérification de la réponse
            if response.status_code == 200:
                data = response.json()
                
                # Structure de réponse Gemini
                if "candidates" in data and len(data["candidates"]) > 0:
                    candidate = data["candidates"][0]
                    
                    # Vérifier si la réponse a été bloquée
                    if "finishReason" in candidate and candidate["finishReason"] == "SAFETY":
                        return {
                            "success": False,
                            "error": "La réponse a été bloquée pour des raisons de sécurité",
                            "finish_reason": candidate.get("finishReason"),
                            "safety_ratings": candidate.get("safetyRatings", []),
                            "raw_response": data
                        }
                    
                    # Extraire le texte
                    if "content" in candidate and "parts" in candidate["content"]:
                        text = candidate["content"]["parts"][0]["text"]
                        
                        # Informations de token
                        prompt_token_count = data.get("usageMetadata", {}).get("promptTokenCount", 0)
                        candidates_token_count = data.get("usageMetadata", {}).get("candidatesTokenCount", 0)
                        
                        return {
                            "success": True,
                            "text": text,
                            "model_used": model,
                            "finish_reason": candidate.get("finishReason"),
                            "prompt_token_count": prompt_token_count,
                            "candidates_token_count": candidates_token_count,
                            "raw_response": data
                        }
                
                # Si la structure est différente
                return {
                    "success": False,
                    "error": "Structure de réponse inattendue",
                    "raw_response": data
                }
                    
            else:
                # Erreur de l'API
                error_detail = response.text
                try:
                    error_json = response.json()
                    error_detail = error_json.get("error", {}).get("message", error_detail)
                except:
                    pass
                    
                return {
                    "success": False,
                    "error": f"Erreur API Gemini ({response.status_code}): {error_detail}",
                    "status_code": response.status_code,
                    "raw_response": response.text
                }
                
        except requests.exceptions.Timeout:
            logger.error("Timeout lors de l'appel à l'API Gemini")
            return {
                "success": False,
                "error": "Timeout de l'API Gemini"
            }
        except Exception as e:
            logger.error(f"Erreur avec Gemini API: {str(e)}", exc_info=True)
            return {
                "success": False,
                "error": f"Exception: {str(e)}"
            }

    def batch_generate_content(self, prompts: list, model_name: Optional[str] = None) -> Dict:
        """
        Génère du contenu pour plusieurs prompts (batch)
        """
        model = model_name or self.default_model
        
        try:
            url = f"{self.api_base_url}/{model}:batchGenerateContent?key={self.api_key}"
            
            # Préparer les requêtes batch
            requests_list = []
            for prompt in prompts:
                requests_list.append({
                    "contents": [{
                        "parts": [{
                            "text": prompt
                        }]
                    }]
                })
            
            payload = {
                "requests": requests_list
            }
            
            headers = {
                "Content-Type": "application/json"
            }
            
            response = requests.post(
                url,
                headers=headers,
                data=json.dumps(payload),
                timeout=60
            )
            
            if response.status_code == 200:
                data = response.json()
                results = []
                
                for resp in data.get("responses", []):
                    if "candidates" in resp and len(resp["candidates"]) > 0:
                        text = resp["candidates"][0]["content"]["parts"][0]["text"]
                        results.append({
                            "success": True,
                            "text": text
                        })
                    else:
                        results.append({
                            "success": False,
                            "error": "Pas de réponse valide"
                        })
                
                return {
                    "success": True,
                    "results": results,
                    "model_used": model
                }
            else:
                return {
                    "success": False,
                    "error": f"Erreur batch: {response.status_code}",
                    "status_code": response.status_code
                }
                
        except Exception as e:
            logger.error(f"Erreur batch Gemini: {e}")
            return {
                "success": False,
                "error": str(e)
            }

# Instance globale
gemini_service = GeminiService()

# Fonction utilitaire
def ask_gemini(prompt: str, model_name: Optional[str] = None) -> Dict:
    return gemini_service.generate_content(prompt, model_name)