from transformers import TrOCRProcessor, VisionEncoderDecoderModel
from PIL import Image
import torch
import io

class TrOCREngine:
    def __init__(self):
        self.processor = TrOCRProcessor.from_pretrained(
            "microsoft/trocr-base-handwritten"
        )
        self.model = VisionEncoderDecoderModel.from_pretrained(
            "microsoft/trocr-base-handwritten"
        )
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        self.model.to(self.device)

    def extract_text(self, image: Image.Image) -> str:
        image = image.convert("RGB")
        pixel_values = self.processor(
            images=image, return_tensors="pt"
        ).pixel_values.to(self.device)

        generated_ids = self.model.generate(pixel_values)
        text = self.processor.batch_decode(
            generated_ids, skip_special_tokens=True
        )[0]

        return text.strip()
