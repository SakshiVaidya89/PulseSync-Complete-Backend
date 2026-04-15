import os
import json
import threading
from urllib.parse import quote
from dotenv import load_dotenv
from google import genai

load_dotenv()

# ─── Known Indian pharmacy sites with their search URL patterns ───────────────
# These are hardcoded so URLs are always correct — Gemini only decides WHICH
# retailers are relevant, not what the URL looks like.
ONLINE_RETAILERS = [
    {
        "name": "1mg",
        "url_template": "https://www.1mg.com/search/all?name={query}",
        "type": "online",
        "note": "India's largest online pharmacy",
    },
    {
        "name": "Netmeds",
        "url_template": "https://www.netmeds.com/catalogsearch/result?q={query}",
        "type": "online",
        "note": "Trusted online pharmacy",
    },
    {
        "name": "PharmEasy",
        "url_template": "https://pharmeasy.in/search/all?name={query}",
        "type": "online",
        "note": "Fast home delivery",
    },
    {
        "name": "Apollo Pharmacy",
        "url_template": "https://www.apollopharmacy.in/search-medicines/{query}",
        "type": "online",
        "note": "Apollo Healthcare",
    },
    {
        "name": "MedPlusMart",
        "url_template": "https://www.medplusmart.com/searchMedicines#srchQry={query}",
        "type": "online",
        "note": "Online & in-store pickup",
    },
]

IN_STORE_OPTIONS = [
    {
        "name": "Apollo Pharmacy",
        "type": "pharmacy",
        "note": "5,000+ stores across India",
    },
    {
        "name": "MedPlus",
        "type": "pharmacy",
        "note": "Widespread retail chain",
    },
    {
        "name": "Local Chemist / General Pharmacy",
        "type": "pharmacy",
        "note": "Available over-the-counter at most pharmacies",
    },
    {
        "name": "Dmart",
        "type": "supermarket",
        "note": "Available in health & wellness aisle",
    },
    {
        "name": "Reliance Smart",
        "type": "supermarket",
        "note": "Select stores carry OTC medicines",
    },
]


def build_where_to_buy(medicine_name: str, online_names: list, instore_names: list) -> list:
    """
    Build structured where_to_buy list using hardcoded URL templates.
    Gemini picks the retailer names; we construct the real URLs here.
    """
    result = []
    query = quote(medicine_name)

    for name in online_names:
        retailer = next((r for r in ONLINE_RETAILERS if r["name"].lower() == name.lower()), None)
        if retailer:
            result.append({
                "name": retailer["name"],
                "url": retailer["url_template"].format(query=query),
                "type": retailer["type"],
                "note": retailer["note"],
            })

    for name in instore_names:
        store = next((s for s in IN_STORE_OPTIONS if s["name"].lower() == name.lower()), None)
        if store:
            result.append({
                "name": store["name"],
                "type": store["type"],
                "note": store["note"],
            })

    return result


class MedicineAnalyzer:
    def __init__(self):
        self.client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
        # Non-daemon lock prevents the _enter_buffered_busy panic on Python 3.14
        # when Werkzeug's reloader tears down daemon threads at shutdown
        self._lock = threading.Lock()

    def extract_medicines_from_image(self, image_bytes: bytes, mime_type: str = "image/jpeg") -> list:
        """
        Given raw image bytes of a doctor's prescription, return a list of
        medicine names found in the image using Gemini Vision.
        """
        import base64
        from google.genai import types

        prompt = """
        You are an expert at reading handwritten and printed doctor prescriptions.
        Look at this prescription image carefully and extract ALL medicine / drug names written on it.

        Rules:
        - Include brand names AND generic names if both are written
        - Do NOT include dosage amounts, frequencies, or instructions — only the medicine name itself
        - If a name is partially illegible, include your best interpretation
        - Return ONLY a valid JSON array of strings, no explanation, no markdown, no backticks

        Example output: ["Crocin", "Azithromycin", "Pantoprazole"]
        """

        image_part = types.Part.from_bytes(data=image_bytes, mime_type=mime_type)

        try:
            import time

            for attempt in range(3):
                try:
                    response = self.client.models.generate_content(
                        model="gemini-2.5-flash",
                        contents=[prompt, image_part],
                    )
                    break
                except Exception as e:
                    print(f"Vision attempt {attempt+1} failed:", str(e))
                    if attempt < 2:
                        time.sleep(2)
                    else:
                        raise ValueError("AI is busy reading prescriptions. Please try again.")
            content = response.text.strip()

            # Strip markdown fences if Gemini adds them
            if content.startswith("```"):
                content = content.split("```")[1]
                if content.startswith("json"):
                    content = content[4:]
                content = content.strip()

            medicines = json.loads(content)
            if not isinstance(medicines, list):
                raise ValueError("Expected a JSON array of medicine names")
            return [str(m).strip() for m in medicines if str(m).strip()]

        except Exception as e:
            print(f"Gemini Vision Error: {str(e)}")
            raise ValueError(f"Failed to read prescription image: {str(e)}")

    def analyze_medicine(self, medicine_name):
        # All available retailer names Gemini can choose from
        online_options = [r["name"] for r in ONLINE_RETAILERS]
        instore_options = [s["name"] for s in IN_STORE_OPTIONS]

        prompt = f"""
        Analyze the medicine: "{medicine_name}"

        Provide a detailed analysis in the following JSON format.
        For "where_to_buy_online" and "where_to_buy_instore", choose ONLY from the provided lists.

        Available online retailers: {json.dumps(online_options)}
        Available in-store options: {json.dumps(instore_options)}

        Return ONLY valid JSON in this exact structure:

        {{
            "medicine_name": "exact name",
            "why_prescribed": "why it is prescribed",
            "how_it_works": "how it works",
            "uses": ["use1", "use2"],
            "alternatives": ["alt1", "alt2"],
            "ingredients": "main active ingredients",
            "dosage": "general dosage information",
            "side_effects": {{
                "common": ["effect1", "effect2"],
                "serious": ["effect1"]
            }},
            "interactions": ["drug or substance interaction1"],
            "where_to_buy_online": ["1mg", "Netmeds"],
            "where_to_buy_instore": ["Apollo Pharmacy", "Local Chemist / General Pharmacy"],
            "storage_tips": "storage instructions",
            "disclaimer": "Always consult a healthcare provider."
        }}

        Rules:
        - "where_to_buy_online" must only contain names from: {json.dumps(online_options)}
        - "where_to_buy_instore" must only contain names from: {json.dumps(instore_options)}
        - Pick 2-4 online retailers and 1-3 in-store options that are most likely to carry this medicine in India
        - Return ONLY valid JSON, no markdown, no backticks.
        """

        try:
            response = self.client.models.generate_content(
                model="gemini-2.5-flash",
                contents=prompt,
            )

            content = response.text.strip()

            try:
                raw = json.loads(content)
            except json.JSONDecodeError:
                start = content.find("{")
                end = content.rfind("}") + 1
                raw = json.loads(content[start:end])

            # Build structured where_to_buy with real URLs using our templates
            raw["where_to_buy"] = build_where_to_buy(
                medicine_name=raw.get("medicine_name", medicine_name),
                online_names=raw.pop("where_to_buy_online", []),
                instore_names=raw.pop("where_to_buy_instore", []),
            )

            return raw

        except Exception as e:
            print("Gemini Error:", str(e))
            raise ValueError(f"Failed to analyze medicine: {str(e)}")