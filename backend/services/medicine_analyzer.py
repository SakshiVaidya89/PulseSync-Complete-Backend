import os
import json
from dotenv import load_dotenv
from google import genai

load_dotenv()

class MedicineAnalyzer:
    def __init__(self):
        self.client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

    def analyze_medicine(self, medicine_name):
        prompt = f"""
        Analyze the medicine: "{medicine_name}"

        Provide a detailed analysis in JSON format:

        {{
            "medicine_name": "exact name",
            "why_prescribed": "why prescribed",
            "how_it_works": "how it works",
            "uses": ["use1", "use2"],
            "alternatives": ["alt1", "alt2"],
            "ingredients": "main ingredients",
            "dosage": "general dosage info",
            "side_effects": {{
                "common": ["effect1"],
                "serious": ["effect2"]
            }},
            "interactions": ["interaction1"],
            "where_to_buy": ["Pharmacy", "Online"],
            "storage_tips": "storage instructions",
            "disclaimer": "Consult healthcare provider."
        }}

        Return ONLY valid JSON.
        """

        try:
            response = self.client.models.generate_content(
                model="gemini-2.5-flash",
                contents=prompt,
            )

            content = response.text.strip()

            try:
                return json.loads(content)
            except json.JSONDecodeError:
                start = content.find("{")
                end = content.rfind("}") + 1
                return json.loads(content[start:end])

        except Exception as e:
            print("Gemini Error:", str(e))
            raise ValueError(f"Failed to analyze medicine: {str(e)}")