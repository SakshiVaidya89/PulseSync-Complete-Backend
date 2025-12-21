from flask import Blueprint, request, jsonify
import google.generativeai as genai
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Create Blueprint
chatbot_bp = Blueprint("chatbot", __name__)

# Configure Gemini API
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))

# Choose Gemini model
model = genai.GenerativeModel("gemini-1.5-flash")

@chatbot_bp.route("/chat", methods=["POST"])
def chat():
    """
    Route to handle chatbot messages from frontend.
    """
    try:
        data = request.get_json()
        user_message = data.get("message", "")

        if not user_message:
            return jsonify({"error": "Message is required"}), 400

        # Generate response using Gemini
        response = model.generate_content(user_message)

        return jsonify({"reply": response.text})
    except Exception as e:
        print("Error:", e)
        return jsonify({"error": str(e)}), 500
