from flask import Blueprint, request, jsonify, send_file
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timedelta
from bson import ObjectId
import sys
import os

# Add parent directory to path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from utils.pdf_generator import PDFGenerator

users_bp = Blueprint('users', __name__, url_prefix='/users')

def init_users_blueprint(mongo, token_required):
    """Initialize the users blueprint with database and auth decorator"""
    users_bp.mongo = mongo
    users_bp.token_required = token_required
    return users_bp

@users_bp.route('/profile', methods=['GET'])
def get_profile():
    @users_bp.token_required
    def _get_profile(current_user):
        try:
            user_data = {
                'id': str(current_user['_id']),
                'email': current_user['email'],
                'firstName': current_user.get('firstName', ''),
                'lastName': current_user.get('lastName', ''),
                'displayName': current_user.get('displayName', ''),
                # Provide `name` for client compatibility (mirrors displayName)
                'name': current_user.get('displayName', ''),
                'phone': current_user.get('phone', ''),
                'address': current_user.get('address', ''),
                'dateOfBirth': current_user.get('dateOfBirth', ''),
                'role': current_user.get('role', 'personal'),
                'ficoreCreditBalance': current_user.get('ficoreCreditBalance', 0.0),
                'setupComplete': current_user.get('setupComplete', False),
                'financialGoals': current_user.get('financialGoals', []),
                'createdAt': current_user.get('createdAt', datetime.utcnow()).isoformat() + 'Z',
                'lastLogin': current_user.get('lastLogin', datetime.utcnow()).isoformat() + 'Z' if current_user.get('lastLogin') else None
            }
            
            return jsonify({
                'success': True,
                'data': user_data,
                'message': 'Profile retrieved successfully'
            })
            
        except Exception as e:
            return jsonify({
                'success': False,
                'message': 'Failed to retrieve profile',
                'errors': {'general': [str(e)]}
            }), 500
    
    return _get_profile()

@users_bp.route('/profile', methods=['PUT'])
def update_profile():
    @users_bp.token_required
    def _update_profile(current_user):
        try:
            data = request.get_json()
            
            # Fields that can be updated
            updatable_fields = ['firstName', 'lastName', 'phone', 'address', 'dateOfBirth', 'displayName']
            update_data = {}
            
            for field in updatable_fields:
                if field in data:
                    update_data[field] = data[field]
            
            # Handle financial goals update with validation
            if 'financialGoals' in data:
                financial_goals = data['financialGoals']
                # Allow expanded list of goals including business-focused keys
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
                
                if isinstance(financial_goals, list):
                    # Allow empty list (user can clear all goals)
                    if len(financial_goals) == 0:
                        update_data['financialGoals'] = financial_goals
                    else:
                        invalid_goals = [goal for goal in financial_goals if goal not in valid_goals]
                        if not invalid_goals:
                            update_data['financialGoals'] = financial_goals
                        else:
                            return jsonify({
                                'success': False,
                                'message': 'Invalid financial goals',
                                'errors': {'financialGoals': [f'Invalid goals: {", ".join(invalid_goals)}']}
                            }), 400
                else:
                    return jsonify({
                        'success': False,
                        'message': 'Financial goals must be an array',
                        'errors': {'financialGoals': ['Financial goals must be an array']}
                    }), 400
            
            # Update display name if first or last name changed
            if 'firstName' in update_data or 'lastName' in update_data:
                first_name = update_data.get('firstName', current_user.get('firstName', ''))
                last_name = update_data.get('lastName', current_user.get('lastName', ''))
                update_data['displayName'] = f"{first_name} {last_name}".strip()
            
            if update_data:
                update_data['updatedAt'] = datetime.utcnow()
                users_bp.mongo.db.users.update_one(
                    {'_id': current_user['_id']},
                    {'$set': update_data}
                )
            
            # Get updated user
            updated_user = users_bp.mongo.db.users.find_one({'_id': current_user['_id']})
            
            user_data = {
                'id': str(updated_user['_id']),
                'email': updated_user['email'],
                'firstName': updated_user.get('firstName', ''),
                'lastName': updated_user.get('lastName', ''),
                'displayName': updated_user.get('displayName', ''),
                # Provide `name` for client compatibility (mirrors displayName)
                'name': updated_user.get('displayName', ''),
                'phone': updated_user.get('phone', ''),
                'address': updated_user.get('address', ''),
                'dateOfBirth': updated_user.get('dateOfBirth', ''),
                'role': updated_user.get('role', 'personal'),
                'ficoreCreditBalance': updated_user.get('ficoreCreditBalance', 0.0),
                'setupComplete': updated_user.get('setupComplete', False),
                'financialGoals': updated_user.get('financialGoals', []),
                'createdAt': updated_user.get('createdAt', datetime.utcnow()).isoformat() + 'Z',
                'lastLogin': updated_user.get('lastLogin', datetime.utcnow()).isoformat() + 'Z' if updated_user.get('lastLogin') else None
            }
            
            return jsonify({
                'success': True,
                'data': user_data,
                'message': 'Profile updated successfully'
            })
            
        except Exception as e:
            return jsonify({
                'success': False,
                'message': 'Failed to update profile',
                'errors': {'general': [str(e)]}
            }), 500
    
    return _update_profile()

@users_bp.route('/setup', methods=['POST'])
def setup_profile():
    @users_bp.token_required
    def _setup_profile(current_user):
        try:
            data = request.get_json()
            
            setup_data = {
                'phone': data.get('phone', ''),
                'address': data.get('address', ''),
                'dateOfBirth': data.get('dateOfBirth', ''),
                'currency': data.get('currency', 'NGN'),
                'language': data.get('language', 'en'),
                'setupComplete': True,
                'setupCompletedAt': datetime.utcnow()
            }
            
            users_bp.mongo.db.users.update_one(
                {'_id': current_user['_id']},
                {'$set': setup_data}
            )
            
            return jsonify({
                'success': True,
                'message': 'Profile setup completed successfully'
            })
            
        except Exception as e:
            return jsonify({
                'success': False,
                'message': 'Profile setup failed',
                'errors': {'general': [str(e)]}
            }), 500
    
    return _setup_profile()

@users_bp.route('/change-password', methods=['POST'])
def change_password():
    @users_bp.token_required
    def _change_password(current_user):
        try:
            data = request.get_json()
            current_password = data.get('currentPassword')
            new_password = data.get('newPassword')
            
            errors = {}
            
            if not current_password:
                errors['currentPassword'] = ['Current password is required']
            elif not check_password_hash(current_user['password'], current_password):
                errors['currentPassword'] = ['Current password is incorrect']
                
            if not new_password:
                errors['newPassword'] = ['New password is required']
            elif len(new_password) < 6:
                errors['newPassword'] = ['Password must be at least 6 characters']
            elif current_password == new_password:
                errors['newPassword'] = ['New password must be different from current password']
            
            if errors:
                return jsonify({
                    'success': False,
                    'message': 'Validation failed',
                    'errors': errors
                }), 400
            
            # Update password
            users_bp.mongo.db.users.update_one(
                {'_id': current_user['_id']},
                {'$set': {
                    'password': generate_password_hash(new_password),
                    'passwordChangedAt': datetime.utcnow()
                }}
            )
            
            return jsonify({
                'success': True,
                'message': 'Password changed successfully'
            })
            
        except Exception as e:
            return jsonify({
                'success': False,
                'message': 'Password change failed',
                'errors': {'general': [str(e)]}
            }), 500
    
    return _change_password()

@users_bp.route('/delete', methods=['DELETE'])
def delete_account():
    @users_bp.token_required
    def _delete_account(current_user):
        try:
            data = request.get_json()
            password = data.get('password')
            
            if not password:
                return jsonify({
                    'success': False,
                    'message': 'Password confirmation required',
                    'errors': {'password': ['Password is required to delete account']}
                }), 400
            
            if not check_password_hash(current_user['password'], password):
                return jsonify({
                    'success': False,
                    'message': 'Invalid password',
                    'errors': {'password': ['Password is incorrect']}
                }), 400
            
            # Soft delete - mark as inactive
            users_bp.mongo.db.users.update_one(
                {'_id': current_user['_id']},
                {'$set': {
                    'isActive': False,
                    'deletedAt': datetime.utcnow()
                }}
            )
            
            return jsonify({
                'success': True,
                'message': 'Account deleted successfully'
            })
            
        except Exception as e:
            return jsonify({
                'success': False,
                'message': 'Account deletion failed',
                'errors': {'general': [str(e)]}
            }), 500
    
    return _delete_account()

@users_bp.route('/settings', methods=['GET'])
def get_settings():
    @users_bp.token_required
    def _get_settings(current_user):
        try:
            settings = {
                'notifications': current_user.get('settings', {}).get('notifications', {
                    'push': True,
                    'email': True,
                    'budgetAlerts': True,
                    'expenseAlerts': True
                }),
                'privacy': current_user.get('settings', {}).get('privacy', {
                    'profileVisibility': 'private',
                    'dataSharing': False
                }),
                'preferences': current_user.get('settings', {}).get('preferences', {
                    'currency': 'NGN',
                    'language': 'en',
                    'theme': 'light',
                    'dateFormat': 'DD/MM/YYYY'
                })
            }
            
            return jsonify({
                'success': True,
                'data': settings,
                'message': 'Settings retrieved successfully'
            })
            
        except Exception as e:
            return jsonify({
                'success': False,
                'message': 'Failed to retrieve settings',
                'errors': {'general': [str(e)]}
            }), 500
    
    return _get_settings()

@users_bp.route('/settings', methods=['PUT'])
def update_settings():
    @users_bp.token_required
    def _update_settings(current_user):
        try:
            data = request.get_json()
            
            # Get current settings or default
            current_settings = current_user.get('settings', {})
            
            # Update settings
            if 'notifications' in data:
                current_settings['notifications'] = {**current_settings.get('notifications', {}), **data['notifications']}
            if 'privacy' in data:
                current_settings['privacy'] = {**current_settings.get('privacy', {}), **data['privacy']}
            if 'preferences' in data:
                current_settings['preferences'] = {**current_settings.get('preferences', {}), **data['preferences']}
            
            users_bp.mongo.db.users.update_one(
                {'_id': current_user['_id']},
                {'$set': {
                    'settings': current_settings,
                    'settingsUpdatedAt': datetime.utcnow()
                }}
            )
            
            return jsonify({
                'success': True,
                'data': current_settings,
                'message': 'Settings updated successfully'
            })
            
        except Exception as e:
            return jsonify({
                'success': False,
                'message': 'Failed to update settings',
                'errors': {'general': [str(e)]}
            }), 500
    
    return _update_settings()

@users_bp.route('/settings/notifications', methods=['GET'])
def get_notification_settings():
    @users_bp.token_required
    def _get_notification_settings(current_user):
        try:
            notifications = current_user.get('settings', {}).get('notifications', {
                'push': True,
                'email': True,
                'budgetAlerts': True,
                'expenseAlerts': True,
                'incomeAlerts': True,
                'creditAlerts': True,
                'weeklyReports': True,
                'monthlyReports': True
            })
            
            return jsonify({
                'success': True,
                'data': {
                    'notifications': notifications
                },
                'message': 'Notification settings retrieved successfully'
            })
            
        except Exception as e:
            return jsonify({
                'success': False,
                'message': 'Failed to retrieve notification settings',
                'errors': {'general': [str(e)]}
            }), 500
    
    return _get_notification_settings()

@users_bp.route('/settings/notifications', methods=['PUT'])
def update_notification_settings():
    @users_bp.token_required
    def _update_notification_settings(current_user):
        try:
            data = request.get_json()
            
            # Get current settings
            current_settings = current_user.get('settings', {})
            current_notifications = current_settings.get('notifications', {})
            
            # Update notification settings
            updated_notifications = {**current_notifications, **data}
            current_settings['notifications'] = updated_notifications
            
            users_bp.mongo.db.users.update_one(
                {'_id': current_user['_id']},
                {'$set': {
                    'settings': current_settings,
                    'settingsUpdatedAt': datetime.utcnow()
                }}
            )
            
            return jsonify({
                'success': True,
                'data': {
                    'notifications': updated_notifications
                },
                'message': 'Notification settings updated successfully'
            })
            
        except Exception as e:
            return jsonify({
                'success': False,
                'message': 'Failed to update notification settings',
                'errors': {'general': [str(e)]}
            }), 500
    
    return _update_notification_settings()

@users_bp.route('/settings/security', methods=['GET'])
def get_security_settings():
    @users_bp.token_required
    def _get_security_settings(current_user):
        try:
            security = current_user.get('settings', {}).get('security', {
                'biometricEnabled': False,
                'twoFactorEnabled': False,
                'sessionTimeout': 30,
                'loginNotifications': True
            })
            
            return jsonify({
                'success': True,
                'data': {
                    'security': security,
                    'lastPasswordChange': current_user.get('passwordChangedAt', current_user.get('createdAt', datetime.utcnow())).isoformat() + 'Z' if current_user.get('passwordChangedAt') else None
                },
                'message': 'Security settings retrieved successfully'
            })
            
        except Exception as e:
            return jsonify({
                'success': False,
                'message': 'Failed to retrieve security settings',
                'errors': {'general': [str(e)]}
            }), 500
    
    return _get_security_settings()

@users_bp.route('/settings/security', methods=['PUT'])
def update_security_settings():
    @users_bp.token_required
    def _update_security_settings(current_user):
        try:
            data = request.get_json()
            
            # Get current settings
            current_settings = current_user.get('settings', {})
            current_security = current_settings.get('security', {})
            
            # Update security settings
            updated_security = {**current_security, **data}
            current_settings['security'] = updated_security
            
            users_bp.mongo.db.users.update_one(
                {'_id': current_user['_id']},
                {'$set': {
                    'settings': current_settings,
                    'settingsUpdatedAt': datetime.utcnow()
                }}
            )
            
            return jsonify({
                'success': True,
                'data': {
                    'security': updated_security
                },
                'message': 'Security settings updated successfully'
            })
            
        except Exception as e:
            return jsonify({
                'success': False,
                'message': 'Failed to update security settings',
                'errors': {'general': [str(e)]}
            }), 500
    
    return _update_security_settings()

@users_bp.route('/export-data', methods=['POST'])
def export_user_data():
    @users_bp.token_required
    def _export_user_data(current_user):
        try:
            data_type = request.get_json().get('type', 'all')  # all, budgets, expenses, incomes, credits
            
            export_data = {
                'user': {
                    'id': str(current_user['_id']),
                    'email': current_user['email'],
                    'firstName': current_user.get('firstName', ''),
                    'lastName': current_user.get('lastName', ''),
                    'exportedAt': datetime.utcnow().isoformat() + 'Z'
                }
            }
            
            if data_type in ['all', 'expenses']:
                expenses = list(users_bp.mongo.db.expenses.find({'userId': current_user['_id']}))
                export_data['expenses'] = []
                for expense in expenses:
                    expense_data = {
                        'id': str(expense['_id']),
                        'title': expense.get('title', ''),
                        'amount': expense.get('amount', 0),
                        'category': expense.get('category', ''),
                        'date': expense.get('date', datetime.utcnow()).isoformat() + 'Z'
                    }
                    export_data['expenses'].append(expense_data)
            
            if data_type in ['all', 'incomes']:
                incomes = list(users_bp.mongo.db.incomes.find({'userId': current_user['_id']}))
                export_data['incomes'] = []
                for income in incomes:
                    income_data = {
                        'id': str(income['_id']),
                        'source': income.get('source', ''),
                        'amount': income.get('amount', 0),
                        'dateReceived': income.get('dateReceived', datetime.utcnow()).isoformat() + 'Z'
                    }
                    export_data['incomes'].append(income_data)
            
            if data_type in ['all', 'credits']:
                credit_transactions = list(users_bp.mongo.db.credit_transactions.find({'userId': current_user['_id']}))
                export_data['creditTransactions'] = []
                for transaction in credit_transactions:
                    transaction_data = {
                        'id': str(transaction['_id']),
                        'type': transaction.get('type', ''),
                        'amount': transaction.get('amount', 0),
                        'description': transaction.get('description', ''),
                        'createdAt': transaction.get('createdAt', datetime.utcnow()).isoformat() + 'Z'
                    }
                    export_data['creditTransactions'].append(transaction_data)
            
            return jsonify({
                'success': True,
                'data': {
                    'exportData': export_data,
                    'downloadUrl': f'/users/download-export/{str(current_user["_id"])}',
                    'expiresAt': (datetime.utcnow() + timedelta(hours=24)).isoformat() + 'Z'
                },
                'message': 'Data export prepared successfully'
            })
            
        except Exception as e:
            return jsonify({
                'success': False,
                'message': 'Failed to export data',
                'errors': {'general': [str(e)]}
            }), 500
    
    return _export_user_data()

@users_bp.route('/export-pdf', methods=['POST'])
def export_pdf():
    """Export user data as PDF with credit deduction"""
    @users_bp.token_required
    def _export_pdf(current_user):
        try:
            request_data = request.get_json()
            data_type = request_data.get('type', 'all')  # all, expenses, incomes, credits
            
            # Define credit costs for different export types
            EXPORT_COSTS = {
                'expenses': 2,
                'incomes': 2,
                'credits': 2,
                'all': 2
            }
            
            credit_cost = EXPORT_COSTS.get(data_type, 2)
            current_balance = current_user.get('ficoreCreditBalance', 0.0)
            
            # Check if user has enough credits
            if current_balance < credit_cost:
                return jsonify({
                    'success': False,
                    'message': 'Insufficient credits',
                    'errors': {
                        'credits': [f'You need {credit_cost} FC to export this report. Current balance: {current_balance} FC']
                    },
                    'data': {
                        'required': credit_cost,
                        'current': current_balance,
                        'shortfall': credit_cost - current_balance
                    }
                }), 402  # Payment Required
            
            # Prepare export data
            export_data = {}
            
            if data_type in ['all', 'expenses']:
                expenses = list(users_bp.mongo.db.expenses.find({'userId': current_user['_id']}))
                export_data['expenses'] = []
                for expense in expenses:
                    expense_data = {
                        'id': str(expense['_id']),
                        'title': expense.get('title', ''),
                        'amount': expense.get('amount', 0),
                        'category': expense.get('category', ''),
                        'date': expense.get('date', datetime.utcnow()).isoformat() + 'Z'
                    }
                    export_data['expenses'].append(expense_data)
            
            if data_type in ['all', 'incomes']:
                incomes = list(users_bp.mongo.db.incomes.find({'userId': current_user['_id']}))
                export_data['incomes'] = []
                for income in incomes:
                    income_data = {
                        'id': str(income['_id']),
                        'source': income.get('source', ''),
                        'amount': income.get('amount', 0),
                        'dateReceived': income.get('dateReceived', datetime.utcnow()).isoformat() + 'Z'
                    }
                    export_data['incomes'].append(income_data)
            
            if data_type in ['all', 'credits']:
                credit_transactions = list(users_bp.mongo.db.credit_transactions.find({'userId': current_user['_id']}))
                export_data['creditTransactions'] = []
                for transaction in credit_transactions:
                    transaction_data = {
                        'id': str(transaction['_id']),
                        'type': transaction.get('type', ''),
                        'amount': transaction.get('amount', 0),
                        'description': transaction.get('description', ''),
                        'createdAt': transaction.get('createdAt', datetime.utcnow()).isoformat() + 'Z'
                    }
                    export_data['creditTransactions'].append(transaction_data)
            
            # Generate PDF
            user_data = {
                'firstName': current_user.get('firstName', ''),
                'lastName': current_user.get('lastName', ''),
                'email': current_user.get('email', '')
            }
            
            pdf_generator = PDFGenerator()
            pdf_buffer = pdf_generator.generate_financial_report(user_data, export_data, data_type)
            
            # Deduct credits from user balance
            new_balance = current_balance - credit_cost
            users_bp.mongo.db.users.update_one(
                {'_id': current_user['_id']},
                {'$set': {'ficoreCreditBalance': new_balance}}
            )
            
            # Record credit transaction
            credit_transaction = {
                'userId': current_user['_id'],
                'type': 'deduction',
                'amount': -credit_cost,
                'description': f'PDF Export - {data_type.upper()}',
                'balanceBefore': current_balance,
                'balanceAfter': new_balance,
                'status': 'completed',
                'createdAt': datetime.utcnow()
            }
            users_bp.mongo.db.credit_transactions.insert_one(credit_transaction)
            
            # Return PDF file
            return send_file(
                pdf_buffer,
                mimetype='application/pdf',
                as_attachment=True,
                download_name=f'ficore_report_{data_type}_{datetime.utcnow().strftime("%Y%m%d_%H%M%S")}.pdf'
            )
            
        except Exception as e:
            return jsonify({
                'success': False,
                'message': 'Failed to generate PDF export',
                'errors': {'general': [str(e)]}
            }), 500
    
    return _export_pdf()

@users_bp.route('/support', methods=['GET'])
def get_support_info():
    @users_bp.token_required
    def _get_support_info(current_user):
        try:
            support_info = {
                'email': 'ficoreafrica@gmail.com',
                'subject': 'Support Request - Ficore Mobile App',
                'message': 'Need support? Reach ficoreafrica@gmail.com for inquiries',
                'faq': [
                    {
                        'question': 'How do I request FiCore Credits?',
                        'answer': 'Go to the Credits section and tap Request to submit a credit top-up request.'
                    },
                    {
                        'question': 'How do I track my expenses?',
                        'answer': 'Use the Expenses section to add and categorize your spending.'
                    },
                    {
                        'question': 'Can I export my financial data?',
                        'answer': 'Yes, go to Settings > Export Data to download your financial reports.'
                    }
                ],
                'appVersion': '1.0.0',
                'lastUpdated': datetime.utcnow().isoformat() + 'Z'
            }
            
            return jsonify({
                'success': True,
                'data': support_info,
                'message': 'Support information retrieved successfully'
            })
            
        except Exception as e:
            return jsonify({
                'success': False,
                'message': 'Failed to retrieve support information',
                'errors': {'general': [str(e)]}
            }), 500
    
    return _get_support_info()

@users_bp.route('/financial-goals', methods=['GET'])
def get_financial_goals():
    @users_bp.token_required
    def _get_financial_goals(current_user):
        try:
            financial_goals = current_user.get('financialGoals', [])
            
            # Available goals with descriptions
            # Updated available goals to avoid investment/savings/budget wording and include business-focused goals
            available_goals = {
                'save_for_emergencies': 'Build a safety fund',
                'pay_off_debt': 'Pay off debt',
                'track_income_expenses': 'Track income & expenses',
                'plan_big_purchases': 'Plan for big purchases',
                'improve_financial_habits': 'Improve financial habits',
                'manage_business_finances': 'Manage Business Finances',
                'know_my_profit': 'Know My Profit'
            }
            
            return jsonify({
                'success': True,
                'data': {
                    'selectedGoals': financial_goals,
                    'availableGoals': available_goals
                },
                'message': 'Financial goals retrieved successfully'
            })
            
        except Exception as e:
            return jsonify({
                'success': False,
                'message': 'Failed to retrieve financial goals',
                'errors': {'general': [str(e)]}
            }), 500
    
    return _get_financial_goals()

@users_bp.route('/financial-goals', methods=['PUT'])
def update_financial_goals():
    @users_bp.token_required
    def _update_financial_goals(current_user):
        try:
            data = request.get_json()
            financial_goals = data.get('financialGoals', [])
            
            # Validate financial goals
            # Validation list updated to reflect frontend changes (no budget/investment wording)
            valid_goals = [
                'save_for_emergencies',
                'pay_off_debt',
                'track_income_expenses',
                'plan_big_purchases',
                'improve_financial_habits',
                'manage_business_finances',
                'know_my_profit'
            ]
            
            if not isinstance(financial_goals, list):
                return jsonify({
                    'success': False,
                    'message': 'Financial goals must be an array',
                    'errors': {'financialGoals': ['Financial goals must be an array']}
                }), 400
            
            invalid_goals = [goal for goal in financial_goals if goal not in valid_goals]
            if invalid_goals:
                return jsonify({
                    'success': False,
                    'message': 'Invalid financial goals',
                    'errors': {'financialGoals': [f'Invalid goals: {", ".join(invalid_goals)}']}
                }), 400
            
            # Update user's financial goals
            users_bp.mongo.db.users.update_one(
                {'_id': current_user['_id']},
                {'$set': {
                    'financialGoals': financial_goals,
                    'goalsUpdatedAt': datetime.utcnow()
                }}
            )
            
            return jsonify({
                'success': True,
                'data': {
                    'financialGoals': financial_goals
                },
                'message': 'Financial goals updated successfully'
            })
            
        except Exception as e:
            return jsonify({
                'success': False,
                'message': 'Failed to update financial goals',
                'errors': {'general': [str(e)]}
            }), 500
    
    return _update_financial_goals()