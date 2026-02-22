# -*- coding: utf-8 -*-

from courriers.models import Courrier
from workflow.services.ocr import process_ocr

file_path = r"C:\Users\LA SOURCE\Documents\test\Courrier1.pdf"

courrier, _ = Courrier.objects.get_or_create(
    reference="CR6OCRTEST",
    defaults={
        "objet": "Test OCR",
        "type": "entrant"
    }
)

texte = process_ocr(file_path=file_path, courrier=courrier)

print("\n====== TEXTE EXTRAIT ======\n")
print(texte if texte else "⚠️ AUCUN TEXTE DÉTECTÉ")