from flask import Blueprint, request, jsonify
from datetime import datetime, timedelta
from bson import ObjectId
from werkzeug.security import generate_password_hash
import uuid
import re

def init_admin_blueprint(mongo, token_required, admin_required, serialize_doc):
    admin_bp = Blueprint('admin', __name__, url_prefix='/admin')

    # ===== DASHBOARD & ANALYTICS ENDPOINTS =====

    @admin_bp.route('/dashboard/stats', methods=['GET'])
    @token_required
    @admin_required
    def get_dashboard_stats(current_user):
        """Get comprehensive dashboard statistics for admin"""
        try:
            # User statistics
            total_users = mongo.db.users.count_documents({})
            active_users = mongo.db.users.count_documents({'isActive': True})
            admin_users = mongo.db.users.count_documents({'role': 'admin'})
            
            # Credit statistics
            pending_credit_requests = mongo.db.credit_requests.count_documents({'status': 'pending'})
            total_credits_issued = mongo.db.credit_transactions.aggregate([
                {'$match': {'type': 'credit', 'status': 'completed'}},
                {'$group': {'_id': None, 'total': {'$sum': '$amount'}}}
            ])
            total_credits_issued = list(total_credits_issued)
            total_credits_issued = total_credits_issued[0]['total'] if total_credits_issued else 0
            
            # Credits this month
            start_of_month = datetime.utcnow().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            credits_this_month = mongo.db.credit_transactions.aggregate([
                {'$match': {
                    'type': 'credit', 
                    'status': 'completed',
                    'createdAt': {'$gte': start_of_month}
                }},
                {'$group': {'_id': None, 'total': {'$sum': '$amount'}}}
            ])
            credits_this_month = list(credits_this_month)
            credits_this_month = credits_this_month[0]['total'] if credits_this_month else 0
            
            # Budget statistics
            total_budgets = mongo.db.budgets.count_documents({})
            budgets_this_month = mongo.db.budgets.count_documents({
                'createdAt': {'$gte': start_of_month}
            })
            
            # Recent activities (last 10)
            recent_activities = []
            
            # Get recent credit approvals
            recent_credits = list(mongo.db.credit_requests.find({
                'status': {'$in': ['approved', 'rejected']},
                'processedAt': {'$exists': True}
            }).sort('processedAt', -1).limit(5))
            
            for credit in recent_credits:
                user = mongo.db.users.find_one({'_id': credit['userId']})
                admin_user = mongo.db.users.find_one({'_id': credit.get('processedBy')})
                
                recent_activities.append({
                    'action': f'Credit request {credit["status"]}',
                    'userName': admin_user.get('displayName', 'Admin') if admin_user else 'Admin',
                    'timestamp': credit['processedAt'].isoformat() + 'Z',
                    'details': f'{credit["amount"]} FC for {user.get("displayName", "Unknown User") if user else "Unknown User"}'
                })
            
            # Get recent user registrations
            recent_users = list(mongo.db.users.find({}).sort('createdAt', -1).limit(3))
            for user in recent_users:
                recent_activities.append({
                    'action': 'New user registered',
                    'userName': user.get('displayName', 'Unknown User'),
                    'timestamp': user.get('createdAt', datetime.utcnow()).isoformat() + 'Z',
                    'details': f'Email: {user.get("email", "")}'
                })
            
            # Sort activities by timestamp
            recent_activities.sort(key=lambda x: x['timestamp'], reverse=True)
            recent_activities = recent_activities[:10]

            stats = {
                'totalUsers': total_users,
                'activeUsers': active_users,
                'adminUsers': admin_users,
                'totalBudgets': total_budgets,
                'budgetsThisMonth': budgets_this_month,
                'pendingCreditRequests': pending_credit_requests,
                'totalCreditsIssued': total_credits_issued,
                'creditsThisMonth': credits_this_month,
                'recentActivities': recent_activities
            }

            return jsonify({
                'success': True,
                'data': stats,
                'message': 'Dashboard statistics retrieved successfully'
            })

        except Exception as e:
            return jsonify({
                'success': False,
                'message': 'Failed to retrieve dashboard statistics',
                'errors': {'general': [str(e)]}
            }), 500

    # ===== COMPREHENSIVE USER MANAGEMENT ENDPOINTS =====

    @admin_bp.route('/users', methods=['GET'])
    @token_required
    @admin_required
    def get_all_users(current_user):
        """Get all users for admin management"""
        try:
            # Get pagination and filter parameters
            page = int(request.args.get('page', 1))
            limit = int(request.args.get('limit', 20))
            search = request.args.get('search', '')
            role = request.args.get('role', '')
            is_active = request.args.get('is_active', '')
            sort_by = request.args.get('sort_by', 'createdAt')
            sort_order = request.args.get('sort_order', 'desc')
            
            # Build query
            query = {}
            if search:
                query['$or'] = [
                    {'email': {'$regex': search, '$options': 'i'}},
                    {'displayName': {'$regex': search, '$options': 'i'}},
                    {'firstName': {'$regex': search, '$options': 'i'}},
                    {'lastName': {'$regex': search, '$options': 'i'}}
                ]
            
            if role:
                query['role'] = role
                
            if is_active:
                query['isActive'] = is_active.lower() == 'true'

            # Get total count
            total = mongo.db.users.count_documents(query)
            
            # Get users with pagination and sorting
            skip = (page - 1) * limit
            sort_direction = -1 if sort_order == 'desc' else 1
            users = list(mongo.db.users.find(query)
                        .sort(sort_by, sort_direction)
                        .skip(skip)
                        .limit(limit))
            
            # Serialize users (exclude sensitive data)
            user_data = []
            for user in users:
                user_info = {
                    'id': str(user['_id']),
                    'email': user.get('email', ''),
                    'firstName': user.get('firstName', ''),
                    'lastName': user.get('lastName', ''),
                    'displayName': user.get('displayName', ''),
                    # Provide `name` for client compatibility (mirrors displayName)
                    'name': user.get('displayName', ''),
                    'role': user.get('role', 'personal'),
                    'ficoreCreditBalance': user.get('ficoreCreditBalance', 0.0),
                    'language': user.get('language', 'en'),
                    'setupComplete': user.get('setupComplete', False),
                    'isActive': user.get('isActive', True),
                    'createdAt': user.get('createdAt', datetime.utcnow()).isoformat() + 'Z',
                    'lastLogin': user.get('lastLogin').isoformat() + 'Z' if user.get('lastLogin') else None,
                    'financialGoals': user.get('financialGoals', [])
                }
                user_data.append(user_info)

            return jsonify({
                'success': True,
                'data': {
                    'users': user_data,
                    'pagination': {
                        'page': page,
                        'limit': limit,
                        'total': total,
                        'pages': (total + limit - 1) // limit,
                        'hasNext': page * limit < total,
                        'hasPrev': page > 1
                    }
                },
                'message': 'Users retrieved successfully'
            })

        except Exception as e:
            return jsonify({
                'success': False,
                'message': 'Failed to retrieve users',
                'errors': {'general': [str(e)]}
            }), 500

    @admin_bp.route('/users', methods=['POST'])
    @token_required
    @admin_required
    def create_user(current_user):
        """Create a new user (admin only)"""
        try:
            data = request.get_json()
            required_fields = ['email', 'firstName', 'lastName', 'password', 'role']
            
            for field in required_fields:
                if field not in data:
                    return jsonify({
                        'success': False,
                        'message': f'Missing required field: {field}'
                    }), 400

            email = data['email'].lower().strip()
            first_name = data['firstName'].strip()
            last_name = data['lastName'].strip()
            password = data['password']
            role = data['role']
            initial_credits = float(data.get('ficoreCreditBalance', 10.0))

            # Validate email format
            if not re.match(r'^[^@]+@[^@]+\.[^@]+', email):
                return jsonify({
                    'success': False,
                    'message': 'Invalid email format'
                }), 400

            # Check if user already exists
            if mongo.db.users.find_one({'email': email}):
                return jsonify({
                    'success': False,
                    'message': 'User with this email already exists'
                }), 400

            # Validate role
            if role not in ['personal', 'admin']:
                return jsonify({
                    'success': False,
                    'message': 'Role must be either "personal" or "admin"'
                }), 400

            # Create user
            user_data = {
                '_id': ObjectId(),
                'email': email,
                'password': generate_password_hash(password),
                'firstName': first_name,
                'lastName': last_name,
                'displayName': f"{first_name} {last_name}",
                'role': role,
                'ficoreCreditBalance': initial_credits,
                'financialGoals': [],
                'createdAt': datetime.utcnow(),
                'lastLogin': None,
                'isActive': True,
                'language': 'en',
                'setupComplete': True
            }

            mongo.db.users.insert_one(user_data)

            # Return user data (without password)
            user_response = serialize_doc(user_data.copy())
            del user_response['password']
            user_response['createdAt'] = user_data['createdAt'].isoformat() + 'Z'
            # Ensure `name` is present (mirror displayName)
            user_response['name'] = user_response.get('displayName', '')

            return jsonify({
                'success': True,
                'data': user_response,
                'message': 'User created successfully'
            })

        except Exception as e:
            return jsonify({
                'success': False,
                'message': 'Failed to create user',
                'errors': {'general': [str(e)]}
            }), 500

    @admin_bp.route('/users/<user_id>', methods=['PUT'])
    @token_required
    @admin_required
    def update_user(current_user, user_id):
        """Update user information (admin only)"""
        try:
            data = request.get_json()
            
            # Find user
            user = mongo.db.users.find_one({'_id': ObjectId(user_id)})
            if not user:
                return jsonify({
                    'success': False,
                    'message': 'User not found'
                }), 404

            # Prepare update data
            update_data = {}
            
            if 'email' in data:
                email = data['email'].lower().strip()
                # Check if email is already taken by another user
                existing_user = mongo.db.users.find_one({
                    'email': email,
                    '_id': {'$ne': ObjectId(user_id)}
                })
                if existing_user:
                    return jsonify({
                        'success': False,
                        'message': 'Email already taken by another user'
                    }), 400
                update_data['email'] = email

            if 'firstName' in data:
                update_data['firstName'] = data['firstName'].strip()
            
            if 'lastName' in data:
                update_data['lastName'] = data['lastName'].strip()
            
            # Update display name if first or last name changed
            if 'firstName' in update_data or 'lastName' in update_data:
                first_name = update_data.get('firstName', user.get('firstName', ''))
                last_name = update_data.get('lastName', user.get('lastName', ''))
                update_data['displayName'] = f"{first_name} {last_name}"

            if update_data:
                update_data['updatedAt'] = datetime.utcnow()
                mongo.db.users.update_one(
                    {'_id': ObjectId(user_id)},
                    {'$set': update_data}
                )

            # Get updated user
            updated_user = mongo.db.users.find_one({'_id': ObjectId(user_id)})
            user_response = serialize_doc(updated_user.copy())
            del user_response['password']
            user_response['createdAt'] = updated_user.get('createdAt', datetime.utcnow()).isoformat() + 'Z'
            if updated_user.get('lastLogin'):
                user_response['lastLogin'] = updated_user['lastLogin'].isoformat() + 'Z'
            # Ensure `name` is present (mirror displayName)
            user_response['name'] = user_response.get('displayName', '')
            # Ensure `name` is present (mirror displayName)
            user_response['name'] = user_response.get('displayName', '')

            return jsonify({
                'success': True,
                'data': user_response,
                'message': 'User updated successfully'
            })

        except Exception as e:
            return jsonify({
                'success': False,
                'message': 'Failed to update user',
                'errors': {'general': [str(e)]}
            }), 500

    @admin_bp.route('/users/<user_id>/reset-password', methods=['POST'])
    @token_required
    @admin_required
    def reset_user_password(current_user, user_id):
        """Send password reset email to user (admin only)"""
        try:
            # Find user
            user = mongo.db.users.find_one({'_id': ObjectId(user_id)})
            if not user:
                return jsonify({
                    'success': False,
                    'message': 'User not found'
                }), 404

            # Generate reset token
            reset_token = str(uuid.uuid4())
            
            mongo.db.users.update_one(
                {'_id': ObjectId(user_id)},
                {'$set': {
                    'resetToken': reset_token,
                    'resetTokenExpiry': datetime.utcnow() + timedelta(hours=1),
                    'updatedAt': datetime.utcnow()
                }}
            )

            return jsonify({
                'success': True,
                'message': f'Password reset email sent to {user["email"]}'
            })

        except Exception as e:
            return jsonify({
                'success': False,
                'message': 'Failed to send password reset email',
                'errors': {'general': [str(e)]}
            }), 500

    @admin_bp.route('/users/<user_id>/role', methods=['PUT'])
    @token_required
    @admin_required
    def update_user_role(current_user, user_id):
        """Update user role (admin only)"""
        try:
            data = request.get_json()
            
            if 'role' not in data:
                return jsonify({
                    'success': False,
                    'message': 'Role is required'
                }), 400

            new_role = data['role']
            if new_role not in ['personal', 'admin']:
                return jsonify({
                    'success': False,
                    'message': 'Role must be either "personal" or "admin"'
                }), 400

            # Find user
            user = mongo.db.users.find_one({'_id': ObjectId(user_id)})
            if not user:
                return jsonify({
                    'success': False,
                    'message': 'User not found'
                }), 404

            # Update role
            mongo.db.users.update_one(
                {'_id': ObjectId(user_id)},
                {'$set': {
                    'role': new_role,
                    'updatedAt': datetime.utcnow()
                }}
            )

            # Get updated user
            updated_user = mongo.db.users.find_one({'_id': ObjectId(user_id)})
            user_response = serialize_doc(updated_user.copy())
            del user_response['password']
            user_response['createdAt'] = updated_user.get('createdAt', datetime.utcnow()).isoformat() + 'Z'
            if updated_user.get('lastLogin'):
                user_response['lastLogin'] = updated_user['lastLogin'].isoformat() + 'Z'

            return jsonify({
                'success': True,
                'data': user_response,
                'message': f'User role updated to {new_role}'
            })

        except Exception as e:
            return jsonify({
                'success': False,
                'message': 'Failed to update user role',
                'errors': {'general': [str(e)]}
            }), 500

    @admin_bp.route('/users/<user_id>/credits', methods=['PUT'])
    @token_required
    @admin_required
    def update_user_credits(current_user, user_id):
        """Update user credits with operation support (admin only)"""
        try:
            data = request.get_json()
            
            required_fields = ['operation', 'amount']
            for field in required_fields:
                if field not in data:
                    return jsonify({
                        'success': False,
                        'message': f'Missing required field: {field}'
                    }), 400

            operation = data['operation']  # 'add', 'deduct', 'set'
            amount = float(data['amount'])
            reason = data.get('reason', 'Admin credit adjustment')

            if operation not in ['add', 'deduct', 'set']:
                return jsonify({
                    'success': False,
                    'message': 'Operation must be "add", "deduct", or "set"'
                }), 400

            if amount < 0:
                return jsonify({
                    'success': False,
                    'message': 'Amount cannot be negative'
                }), 400

            # Find user
            user = mongo.db.users.find_one({'_id': ObjectId(user_id)})
            if not user:
                return jsonify({
                    'success': False,
                    'message': 'User not found'
                }), 404

            current_balance = user.get('ficoreCreditBalance', 0.0)
            
            # Calculate new balance based on operation
            if operation == 'add':
                new_balance = current_balance + amount
                transaction_type = 'credit'
                description = f'Admin credit addition: {reason}'
            elif operation == 'deduct':
                if current_balance < amount:
                    return jsonify({
                        'success': False,
                        'message': 'Insufficient credits to deduct',
                        'data': {
                            'currentBalance': current_balance,
                            'requestedDeduction': amount
                        }
                    }), 400
                new_balance = current_balance - amount
                transaction_type = 'debit'
                description = f'Admin credit deduction: {reason}'
            else:  # set
                new_balance = amount
                transaction_type = 'credit' if amount > current_balance else 'debit'
                description = f'Admin credit balance set: {reason}'

            # Update user balance
            mongo.db.users.update_one(
                {'_id': ObjectId(user_id)},
                {'$set': {
                    'ficoreCreditBalance': new_balance,
                    'updatedAt': datetime.utcnow()
                }}
            )

            # Create transaction record
            transaction = {
                '_id': ObjectId(),
                'userId': ObjectId(user_id),
                'type': transaction_type,
                'amount': abs(new_balance - current_balance),
                'description': description,
                'status': 'completed',
                'balanceBefore': current_balance,
                'balanceAfter': new_balance,
                'processedBy': current_user['_id'],
                'createdAt': datetime.utcnow(),
                'metadata': {
                    'adjustmentType': 'admin',
                    'operation': operation,
                    'adjustedBy': current_user.get('displayName', 'Admin'),
                    'reason': reason
                }
            }
            
            mongo.db.credit_transactions.insert_one(transaction)

            # Get updated user
            updated_user = mongo.db.users.find_one({'_id': ObjectId(user_id)})
            user_response = serialize_doc(updated_user.copy())
            del user_response['password']
            user_response['createdAt'] = updated_user.get('createdAt', datetime.utcnow()).isoformat() + 'Z'
            if updated_user.get('lastLogin'):
                user_response['lastLogin'] = updated_user['lastLogin'].isoformat() + 'Z'

            return jsonify({
                'success': True,
                'data': user_response,
                'message': f'User credits {operation}ed successfully'
            })

        except ValueError:
            return jsonify({
                'success': False,
                'message': 'Invalid amount format'
            }), 400
        except Exception as e:
            return jsonify({
                'success': False,
                'message': 'Failed to update user credits',
                'errors': {'general': [str(e)]}
            }), 500

    @admin_bp.route('/users/<user_id>/activity', methods=['GET'])
    @token_required
    @admin_required
    def get_user_activity(current_user, user_id):
        """Get user activity history (admin only)"""
        try:
            # Find user
            user = mongo.db.users.find_one({'_id': ObjectId(user_id)})
            if not user:
                return jsonify({
                    'success': False,
                    'message': 'User not found'
                }), 404

            activities = []
            
            # Get credit transactions
            credit_transactions = list(mongo.db.credit_transactions.find({
                'userId': ObjectId(user_id)
            }).sort('createdAt', -1).limit(20))
            
            for transaction in credit_transactions:
                activities.append({
                    'action': f'Credit {transaction["type"]}',
                    'timestamp': transaction.get('createdAt', datetime.utcnow()).isoformat() + 'Z',
                    'details': f'{transaction["amount"]} FC - {transaction.get("description", "")}'
                })

            # Get expense activities
            expenses = list(mongo.db.expenses.find({
                'userId': ObjectId(user_id)
            }).sort('date', -1).limit(10))
            
            for expense in expenses:
                activities.append({
                    'action': 'Expense recorded',
                    'timestamp': expense.get('date', datetime.utcnow()).isoformat() + 'Z',
                    'details': f'{expense["amount"]} NGN - {expense.get("description", expense.get("category", ""))}'
                })

            # Get income activities
            incomes = list(mongo.db.incomes.find({
                'userId': ObjectId(user_id)
            }).sort('dateReceived', -1).limit(10))
            
            for income in incomes:
                activities.append({
                    'action': 'Income recorded',
                    'timestamp': income.get('dateReceived', datetime.utcnow()).isoformat() + 'Z',
                    'details': f'{income["amount"]} NGN - {income.get("description", income.get("source", ""))}'
                })

            # Sort activities by timestamp
            activities.sort(key=lambda x: x['timestamp'], reverse=True)
            activities = activities[:30]  # Limit to 30 most recent

            return jsonify({
                'success': True,
                'data': activities,
                'message': 'User activity retrieved successfully'
            })

        except Exception as e:
            return jsonify({
                'success': False,
                'message': 'Failed to retrieve user activity',
                'errors': {'general': [str(e)]}
            }), 500

    @admin_bp.route('/users/<user_id>/suspend', methods=['POST'])
    @token_required
    @admin_required
    def suspend_user(current_user, user_id):
        """Suspend a user account (admin only)"""
        try:
            data = request.get_json() or {}
            reason = data.get('reason', 'Account suspended by admin')
            
            # Find user
            user = mongo.db.users.find_one({'_id': ObjectId(user_id)})
            if not user:
                return jsonify({
                    'success': False,
                    'message': 'User not found'
                }), 404

            # Update user status
            mongo.db.users.update_one(
                {'_id': ObjectId(user_id)},
                {'$set': {
                    'isActive': False,
                    'suspendedAt': datetime.utcnow(),
                    'suspendedBy': current_user['_id'],
                    'suspensionReason': reason,
                    'updatedAt': datetime.utcnow()
                }}
            )

            # Get updated user
            updated_user = mongo.db.users.find_one({'_id': ObjectId(user_id)})
            user_response = serialize_doc(updated_user.copy())
            del user_response['password']
            user_response['createdAt'] = updated_user.get('createdAt', datetime.utcnow()).isoformat() + 'Z'
            if updated_user.get('lastLogin'):
                user_response['lastLogin'] = updated_user['lastLogin'].isoformat() + 'Z'

            return jsonify({
                'success': True,
                'data': user_response,
                'message': 'User suspended successfully'
            })

        except Exception as e:
            return jsonify({
                'success': False,
                'message': 'Failed to suspend user',
                'errors': {'general': [str(e)]}
            }), 500

    @admin_bp.route('/users/<user_id>/activate', methods=['POST'])
    @token_required
    @admin_required
    def activate_user(current_user, user_id):
        """Activate a suspended user account (admin only)"""
        try:
            # Find user
            user = mongo.db.users.find_one({'_id': ObjectId(user_id)})
            if not user:
                return jsonify({
                    'success': False,
                    'message': 'User not found'
                }), 404

            # Update user status
            mongo.db.users.update_one(
                {'_id': ObjectId(user_id)},
                {'$set': {
                    'isActive': True,
                    'activatedAt': datetime.utcnow(),
                    'activatedBy': current_user['_id'],
                    'updatedAt': datetime.utcnow()
                },
                '$unset': {
                    'suspendedAt': '',
                    'suspendedBy': '',
                    'suspensionReason': ''
                }}
            )

            # Get updated user
            updated_user = mongo.db.users.find_one({'_id': ObjectId(user_id)})
            user_response = serialize_doc(updated_user.copy())
            del user_response['password']
            user_response['createdAt'] = updated_user.get('createdAt', datetime.utcnow()).isoformat() + 'Z'
            if updated_user.get('lastLogin'):
                user_response['lastLogin'] = updated_user['lastLogin'].isoformat() + 'Z'

            return jsonify({
                'success': True,
                'data': user_response,
                'message': 'User activated successfully'
            })

        except Exception as e:
            return jsonify({
                'success': False,
                'message': 'Failed to activate user',
                'errors': {'general': [str(e)]}
            }), 500

    @admin_bp.route('/users/<user_id>', methods=['DELETE'])
    @token_required
    @admin_required
    def delete_user(current_user, user_id):
        """Delete a user account permanently (admin only)"""
        try:
            # Find user
            user = mongo.db.users.find_one({'_id': ObjectId(user_id)})
            if not user:
                return jsonify({
                    'success': False,
                    'message': 'User not found'
                }), 404

            # Prevent deleting admin users (safety check)
            if user.get('role') == 'admin':
                return jsonify({
                    'success': False,
                    'message': 'Cannot delete admin users'
                }), 403

            # Delete user and related data
            mongo.db.users.delete_one({'_id': ObjectId(user_id)})
            mongo.db.expenses.delete_many({'userId': ObjectId(user_id)})
            mongo.db.incomes.delete_many({'userId': ObjectId(user_id)})
            mongo.db.budgets.delete_many({'userId': ObjectId(user_id)})
            mongo.db.credit_requests.delete_many({'userId': ObjectId(user_id)})
            mongo.db.credit_transactions.delete_many({'userId': ObjectId(user_id)})

            return jsonify({
                'success': True,
                'message': 'User deleted successfully'
            })

        except Exception as e:
            return jsonify({
                'success': False,
                'message': 'Failed to delete user',
                'errors': {'general': [str(e)]}
            }), 500

    # ===== CREDIT REQUEST MANAGEMENT ENDPOINTS =====

    @admin_bp.route('/credit-requests', methods=['GET'])
    @admin_bp.route('/credits/requests', methods=['GET'])  # Alternative endpoint for frontend compatibility
    @token_required
    @admin_required
    def get_all_credit_requests(current_user):
        """Get all credit requests for admin review"""
        try:
            # Get pagination parameters
            page = int(request.args.get('page', 1))
            limit = int(request.args.get('limit', 20))
            status = request.args.get('status', 'all')  # all, pending, approved, rejected
            
            # Build query
            query = {}
            if status != 'all':
                query['status'] = status

            # Get total count
            total = mongo.db.credit_requests.count_documents(query)
            
            # Get requests with pagination
            skip = (page - 1) * limit
            requests = list(mongo.db.credit_requests.find(query)
                          .sort('createdAt', -1)
                          .skip(skip)
                          .limit(limit))
            
            # Get user details for each request
            request_data = []
            for req in requests:
                req_data = serialize_doc(req.copy())
                
                # Get user info
                user = mongo.db.users.find_one({'_id': req['userId']})
                if user:
                    req_data['user'] = {
                        'id': str(user['_id']),
                        'email': user.get('email', ''),
                        'displayName': user.get('displayName', ''),
                        'name': user.get('displayName', ''),
                        'currentBalance': user.get('ficoreCreditBalance', 0.0)
                    }
                
                # Format dates
                req_data['createdAt'] = req_data.get('createdAt', datetime.utcnow()).isoformat() + 'Z'
                req_data['updatedAt'] = req_data.get('updatedAt', datetime.utcnow()).isoformat() + 'Z'
                if req_data.get('processedAt'):
                    req_data['processedAt'] = req_data.get('processedAt', datetime.utcnow()).isoformat() + 'Z'
                
                request_data.append(req_data)

            # Get summary statistics
            stats = {
                'total': total,
                'pending': mongo.db.credit_requests.count_documents({'status': 'pending'}),
                'approved': mongo.db.credit_requests.count_documents({'status': 'approved'}),
                'rejected': mongo.db.credit_requests.count_documents({'status': 'rejected'}),
                'processing': mongo.db.credit_requests.count_documents({'status': 'processing'})
            }

            return jsonify({
                'success': True,
                'data': {
                    'requests': request_data,
                    'pagination': {
                        'page': page,
                        'limit': limit,
                        'total': total,
                        'pages': (total + limit - 1) // limit,
                        'hasNext': page * limit < total,
                        'hasPrev': page > 1
                    },
                    'statistics': stats
                },
                'message': 'Credit requests retrieved successfully'
            })

        except Exception as e:
            return jsonify({
                'success': False,
                'message': 'Failed to retrieve credit requests',
                'errors': {'general': [str(e)]}
            }), 500

    @admin_bp.route('/credit-requests/<request_id>/approve', methods=['POST'])
    @admin_bp.route('/credits/requests/<request_id>/approve', methods=['POST'])  # Alternative endpoint
    @token_required
    @admin_required
    def approve_credit_request(current_user, request_id):
        """Approve a credit request and add credits to user account"""
        try:
            data = request.get_json() or {}
            admin_notes = data.get('notes', '')
            
            # Find the credit request
            credit_request = mongo.db.credit_requests.find_one({'requestId': request_id})
            
            if not credit_request:
                return jsonify({
                    'success': False,
                    'message': 'Credit request not found'
                }), 404

            if credit_request['status'] != 'pending':
                return jsonify({
                    'success': False,
                    'message': 'Credit request has already been processed'
                }), 400

            # Get the user
            user = mongo.db.users.find_one({'_id': credit_request['userId']})
            if not user:
                return jsonify({
                    'success': False,
                    'message': 'User not found'
                }), 404

            # Update credit request status
            mongo.db.credit_requests.update_one(
                {'requestId': request_id},
                {
                    '$set': {
                        'status': 'approved',
                        'processedBy': current_user['_id'],
                        'processedAt': datetime.utcnow(),
                        'updatedAt': datetime.utcnow(),
                        'adminNotes': admin_notes
                    }
                }
            )

            # Add credits to user account
            current_balance = user.get('ficoreCreditBalance', 0.0)
            new_balance = current_balance + credit_request['amount']
            
            mongo.db.users.update_one(
                {'_id': credit_request['userId']},
                {'$set': {'ficoreCreditBalance': new_balance}}
            )

            # Get naira amount for description
            naira_amount = credit_request.get('nairaAmount', 0)
            credit_amount = credit_request['amount']
            
            # Update the pending transaction to completed status
            mongo.db.credit_transactions.update_one(
                {'requestId': request_id, 'type': 'credit'},
                {
                    '$set': {
                        'status': 'completed',
                        'description': f'Credit top-up approved for {credit_amount:.1f} FCs ({naira_amount:.0f} NGN) - {credit_request["paymentMethod"]}',
                        'balanceBefore': current_balance,
                        'balanceAfter': new_balance,
                        'processedBy': current_user['_id'],
                        'updatedAt': datetime.utcnow(),
                        'metadata': {
                            'requestType': 'topup',
                            'approvedBy': current_user.get('displayName', 'Admin'),
                            'adminNotes': admin_notes,
                            'paymentMethod': credit_request['paymentMethod'],
                            'nairaAmount': naira_amount,
                            'creditAmount': credit_amount
                        }
                    }
                }
            )

            return jsonify({
                'success': True,
                'data': {
                    'requestId': request_id,
                    'amount': credit_request['amount'],
                    'userPreviousBalance': current_balance,
                    'userNewBalance': new_balance,
                    'processedBy': current_user.get('displayName', 'Admin'),
                    'processedAt': datetime.utcnow().isoformat() + 'Z'
                },
                'message': 'Credit request approved successfully'
            })

        except Exception as e:
            return jsonify({
                'success': False,
                'message': 'Failed to approve credit request',
                'errors': {'general': [str(e)]}
            }), 500

    @admin_bp.route('/credit-requests/<request_id>/reject', methods=['POST'])
    @admin_bp.route('/credits/requests/<request_id>/reject', methods=['POST'])  # Alternative endpoint
    @token_required
    @admin_required
    def reject_credit_request(current_user, request_id):
        """Reject a credit request"""
        try:
            data = request.get_json() or {}
            rejection_reason = data.get('reason', 'Request rejected by admin')
            admin_notes = data.get('notes', '')
            
            # Find the credit request
            credit_request = mongo.db.credit_requests.find_one({'requestId': request_id})
            
            if not credit_request:
                return jsonify({
                    'success': False,
                    'message': 'Credit request not found'
                }), 404

            if credit_request['status'] != 'pending':
                return jsonify({
                    'success': False,
                    'message': 'Credit request has already been processed'
                }), 400

            # Update credit request status
            mongo.db.credit_requests.update_one(
                {'requestId': request_id},
                {
                    '$set': {
                        'status': 'rejected',
                        'processedBy': current_user['_id'],
                        'processedAt': datetime.utcnow(),
                        'updatedAt': datetime.utcnow(),
                        'rejectionReason': rejection_reason,
                        'adminNotes': admin_notes
                    }
                }
            )

            # Get naira amount for description
            naira_amount = credit_request.get('nairaAmount', 0)
            credit_amount = credit_request['amount']
            
            # Update the pending transaction status
            mongo.db.credit_transactions.update_one(
                {'requestId': request_id, 'type': 'credit'},
                {
                    '$set': {
                        'status': 'rejected',
                        'updatedAt': datetime.utcnow(),
                        'rejectionReason': rejection_reason,
                        'description': f'Credit top-up rejected for {credit_amount:.1f} FCs ({naira_amount:.0f} NGN) - {credit_request["paymentMethod"]}'
                    }
                }
            )

            return jsonify({
                'success': True,
                'data': {
                    'requestId': request_id,
                    'rejectionReason': rejection_reason,
                    'processedBy': current_user.get('displayName', 'Admin'),
                    'processedAt': datetime.utcnow().isoformat() + 'Z'
                },
                'message': 'Credit request rejected successfully'
            })

        except Exception as e:
            return jsonify({
                'success': False,
                'message': 'Failed to reject credit request',
                'errors': {'general': [str(e)]}
            }), 500

    @admin_bp.route('/credits/requests/<request_id>', methods=['PUT'])
    @token_required
    @admin_required
    def update_credit_request_status(current_user, request_id):
        """Update credit request status (approve/deny) - unified endpoint for frontend"""
        try:
            data = request.get_json() or {}
            status = data.get('status')
            comments = data.get('comments', '')
            
            if not status:
                return jsonify({
                    'success': False,
                    'message': 'Status is required'
                }), 400
            
            if status not in ['approved', 'denied', 'rejected']:
                return jsonify({
                    'success': False,
                    'message': 'Invalid status. Must be approved, denied, or rejected'
                }), 400
            
            # Find the credit request
            credit_request = mongo.db.credit_requests.find_one({'requestId': request_id})
            
            if not credit_request:
                return jsonify({
                    'success': False,
                    'message': 'Credit request not found'
                }), 404

            if credit_request['status'] != 'pending':
                return jsonify({
                    'success': False,
                    'message': 'Credit request has already been processed'
                }), 400

            # Handle approval
            if status == 'approved':
                # Get the user
                user = mongo.db.users.find_one({'_id': credit_request['userId']})
                if not user:
                    return jsonify({
                        'success': False,
                        'message': 'User not found'
                    }), 404

                # Update credit request status
                mongo.db.credit_requests.update_one(
                    {'requestId': request_id},
                    {
                        '$set': {
                            'status': 'approved',
                            'processedAt': datetime.utcnow(),
                            'processedBy': current_user['_id'],
                            'adminNotes': comments,
                            'updatedAt': datetime.utcnow()
                        }
                    }
                )

                # Add credits to user account
                current_balance = user.get('ficoreCreditBalance', 0.0)
                new_balance = current_balance + credit_request['amount']
                
                mongo.db.users.update_one(
                    {'_id': credit_request['userId']},
                    {'$set': {'ficoreCreditBalance': new_balance}}
                )

                # Update the pending transaction to completed status
                naira_amount = credit_request.get('nairaAmount', 0)
                credit_amount = credit_request['amount']
                
                mongo.db.credit_transactions.update_one(
                    {'requestId': request_id},
                    {
                        '$set': {
                            'status': 'completed',
                            'description': f'Credit top-up approved for {credit_amount:.1f} FCs ({naira_amount:.0f} NGN) - {credit_request["paymentMethod"]}',
                            'balanceBefore': current_balance,
                            'balanceAfter': new_balance,
                            'processedAt': datetime.utcnow(),
                            'processedBy': current_user['_id'],
                            'metadata': {
                                'approvedBy': current_user.get('displayName', 'Admin'),
                                'adminNotes': comments,
                                'paymentMethod': credit_request['paymentMethod'],
                                'nairaAmount': naira_amount,
                                'creditAmount': credit_amount
                            }
                        }
                    }
                )

            else:  # Handle denial/rejection
                # Normalize status (both 'denied' and 'rejected' are treated as 'rejected')
                final_status = 'rejected' if status in ['denied', 'rejected'] else status
                
                # Update credit request status
                mongo.db.credit_requests.update_one(
                    {'requestId': request_id},
                    {
                        '$set': {
                            'status': final_status,
                            'processedAt': datetime.utcnow(),
                            'processedBy': current_user['_id'],
                            'rejectionReason': comments,
                            'adminNotes': comments,
                            'updatedAt': datetime.utcnow()
                        }
                    }
                )

                # Update the pending transaction to rejected status
                mongo.db.credit_transactions.update_one(
                    {'requestId': request_id},
                    {
                        '$set': {
                            'status': 'rejected',
                            'processedAt': datetime.utcnow(),
                            'processedBy': current_user['_id'],
                            'metadata': {
                                'rejectedBy': current_user.get('displayName', 'Admin'),
                                'rejectionReason': comments,
                                'adminNotes': comments
                            }
                        }
                    }
                )

            # Get updated credit request
            updated_request = mongo.db.credit_requests.find_one({'requestId': request_id})
            request_data = serialize_doc(updated_request.copy())
            request_data['createdAt'] = updated_request.get('createdAt', datetime.utcnow()).isoformat() + 'Z'
            request_data['updatedAt'] = updated_request.get('updatedAt', datetime.utcnow()).isoformat() + 'Z'
            if updated_request.get('processedAt'):
                request_data['processedAt'] = updated_request['processedAt'].isoformat() + 'Z'

            return jsonify({
                'success': True,
                'data': request_data,
                'message': f'Credit request {status} successfully'
            })

        except Exception as e:
            return jsonify({
                'success': False,
                'message': f'Failed to {status} credit request',
                'errors': {'general': [str(e)]}
            }), 500

    # ===== SYSTEM MONITORING & ANALYTICS ENDPOINTS =====

    @admin_bp.route('/system/health', methods=['GET'])
    @token_required
    @admin_required
    def get_system_health(current_user):
        """Get system health status (admin only)"""
        try:
            # Database health
            try:
                mongo.db.users.find_one()
                db_status = 'healthy'
            except:
                db_status = 'unhealthy'
            
            # System metrics (simplified for basic implementation)
            health_data = {
                'isHealthy': db_status == 'healthy',
                'databaseStatus': db_status,
                'apiStatus': 'healthy',
                'cpuUsage': 45.0,  # Mock data
                'memoryUsage': 62.0,  # Mock data
                'diskUsage': 78.0,  # Mock data
                'errorCount': 0,
                'lastUpdated': datetime.utcnow().isoformat() + 'Z'
            }

            return jsonify({
                'success': True,
                'data': health_data,
                'message': 'System health retrieved successfully'
            })

        except Exception as e:
            return jsonify({
                'success': True,  # Don't fail the request
                'data': {
                    'isHealthy': False,
                    'databaseStatus': 'unknown',
                    'apiStatus': 'unknown',
                    'cpuUsage': 0,
                    'memoryUsage': 0,
                    'diskUsage': 0,
                    'errorCount': 0,
                    'lastUpdated': datetime.utcnow().isoformat() + 'Z',
                    'error': 'Could not retrieve system metrics'
                },
                'message': 'System health retrieved with limited data'
            })

    @admin_bp.route('/analytics/users', methods=['GET'])
    @token_required
    @admin_required
    def get_user_analytics(current_user):
        """Get comprehensive user analytics (admin only)"""
        try:
            # Time-based user registration
            start_date = datetime.utcnow() - timedelta(days=30)
            
            # Daily user registrations (last 30 days)
            daily_registrations = mongo.db.users.aggregate([
                {'$match': {'createdAt': {'$gte': start_date}}},
                {'$group': {
                    '_id': {
                        'year': {'$year': '$createdAt'},
                        'month': {'$month': '$createdAt'},
                        'day': {'$dayOfMonth': '$createdAt'}
                    },
                    'count': {'$sum': 1}
                }},
                {'$sort': {'_id': 1}}
            ])
            
            # User role distribution
            role_distribution = mongo.db.users.aggregate([
                {'$group': {
                    '_id': '$role',
                    'count': {'$sum': 1}
                }}
            ])
            
            # Active vs inactive users
            status_distribution = mongo.db.users.aggregate([
                {'$group': {
                    '_id': '$isActive',
                    'count': {'$sum': 1}
                }}
            ])
            
            # User engagement metrics
            total_users = mongo.db.users.count_documents({})
            active_users = mongo.db.users.count_documents({'isActive': True})
            users_with_expenses = mongo.db.expenses.distinct('userId')
            users_with_income = mongo.db.incomes.distinct('userId')
            users_with_budgets = mongo.db.budgets.distinct('userId')
            
            analytics_data = {
                'totalUsers': total_users,
                'activeUsers': active_users,
                'inactiveUsers': total_users - active_users,
                'dailyRegistrations': list(daily_registrations),
                'roleDistribution': list(role_distribution),
                'statusDistribution': list(status_distribution),
                'engagementMetrics': {
                    'usersWithExpenses': len(users_with_expenses),
                    'usersWithIncome': len(users_with_income),
                    'usersWithBudgets': len(users_with_budgets),
                    'engagementRate': (len(set(users_with_expenses + users_with_income + users_with_budgets)) / total_users * 100) if total_users > 0 else 0
                }
            }

            return jsonify({
                'success': True,
                'data': analytics_data,
                'message': 'User analytics retrieved successfully'
            })

        except Exception as e:
            return jsonify({
                'success': False,
                'message': 'Failed to retrieve user analytics',
                'errors': {'general': [str(e)]}
            }), 500

    @admin_bp.route('/credits/statistics', methods=['GET'])
    @token_required
    @admin_required
    def get_credit_statistics(current_user):
        """Get comprehensive credit statistics (admin only)"""
        try:
            # Date range parameters
            start_date_str = request.args.get('start_date')
            end_date_str = request.args.get('end_date')
            
            # Default to last 30 days if no dates provided
            if not start_date_str:
                start_date = datetime.utcnow() - timedelta(days=30)
            else:
                start_date = datetime.fromisoformat(start_date_str.replace('Z', ''))
                
            if not end_date_str:
                end_date = datetime.utcnow()
            else:
                end_date = datetime.fromisoformat(end_date_str.replace('Z', ''))

            # Credit request statistics
            total_requests = mongo.db.credit_requests.count_documents({})
            pending_requests = mongo.db.credit_requests.count_documents({'status': 'pending'})
            approved_requests = mongo.db.credit_requests.count_documents({'status': 'approved'})
            rejected_requests = mongo.db.credit_requests.count_documents({'status': 'rejected'})
            
            # Credit amounts
            total_credits_requested = mongo.db.credit_requests.aggregate([
                {'$group': {'_id': None, 'total': {'$sum': '$amount'}}}
            ])
            total_credits_requested = list(total_credits_requested)
            total_credits_requested = total_credits_requested[0]['total'] if total_credits_requested else 0
            
            total_credits_issued = mongo.db.credit_requests.aggregate([
                {'$match': {'status': 'approved'}},
                {'$group': {'_id': None, 'total': {'$sum': '$amount'}}}
            ])
            total_credits_issued = list(total_credits_issued)
            total_credits_issued = total_credits_issued[0]['total'] if total_credits_issued else 0
            
            # Approval rate
            approval_rate = (approved_requests / total_requests * 100) if total_requests > 0 else 0
            
            # Credits in date range
            credits_in_range = mongo.db.credit_requests.aggregate([
                {'$match': {
                    'createdAt': {'$gte': start_date, '$lte': end_date}
                }},
                {'$group': {'_id': None, 'total': {'$sum': '$amount'}}}
            ])
            credits_in_range = list(credits_in_range)
            credits_in_range = credits_in_range[0]['total'] if credits_in_range else 0

            statistics = {
                'totalRequests': total_requests,
                'pendingRequests': pending_requests,
                'approvedRequests': approved_requests,
                'rejectedRequests': rejected_requests,
                'totalCreditsRequested': total_credits_requested,
                'totalCreditsIssued': total_credits_issued,
                'creditsInDateRange': credits_in_range,
                'approvalRate': approval_rate,
                'dateRange': {
                    'startDate': start_date.isoformat() + 'Z',
                    'endDate': end_date.isoformat() + 'Z'
                }
            }

            return jsonify({
                'success': True,
                'data': statistics,
                'message': 'Credit statistics retrieved successfully'
            })

        except Exception as e:
            return jsonify({
                'success': False,
                'message': 'Failed to retrieve credit statistics',
                'errors': {'general': [str(e)]}
            }), 500

    return admin_bp