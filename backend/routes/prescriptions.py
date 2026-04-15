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

@prescriptions_bp.route('/analyze-prescription-image', methods=['POST'])
@token_required
def analyze_prescription_image():
    """
    Accept a prescription photo, extract medicine names via Gemini Vision,
    analyze each one, save them all, and return the full analyses.
    Expected: multipart/form-data with field "image" (jpg/png/webp/heic)
    """
    try:
        if 'image' not in request.files:
            return jsonify({'error': 'No image file provided'}), 400

        image_file = request.files['image']
        if image_file.filename == '':
            return jsonify({'error': 'Empty filename'}), 400

        mime_type = image_file.content_type or 'image/jpeg'
        allowed_types = {'image/jpeg', 'image/png', 'image/webp', 'image/heic', 'image/heif'}
        if mime_type not in allowed_types:
            return jsonify({'error': f'Unsupported image type: {mime_type}'}), 400

        image_bytes = image_file.read()
        if len(image_bytes) > 10 * 1024 * 1024:  # 10 MB cap
            return jsonify({'error': 'Image too large. Please upload under 10 MB.'}), 400

        # Step 1: Extract medicine names from the image
        medicine_names = medicine_analyzer.extract_medicines_from_image(image_bytes, mime_type)

        if not medicine_names:
            return jsonify({'error': 'No medicines found in the prescription image'}), 422

        # Step 2: Analyze each medicine and save to DB
        # Use a short delay between calls to avoid Gemini rate limits
        import time
        db = get_db()
        prescription_model = PrescriptionModel(db)
        user_id = request.user_id

        analyses = []
        failed = []

        for i, name in enumerate(medicine_names):
            if i > 0:
                time.sleep(1)  # 1s gap between Gemini calls to avoid rate limits
            for attempt in range(3):
                try:
                    analysis = medicine_analyzer.analyze_medicine(name)
                    prescription_model.save_prescription(user_id, analysis)
                    analyses.append(analysis)
                    break
                except Exception as e:
                    print(f"Attempt {attempt+1} failed for '{name}': {str(e)}")
                    if attempt < 2:
                        time.sleep(2)
                    else:
                        failed.append(name)

        return jsonify({
            'medicines_found': medicine_names,
            'analyses': analyses,
            'failed': failed,
            'count': len(analyses),
        }), 200

    except ValueError as e:
        return jsonify({'error': str(e), 'type': 'AI_ERROR'}), 503
    except Exception as e:
        print(f"Error processing prescription image: {str(e)}")
        return jsonify({'error': 'Failed to process prescription image'}), 500


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
        return jsonify({
        'error': str(e),
        'type': 'AI_ERROR'
    }), 503
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