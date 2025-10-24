from flask import Blueprint, request, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timedelta
import jwt
import uuid
from bson import ObjectId
from functools import wraps

auth_bp = Blueprint('auth', __name__, url_prefix='/auth')

def init_auth_blueprint(mongo, app_config):
    """Initialize the auth blueprint with database and config"""
    auth_bp.mongo = mongo
    auth_bp.config = app_config
    return auth_bp

# Validation helpers
def validate_email(email):
    import re
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return re.match(pattern, email) is not None

def validate_password(password):
    return len(password) >= 6

@auth_bp.route('/login', methods=['POST'])
def login():
    try:
        data = request.get_json()
        email = data.get('email', '').lower().strip()
        password = data.get('password', '')
        
        if not email or not password:
            return jsonify({
                'success': False,
                'message': 'Email and password are required',
                'errors': {
                    'email': ['Email is required'] if not email else [],
                    'password': ['Password is required'] if not password else []
                }
            }), 400
        
        # Find user
        user = auth_bp.mongo.db.users.find_one({'email': email})
        if not user or not check_password_hash(user['password'], password):
            return jsonify({
                'success': False,
                'message': 'Invalid credentials',
                'errors': {'email': ['Invalid email or password']}
            }), 401
        
        # Generate tokens
        access_token = jwt.encode({
            'user_id': str(user['_id']),
            'exp': datetime.utcnow() + auth_bp.config['JWT_EXPIRATION_DELTA']
        }, auth_bp.config['SECRET_KEY'], algorithm='HS256')
        
        refresh_token = jwt.encode({
            'user_id': str(user['_id']),
            'type': 'refresh',
            'exp': datetime.utcnow() + timedelta(days=30)
        }, auth_bp.config['SECRET_KEY'], algorithm='HS256')
        
        # Update last login
        auth_bp.mongo.db.users.update_one(
            {'_id': user['_id']},
            {'$set': {'lastLogin': datetime.utcnow()}}
        )
        
        return jsonify({
            'success': True,
            'data': {
                'token': access_token,  # Keep for frontend compatibility
                'access_token': access_token,  # Keep for backward compatibility
                'refresh_token': refresh_token,
                'expires_at': (datetime.utcnow() + auth_bp.config['JWT_EXPIRATION_DELTA']).isoformat() + 'Z',
                'user': {
                    'id': str(user['_id']),
                    'email': user['email'],
                    'displayName': user.get('displayName', user.get('firstName', '') + ' ' + user.get('lastName', '')),
                    # Backwards/forwards compatibility: include `name` keyed value as well
                    'name': user.get('displayName', user.get('firstName', '') + ' ' + user.get('lastName', '')),
                    'role': user.get('role', 'personal'),
                    'ficoreCreditBalance': user.get('ficoreCreditBalance', 10.0),
                    'financialGoals': user.get('financialGoals', []),
                    'createdAt': user.get('createdAt', datetime.utcnow()).isoformat() + 'Z'
                }
            },
            'message': 'Login successful'
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'message': 'Login failed',
            'errors': {'general': [str(e)]}
        }), 500

@auth_bp.route('/signup', methods=['POST'])
def signup():
    try:
        data = request.get_json()
        email = data.get('email', '').lower().strip()
        password = data.get('password', '')
        first_name = data.get('firstName', '').strip()
        last_name = data.get('lastName', '').strip()
        
        errors = {}
        
        # Validation (unchanged)
        if not email:
            errors['email'] = ['Email is required']
        elif not validate_email(email):
            errors['email'] = ['Invalid email format']
        elif auth_bp.mongo.db.users.find_one({'email': email}):
            errors['email'] = ['Email already exists']
            
        if not password:
            errors['password'] = ['Password is required']
        elif not validate_password(password):
            errors['password'] = ['Password must be at least 6 characters']
            
        if not first_name:
            errors['firstName'] = ['First name is required']
            
        if not last_name:
            errors['lastName'] = ['Last name is required']
        
        if errors:
            return jsonify({
                'success': False,
                'message': 'Validation failed',
                'errors': errors
            }), 400
        # Get financial goals from request (optional)
        financial_goals = data.get('financialGoals', [])
        # Optional displayName or businessName from frontend
        display_name = data.get('displayName')

        # Validate financial goals if provided
        valid_goals = [
            'save_for_emergencies',
            'pay_off_debt', 
            'budget_better',
            'track_income_expenses',
            'grow_savings_investments',
            'plan_big_purchases',
            'improve_financial_habits',
            'financial_education',
            'manage_business_finances',
            'know_my_profit'
        ]

        if financial_goals:
            invalid_goals = [goal for goal in financial_goals if goal not in valid_goals]
            if invalid_goals:
                errors['financialGoals'] = [f'Invalid goals: {", ".join(invalid_goals)}']

        if errors:
            return jsonify({
                'success': False,
                'message': 'Validation failed',
                'errors': errors
            }), 400

        # Create user with clean account (no demo data, removed setupComplete)
        user_data = {
            'email': email,
            'password': generate_password_hash(password),
            'firstName': first_name,
            'lastName': last_name,
            # Prefer explicit displayName if provided by client (business name), else generate from names
            'displayName': display_name.strip() if display_name and isinstance(display_name, str) and display_name.strip() else f"{first_name} {last_name}",
            'role': 'personal',
            'ficoreCreditBalance': 10.0,  # Starting balance: 10 FC
            'financialGoals': financial_goals,
            'createdAt': datetime.utcnow(),
            'lastLogin': None,
            'isActive': True
        }
        
        result = auth_bp.mongo.db.users.insert_one(user_data)
        user_id = str(result.inserted_id)
        
        # Generate tokens (unchanged)
        access_token = jwt.encode({
            'user_id': user_id,
            'exp': datetime.utcnow() + auth_bp.config['JWT_EXPIRATION_DELTA']
        }, auth_bp.config['SECRET_KEY'], algorithm='HS256')
        
        refresh_token = jwt.encode({
            'user_id': user_id,
            'type': 'refresh',
            'exp': datetime.utcnow() + timedelta(days=30)
        }, auth_bp.config['SECRET_KEY'], algorithm='HS256')
        
        return jsonify({
            'success': True,
            'data': {
                'access_token': access_token,
                'refresh_token': refresh_token,
                'expires_at': (datetime.utcnow() + auth_bp.config['JWT_EXPIRATION_DELTA']).isoformat() + 'Z',
                'user': {
                    'id': user_id,
                    'email': email,
                    'displayName': user_data.get('displayName'),
                    # Also include `name` for client compatibility (mirrors displayName)
                    'name': user_data.get('displayName'),
                    'role': 'personal',
                    'ficoreCreditBalance': 10.0,  # Starting balance: 10 FC
                    'financialGoals': financial_goals,
                    'createdAt': datetime.utcnow().isoformat() + 'Z'
                }
            },
            'message': 'Account created successfully'
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'message': 'Registration failed',
            'errors': {'general': [str(e)]}
        }), 500

@auth_bp.route('/logout', methods=['POST'])
def logout():
    return jsonify({
        'success': True,
        'message': 'Logged out successfully'
    })

@auth_bp.route('/refresh', methods=['POST'])
def refresh_token():
    try:
        data = request.get_json()
        refresh_token = data.get('refresh_token')
        
        if not refresh_token:
            return jsonify({'success': False, 'message': 'Refresh token required'}), 400
        
        try:
            data = jwt.decode(refresh_token, auth_bp.config['SECRET_KEY'], algorithms=['HS256'])
            if data.get('type') != 'refresh':
                return jsonify({'success': False, 'message': 'Invalid refresh token'}), 401
                
            user = auth_bp.mongo.db.users.find_one({'_id': ObjectId(data['user_id'])})
            if not user:
                return jsonify({'success': False, 'message': 'User not found'}), 401
        except jwt.ExpiredSignatureError:
            return jsonify({'success': False, 'message': 'Refresh token expired'}), 401
        except jwt.InvalidTokenError:
            return jsonify({'success': False, 'message': 'Invalid refresh token'}), 401
        
        # Generate new access token
        access_token = jwt.encode({
            'user_id': str(user['_id']),
            'exp': datetime.utcnow() + auth_bp.config['JWT_EXPIRATION_DELTA']
        }, auth_bp.config['SECRET_KEY'], algorithm='HS256')
        
        return jsonify({
            'success': True,
            'data': {
                'access_token': access_token,
                'expires_at': (datetime.utcnow() + auth_bp.config['JWT_EXPIRATION_DELTA']).isoformat() + 'Z'
            },
            'message': 'Token refreshed successfully'
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'message': 'Token refresh failed',
            'errors': {'general': [str(e)]}
        }), 500

@auth_bp.route('/forgot-password', methods=['POST'])
def forgot_password():
    try:
        data = request.get_json()
        email = data.get('email', '').lower().strip()
        
        if not email:
            return jsonify({
                'success': False,
                'message': 'Email is required',
                'errors': {'email': ['Email is required']}
            }), 400
        
        user = auth_bp.mongo.db.users.find_one({'email': email})
        if not user:
            # Don't reveal if email exists or not
            return jsonify({
                'success': True,
                'message': 'If the email exists, a reset link has been sent'
            })
        
        # Generate reset token
        reset_token = str(uuid.uuid4())
        auth_bp.mongo.db.users.update_one(
            {'_id': user['_id']},
            {'$set': {
                'resetToken': reset_token,
                'resetTokenExpiry': datetime.utcnow() + timedelta(hours=1)
            }}
        )
        
        return jsonify({
            'success': True,
            'message': 'Password reset instructions sent to your email'
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'message': 'Password reset failed',
            'errors': {'general': [str(e)]}
        }), 500

@auth_bp.route('/reset-password', methods=['POST'])
def reset_password():
    try:
        data = request.get_json()
        token = data.get('token')
        new_password = data.get('password')
        
        if not token or not new_password:
            return jsonify({
                'success': False,
                'message': 'Token and new password are required',
                'errors': {
                    'token': ['Reset token is required'] if not token else [],
                    'password': ['New password is required'] if not new_password else []
                }
            }), 400
        
        if not validate_password(new_password):
            return jsonify({
                'success': False,
                'message': 'Invalid password',
                'errors': {'password': ['Password must be at least 6 characters']}
            }), 400
        
        user = auth_bp.mongo.db.users.find_one({
            'resetToken': token,
            'resetTokenExpiry': {'$gt': datetime.utcnow()}
        })
        
        if not user:
            return jsonify({
                'success': False,
                'message': 'Invalid or expired reset token',
                'errors': {'token': ['Invalid or expired reset token']}
            }), 400
        
        # Update password and clear reset token
        auth_bp.mongo.db.users.update_one(
            {'_id': user['_id']},
            {'$set': {
                'password': generate_password_hash(new_password)
            }, '$unset': {
                'resetToken': '',
                'resetTokenExpiry': ''
            }}
        )
        
        return jsonify({
            'success': True,
            'message': 'Password reset successfully'
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'message': 'Password reset failed',
            'errors': {'general': [str(e)]}

        }), 500
