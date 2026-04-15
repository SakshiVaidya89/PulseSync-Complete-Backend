# routes/chatbot.py
# Paste this into your existing routes/chatbot.py file.
# Make sure GEMINI_API_KEY is set in your .env file.

import os
import requests
from flask import Blueprint, request, jsonify

chatbot_bp = Blueprint("chatbot", __name__)

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
GEMINI_MODEL = "gemini-2.5-flash"
GEMINI_URL = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent"

SYSTEM_INSTRUCTION = {
    "role": "system",
    "parts": [
        {
            "text": (
                "You are 'Pulse', a friendly, empathetic, and cautious AI healthcare assistant.\n"
                "Your primary goal is to help users understand their symptoms by asking clarifying follow-up questions.\n"
                "RULES:\n"
                "1. NEVER PROVIDE A DIAGNOSIS. Never say 'you have...' or 'it is...'. "
                "Use cautious phrases like 'Your symptoms could suggest...', 'This might be related to...', or 'It's possible that...'.\n"
                "2. ASK FOLLOW-UP QUESTIONS. Ask one clear, relevant question at a time to gather more information. "
                "Continue asking until you have a clear picture.\n"
                "3. EXPLAIN POSSIBILITIES. Once you have enough information, explain what the combination of symptoms "
                "could mean in simple terms.\n"
                "4. SUGGEST SPECIALISTS. Recommend the type of doctor to see "
                "(e.g., for persistent joint pain, suggest a Rheumatologist).\n"
                "5. PRIORITIZE URGENCY. For severe symptoms (chest pain, difficulty breathing, severe headache, "
                "high fever, confusion), immediately and strongly advise seeking emergency medical attention.\n"
                "6. SUGGEST OTC MEDS CAUTIOUSLY. For minor, non-urgent issues, you can suggest common "
                "over-the-counter medicine but ALWAYS follow with "
                "'consult a doctor or pharmacist before taking any medication.'\n"
                "7. FORMATTING. Format responses using HTML for readability — use <p>, <strong>, <ul>, <li> tags."
            )
        }
    ],
}


@chatbot_bp.route("/api/chatbot", methods=["POST"])
def chat():
    data = request.get_json()

    if not data or "history" not in data:
        return jsonify({"error": "Missing 'history' in request body"}), 400

    history = data["history"]

    if not GEMINI_API_KEY:
        return jsonify({"error": "GEMINI_API_KEY not configured on server"}), 500

    payload = {
        "contents": history,
        "systemInstruction": SYSTEM_INSTRUCTION,
    }

    try:
        print("Sending to Gemini...")
        print(payload)
        response = requests.post(
            f"{GEMINI_URL}?key={GEMINI_API_KEY}",
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=30,
        )
        print(response.status_code)
        print(response.text)
        response.raise_for_status()

        gemini_data = response.json()
        bot_text = gemini_data["candidates"][0]["content"]["parts"][0]["text"]
        return jsonify({"response": bot_text})

    except requests.exceptions.Timeout:
        return jsonify({"error": "Request to Gemini timed out"}), 504
    except requests.exceptions.HTTPError as e:
        print("Gemini ERROR:", response.text)
        return jsonify({"error": response.text}), 502
    except (KeyError, IndexError):
        return jsonify({"error": "Unexpected response format from Gemini"}), 502
    except Exception as e:
        return jsonify({"error": f"Unexpected error: {str(e)}"}), 500