from dotenv import load_dotenv
load_dotenv()
from flask import Flask
from flask_cors import CORS
from datetime import datetime
import os
from pymongo import MongoClient
# from google import genai
# print("✅ USING NEW GOOGLE-GENAI SDK")
# client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

# print("\nAvailable Models:")
# for model in client.models.list():
#     print(model.name)
# print("\n")
# from routes.chatbot import chatbot_bp
# Initialize Flask app
app = Flask(__name__)

MONGO_URI = os.getenv('MONGODB_URI', 'mongodb://localhost:27017/pulsesync')
JWT_SECRET = os.getenv('JWT_SECRET', 'your-secret-key-change-this')
CORS_ORIGINS = os.getenv('CORS_ORIGINS', 'http://localhost:3000,http://localhost:3001,http://localhost:3002,http://localhost:5173').split(',')
PORT = int(os.getenv('FLASK_PORT', 5000))

cors_config = {
    'origins': [origin.strip() for origin in CORS_ORIGINS],
    'methods': ['GET', 'POST', 'PUT', 'DELETE', 'OPTIONS', 'PATCH'],
    'allow_headers': ['Content-Type', 'Authorization', 'X-Requested-With'],
    'expose_headers': ['Content-Type', 'Authorization'],
    'supports_credentials': True,
    'max_age': 3600
}

# Apply CORS to entire app, not just /api/* routes
CORS(app, resources={"/*": cors_config})

# app.register_blueprint(chatbot_bp, url_prefix="/api/chatbot")

# Global database connection
db = None

# Test MongoDB connection
try:
    client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
    client.admin.command('ping')
    db = client['pulsesync']
    print("✓ Connected to MongoDB successfully")
except Exception as e:
    print(f"✗ Failed to connect to MongoDB: {e}")
    print("Make sure MongoDB is running on localhost:27017")

# Store database in app context for route access
app.db = db

# Register blueprints
from routes.auth import auth_bp
from routes.appointments import appointments_bp
from routes.prescriptions import prescriptions_bp
app.register_blueprint(auth_bp)
app.register_blueprint(appointments_bp)
app.register_blueprint(prescriptions_bp)

# Health check route
@app.route('/health', methods=['GET'])
def health():
    return {'status': 'Backend is running', 'database': 'connected' if db else 'disconnected'}, 200

# Error handlers
@app.errorhandler(404)
def not_found(error):
    return {'error': 'Route not found', 'path': error.description}, 404

@app.errorhandler(500)
def server_error(error):
    return {'error': 'Internal server error'}, 500

@app.errorhandler(400)
def bad_request(error):
    return {'error': 'Bad request'}, 400

if __name__ == '__main__':
    print("\n" + "="*60)
    print("Starting PulseSync Backend...")
    print("="*60)
    print(f"📍 MongoDB URI: {MONGO_URI}")
    print(f"🔐 JWT Secret: {'*' * 15}...")
    print(f"🌐 CORS Origins: {CORS_ORIGINS}")
    print(f"🚀 Server Port: {PORT}")
    print("="*60)
    print("✓ Press Ctrl+C to stop the server\n")
    
    app.run(host='0.0.0.0', port=PORT, debug=True)
