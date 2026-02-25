# courriers/utils/pdf_utils.py
import io
import os
from PyPDF2 import PdfReader, PdfWriter
from django.conf import settings
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

def fusionner_avec_entete(contenu_pdf_buffer, entete_pdf_path=None):
    """
    Fusionne le contenu PDF avec l'en-tête ZEPINTEL
    L'en-tête est placé en arrière-plan, le contenu par-dessus
    
    Args:
        contenu_pdf_buffer: BytesIO buffer contenant le PDF généré
        entete_pdf_path: Chemin vers le fichier PDF d'en-tête (optionnel)
    
    Returns:
        BytesIO buffer avec le PDF fusionné
    """
    try:
        # Si aucun chemin d'en-tête n'est fourni, utiliser le chemin par défaut
        if entete_pdf_path is None:
            entete_pdf_path = r"C:\MesProjets\gestion_courrier\frontend-admin-courrier-amina\public\images\Papier entete zepintel_vf.pdf"
        
        # Vérifier que le fichier d'en-tête existe
        if not os.path.exists(entete_pdf_path):
            logger.warning(f"Fichier d'en-tête non trouvé: {entete_pdf_path}")
            return contenu_pdf_buffer
        
        logger.info(f"Fichier d'en-tête trouvé: {entete_pdf_path}")
        
        # Lire l'en-tête et le contenu
        entete = PdfReader(entete_pdf_path)
        contenu = PdfReader(contenu_pdf_buffer)
        
        # Vérifier que l'en-tête a au moins une page
        if len(entete.pages) == 0:
            logger.warning("Le fichier d'en-tête est vide")
            return contenu_pdf_buffer
        
        output = PdfWriter()
        
        # Obtenir la page d'en-tête
        page_entete = entete.pages[0]
        
        # Dimensions de la page d'en-tête
        entete_box = page_entete.mediabox
        
        # Pour chaque page du contenu
        for i, page in enumerate(contenu.pages):
            if i == 0:
                # Créer une nouvelle page vierge aux dimensions A4
                from reportlab.pdfgen import canvas
                from reportlab.lib.pagesizes import A4
                
                # Créer un buffer temporaire pour la page fusionnée
                temp_buffer = io.BytesIO()
                c = canvas.Canvas(temp_buffer, pagesize=A4)
                
                # Terminer le canvas pour créer une page vierge
                c.showPage()
                c.save()
                
                temp_buffer.seek(0)
                temp_pdf = PdfReader(temp_buffer)
                nouvelle_page = temp_pdf.pages[0]
                
                # Fusionner l'en-tête en arrière-plan
                nouvelle_page.merge_page(page_entete)
                
                # Fusionner le contenu par-dessus
                nouvelle_page.merge_page(page)
                
                output.add_page(nouvelle_page)
            else:
                # Pour les pages suivantes, ajouter le contenu tel quel
                output.add_page(page)
        
        # Écrire le résultat dans un buffer
        result_buffer = io.BytesIO()
        output.write(result_buffer)
        result_buffer.seek(0)
        
        logger.info(f"Fusion PDF réussie: {len(contenu.pages)} page(s) traitée(s)")
        return result_buffer
        
    except Exception as e:
        logger.error(f"Erreur lors de la fusion PDF: {str(e)}", exc_info=True)
        # En cas d'erreur, retourner le contenu original
        return contenu_pdf_buffer


def fusionner_avec_entete_v2(contenu_pdf_buffer, entete_pdf_path=None):
    """
    Version alternative: Crée d'abord une page avec l'en-tête,
    puis ajoute le contenu par-dessus avec un décalage
    """
    try:
        if entete_pdf_path is None:
            entete_pdf_path = r"C:\MesProjets\gestion_courrier\frontend-admin-courrier-amina\public\images\Papier entete zepintel_vf.pdf"
        
        if not os.path.exists(entete_pdf_path):
            return contenu_pdf_buffer
        
        # Lire les PDFs
        entete = PdfReader(entete_pdf_path)
        contenu = PdfReader(contenu_pdf_buffer)
        
        output = PdfWriter()
        
        # Dimensions A4
        from reportlab.lib.pagesizes import A4
        width, height = A4
        
        for i, page in enumerate(contenu.pages):
            if i == 0:
                # Créer une nouvelle page avec l'en-tête en arrière-plan
                from reportlab.pdfgen import canvas
                
                temp_buffer = io.BytesIO()
                c = canvas.Canvas(temp_buffer, pagesize=A4)
                
                # Dessiner l'en-tête (à adapter selon votre PDF)
                # Si l'en-tête est une image, on peut la redessiner
                # Mais ici on va utiliser la page d'en-tête existante
                
                c.showPage()
                c.save()
                
                temp_buffer.seek(0)
                temp_pdf = PdfReader(temp_buffer)
                base_page = temp_pdf.pages[0]
                
                # Fusionner l'en-tête
                base_page.merge_page(entete.pages[0])
                
                # Appliquer une transformation pour décaler le contenu
                # pour qu'il commence après l'en-tête
                op = Transformation().translate(0, -100)  # Décaler vers le bas de 100 points
                page.add_transformation(op)
                
                # Fusionner le contenu
                base_page.merge_page(page)
                
                output.add_page(base_page)
            else:
                output.add_page(page)
        
        result_buffer = io.BytesIO()
        output.write(result_buffer)
        result_buffer.seek(0)
        
        return result_buffer
        
    except Exception as e:
        logger.error(f"Erreur: {e}")
        return contenu_pdf_buffer
    
def convertir_png_en_pdf(png_path, pdf_path=None):
    """
    Convertit une image PNG en PDF pour l'utiliser comme en-tête
    
    Args:
        png_path: Chemin vers l'image PNG
        pdf_path: Chemin de sortie pour le PDF (optionnel)
    
    Returns:
        Chemin du PDF créé ou None en cas d'erreur
    """
    try:
        from reportlab.pdfgen import canvas
        from reportlab.lib.pagesizes import A4
        from PIL import Image
        
        if not os.path.exists(png_path):
            logger.error(f"Image PNG non trouvée: {png_path}")
            return None
        
        if pdf_path is None:
            pdf_path = png_path.replace('.png', '.pdf')
        
        # Créer le PDF avec l'image
        c = canvas.Canvas(pdf_path, pagesize=A4)
        width, height = A4
        
        # Obtenir les dimensions de l'image
        img = Image.open(png_path)
        img_width, img_height = img.size
        
        # Calculer le ratio pour bien positionner l'image
        ratio = min(width / img_width, 150 / img_height)
        new_width = img_width * ratio
        new_height = img_height * ratio
        
        # Positionner l'image en haut de la page
        x_position = (width - new_width) / 2
        y_position = height - new_height - 20
        
        c.drawImage(png_path, x_position, y_position, width=new_width, height=new_height, preserveAspectRatio=True)
        c.save()
        
        logger.info(f"PDF créé avec succès: {pdf_path}")
        return pdf_path
        
    except Exception as e:
        logger.error(f"Erreur lors de la conversion PNG en PDF: {str(e)}")
        return None


def tester_chemin_en_tete():
    """
    Fonction de test pour vérifier que le chemin de l'en-tête est correct
    """
    chemins_a_tester = [
        r"C:\MesProjets\gestion_courrier\frontend-admin-courrier-amina\public\images\Papier entete zepintel_vf.pdf",
        r"C:\MesProjets\gestion_courrier\frontend-admin-courrier-amina\public\images\Papier entete zepintel_vf.png",
        os.path.join(settings.BASE_DIR, 'frontend-admin-courrier-amina', 'public', 'images', 'Papier entete zepintel_vf.pdf'),
        os.path.join(settings.BASE_DIR, 'frontend', 'public', 'images', 'Papier entete zepintel_vf.pdf'),
    ]
    
    print("=== TEST DES CHEMINS D'EN-TÊTE ===")
    for chemin in chemins_a_tester:
        existe = os.path.exists(chemin)
        print(f"Chemin: {chemin}")
        print(f"Existe: {existe}")
        if existe:
            print(f"  ✓ FICHIER TROUVÉ!")
            if chemin.endswith('.png'):
                print(f"  (c'est un PNG, conversion possible)")
        print()
    
    return any(os.path.exists(c) for c in chemins_a_tester)


# Si le fichier est exécuté directement, lancer le test
if __name__ == "__main__":
    tester_chemin_en_tete()