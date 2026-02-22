import base64
from openai import OpenAI

client = OpenAI(api_key="OPENAI_API_KEY")

def analyze_document(text: str, image_bytes: bytes) -> dict:
    image_b64 = base64.b64encode(image_bytes).decode()

    response = client.responses.create(
        model="gpt-4.1",
        input=[{
            "role": "user",
            "content": [
                {"type": "input_text", "text": f"""
Analyse ce courrier officiel.

1. Dis s'il contient :
   - une signature manuscrite
   - un cachet officiel
2. Résume le courrier en 5 lignes max
3. Extrais : date, expéditeur, destinataire, objet
4. Classe le courrier (demande, plainte, information…)

Texte OCR :
{text}
"""},

                {"type": "input_image", "image_base64": image_b64}
            ]
        }]
    )

    return response.output_text
