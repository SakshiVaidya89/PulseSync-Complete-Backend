from pymongo import MongoClient
from bson.objectid import ObjectId
from werkzeug.security import generate_password_hash
from datetime import datetime

class UserModel:
    """User model for MongoDB operations"""
    
    def __init__(self, db):
        self.db = db
        self.collection = db['users']
    
    @staticmethod
    def create_user(email, password, full_name, role):
        """
        Create a new user in the database.
        
        Args:
            email: User's email address
            password: User's password (will be hashed)
            full_name: User's full name
            role: User role ('patient' or 'hospital')
        
        Returns:
            dict: Created user document with id
        
        Raises:
            ValueError: If email already exists
        """
        # Check if user already exists
        existing_user = UserModel.find_by_email(email)
        if existing_user:
            raise ValueError("Email already registered")
        
        # Create new user document
        user_data = {
            'email': email,
            'password': generate_password_hash(password),
            'full_name': full_name,
            'role': role,
            'profile_complete': False,
            'created_at': datetime.utcnow()
        }
        
        return user_data
    
    @staticmethod
    def find_by_email(email):
        """Find a user by email"""
        client = MongoClient('mongodb://localhost:27017/')
        db = client['pulsesync']
        users_collection = db['users']
        return users_collection.find_one({'email': email})
    
    @staticmethod
    def find_by_id(user_id):
        """Find a user by ID"""
        client = MongoClient('mongodb://localhost:27017/')
        db = client['pulsesync']
        users_collection = db['users']
        return users_collection.find_one({'_id': ObjectId(user_id)})
