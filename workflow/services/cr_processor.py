from pdf2image import convert_from_path
from PIL import Image
import io
import logging

from .trocr_ocr import TrOCREngine
from .gpt_vision import analyze_document

logger = logging.getLogger(__name__)

class OCRProcessor:

    def __init__(self):
        self.trocr = TrOCREngine()

    def process_ocr(self, file_path: str, courrier=None) -> dict:
        pages = []

        # PDF → images
        if file_path.lower().endswith(".pdf"):
            pages = convert_from_path(file_path, dpi=300)
        else:
            pages = [Image.open(file_path)]

        full_text = ""
        full_analysis = []

        for i, image in enumerate(pages):
            logger.info(f"OCR TrOCR page {i+1}")

            text = self.trocr.extract_text(image)
            full_text += f"\n--- Page {i+1} ---\n{text}"

            # Image → bytes pour GPT-4V
            buffer = io.BytesIO()
            image.save(buffer, format="PNG")

            analysis = analyze_document(text, buffer.getvalue())
            full_analysis.append(analysis)

        result = {
            "texte_ocr": full_text.strip(),
            "analyse_ia": "\n\n".join(full_analysis)
        }

        if courrier:
            courrier.contenu_texte = result["texte_ocr"]
            courrier.analyse_ia = result["analyse_ia"]
            courrier.save(
                update_fields=["contenu_texte", "analyse_ia"]
            )

        return result
