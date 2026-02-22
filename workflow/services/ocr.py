from PIL import Image, ImageEnhance, ImageFilter
import pytesseract
import os
import re
from pdf2image import convert_from_path
from PyPDF2 import PdfReader
import logging
from datetime import datetime
from workflow.services.file_storage import text_storage

# Configuration du logging
logger = logging.getLogger(__name__)

# Chemin Tesseract (Windows)
TESSERACT_PATH = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
if os.path.exists(TESSERACT_PATH):
    pytesseract.pytesseract.tesseract_cmd = TESSERACT_PATH

class OCRProcessor:
    """Processeur OCR principal amélioré"""
    
    def __init__(self):
        self.text_storage = text_storage  # Importé depuis file_storage
    
    def process_ocr(self, file_path: str, courrier=None):
        """
        Traite un document avec OCR
        
        Args:
            file_path (str): Chemin du fichier
            courrier (Courrier): Objet courrier (optionnel)
            
        Returns:
            str: Texte extrait et nettoyé
        """
        extracted_text = ""
        
        try:
            # Vérifier que le fichier existe
            if not os.path.exists(file_path):
                raise FileNotFoundError(f"Fichier non trouvé: {file_path}")
            
            logger.info(f"Début de l'OCR sur: {file_path}")
            
            # -------------------------
            # CAS 1 : PDF
            # -------------------------
            if file_path.lower().endswith(".pdf"):
                extracted_text = self._process_pdf(file_path)
            
            # -------------------------
            # CAS 2 : IMAGE
            # -------------------------
            else:
                extracted_text = self._process_image(file_path)
            
            # Si aucune extraction, essayer une méthode de secours
            if not extracted_text or len(extracted_text.strip()) < 50:
                logger.warning("Peu de texte extrait, tentative avec méthode alternative")
                extracted_text = self._fallback_extraction(file_path)
            
            # Nettoyage intelligent du texte extrait
            cleaned_text = self._clean_extracted_text(extracted_text)
            
            # Sauvegarde dans le modèle (comportement existant)
            if courrier and cleaned_text:
                courrier.contenu_texte = cleaned_text
                courrier.save(update_fields=["contenu_texte"])
            
            logger.info(f"OCR terminé: {len(cleaned_text)} caractères extraits")
            return cleaned_text
            
        except Exception as e:
            logger.error(f"Erreur OCR: {str(e)}", exc_info=True)
            # Ne pas lever d'exception, retourner un message d'erreur
            return f"ERREUR lors de l'extraction OCR: {str(e)}"
    
    def _fallback_extraction(self, file_path):
        """Méthode de secours pour l'extraction"""
        try:
            if file_path.lower().endswith(".pdf"):
                # Essayer une conversion PDF simple
                images = convert_from_path(file_path, dpi=150)
                text = ""
                for image in images:
                    # Utiliser une configuration minimaliste
                    page_text = pytesseract.image_to_string(
                        image,
                        lang="fra",
                        config="--oem 1 --psm 3"
                    )
                    text += page_text + "\n"
                return text
            else:
                # Pour les images, essayer sans prétraitement
                image = Image.open(file_path)
                return pytesseract.image_to_string(image, lang="fra")
        except Exception as e:
            logger.error(f"Échec méthode de secours: {str(e)}")
            return ""
    
    def _process_pdf(self, file_path):
        """Traite un fichier PDF avec améliorations"""
        extracted_text = ""
        
        # 1. Tentative PDF texte (méthode native)
        try:
            logger.info("Tentative d'extraction texte natif PDF...")
            reader = PdfReader(file_path)
            for page_num, page in enumerate(reader.pages):
                page_text = page.extract_text()
                if page_text and page_text.strip():
                    extracted_text += f"{page_text}\n\n"
            
            if extracted_text.strip():
                logger.info(f"Texte natif PDF extrait: {len(extracted_text)} caractères")
                return extracted_text
        except Exception as e:
            logger.warning(f"PDF texte non lisible avec extract_text(): {str(e)}")
        
        # 2. OCR sur PDF scanné avec améliorations
        try:
            logger.info("Début de l'OCR PDF (document scanné)...")
            
            # Configuration pour améliorer la qualité de conversion
            # Note: Si poppler n'est pas installé, vous devrez peut-être spécifier le chemin
            images = convert_from_path(
                file_path,
                dpi=250,  # Bon compromis qualité/performance
                poppler_path=None  # À ajuster si nécessaire (ex: r"C:\poppler\bin")
            )
            
            logger.info(f"PDF converti en {len(images)} images")
            
            for i, image in enumerate(images):
                logger.info(f"Traitement OCR page {i+1}/{len(images)}")
                
                # Pré-traitement de l'image pour améliorer l'OCR
                processed_image = self._preprocess_image(image)
                
                # Configuration optimisée pour le français - SANS whitelist restrictive
                custom_config = (
                    r'--oem 3 '  # Mode OCR LSTM
                    r'--psm 6 '  # Mode: bloc de texte uniforme
                    r'-c preserve_interword_spaces=1 '
                    r'-c textord_min_linesize=2.5'
                )
                
                page_text = pytesseract.image_to_string(
                    processed_image,
                    lang="fra+eng",  # Français + anglais
                    config=custom_config
                )
                
                if page_text and page_text.strip():
                    # Nettoyage basique de la page
                    page_text = self._clean_page_text(page_text)
                    extracted_text += f"--- Page {i+1} ---\n{page_text}\n\n"
                else:
                    logger.warning(f"Page {i+1}: aucun texte détecté")
            
            if not extracted_text.strip():
                logger.warning("Aucun texte extrait par OCR")
            
            return extracted_text
            
        except Exception as e:
            logger.error(f"OCR PDF impossible: {str(e)}", exc_info=True)
            # Essayer avec une approche plus simple
            try:
                logger.info("Tentative avec approche simplifiée...")
                images = convert_from_path(file_path, dpi=200)
                simple_text = ""
                for image in images:
                    simple_text += pytesseract.image_to_string(image, lang="fra") + "\n\n"
                return simple_text
            except Exception as e2:
                raise ValueError(f"Échec complet OCR PDF: {str(e2)}")
    
    def _process_image(self, file_path):
        """Traite un fichier image avec améliorations"""
        try:
            logger.info(f"Traitement image: {os.path.basename(file_path)}")
            image = Image.open(file_path)
            
            # Pré-traitement de l'image
            processed_image = self._preprocess_image(image)
            
            # Configuration optimisée - SANS whitelist
            custom_config = (
                r'--oem 3 '
                r'--psm 6 '
                r'-c preserve_interword_spaces=1 '
                r'-c textord_min_linesize=2.5'
            )
            
            extracted_text = pytesseract.image_to_string(
                processed_image,
                lang="fra+eng",
                config=custom_config
            )
            
            # Nettoyage du texte extrait
            extracted_text = self._clean_page_text(extracted_text)
            
            logger.info(f"Image traitée: {len(extracted_text)} caractères extraits")
            return extracted_text
            
        except Exception as e:
            logger.error(f"OCR image impossible: {str(e)}", exc_info=True)
            # Essayer sans prétraitement
            try:
                image = Image.open(file_path)
                return pytesseract.image_to_string(image, lang="fra")
            except:
                raise ValueError(f"Échec complet OCR image: {str(e)}")
    
    def _preprocess_image(self, image):
        """
        Pré-traite l'image pour améliorer la qualité de l'OCR
        """
        try:
            # Convertir en niveaux de gris si ce n'est pas déjà le cas
            if image.mode != 'L':
                image = image.convert('L')
            
            # Améliorer le contraste
            try:
                enhancer = ImageEnhance.Contrast(image)
                image = enhancer.enhance(1.3)  # Augmenter le contraste de 30%
            except:
                pass
            
            # Améliorer la netteté
            try:
                enhancer = ImageEnhance.Sharpness(image)
                image = enhancer.enhance(1.2)
            except:
                pass
            
            # Réduction légère du bruit
            try:
                image = image.filter(ImageFilter.MedianFilter(size=1))
            except:
                pass
            
            return image
            
        except Exception as e:
            logger.warning(f"Pré-traitement d'image échoué: {str(e)}")
            return image  # Retourner l'image originale en cas d'erreur
    
    def _clean_page_text(self, text):
        """
        Nettoyage basique du texte d'une page - CONSERVE LE TEXTE
        """
        if not text:
            return ""
        
        # Supprimer les caractères de contrôle non désirés
        text = ''.join(char for char in text if ord(char) >= 32 or char == '\n' or char == '\t')
        
        # Normaliser les sauts de ligne
        text = re.sub(r'\r\n', '\n', text)
        text = re.sub(r'\r', '\n', text)
        
        # Supprimer les lignes vides multiples (conserver au max 2 lignes vides)
        text = re.sub(r'\n{3,}', '\n\n', text)
        
        # Nettoyer les espaces multiples
        text = re.sub(r'[ \t]{2,}', ' ', text)
        
        # Supprimer les espaces en début/fin de ligne
        lines = text.split('\n')
        lines = [line.strip() for line in lines]
        text = '\n'.join(lines)
        
        return text
    
    def _clean_extracted_text(self, text):
        """
        Nettoyage avancé du texte extrait
        - Supprime les en-têtes de page
        - Supprime les noms de fichiers
        - Nettoie les artefacts d'OCR
        """
        if not text:
            return ""
        
        # Créer une copie pour travailler
        cleaned_text = text
        
        # 1. Supprimer les en-têtes de page (--- Page X ---)
        # Mais uniquement si elles sont sur leur propre ligne
        cleaned_text = re.sub(r'^\s*---\s*Page\s*\d+\s*---\s*$', '', cleaned_text, flags=re.MULTILINE)
        
        # 2. Supprimer les noms de fichiers entre --- (uniquement au début)
        cleaned_text = re.sub(r'^\s*---\s*[^-]+\.(pdf|PDF|jpg|jpeg|png|tiff)\s*---\s*', '', cleaned_text, flags=re.MULTILINE)
        
        # 3. Supprimer les marqueurs de début/fin de fichier
        cleaned_text = re.sub(r'^\s*---\s*Courrier\d+\.pdf\s*---\s*$', '', cleaned_text, flags=re.MULTILINE)
        
        # 4. Corriger les erreurs d'OCR courantes MAIS conserver le texte original aussi
        corrections = {
            r'\bMonsicur\b': 'Monsieur',
            r'\bMonsiéur\b': 'Monsieur',
            r'\bbtention\b': 'obtention',
            r'\bdiplame\b': 'diplôme',
            r'\bdiplóme\b': 'diplôme',
            r'\benscignements\b': 'enseignements',
            r'\benseigneéments\b': 'enseignements',
            r'\bsollicitions\b': 'sollicitons',
            r'\beludiants\b': 'étudiants',
            r'\bétudiénts\b': 'étudiants',
            r'\breservee\b': 'réservée',
            r'\brésevée\b': 'réservée',
            r'\brequéte\b': 'requête',
            r'\banticipees\b': 'anticipés',
            r'\banticippés\b': 'anticipés',
            r'\bLincence\b': 'Licence',
            r'\bUnivérsité\b': 'Université',
            r'\bdirecteur\b': 'directeur',
            r'\bpractique\b': 'pratique',
            r'\bminimém\b': 'minimum',
            r'\bformétion\b': 'formation',
        }
        
        for pattern, replacement in corrections.items():
            cleaned_text = re.sub(pattern, replacement, cleaned_text, flags=re.IGNORECASE)
        
        # 5. Réorganiser les paragraphes cassés - APPROCHE CONSERVATIVE
        lines = cleaned_text.split('\n')
        reconstructed_lines = []
        current_paragraph = []
        
        for line in lines:
            line = line.strip()
            if not line:
                # Ligne vide: fin du paragraphe courant
                if current_paragraph:
                    reconstructed_lines.append(' '.join(current_paragraph))
                    current_paragraph = []
                reconstructed_lines.append('')  # Garder une ligne vide
            elif len(line) < 100 and not line.endswith(('.', '!', '?', ':', ';', ',')):
                # Ligne courte sans ponctuation: probablement un titre ou début de paragraphe
                if current_paragraph:
                    reconstructed_lines.append(' '.join(current_paragraph))
                current_paragraph = [line]
            else:
                # Ajouter à paragraphe courant
                current_paragraph.append(line)
        
        # Ajouter le dernier paragraphe s'il existe
        if current_paragraph:
            reconstructed_lines.append(' '.join(current_paragraph))
        
        # 6. Reconstruire le texte
        cleaned_text = '\n'.join(reconstructed_lines)
        
        # 7. Supprimer les lignes très courtes et isolées (bruit) mais être conservatif
        final_lines = []
        for i, line in enumerate(cleaned_text.split('\n')):
            line_stripped = line.strip()
            if len(line_stripped) > 3 or line_stripped == '':
                final_lines.append(line)
            elif i > 0 and i < len(cleaned_text.split('\n')) - 1:
                # Vérifier le contexte: si c'est entre deux lignes de texte, c'est probablement du bruit
                prev_line = cleaned_text.split('\n')[i-1].strip()
                next_line = cleaned_text.split('\n')[i+1].strip()
                if len(prev_line) > 10 and len(next_line) > 10:
                    continue  # Supprimer cette ligne courte entre deux lignes longues
                else:
                    final_lines.append(line)
        
        cleaned_text = '\n'.join(final_lines)
        
        # 8. Nettoyer les espaces et sauts de ligne finaux
        cleaned_text = re.sub(r'\n{3,}', '\n\n', cleaned_text)
        cleaned_text = cleaned_text.strip()
        
        # 9. Si après nettoyage le texte est très court, retourner l'original
        if len(cleaned_text) < 50 and len(text) > 100:
            logger.warning("Nettoyage trop aggressif, retour du texte original nettoyé basiquement")
            return self._clean_page_text(text)
        
        return cleaned_text

# Instance globale pour la rétrocompatibilité
ocr_processor = OCRProcessor()
process_ocr = ocr_processor.process_ocr
