from flask import Blueprint, request, jsonify
from werkzeug.security import check_password_hash, generate_password_hash
from functools import wraps
import jwt
from datetime import datetime, timedelta
import os
from pymongo import MongoClient
from bson.objectid import ObjectId

auth_bp = Blueprint('auth', __name__, url_prefix='/api/auth')

# MongoDB connection
def get_db():
    client = MongoClient('mongodb://localhost:27017/')
    return client['pulsesync']

def token_required(f):
    """Decorator to check if user has valid JWT token"""
    @wraps(f)
    def decorated(*args, **kwargs):
        token = None
        
        if 'Authorization' in request.headers:
            auth_header = request.headers['Authorization']
            try:
                token = auth_header.split(" ")[1]
            except IndexError:
                return jsonify({'error': 'Invalid token format'}), 401
        
        if not token:
            return jsonify({'error': 'Token is missing'}), 401
        
        try:
            data = jwt.decode(token, os.getenv('JWT_SECRET', 'your-secret-key'), algorithms=['HS256'])
            request.user_id = data['user_id']
            request.user_role = data['role']
        except jwt.ExpiredSignatureError:
            return jsonify({'error': 'Token has expired'}), 401
        except jwt.InvalidTokenError:
            return jsonify({'error': 'Invalid token'}), 401
        
        return f(*args, **kwargs)
    
    return decorated

def generate_token(user_id, role):
    """Generate JWT token"""
    payload = {
        'user_id': str(user_id),
        'role': role,
        'exp': datetime.utcnow() + timedelta(days=30)
    }
    return jwt.encode(payload, os.getenv('JWT_SECRET', 'your-secret-key'), algorithm='HS256')

@auth_bp.route('/signup', methods=['POST'])
def signup():
    """Handle user signup"""
    try:
        data = request.get_json()
        
        # Validate required fields
        if not data or not all(k in data for k in ['email', 'password', 'fullName', 'role']):
            return jsonify({'error': 'Missing required fields: email, password, fullName, role'}), 400
        
        email = data['email'].strip().lower()
        password = data['password']
        full_name = data['fullName']
        role = data['role'].lower()
        
        # Validate role
        if role not in ['patient', 'hospital']:
            return jsonify({'error': 'Invalid role. Must be patient or hospital'}), 400
        
        # Validate password length
        if len(password) < 6:
            return jsonify({'error': 'Password must be at least 6 characters'}), 400
        
        db = get_db()
        users_collection = db['users']
        
        # Check if user already exists
        if users_collection.find_one({'email': email}):
            return jsonify({'error': 'Email already registered'}), 400
        
        # Create new user
        user_data = {
            'email': email,
            'password': generate_password_hash(password),
            'full_name': full_name,
            'role': role,
            'profile_complete': False,
            'created_at': datetime.utcnow()
        }
        
        if role == 'hospital':
            user_data.update({
                'registration_number': data.get('registrationNumber', ''),
                'department': data.get('department', ''),
                'license_number': data.get('licenseNumber', ''),
                'address': data.get('address', ''),
                'staff_position': data.get('staffPosition', '')
            })
        
        result = users_collection.insert_one(user_data)
        user_id = result.inserted_id
        
        # Generate token
        token = generate_token(user_id, role)
        
        return jsonify({
            'message': 'User created successfully',
            'token': token,
            'user_id': str(user_id),
            'role': role,
            'profile_complete': False
        }), 201
    
    except Exception as e:
        print(f"[v0] Signup error: {str(e)}")
        return jsonify({'error': f'Error during signup: {str(e)}'}), 500

@auth_bp.route('/login', methods=['POST'])
def login():
    """Handle user login"""
    try:
        data = request.get_json()
        
        if not data or not all(k in data for k in ['email', 'password']):
            return jsonify({'error': 'Missing email or password'}), 400
        
        email = data['email'].strip().lower()
        password = data['password']
        
        db = get_db()
        users_collection = db['users']
        
        # Find user
        user = users_collection.find_one({'email': email})
        if not user:
            return jsonify({'error': 'Invalid credentials'}), 401
        
        # Check password
        if not check_password_hash(user['password'], password):
            return jsonify({'error': 'Invalid credentials'}), 401
        
        # Generate token
        token = generate_token(user['_id'], user['role'])
        
        return jsonify({
            'message': 'Login successful',
            'token': token,
            'user_id': str(user['_id']),
            'role': user['role'],
            'profile_complete': user.get('profile_complete', False),
            'is_login': True
        }), 200
    
    except Exception as e:
        print(f"[v0] Login error: {str(e)}")
        return jsonify({'error': f'Error during login: {str(e)}'}), 500

@auth_bp.route('/update-patient-profile', methods=['POST'])
@token_required
def update_patient_profile():
    """Update patient profile information"""
    try:
        if request.user_role != 'patient':
            return jsonify({'error': 'Only patients can update profile'}), 403
        
        data = request.get_json()
        
        db = get_db()
        users_collection = db['users']
        
        # Update user profile
        update_data = {
            'profile_complete': True,
            'updated_at': datetime.utcnow()
        }
        
        # Add optional fields if provided
        optional_fields = ['date_of_birth', 'blood_type', 'address', 'phone', 'gender', 'emergency_contact', 'emergency_phone']
        for field in optional_fields:
            if field in data:
                update_data[field] = data[field]
        
        users_collection.update_one(
            {'_id': ObjectId(request.user_id)},
            {'$set': update_data}
        )
        
        return jsonify({
            'message': 'Profile updated successfully',
            'profile_complete': True
        }), 200
    
    except Exception as e:
        print(f"[v0] Profile update error: {str(e)}")
        return jsonify({'error': f'Error updating profile: {str(e)}'}), 500

@auth_bp.route('/update-hospital-profile', methods=['POST'])
@token_required
def update_hospital_profile():
    """Update hospital profile information"""
    try:
        if request.user_role != 'hospital':
            return jsonify({'error': 'Only hospitals can update hospital profile'}), 403
        
        data = request.get_json()
        
        db = get_db()
        users_collection = db['users']
        
        # Update user profile
        update_data = {
            'profile_complete': True,
            'updated_at': datetime.utcnow()
        }
        
        optional_fields = ['registration_number', 'department', 'license_number', 'address', 'staff_position', 'hospital_phone', 'hospital_email']
        for field in optional_fields:
            if field in data:
                update_data[field] = data[field]
        
        users_collection.update_one(
            {'_id': ObjectId(request.user_id)},
            {'$set': update_data}
        )
        
        return jsonify({
            'message': 'Hospital profile updated successfully',
            'profile_complete': True
        }), 200
    
    except Exception as e:
        print(f"[v0] Hospital profile update error: {str(e)}")
        return jsonify({'error': f'Error updating profile: {str(e)}'}), 500

@auth_bp.route('/get-patient-profile', methods=['GET'])
@token_required
def get_patient_profile():
    """Get patient profile information"""
    try:
        if request.user_role != 'patient':
            return jsonify({'error': 'Only patients can access patient profile'}), 403
        
        db = get_db()
        users_collection = db['users']
        
        user = users_collection.find_one({'_id': ObjectId(request.user_id)})
        
        if not user:
            return jsonify({'error': 'User not found'}), 404
        
        return jsonify({
            'full_name': user.get('full_name', ''),
            'email': user.get('email', ''),
            'phone': user.get('phone', ''),
            'date_of_birth': user.get('date_of_birth', ''),
            'blood_type': user.get('blood_type', ''),
            'emergency_contact': user.get('emergency_contact', ''),
            'emergency_phone': user.get('emergency_phone', ''),
            'address': user.get('address', ''),
            'profile_complete': user.get('profile_complete', False)
        }), 200
    
    except Exception as e:
        print(f"[v0] Get patient profile error: {str(e)}")
        return jsonify({'error': f'Error fetching profile: {str(e)}'}), 500

@auth_bp.route('/get-hospital-profile', methods=['GET'])
@token_required
def get_hospital_profile():
    """Get hospital profile information"""
    try:
        if request.user_role != 'hospital':
            return jsonify({'error': 'Only hospitals can access hospital profile'}), 403
        
        db = get_db()
        users_collection = db['users']
        
        user = users_collection.find_one({'_id': ObjectId(request.user_id)})
        
        if not user:
            return jsonify({'error': 'User not found'}), 404
        
        return jsonify({
            'full_name': user.get('full_name', ''),
            'email': user.get('email', ''),
            'registration_number': user.get('registration_number', ''),
            'department': user.get('department', ''),
            'license_number': user.get('license_number', ''),
            'address': user.get('address', ''),
            'staff_position': user.get('staff_position', ''),
            'hospital_phone': user.get('hospital_phone', ''),
            'hospital_email': user.get('hospital_email', ''),
            'profile_complete': user.get('profile_complete', False)
        }), 200
    
    except Exception as e:
        print(f"[v0] Get hospital profile error: {str(e)}")
        return jsonify({'error': f'Error fetching profile: {str(e)}'}), 500

@auth_bp.route('/doctors', methods=['GET'])
def get_all_doctors():
    """Get all doctors who have logged in (hospital staff registered as doctors)"""
    try:
        db = get_db()
        users_collection = db['users']
        
        # Find all hospital users (doctors/staff)
        doctors = list(users_collection.find(
            {'role': 'hospital'},
            {
                '_id': 1,
                'full_name': 1,
                'email': 1,
                'department': 1,
                'staff_position': 1,
                'registration_number': 1,
                'address': 1,
                'created_at': 1
            }
        ))
        
        # Transform data for frontend
        doctor_list = []
        for doc in doctors:
            doctor_list.append({
                'id': str(doc['_id']),
                'name': doc.get('full_name', 'Dr. Unknown'),
                'specialty': doc.get('department', 'General Practice'),
                'hospital': 'PulseSync Hospital',
                'position': doc.get('staff_position', 'Doctor'),
                'registration_number': doc.get('registration_number', ''),
                'email': doc.get('email', ''),
                'rating': 4.8,  # Default rating
                'experience': '5+ years',  # Default experience
                'image': '/male-doctor.png'  # Default image
            })
        
        return jsonify({
            'doctors': doctor_list,
            'total': len(doctor_list)
        }), 200
    
    except Exception as e:
        print(f"[v0] Get doctors error: {str(e)}")
        return jsonify({'error': f'Error fetching doctors: {str(e)}'}), 500
    
@auth_bp.route('/doctors/availability', methods=['GET'])
def get_doctors_availability():
    """Get all doctors with their availability information"""
    try:
        db = get_db()
        users_collection = db['users']
        availability_collection = db['availability']
        
        # Find all hospital users (doctors/staff)
        doctors = list(users_collection.find(
            {'role': 'hospital'},
            {
                '_id': 1,
                'full_name': 1,
                'email': 1,
                'department': 1,
                'staff_position': 1,
                'address': 1,
            }
        ))
        
        # Get availability data for each doctor
        doctor_list = []
        for doc in doctors:
            doctor_id = str(doc['_id'])
            availability = availability_collection.find_one({'doctor_id': doctor_id})
            
            doctor_list.append({
                'id': doctor_id,
                'name': doc.get('full_name', 'Dr. Unknown'),
                'specialty': doc.get('department', 'General Practice'),
                'hospital': 'PulseSync Hospital',
                'position': doc.get('staff_position', 'Doctor'),
                'email': doc.get('email', ''),
                'rating': 4.8,
                'experience': '5+ years',
                'image': '/male-doctor.png',
                'nextAvailable': availability.get('next_available', 'Not set') if availability else 'Not set',
                'slots': availability.get('available_slots', []) if availability else []
            })
        
        return jsonify({
            'doctors': doctor_list,
            'total': len(doctor_list)
        }), 200
    
    except Exception as e:
        print(f"[v0] Get doctors availability error: {str(e)}")
        return jsonify({'error': f'Error fetching doctors: {str(e)}'}), 500

@auth_bp.route('/health', methods=['GET'])
def health():
    """Health check endpoint"""
    return jsonify({'status': 'Auth backend is running'}), 200
