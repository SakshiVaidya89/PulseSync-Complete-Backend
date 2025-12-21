from flask import Blueprint, request, jsonify
from functools import wraps
from datetime import datetime
from bson.objectid import ObjectId
import os
import jwt
from models.appointment import AppointmentModel

appointments_bp = Blueprint('appointments', __name__, url_prefix='/api/appointments')

def get_db():
    from pymongo import MongoClient
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

@appointments_bp.route('/create', methods=['POST'])
@token_required
def create_appointment():
    """Create a new appointment (Patient only)"""
    try:
        data = request.get_json()
        
        # Validate required fields
        required_fields = ['doctor_id', 'hospital_id', 'appointment_date', 'appointment_time', 'reason']
        if not data or not all(k in data for k in required_fields):
            return jsonify({'error': f'Missing required fields: {", ".join(required_fields)}'}), 400
        
        if request.user_role != 'patient':
            return jsonify({'error': 'Only patients can book appointments'}), 403
        
        db = get_db()
        
        patient_id = request.user_id
        
        # Create appointment
        appointment = AppointmentModel.create_appointment(
            db,
            patient_id=patient_id,
            doctor_id=data['doctor_id'],
            hospital_id=data['hospital_id'],
            appointment_date=data['appointment_date'],
            appointment_time=data['appointment_time'],
            reason=data['reason'],
            notes=data.get('notes', '')
        )
        
        return jsonify({
            'message': 'Appointment created successfully',
            'appointment': appointment
        }), 201
    
    except Exception as e:
        print(f"[v0] Create appointment error: {str(e)}")
        return jsonify({'error': f'Error creating appointment: {str(e)}'}), 500

@appointments_bp.route('/patient/appointments', methods=['GET'])
@token_required
def get_patient_appointments():
    """Get all appointments for the logged-in patient"""
    try:
        if request.user_role != 'patient':
            return jsonify({'error': 'Only patients can view their appointments'}), 403
        
        db = get_db()
        appointments = AppointmentModel.get_patient_appointments(db, request.user_id)
        
        # Separate into upcoming and past
        today = datetime.utcnow().date().isoformat()
        upcoming = []
        past = []
        
        for apt in appointments:
            apt_date = apt['appointment_date']
            if apt_date >= today and apt['status'] not in ['completed', 'cancelled']:
                upcoming.append(apt)
            else:
                past.append(apt)
        
        return jsonify({
            'upcoming': upcoming,
            'past': past,
            'total': len(appointments),
            'total_completed': len([a for a in appointments if a['status'] == 'completed']),
            'total_upcoming': len(upcoming)
        }), 200
    
    except Exception as e:
        print(f"[v0] Get patient appointments error: {str(e)}")
        return jsonify({'error': f'Error fetching appointments: {str(e)}'}), 500

@appointments_bp.route('/doctor/appointments', methods=['GET'])
@token_required
def get_doctor_appointments():
    """Get all appointments for a doctor"""
    try:
        if request.user_role != 'doctor':
            return jsonify({'error': 'Only doctors can view their appointments'}), 403
        
        db = get_db()
        appointments = AppointmentModel.get_doctor_appointments(db, request.user_id)
        
        # Separate into today, upcoming and past
        today = datetime.utcnow().date().isoformat()
        today_appointments = []
        upcoming = []
        past = []
        
        for apt in appointments:
            apt_date = apt['appointment_date']
            if apt_date == today and apt['status'] != 'cancelled':
                today_appointments.append(apt)
            elif apt_date > today and apt['status'] != 'cancelled':
                upcoming.append(apt)
            else:
                past.append(apt)
        
        return jsonify({
            'today': today_appointments,
            'upcoming': upcoming,
            'past': past,
            'total': len(appointments),
            'total_today': len(today_appointments)
        }), 200
    
    except Exception as e:
        print(f"[v0] Get doctor appointments error: {str(e)}")
        return jsonify({'error': f'Error fetching appointments: {str(e)}'}), 500

@appointments_bp.route('/hospital/appointments', methods=['GET'])
@token_required
def get_hospital_appointments():
    """Get all appointments for the logged-in hospital"""
    try:
        if request.user_role != 'hospital':
            return jsonify({'error': 'Only hospitals can view their appointments'}), 403
        
        db = get_db()
        
        # Get the hospital ID from user profile
        users_collection = db['users']
        hospital_user = users_collection.find_one({'_id': ObjectId(request.user_id)})
        hospital_id = hospital_user.get('full_name', '')  # Use hospital name as ID
        
        appointments = AppointmentModel.get_hospital_appointments(db, hospital_id)
        
        # Separate into today, upcoming and past
        today = datetime.utcnow().date().isoformat()
        today_appointments = []
        upcoming = []
        past = []
        
        for apt in appointments:
            apt_date = apt['appointment_date']
            if apt_date == today and apt['status'] != 'cancelled':
                today_appointments.append(apt)
            elif apt_date > today and apt['status'] != 'cancelled':
                upcoming.append(apt)
            else:
                past.append(apt)
        
        return jsonify({
            'today': today_appointments,
            'upcoming': upcoming,
            'past': past,
            'total': len(appointments),
            'total_today': len(today_appointments)
        }), 200
    
    except Exception as e:
        print(f"[v0] Get hospital appointments error: {str(e)}")
        return jsonify({'error': f'Error fetching appointments: {str(e)}'}), 500

@appointments_bp.route('/<appointment_id>/status', methods=['PUT'])
@token_required
def update_appointment_status(appointment_id):
    """Update appointment status"""
    try:
        data = request.get_json()
        
        if not data or 'status' not in data:
            return jsonify({'error': 'Status field is required'}), 400
        
        db = get_db()
        
        # Verify appointment exists
        appointment = AppointmentModel.get_appointment_by_id(db, appointment_id)
        if not appointment:
            return jsonify({'error': 'Appointment not found'}), 404
        
        # Verify authorization
        if request.user_role == 'patient' and appointment['patient_id'] != request.user_id:
            return jsonify({'error': 'Unauthorized'}), 403
        
        new_status = data['status'].lower()
        valid_statuses = ['pending', 'confirmed', 'completed', 'cancelled']
        
        if new_status not in valid_statuses:
            return jsonify({'error': f'Invalid status. Must be one of: {", ".join(valid_statuses)}'}), 400
        
        success = AppointmentModel.update_appointment_status(db, appointment_id, new_status)
        
        if success:
            return jsonify({
                'message': f'Appointment status updated to {new_status}',
                'appointment_id': appointment_id,
                'status': new_status
            }), 200
        else:
            return jsonify({'error': 'Failed to update appointment'}), 500
    
    except Exception as e:
        print(f"[v0] Update appointment status error: {str(e)}")
        return jsonify({'error': f'Error updating appointment: {str(e)}'}), 500

@appointments_bp.route('/<appointment_id>/cancel', methods=['POST'])
@token_required
def cancel_appointment(appointment_id):
    """Cancel an appointment"""
    try:
        db = get_db()
        
        # Verify appointment exists
        appointment = AppointmentModel.get_appointment_by_id(db, appointment_id)
        if not appointment:
            return jsonify({'error': 'Appointment not found'}), 404
        
        # Verify authorization - only patient or hospital can cancel
        if request.user_role == 'patient' and appointment['patient_id'] != request.user_id:
            return jsonify({'error': 'Unauthorized'}), 403
        
        success = AppointmentModel.cancel_appointment(db, appointment_id)
        
        if success:
            return jsonify({
                'message': 'Appointment cancelled successfully',
                'appointment_id': appointment_id
            }), 200
        else:
            return jsonify({'error': 'Failed to cancel appointment'}), 500
    
    except Exception as e:
        print(f"[v0] Cancel appointment error: {str(e)}")
        return jsonify({'error': f'Error cancelling appointment: {str(e)}'}), 500

@appointments_bp.route('/doctors/<doctor_id>/availability', methods=['PUT'])
def update_doctor_availability(doctor_id):
    """Update doctor availability (for doctors to set their schedules)"""
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({'error': 'Request body is required'}), 400
        
        db = get_db()
        availability_collection = db['availability']
        
        availability_data = {
            'doctor_id': doctor_id,
            'status': data.get('status', 'available'),
            'available_from': data.get('available_from'),
            'available_until': data.get('available_until'),
            'date': data.get('date', datetime.utcnow().date().isoformat()),
            'available_slots': data.get('slots', []),
            'updated_at': datetime.utcnow()
        }
        
        # Upsert the availability document
        result = availability_collection.update_one(
            {'doctor_id': doctor_id},
            {'$set': availability_data},
            upsert=True
        )
        
        return jsonify({
            'message': 'Availability updated successfully',
            'doctor_id': doctor_id,
            'availability': availability_data
        }), 200
    
    except Exception as e:
        print(f"[v0] Update availability error: {str(e)}")
        return jsonify({'error': f'Error updating availability: {str(e)}'}), 500

@appointments_bp.route('/doctors/availability', methods=['PUT', 'OPTIONS'])
def save_doctor_availability():
    """Save doctor availability - handles requests from Hospital Dashboard"""
    if request.method == 'OPTIONS':
        return '', 200
    
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({'error': 'Request body is required'}), 400
        
        db = get_db()
        availability_collection = db['availability']
        
        doctor_id = data.get('doctor_id')
        if not doctor_id:
            return jsonify({'error': 'doctor_id is required in request body'}), 400
        
        availability_data = {
            'doctor_id': doctor_id,
            'status': data.get('status', 'available'),
            'available_from': data.get('available_from'),
            'available_until': data.get('available_until'),
            'date': data.get('date', datetime.utcnow().date().isoformat()),
            'available_slots': data.get('slots', []),
            'updated_at': datetime.utcnow()
        }
        
        result = availability_collection.update_one(
            {'doctor_id': doctor_id},
            {'$set': availability_data},
            upsert=True
        )
        
        return jsonify({
            'message': 'Availability saved successfully',
            'doctor_id': doctor_id,
            'status': data.get('status'),
            'date': data.get('date')
        }), 200
    
    except Exception as e:
        print(f"Save availability error: {str(e)}")
        return jsonify({'error': f'Error saving availability: {str(e)}'}), 500

@appointments_bp.route('/notifications', methods=['GET'])
@token_required
def get_notifications():
    """Get notifications for the logged-in user"""
    try:
        db = get_db()
        notifications_collection = db['notifications']
        
        notifications = list(notifications_collection.find(
            {'doctor_id': request.user_id}
        ).sort('created_at', -1))
        
        return jsonify({
            'notifications': [
                {
                    'id': str(notif['_id']),
                    'message': notif['message'],
                    'type': notif['type'],
                    'read': notif['read'],
                    'created_at': notif['created_at'].isoformat()
                }
                for notif in notifications
            ],
            'unread_count': len([n for n in notifications if not n['read']])
        }), 200
    
    except Exception as e:
        print(f"[v0] Get notifications error: {str(e)}")
        return jsonify({'error': f'Error fetching notifications: {str(e)}'}), 500

@appointments_bp.route('/notifications/<notification_id>/read', methods=['PUT'])
@token_required
def mark_notification_read(notification_id):
    """Mark a notification as read"""
    try:
        db = get_db()
        notifications_collection = db['notifications']
        
        result = notifications_collection.update_one(
            {'_id': ObjectId(notification_id)},
            {'$set': {'read': True}}
        )
        
        if result.modified_count > 0:
            return jsonify({'message': 'Notification marked as read'}), 200
        else:
            return jsonify({'error': 'Notification not found'}), 404
    
    except Exception as e:
        print(f"[v0] Mark notification read error: {str(e)}")
        return jsonify({'error': f'Error marking notification: {str(e)}'}), 500

@appointments_bp.route('/health', methods=['GET'])
def health():
    """Health check endpoint"""
    return jsonify({'status': 'Appointments backend is running'}), 200
