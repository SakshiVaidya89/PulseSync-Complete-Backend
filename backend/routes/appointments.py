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
        
        # Create notification for doctor
        try:
            notifications_collection = db['notifications']
            users_collection = db['users']
            
            patient = users_collection.find_one({'_id': ObjectId(patient_id)})
            # Find doctor by name or ID
            doctor = users_collection.find_one({'full_name': data.get('doctor_id')}) or \
                     users_collection.find_one({'_id': ObjectId(data.get('doctor_id'))})
            
            if doctor:
                doctor_notification = {
                    'user_id': str(doctor['_id']),
                    'appointment_id': ObjectId(appointment['_id']),
                    'message': f"New appointment request from {patient.get('full_name', 'Patient')} on {data.get('appointment_date')} at {data.get('appointment_time')} - {data.get('reason')}",
                    'type': 'info',
                    'read': False,
                    'cleared': False,
                    'created_at': datetime.utcnow(),
                    'updated_at': datetime.utcnow()
                }
                notifications_collection.insert_one(doctor_notification)
        except Exception as notif_err:
            print(f"[v0] Warning: Could not create notification: {str(notif_err)}")
        
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
        
        # Get the hospital user profile
        users_collection = db['users']
        hospital_user = users_collection.find_one({'_id': ObjectId(request.user_id)})
        if not hospital_user:
            return jsonify({'error': 'Hospital user not found'}), 404
        
        # Get all possible hospital identifiers
        hospital_id_str = hospital_user.get('full_name', '')
        hospital_user_id = str(hospital_user.get('_id', ''))
        
        # Get all appointments and filter by any matching hospital identifier
        appointments_collection = db['appointments']
        # Query: match by hospital_id field (which stores the hospital name from patient booking)
        # OR match by hospital_user_id (future-proof matching)
        all_appointments = list(appointments_collection.find({
            '$or': [
                {'hospital_id': hospital_id_str},
                {'hospital_id': hospital_user_id}
            ]
        }).sort('appointment_date', -1))
        
        # Convert ObjectId to string for JSON serialization
        appointments = [
            {
                'id': str(apt['_id']),
                'patient_id': str(apt['patient_id']),
                'doctor_id': apt['doctor_id'],
                'hospital_id': apt['hospital_id'],
                'appointment_date': apt['appointment_date'],
                'appointment_time': apt['appointment_time'],
                'reason': apt['reason'],
                'notes': apt['notes'],
                'status': apt['status'],
                'created_at': apt['created_at'].isoformat() if isinstance(apt.get('created_at'), datetime) else apt.get('created_at'),
                'updated_at': apt['updated_at'].isoformat() if isinstance(apt.get('updated_at'), datetime) else apt.get('updated_at')
            }
            for apt in all_appointments
        ]
        
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

@appointments_bp.route('/availability/create', methods=['POST'])
@token_required
def create_availability():
    """Create or update doctor availability"""
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({'error': 'Request body is required'}), 400
        
        doctor_id = data.get('doctor_id')
        if not doctor_id:
            return jsonify({'error': 'doctor_id is required in request body'}), 400
        
        db = get_db()
        availability_collection = db['availability']
        
        # Generate time slots between start and end time with given duration
        start_time_str = data.get('start_time')  # HH:MM format
        end_time_str = data.get('end_time')      # HH:MM format
        duration_minutes = data.get('duration_minutes', 30)
        
        slots = []
        if start_time_str and end_time_str:
            from datetime import datetime as dt, timedelta
            start_dt = dt.strptime(start_time_str, '%H:%M')
            end_dt = dt.strptime(end_time_str, '%H:%M')
            
            current = start_dt
            while current < end_dt:
                next_slot = current + timedelta(minutes=duration_minutes)
                slot_end = min(next_slot, end_dt)
                slots.append({
                    'time': current.strftime('%H:%M'),
                    'end': slot_end.strftime('%H:%M'),
                    'available': True
                })
                current = slot_end
        
        availability_data = {
            'doctor_id': doctor_id,
            'date': data.get('date'),
            'start_time': start_time_str,
            'end_time': end_time_str,
            'duration_minutes': duration_minutes,
            'available_slots': slots,
            'next_available': f"{data.get('date')} {start_time_str}" if data.get('date') and start_time_str else None,
            'status': 'available',
            'created_at': datetime.utcnow(),
            'updated_at': datetime.utcnow()
        }
        
        # Upsert - update if exists for this doctor on this date, otherwise create
        result = availability_collection.update_one(
            {'doctor_id': doctor_id, 'date': data.get('date')},
            {'$set': availability_data},
            upsert=True
        )
        
        return jsonify({
            'message': 'Availability slot created successfully',
            'doctor_id': doctor_id,
            'id': str(result.upserted_id) if result.upserted_id else str(result.matched_ids[0]) if result.matched_ids else None,
            'slots': slots
        }), 200
    
    except Exception as e:
        print(f"[v0] Create availability error: {str(e)}")
        return jsonify({'error': f'Error creating availability: {str(e)}'}), 500

@appointments_bp.route('/availability/hospital/<hospital_id>/slots', methods=['GET'])
@token_required
def get_hospital_availability_slots(hospital_id):
    """Get all availability slots for a hospital"""
    try:
        db = get_db()
        availability_collection = db['availability']
        
        # Get all doctors for this hospital
        users_collection = db['users']
        hospital_user = users_collection.find_one({'_id': ObjectId(hospital_id)})
        
        if not hospital_user:
            return jsonify({'error': 'Hospital not found'}), 404
        
        # Find all availability slots for doctors of this hospital
        slots = list(availability_collection.find({'hospital_id': hospital_id}))
        
        availabilities = [
            {
                'id': str(slot['_id']),
                'doctor_id': slot['doctor_id'],
                'doctor_name': slot.get('doctor_name', 'Unknown'),
                'date': slot['date'],
                'start_time': slot['start_time'],
                'end_time': slot['end_time'],
                'duration_minutes': slot.get('duration_minutes', 30),
                'is_available': slot.get('status') == 'available',
                'created_at': slot['created_at'].isoformat() if isinstance(slot.get('created_at'), datetime) else slot.get('created_at'),
            }
            for slot in slots
        ]
        
        return jsonify({
            'availabilities': availabilities,
            'total': len(availabilities)
        }), 200
    
    except Exception as e:
        print(f"[v0] Get hospital availability slots error: {str(e)}")
        return jsonify({'error': f'Error fetching slots: {str(e)}'}), 500

@appointments_bp.route('/availability/<slot_id>/toggle', methods=['PUT'])
@token_required
def toggle_availability(slot_id):
    """Toggle availability slot status"""
    try:
        db = get_db()
        availability_collection = db['availability']
        
        slot = availability_collection.find_one({'_id': ObjectId(slot_id)})
        if not slot:
            return jsonify({'error': 'Slot not found'}), 404
        
        new_status = 'unavailable' if slot.get('status') == 'available' else 'available'
        
        availability_collection.update_one(
            {'_id': ObjectId(slot_id)},
            {'$set': {'status': new_status, 'updated_at': datetime.utcnow()}}
        )
        
        return jsonify({
            'message': f'Availability toggled to {new_status}',
            'slot_id': slot_id,
            'status': new_status
        }), 200
    
    except Exception as e:
        print(f"[v0] Toggle availability error: {str(e)}")
        return jsonify({'error': f'Error toggling availability: {str(e)}'}), 500

@appointments_bp.route('/notifications', methods=['GET'])
@token_required
def get_notifications():
    """Get unread and uncleared notifications for the user"""
    try:
        db = get_db()
        user_id = request.user_id
        
        # Get notifications for this user that haven't been cleared
        notifications_collection = db['notifications']
        notifications = list(notifications_collection.find({
            'user_id': user_id,
            'cleared': False
        }).sort('created_at', -1))
        
        notifications_data = [
            {
                'id': str(notif['_id']),
                'appointment_id': str(notif.get('appointment_id', '')),
                'message': notif.get('message', ''),
                'type': notif.get('type', 'info'),
                'read': notif.get('read', False),
                'created_at': notif['created_at'].isoformat() if isinstance(notif.get('created_at'), datetime) else notif.get('created_at'),
            }
            for notif in notifications
        ]
        
        return jsonify({
            'notifications': notifications_data,
            'total': len(notifications_data)
        }), 200
    
    except Exception as e:
        print(f"[v0] Get notifications error: {str(e)}")
        return jsonify({'error': f'Error fetching notifications: {str(e)}'}), 500

@appointments_bp.route('/notifications/<notification_id>/clear', methods=['POST'])
@token_required
def clear_notification(notification_id):
    """Clear a notification (mark it as read and cleared)"""
    try:
        db = get_db()
        notifications_collection = db['notifications']
        
        result = notifications_collection.update_one(
            {'_id': ObjectId(notification_id), 'user_id': request.user_id},
            {'$set': {'cleared': True, 'read': True, 'updated_at': datetime.utcnow()}}
        )
        
        if result.matched_count == 0:
            return jsonify({'error': 'Notification not found'}), 404
        
        return jsonify({
            'message': 'Notification cleared',
            'notification_id': notification_id
        }), 200
    
    except Exception as e:
        print(f"[v0] Clear notification error: {str(e)}")
        return jsonify({'error': f'Error clearing notification: {str(e)}'}), 500

@appointments_bp.route('/appointments/<appointment_id>/confirm', methods=['POST'])
@token_required
def confirm_appointment(appointment_id):
    """Confirm an appointment and notify patient"""
    try:
        db = get_db()
        appointments_collection = db['appointments']
        notifications_collection = db['notifications']
        users_collection = db['users']
        
        # Update appointment status
        appointment = appointments_collection.find_one({'_id': ObjectId(appointment_id)})
        if not appointment:
            return jsonify({'error': 'Appointment not found'}), 404
        
        appointments_collection.update_one(
            {'_id': ObjectId(appointment_id)},
            {'$set': {'status': 'confirmed', 'updated_at': datetime.utcnow()}}
        )
        
        # Get patient info
        patient = users_collection.find_one({'_id': ObjectId(appointment['patient_id'])})
        doctor = users_collection.find_one({'_id': ObjectId(request.user_id)})
        
        # Create notification for patient
        patient_notification = {
            'user_id': appointment['patient_id'],
            'appointment_id': ObjectId(appointment_id),
            'message': f"Your appointment with Dr. {doctor.get('full_name', 'Doctor')} has been confirmed for {appointment.get('appointment_date')} at {appointment.get('appointment_time')}",
            'type': 'success',
            'read': False,
            'cleared': False,
            'created_at': datetime.utcnow(),
            'updated_at': datetime.utcnow()
        }
        
        notifications_collection.insert_one(patient_notification)
        
        return jsonify({
            'message': 'Appointment confirmed',
            'appointment_id': appointment_id
        }), 200
    
    except Exception as e:
        print(f"[v0] Confirm appointment error: {str(e)}")
        return jsonify({'error': f'Error confirming appointment: {str(e)}'}), 500

@appointments_bp.route('/appointments/<appointment_id>/cancel', methods=['POST'])
@token_required
def cancel_appointment(appointment_id):
    """Cancel an appointment and notify the other party"""
    try:
        db = get_db()
        appointments_collection = db['appointments']
        notifications_collection = db['notifications']
        users_collection = db['users']
        
        data = request.get_json() or {}
        cancel_reason = data.get('reason', 'No reason provided')
        
        print(f"[v0] Cancel appointment: id={appointment_id}, user_id={request.user_id}, role={request.user_role}")
        
        # Get appointment
        try:
            appointment = appointments_collection.find_one({'_id': ObjectId(appointment_id)})
        except Exception as e:
            print(f"[v0] Invalid appointment ID format: {appointment_id}")
            return jsonify({'error': f'Invalid appointment ID: {str(e)}'}), 400
        
        if not appointment:
            return jsonify({'error': 'Appointment not found'}), 404
        
        # Update appointment status
        appointments_collection.update_one(
            {'_id': ObjectId(appointment_id)},
            {'$set': {'status': 'cancelled', 'cancel_reason': cancel_reason, 'cancelled_by': request.user_id, 'updated_at': datetime.utcnow()}}
        )
        
        # Get user info
        try:
            current_user = users_collection.find_one({'_id': ObjectId(request.user_id)})
        except:
            current_user = {'full_name': 'User'}
        
        # Determine who to notify
        is_doctor_cancelling = request.user_role == 'hospital'
        
        # Notify the other party
        if is_doctor_cancelling:
            # Doctor cancelled - notify patient
            recipient_id = str(appointment['patient_id'])
            notification_message = f"Your appointment on {appointment.get('appointment_date')} at {appointment.get('appointment_time')} has been cancelled. Reason: {cancel_reason}"
        else:
            # Patient cancelled - notify doctor
            recipient_id = str(appointment.get('doctor_id', ''))
            notification_message = f"Appointment on {appointment.get('appointment_date')} at {appointment.get('appointment_time')} has been cancelled by patient. Reason: {cancel_reason}"
        
        if recipient_id:
            cancellation_notification = {
                'user_id': recipient_id,
                'appointment_id': ObjectId(appointment_id),
                'message': notification_message,
                'type': 'warning',
                'read': False,
                'cleared': False,
                'created_at': datetime.utcnow(),
                'updated_at': datetime.utcnow()
            }
            notifications_collection.insert_one(cancellation_notification)
        
        return jsonify({
            'message': 'Appointment cancelled',
            'appointment_id': appointment_id
        }), 200
    
    except Exception as e:
        print(f"[v0] Cancel appointment error: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': f'Error cancelling appointment: {str(e)}'}), 500

@appointments_bp.route('/health', methods=['GET'])
def health():
    """Health check endpoint"""
    return jsonify({'status': 'Appointments backend is running'}), 200
