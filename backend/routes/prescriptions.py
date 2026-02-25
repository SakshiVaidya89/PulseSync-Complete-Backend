from flask import Blueprint, request, jsonify
from functools import wraps
import jwt
import os
from models.prescription import PrescriptionModel
from services.medicine_analyzer import MedicineAnalyzer

prescriptions_bp = Blueprint('prescriptions', __name__, url_prefix='/api/prescriptions')

JWT_SECRET = os.getenv('JWT_SECRET', 'your-secret-key-change-this')

# Dependency: Get database from app context
def get_db():
    from flask import current_app
    return current_app.db

# Authentication decorator
def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = request.headers.get('Authorization')
        
        if not token:
            return jsonify({'error': 'Missing authorization token'}), 401
        
        try:
            # Remove 'Bearer ' prefix if present
            if token.startswith('Bearer '):
                token = token[7:]
            
            data = jwt.decode(token, JWT_SECRET, algorithms=['HS256'])
            request.user_id = data['user_id']
        except jwt.ExpiredSignatureError:
            return jsonify({'error': 'Token has expired'}), 401
        except jwt.InvalidTokenError:
            return jsonify({'error': 'Invalid token'}), 401
        
        return f(*args, **kwargs)
    
    return decorated

# Medicine analyzer instance
medicine_analyzer = MedicineAnalyzer()

@prescriptions_bp.route('/analyze', methods=['POST'])
@token_required
def analyze_medicine():
    """
    Analyze a medicine and save it to the database.
    Expected JSON: { "medicine_name": "Medicine Name" }
    """
    try:
        data = request.get_json()
        medicine_name = data.get('medicine_name', '').strip()
        user_id = request.user_id
        
        if not medicine_name:
            return jsonify({'error': 'Medicine name is required'}), 400
        
        # Analyze the medicine using OpenAI
        analysis = medicine_analyzer.analyze_medicine(medicine_name)
        
        # Save to database
        db = get_db()
        prescription_model = PrescriptionModel(db)
        prescription_model.save_prescription(user_id, analysis)
        
        return jsonify(analysis), 200
        
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        print(f"Error analyzing medicine: {str(e)}")
        return jsonify({'error': 'Failed to analyze medicine'}), 500

@prescriptions_bp.route('/<user_id>', methods=['GET'])
@token_required
def get_prescriptions(user_id):
    """
    Get all prescriptions for a user.
    """
    try:
        # Security: Ensure user can only access their own prescriptions
        if request.user_id != user_id:
            return jsonify({'error': 'Unauthorized'}), 403
        
        db = get_db()
        prescription_model = PrescriptionModel(db)
        prescriptions = prescription_model.get_user_prescriptions(user_id)
        
        return jsonify({
            'prescriptions': prescriptions,
            'count': len(prescriptions)
        }), 200
        
    except Exception as e:
        print(f"Error fetching prescriptions: {str(e)}")
        return jsonify({'error': 'Failed to fetch prescriptions'}), 500

@prescriptions_bp.route('/<prescription_id>', methods=['DELETE'])
@token_required
def delete_prescription(prescription_id):
    """
    Delete a prescription.
    """
    try:
        db = get_db()
        prescription_model = PrescriptionModel(db)
        
        # Delete with user verification
        success = prescription_model.delete_prescription(prescription_id, request.user_id)
        
        if not success:
            return jsonify({'error': 'Prescription not found or unauthorized'}), 404
        
        return jsonify({'message': 'Prescription deleted successfully'}), 200
        
    except Exception as e:
        print(f"Error deleting prescription: {str(e)}")
        return jsonify({'error': 'Failed to delete prescription'}), 500

@prescriptions_bp.route('/health', methods=['GET'])
def health():
    """Health check for prescriptions API"""
    return jsonify({'status': 'ok', 'service': 'prescriptions'}), 200
