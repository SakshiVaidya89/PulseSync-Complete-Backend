from pymongo import MongoClient
from bson.objectid import ObjectId
from datetime import datetime

class PrescriptionModel:
    """Prescription model for MongoDB operations"""
    
    def __init__(self, db):
        self.db = db
        self.collection = db['prescriptions']
    
    def save_prescription(self, user_id, medicine_data):
        """
        Save a prescription to the database.
        
        Args:
            user_id: The patient's user ID
            medicine_data: Dictionary containing medicine analysis
        
        Returns:
            dict: Created prescription document with id
        """
        prescription = {
            'user_id': user_id,
            'medicine_name': medicine_data.get('medicine_name'),
            'why_prescribed': medicine_data.get('why_prescribed'),
            'how_it_works': medicine_data.get('how_it_works'),
            'alternatives': medicine_data.get('alternatives', []),
            'ingredients': medicine_data.get('ingredients'),
            'uses': medicine_data.get('uses', []),
            'dosage': medicine_data.get('dosage'),
            'side_effects': medicine_data.get('side_effects', {'common': [], 'serious': []}),
            'interactions': medicine_data.get('interactions', []),
            'where_to_buy': medicine_data.get('where_to_buy', []),
            'storage_tips': medicine_data.get('storage_tips'),
            'created_at': datetime.utcnow(),
            'updated_at': datetime.utcnow()
        }
        
        result = self.collection.insert_one(prescription)
        prescription['_id'] = str(result.inserted_id)
        return prescription
    
    def get_user_prescriptions(self, user_id):
        """
        Get all prescriptions for a user.
        
        Args:
            user_id: The patient's user ID
        
        Returns:
            list: List of prescription documents
        """
        prescriptions = list(self.collection.find({'user_id': user_id}).sort('created_at', -1))
        for prescription in prescriptions:
            prescription['_id'] = str(prescription['_id'])
        return prescriptions
    
    def delete_prescription(self, prescription_id, user_id):
        """
        Delete a prescription (user verification).
        
        Args:
            prescription_id: The prescription ID
            user_id: The user ID (for security)
        
        Returns:
            bool: True if deleted, False if not found
        """
        result = self.collection.delete_one({
            '_id': ObjectId(prescription_id),
            'user_id': user_id
        })
        return result.deleted_count > 0
