from pymongo import MongoClient
from bson.objectid import ObjectId
from datetime import datetime

class AppointmentModel:
    """Appointment model for MongoDB operations"""
    
    def __init__(self, db):
        self.db = db
        self.collection = db['appointments']
    
    @staticmethod
    def create_appointment(db, patient_id, doctor_id, hospital_id, appointment_date, appointment_time, reason, notes):
        """
        Create a new appointment in the database.
        """
        appointment_data = {
            'patient_id': ObjectId(patient_id) if patient_id != 'default_patient' else patient_id,
            'doctor_id': doctor_id,
            'hospital_id': hospital_id,
            'appointment_date': appointment_date,
            'appointment_time': appointment_time,
            'reason': reason,
            'notes': notes,
            'status': 'pending',
            'created_at': datetime.utcnow(),
            'updated_at': datetime.utcnow()
        }
        
        collection = db['appointments']
        result = collection.insert_one(appointment_data)
        
        notification_collection = db['notifications']
        notification_collection.insert_one({
            'doctor_id': doctor_id,
            'appointment_id': str(result.inserted_id),
            'message': f'New appointment booking for {appointment_date} at {appointment_time}. Reason: {reason}',
            'type': 'appointment_booking',
            'read': False,
            'created_at': datetime.utcnow()
        })
        
        return {
            'id': str(result.inserted_id),
            'patient_id': str(appointment_data['patient_id']),
            'doctor_id': appointment_data['doctor_id'],
            'hospital_id': appointment_data['hospital_id'],
            'appointment_date': appointment_data['appointment_date'],
            'appointment_time': appointment_data['appointment_time'],
            'reason': appointment_data['reason'],
            'notes': appointment_data['notes'],
            'status': appointment_data['status'],
            'created_at': appointment_data['created_at'].isoformat(),
            'updated_at': appointment_data['updated_at'].isoformat()
        }
    
    @staticmethod
    def get_patient_appointments(db, patient_id):
        """Get all appointments for a patient"""
        collection = db['appointments']
        query = {'patient_id': ObjectId(patient_id)} if patient_id != 'default_patient' else {'patient_id': patient_id}
        appointments = list(collection.find(query).sort('appointment_date', -1))
        
        return [
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
                'created_at': apt['created_at'].isoformat(),
                'updated_at': apt['updated_at'].isoformat()
            }
            for apt in appointments
        ]
    
    @staticmethod
    def get_doctor_appointments(db, doctor_id):
        """Get all appointments for a doctor"""
        collection = db['appointments']
        appointments = list(collection.find({'doctor_id': doctor_id}).sort('appointment_date', -1))
        
        return [
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
                'created_at': apt['created_at'].isoformat(),
                'updated_at': apt['updated_at'].isoformat()
            }
            for apt in appointments
        ]
    
    @staticmethod
    def get_hospital_appointments(db, hospital_id):
        """Get all appointments for a hospital"""
        collection = db['appointments']
        appointments = list(collection.find({'hospital_id': hospital_id}).sort('appointment_date', -1))
        
        return [
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
                'created_at': apt['created_at'].isoformat(),
                'updated_at': apt['updated_at'].isoformat()
            }
            for apt in appointments
        ]
    
    @staticmethod
    def update_appointment_status(db, appointment_id, new_status):
        """Update appointment status"""
        collection = db['appointments']
        result = collection.update_one(
            {'_id': ObjectId(appointment_id)},
            {'$set': {
                'status': new_status,
                'updated_at': datetime.utcnow()
            }}
        )
        return result.modified_count > 0
    
    @staticmethod
    def cancel_appointment(db, appointment_id):
        """Cancel an appointment"""
        return AppointmentModel.update_appointment_status(db, appointment_id, 'cancelled')
    
    @staticmethod
    def confirm_appointment(db, appointment_id):
        """Confirm an appointment"""
        return AppointmentModel.update_appointment_status(db, appointment_id, 'confirmed')
    
    @staticmethod
    def get_appointment_by_id(db, appointment_id):
        """Get appointment by ID"""
        collection = db['appointments']
        apt = collection.find_one({'_id': ObjectId(appointment_id)})
        
        if not apt:
            return None
        
        return {
            'id': str(apt['_id']),
            'patient_id': str(apt['patient_id']),
            'doctor_id': apt['doctor_id'],
            'hospital_id': apt['hospital_id'],
            'appointment_date': apt['appointment_date'],
            'appointment_time': apt['appointment_time'],
            'reason': apt['reason'],
            'notes': apt['notes'],
            'status': apt['status'],
            'created_at': apt['created_at'].isoformat(),
            'updated_at': apt['updated_at'].isoformat()
        }
