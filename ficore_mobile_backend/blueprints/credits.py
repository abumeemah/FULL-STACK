from flask import Blueprint, request, jsonify
from datetime import datetime, timedelta
from bson import ObjectId
from werkzeug.utils import secure_filename
import uuid
import os
import base64
import traceback

def init_credits_blueprint(mongo, token_required, serialize_doc):
    credits_bp = Blueprint('credits', __name__, url_prefix='/credits')
    
    # Credit top-up configuration - Users buy FiCore Credits at ₦50 per credit
    CREDIT_PACKAGES = [
        {'credits': 10, 'naira': 500},    # 10 FCs for ₦500
        {'credits': 50, 'naira': 2500},   # 50 FCs for ₦2,500  
        {'credits': 100, 'naira': 5000},  # 100 FCs for ₦5,000
        {'credits': 200, 'naira': 10000}, # 200 FCs for ₦10,000
    ]
    NAIRA_PER_CREDIT = 50  # Price: ₦50 per 1 FiCore Credit
    
    # Configure upload settings
    UPLOAD_FOLDER = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'uploads', 'receipts')
    ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'pdf', 'gif'}
    MAX_FILE_SIZE = 5 * 1024 * 1024  # 5MB
    
    # Ensure upload directory exists
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)
    
    def allowed_file(filename):
        """Check if file extension is allowed"""
        return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

    @credits_bp.route('/topup-options', methods=['GET'])
    @token_required
    def get_topup_options(current_user):
        """Get available credit packages for purchase"""
        try:
            options = []
            for package in CREDIT_PACKAGES:
                options.append({
                    'creditAmount': package['credits'],
                    'nairaAmount': package['naira'],
                    'displayText': f'{package["credits"]} FCs - ₦{package["naira"]:,}'
                })
            
            # Extract allowed Naira amounts for frontend compatibility
            allowed_naira_amounts = [package['naira'] for package in CREDIT_PACKAGES]
            
            return jsonify({
                'success': True,
                'data': {
                    'options': options,
                    'conversionRate': float(NAIRA_PER_CREDIT),
                    'allowedNairaAmounts': allowed_naira_amounts,
                    'pricePerCredit': NAIRA_PER_CREDIT,
                    'packages': CREDIT_PACKAGES
                },
                'message': 'Credit packages retrieved successfully'
            })

        except Exception as e:
            return jsonify({
                'success': False,
                'message': 'Failed to retrieve credit packages',
                'errors': {'general': [str(e)]}
            }), 500

    @credits_bp.route('/balance', methods=['GET'])
    @token_required
    def get_credit_balance(current_user):
        """Get user's current FiCore Credits balance"""
        try:
            # Validate user exists and has required fields
            if not current_user or '_id' not in current_user:
                return jsonify({
                    'success': False,
                    'message': 'Invalid user session'
                }), 401

            # Get user's current credit balance with error handling
            user = mongo.db.users.find_one({'_id': current_user['_id']})
            if not user:
                return jsonify({
                    'success': False,
                    'message': 'User not found'
                }), 404

            # Ensure balance is a valid number
            balance = user.get('ficoreCreditBalance', 0.0)
            if not isinstance(balance, (int, float)):
                balance = 0.0
            
            # Get recent credit transactions for context with error handling
            try:
                recent_transactions = list(mongo.db.credit_transactions.find({
                    'userId': current_user['_id']
                }).sort('createdAt', -1).limit(5))
            except Exception as db_error:
                # If transaction query fails, continue with empty list
                recent_transactions = []
                print(f"Warning: Failed to fetch recent transactions: {str(db_error)}")
            
            # Serialize transactions with error handling
            transactions = []
            for transaction in recent_transactions:
                try:
                    trans_data = serialize_doc(transaction.copy())
                    # Ensure createdAt is properly formatted
                    created_at = trans_data.get('createdAt')
                    if isinstance(created_at, datetime):
                        trans_data['createdAt'] = created_at.isoformat() + 'Z'
                    elif created_at is None:
                        trans_data['createdAt'] = datetime.utcnow().isoformat() + 'Z'
                    transactions.append(trans_data)
                except Exception as serialize_error:
                    # Skip problematic transactions
                    print(f"Warning: Failed to serialize transaction: {str(serialize_error)}")
                    continue

            return jsonify({
                'success': True,
                'data': {
                    'balance': float(balance),
                    'formattedBalance': f"{balance:,.0f}",
                    'recentTransactions': transactions,
                    'lastUpdated': datetime.utcnow().isoformat() + 'Z'
                },
                'message': 'Credit balance retrieved successfully'
            })

        except Exception as e:
            # Log the error for debugging
            print(f"Error in get_credit_balance: {str(e)}")
            return jsonify({
                'success': False,
                'message': 'Failed to retrieve credit balance',
                'errors': {'general': [str(e)]}
            }), 500

    @credits_bp.route('/history', methods=['GET'])
    @token_required
    def get_credit_history(current_user):
        """Get user's credit transaction history"""
        try:
            # Get pagination parameters
            page = int(request.args.get('page', 1))
            limit = int(request.args.get('limit', 20))
            transaction_type = request.args.get('type', 'all')  # all, credit, debit, request
            
            # Build query
            query = {'userId': current_user['_id']}
            if transaction_type != 'all':
                query['type'] = transaction_type

            # Get total count
            total = mongo.db.credit_transactions.count_documents(query)
            
            # Get transactions with pagination
            skip = (page - 1) * limit
            transactions = list(mongo.db.credit_transactions.find(query)
                              .sort('createdAt', -1)
                              .skip(skip)
                              .limit(limit))
            
            # Serialize transactions
            transaction_data = []
            for transaction in transactions:
                trans_data = serialize_doc(transaction.copy())
                trans_data['createdAt'] = trans_data.get('createdAt', datetime.utcnow()).isoformat() + 'Z'
                if 'updatedAt' in trans_data:
                    trans_data['updatedAt'] = trans_data.get('updatedAt', datetime.utcnow()).isoformat() + 'Z'
                transaction_data.append(trans_data)

            # Calculate summary statistics
            total_credits = mongo.db.credit_transactions.aggregate([
                {'$match': {'userId': current_user['_id'], 'type': 'credit'}},
                {'$group': {'_id': None, 'total': {'$sum': '$amount'}}}
            ])
            total_credits = list(total_credits)
            total_credits_amount = total_credits[0]['total'] if total_credits else 0

            total_debits = mongo.db.credit_transactions.aggregate([
                {'$match': {'userId': current_user['_id'], 'type': 'debit'}},
                {'$group': {'_id': None, 'total': {'$sum': '$amount'}}}
            ])
            total_debits = list(total_debits)
            total_debits_amount = total_debits[0]['total'] if total_debits else 0

            return jsonify({
                'success': True,
                'data': {
                    'transactions': transaction_data,
                    'pagination': {
                        'page': page,
                        'limit': limit,
                        'total': total,
                        'pages': (total + limit - 1) // limit,
                        'hasNext': page * limit < total,
                        'hasPrev': page > 1
                    },
                    'summary': {
                        'totalCredits': total_credits_amount,
                        'totalDebits': total_debits_amount,
                        'netBalance': total_credits_amount - total_debits_amount
                    }
                },
                'message': 'Credit history retrieved successfully'
            })

        except Exception as e:
            return jsonify({
                'success': False,
                'message': 'Failed to retrieve credit history',
                'errors': {'general': [str(e)]}
            }), 500

    @credits_bp.route('/request', methods=['POST'])
    @token_required
    def create_credit_request(current_user):
        """Submit a new credit top-up request"""
        try:
            data = request.get_json()
            
            # Validate required fields
            required_fields = ['amount', 'paymentMethod']
            for field in required_fields:
                if field not in data or not data[field]:
                    return jsonify({
                        'success': False,
                        'message': f'Missing required field: {field}',
                        'errors': {field: ['This field is required']}
                    }), 400

            # The 'amount' field now represents the FiCore Credits selected by the user
            credit_amount = float(data['amount'])
            
            # Find the matching package
            selected_package = None
            for package in CREDIT_PACKAGES:
                if package['credits'] == credit_amount:
                    selected_package = package
                    break
            
            if selected_package is None:
                valid_credits = [str(pkg['credits']) for pkg in CREDIT_PACKAGES]
                return jsonify({
                    'success': False,
                    'message': f'Invalid credit amount. Available packages: {", ".join(valid_credits)} FCs',
                    'errors': {'amount': [f'Credit amount must be one of: {", ".join(valid_credits)} FCs']}
                }), 400

            naira_amount = selected_package['naira']

            # Create credit request
            credit_request = {
                '_id': ObjectId(),
                'userId': current_user['_id'],
                'requestId': str(uuid.uuid4()),
                'amount': credit_amount,  # Store FiCore Credit amount
                'nairaAmount': naira_amount,  # Store original Naira amount
                'paymentMethod': data['paymentMethod'],
                'paymentReference': data.get('paymentReference', ''),
                'receiptUrl': data.get('receiptUrl', ''),
                'notes': data.get('notes', ''),
                'status': 'pending',  # pending, approved, rejected, processing
                'createdAt': datetime.utcnow(),
                'updatedAt': datetime.utcnow(),
                'processedBy': None,
                'processedAt': None,
                'rejectionReason': None
            }

            # Insert credit request
            result = mongo.db.credit_requests.insert_one(credit_request)
            
            # Create transaction record
            transaction = {
                '_id': ObjectId(),
                'userId': current_user['_id'],
                'requestId': credit_request['requestId'],
                'type': 'credit',
                'amount': credit_amount,  # Store FiCore Credit amount
                'nairaAmount': naira_amount,  # Store original Naira amount
                'description': f'Credit top-up request for {credit_amount:.1f} FCs ({naira_amount:.0f} NGN) - {data["paymentMethod"]}',
                'status': 'pending',
                'paymentMethod': data['paymentMethod'],
                'paymentReference': data.get('paymentReference', ''),
                'createdAt': datetime.utcnow(),
                'metadata': {
                    'requestType': 'topup',
                    'paymentMethod': data['paymentMethod'],
                    'nairaAmount': naira_amount,
                    'creditAmount': credit_amount
                }
            }
            
            mongo.db.credit_transactions.insert_one(transaction)

            # Return created request
            credit_request = serialize_doc(credit_request)
            credit_request['createdAt'] = credit_request.get('createdAt', datetime.utcnow()).isoformat() + 'Z'
            credit_request['updatedAt'] = credit_request.get('updatedAt', datetime.utcnow()).isoformat() + 'Z'

            return jsonify({
                'success': True,
                'data': credit_request,
                'message': f'Credit request submitted successfully for {credit_amount:.1f} FCs ({naira_amount:.0f} NGN)'
            }), 201

        except ValueError as e:
            return jsonify({
                'success': False,
                'message': 'Invalid amount format',
                'errors': {'amount': ['Please enter a valid number']}
            }), 400
        except Exception as e:
            return jsonify({
                'success': False,
                'message': 'Failed to create credit request',
                'errors': {'general': [str(e)]}
            }), 500

    @credits_bp.route('/request/<request_id>', methods=['PUT'])
    @token_required
    def update_credit_request(current_user, request_id):
        """Update a credit request (user can only update their own pending requests)"""
        try:
            data = request.get_json()
            
            # Find the credit request
            credit_request = mongo.db.credit_requests.find_one({
                'requestId': request_id,
                'userId': current_user['_id']
            })
            
            if not credit_request:
                return jsonify({
                    'success': False,
                    'message': 'Credit request not found'
                }), 404

            # Only allow updates to pending requests
            if credit_request['status'] != 'pending':
                return jsonify({
                    'success': False,
                    'message': 'Cannot update processed credit request'
                }), 400

            # Update allowed fields
            update_data = {
                'updatedAt': datetime.utcnow()
            }
            
            if 'paymentReference' in data:
                update_data['paymentReference'] = data['paymentReference']
            if 'receiptUrl' in data:
                update_data['receiptUrl'] = data['receiptUrl']
            if 'notes' in data:
                update_data['notes'] = data['notes']

            # Update the request
            mongo.db.credit_requests.update_one(
                {'requestId': request_id, 'userId': current_user['_id']},
                {'$set': update_data}
            )

            # Get updated request
            updated_request = mongo.db.credit_requests.find_one({
                'requestId': request_id,
                'userId': current_user['_id']
            })

            # Serialize and return
            request_data = serialize_doc(updated_request)
            request_data['createdAt'] = request_data.get('createdAt', datetime.utcnow()).isoformat() + 'Z'
            request_data['updatedAt'] = request_data.get('updatedAt', datetime.utcnow()).isoformat() + 'Z'

            return jsonify({
                'success': True,
                'data': request_data,
                'message': 'Credit request updated successfully'
            })

        except Exception as e:
            return jsonify({
                'success': False,
                'message': 'Failed to update credit request',
                'errors': {'general': [str(e)]}
            }), 500

    @credits_bp.route('/requests', methods=['GET'])
    @token_required
    def get_user_credit_requests(current_user):
        """Get user's credit requests"""
        try:
            # Get pagination parameters
            page = int(request.args.get('page', 1))
            limit = int(request.args.get('limit', 20))
            status = request.args.get('status', 'all')  # all, pending, approved, rejected
            
            # Build query
            query = {'userId': current_user['_id']}
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
            
            # Serialize requests
            request_data = []
            for req in requests:
                req_data = serialize_doc(req.copy())
                req_data['createdAt'] = req_data.get('createdAt', datetime.utcnow()).isoformat() + 'Z'
                req_data['updatedAt'] = req_data.get('updatedAt', datetime.utcnow()).isoformat() + 'Z'
                if req_data.get('processedAt'):
                    req_data['processedAt'] = req_data.get('processedAt', datetime.utcnow()).isoformat() + 'Z'
                request_data.append(req_data)

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
                    }
                },
                'message': 'Credit requests retrieved successfully'
            })

        except Exception as e:
            return jsonify({
                'success': False,
                'message': 'Failed to retrieve credit requests',
                'errors': {'general': [str(e)]}
            }), 500

    @credits_bp.route('/deduct', methods=['POST'])
    @token_required
    def deduct_credits(current_user):
        """Deduct credits from user account (for app operations)"""
        try:
            data = request.get_json()
            
            # Validate required fields
            if 'amount' not in data or 'operation' not in data:
                return jsonify({
                    'success': False,
                    'message': 'Missing required fields: amount, operation'
                }), 400

            amount = float(data['amount'])
            operation = data['operation']
            description = data.get('description', f'Credits used for {operation}')

            if amount <= 0:
                return jsonify({
                    'success': False,
                    'message': 'Amount must be greater than zero'
                }), 400

            # Validate operation is a known FC cost operation
            valid_operations = [
                # Income & Expense operations
                'create_income', 'delete_income', 'create_expense', 'delete_expense',
                # Inventory operations
                'create_item', 'delete_item', 'create_movement', 'stock_in', 'stock_out', 'adjust_stock',
                # Creditors operations
                'create_vendor', 'delete_vendor', 'create_creditor_transaction', 'delete_creditor_transaction',
                # Debtors operations
                'create_customer', 'delete_customer', 'create_debtor_transaction', 'delete_debtor_transaction',
                # Export operations
                'export_inventory_csv', 'export_inventory_pdf', 'export_creditors_csv', 'export_creditors_pdf',
                'export_debtors_csv', 'export_debtors_pdf', 'export_net_income_report', 'export_financial_report',
                'export_dashboard_summary', 'export_enhanced_profit_report', 'export_complete_data_export',
                'export_movements_csv', 'export_valuation_pdf', 'export_aging_report_pdf', 'export_payments_due_csv',
                'export_debtors_aging_report_pdf', 'export_debtors_payments_due_csv'
            ]
            
            if operation not in valid_operations:
                print(f"Warning: Unknown operation '{operation}' for credit deduction")
                # Don't fail, just log for monitoring

            # Get current user balance
            user = mongo.db.users.find_one({'_id': current_user['_id']})
            current_balance = user.get('ficoreCreditBalance', 0.0)

            if current_balance < amount:
                return jsonify({
                    'success': False,
                    'message': 'Insufficient credits',
                    'data': {
                        'currentBalance': current_balance,
                        'requiredAmount': amount,
                        'shortfall': amount - current_balance
                    }
                }), 402  # Payment Required

            # Deduct credits from user account
            new_balance = current_balance - amount
            mongo.db.users.update_one(
                {'_id': current_user['_id']},
                {'$set': {'ficoreCreditBalance': new_balance}}
            )

            # Create transaction record
            transaction = {
                '_id': ObjectId(),
                'userId': current_user['_id'],
                'type': 'debit',
                'amount': amount,
                'description': description,
                'operation': operation,
                'balanceBefore': current_balance,
                'balanceAfter': new_balance,
                'status': 'completed',
                'createdAt': datetime.utcnow(),
                'metadata': {
                    'operation': operation,
                    'deductionType': 'app_usage'
                }
            }
            
            mongo.db.credit_transactions.insert_one(transaction)

            return jsonify({
                'success': True,
                'data': {
                    'transactionId': str(transaction['_id']),
                    'amountDeducted': amount,
                    'previousBalance': current_balance,
                    'newBalance': new_balance,
                    'operation': operation
                },
                'message': f'Credits deducted successfully for {operation}'
            })

        except ValueError as e:
            return jsonify({
                'success': False,
                'message': 'Invalid amount format'
            }), 400
        except Exception as e:
            return jsonify({
                'success': False,
                'message': 'Failed to deduct credits',
                'errors': {'general': [str(e)]}
            }), 500

    @credits_bp.route('/award', methods=['POST'])
    @token_required
    def award_credits(current_user):
        """Award credits to user account (for completing tasks like tax education)"""
        try:
            data = request.get_json()
            
            # Validate required fields
            if 'amount' not in data or 'operation' not in data:
                return jsonify({
                    'success': False,
                    'message': 'Missing required fields: amount, operation'
                }), 400

            amount = float(data['amount'])
            operation = data['operation']
            description = data.get('description', f'Credits earned from {operation}')

            if amount <= 0:
                return jsonify({
                    'success': False,
                    'message': 'Amount must be greater than zero'
                }), 400

            # Validate operation is a known credit-earning operation
            valid_award_operations = [
                'tax_education_progress',  # Users earn 1 FC per tax education module
                'signup_bonus',           # Initial signup bonus
                'referral_bonus',         # Future referral system
                'admin_award'             # Manual admin awards
            ]
            
            if operation not in valid_award_operations:
                print(f"Warning: Unknown operation '{operation}' for credit award")
                # Don't fail, just log for monitoring

            # Get current user balance
            user = mongo.db.users.find_one({'_id': current_user['_id']})
            current_balance = user.get('ficoreCreditBalance', 0.0)

            # Award credits to user account
            new_balance = current_balance + amount
            mongo.db.users.update_one(
                {'_id': current_user['_id']},
                {'$set': {'ficoreCreditBalance': new_balance}}
            )

            # Create transaction record
            transaction = {
                '_id': ObjectId(),
                'userId': current_user['_id'],
                'type': 'credit',
                'amount': amount,
                'description': description,
                'operation': operation,
                'balanceBefore': current_balance,
                'balanceAfter': new_balance,
                'status': 'completed',
                'createdAt': datetime.utcnow(),
                'metadata': {
                    'operation': operation,
                    'awardType': 'task_completion'
                }
            }
            
            mongo.db.credit_transactions.insert_one(transaction)

            return jsonify({
                'success': True,
                'data': {
                    'transactionId': str(transaction['_id']),
                    'amountAwarded': amount,
                    'previousBalance': current_balance,
                    'newBalance': new_balance,
                    'operation': operation
                },
                'message': f'Credits awarded successfully for {operation}'
            })

        except ValueError as e:
            return jsonify({
                'success': False,
                'message': 'Invalid amount format'
            }), 400
        except Exception as e:
            return jsonify({
                'success': False,
                'message': 'Failed to award credits',
                'errors': {'general': [str(e)]}
            }), 500

    @credits_bp.route('/transactions/recent', methods=['GET'])
    @token_required
    def get_recent_credit_transactions(current_user):
        """Get recent credit transactions"""
        try:
            # Validate user exists and has required fields
            if not current_user or '_id' not in current_user:
                return jsonify({
                    'success': False,
                    'message': 'Invalid user session'
                }), 401

            # Validate and sanitize limit parameter
            try:
                limit = int(request.args.get('limit', 5))
                # Ensure reasonable limits
                if limit < 1:
                    limit = 5
                elif limit > 100:
                    limit = 100
            except (ValueError, TypeError):
                limit = 5
            
            # Get recent transactions with error handling
            try:
                transactions = list(mongo.db.credit_transactions.find({
                    'userId': current_user['_id']
                }).sort('createdAt', -1).limit(limit))
            except Exception as db_error:
                print(f"Database error in get_recent_credit_transactions: {str(db_error)}")
                return jsonify({
                    'success': False,
                    'message': 'Database connection error',
                    'errors': {'database': [str(db_error)]}
                }), 500
            
            # Serialize transactions with error handling
            transaction_data = []
            for transaction in transactions:
                try:
                    trans_data = serialize_doc(transaction.copy())
                    # Ensure createdAt is properly formatted
                    created_at = trans_data.get('createdAt')
                    if isinstance(created_at, datetime):
                        trans_data['createdAt'] = created_at.isoformat() + 'Z'
                    elif created_at is None:
                        trans_data['createdAt'] = datetime.utcnow().isoformat() + 'Z'
                    transaction_data.append(trans_data)
                except Exception as serialize_error:
                    # Skip problematic transactions
                    print(f"Warning: Failed to serialize transaction: {str(serialize_error)}")
                    continue

            return jsonify({
                'success': True,
                'data': {
                    'transactions': transaction_data
                },
                'message': 'Recent credit transactions retrieved successfully'
            })

        except Exception as e:
            # Log the error for debugging
            print(f"Error in get_recent_credit_transactions: {str(e)}")
            return jsonify({
                'success': False,
                'message': 'Failed to retrieve recent credit transactions',
                'errors': {'general': [str(e)]}
            }), 500

    @credits_bp.route('/transactions', methods=['GET'])
    @token_required
    def get_credit_transactions(current_user):
        """Get credit transactions with pagination"""
        try:
            limit = int(request.args.get('limit', 20))
            offset = int(request.args.get('offset', 0))
            
            # Get transactions with pagination
            transactions = list(mongo.db.credit_transactions.find({
                'userId': current_user['_id']
            }).sort('createdAt', -1).skip(offset).limit(limit))
            
            total = mongo.db.credit_transactions.count_documents({
                'userId': current_user['_id']
            })
            
            # Serialize transactions
            transaction_data = []
            for transaction in transactions:
                trans_data = serialize_doc(transaction.copy())
                trans_data['createdAt'] = trans_data.get('createdAt', datetime.utcnow()).isoformat() + 'Z'
                transaction_data.append(trans_data)

            return jsonify({
                'success': True,
                'data': {
                    'transactions': transaction_data,
                    'pagination': {
                        'limit': limit,
                        'offset': offset,
                        'total': total,
                        'hasMore': offset + limit < total
                    }
                },
                'message': 'Credit transactions retrieved successfully'
            })

        except Exception as e:
            return jsonify({
                'success': False,
                'message': 'Failed to retrieve credit transactions',
                'errors': {'general': [str(e)]}
            }), 500

    @credits_bp.route('/upload-receipt', methods=['POST'])
    @token_required
    def upload_receipt(current_user):
        """Upload payment receipt for credit request"""
        try:
            # Debug logging for request details
            print(f"Upload receipt request from user: {current_user.get('_id', 'Unknown')}")
            print(f"Request method: {request.method}")
            print(f"Request content type: {request.content_type}")
            print(f"Request files keys: {list(request.files.keys())}")
            print(f"Request is_json: {request.is_json}")
            print(f"Upload folder: {UPLOAD_FOLDER}")
            print(f"Upload folder exists: {os.path.exists(UPLOAD_FOLDER)}")
            print(f"Upload folder permissions: {oct(os.stat(UPLOAD_FOLDER).st_mode)[-3:] if os.path.exists(UPLOAD_FOLDER) else 'N/A'}")
            # Check if file is in request
            if 'receipt' not in request.files:
                # Check if base64 data is provided instead
                data = request.get_json() if request.is_json else {}
                if 'receiptData' in data and 'fileName' in data:
                    # Handle base64 upload
                    try:
                        receipt_data = data['receiptData']
                        file_name = secure_filename(data['fileName'])
                        
                        # Remove data URL prefix if present
                        if ',' in receipt_data:
                            receipt_data = receipt_data.split(',')[1]
                        
                        # Decode base64
                        file_bytes = base64.b64decode(receipt_data)
                        
                        # Check file size
                        if len(file_bytes) > MAX_FILE_SIZE:
                            return jsonify({
                                'success': False,
                                'message': f'File size exceeds maximum allowed size of {MAX_FILE_SIZE / (1024*1024)}MB'
                            }), 400
                        
                        # Generate unique filename
                        file_ext = file_name.rsplit('.', 1)[1].lower() if '.' in file_name else 'jpg'
                        if file_ext not in ALLOWED_EXTENSIONS:
                            return jsonify({
                                'success': False,
                                'message': f'File type not allowed. Allowed types: {", ".join(ALLOWED_EXTENSIONS)}'
                            }), 400
                        
                        unique_filename = f"{current_user['_id']}_{uuid.uuid4().hex[:8]}.{file_ext}"
                        file_path = os.path.join(UPLOAD_FOLDER, unique_filename)
                        
                        # Save file
                        with open(file_path, 'wb') as f:
                            f.write(file_bytes)
                        
                        # Generate URL (relative path)
                        receipt_url = f"/uploads/receipts/{unique_filename}"
                        
                        return jsonify({
                            'success': True,
                            'data': {
                                'receiptUrl': receipt_url,
                                'fileName': unique_filename,
                                'fileSize': len(file_bytes),
                                'uploadedAt': datetime.utcnow().isoformat() + 'Z'
                            },
                            'message': 'Receipt uploaded successfully'
                        }), 201
                        
                    except Exception as e:
                        # Enhanced error logging for base64 processing
                        error_traceback = traceback.format_exc()
                        print(f"Error in base64 upload processing: {error_traceback}")
                        print(f"Exception type: {type(e).__name__}")
                        print(f"Exception message: {str(e)}")
                        
                        return jsonify({
                            'success': False,
                            'message': f'Failed to process base64 file: {str(e)}'
                        }), 400
                else:
                    return jsonify({
                        'success': False,
                        'message': 'No receipt file provided'
                    }), 400
            
            file = request.files['receipt']
            
            # Check if file is selected
            if file.filename == '':
                return jsonify({
                    'success': False,
                    'message': 'No file selected'
                }), 400
            
            # Check file extension
            if not allowed_file(file.filename):
                return jsonify({
                    'success': False,
                    'message': f'File type not allowed. Allowed types: {", ".join(ALLOWED_EXTENSIONS)}'
                }), 400
            
            # Check file size
            file.seek(0, os.SEEK_END)
            file_size = file.tell()
            file.seek(0)
            
            if file_size > MAX_FILE_SIZE:
                return jsonify({
                    'success': False,
                    'message': f'File size exceeds maximum allowed size of {MAX_FILE_SIZE / (1024*1024)}MB'
                }), 400
            
            # Generate unique filename
            file_ext = file.filename.rsplit('.', 1)[1].lower()
            unique_filename = f"{current_user['_id']}_{uuid.uuid4().hex[:8]}.{file_ext}"
            file_path = os.path.join(UPLOAD_FOLDER, unique_filename)
            
            # Save file
            file.save(file_path)
            
            # Generate URL (relative path)
            receipt_url = f"/uploads/receipts/{unique_filename}"
            
            return jsonify({
                'success': True,
                'data': {
                    'receiptUrl': receipt_url,
                    'fileName': unique_filename,
                    'fileSize': file_size,
                    'uploadedAt': datetime.utcnow().isoformat() + 'Z'
                },
                'message': 'Receipt uploaded successfully'
            }), 201
            
        except Exception as e:
            # Enhanced error logging with full traceback
            error_traceback = traceback.format_exc()
            print(f"Error in upload_receipt: {error_traceback}")
            print(f"Exception type: {type(e).__name__}")
            print(f"Exception message: {str(e)}")
            
            # Log additional context for debugging
            print(f"Upload folder path: {UPLOAD_FOLDER}")
            print(f"Upload folder exists: {os.path.exists(UPLOAD_FOLDER)}")
            print(f"Upload folder writable: {os.access(UPLOAD_FOLDER, os.W_OK) if os.path.exists(UPLOAD_FOLDER) else 'N/A'}")
            
            return jsonify({
                'success': False,
                'message': 'Failed to upload receipt',
                'errors': {'general': [str(e)]}
            }), 500

    @credits_bp.route('/summary', methods=['GET'])
    @token_required
    def get_credit_summary(current_user):
        """Get credit summary statistics"""
        try:
            # Validate user exists and has required fields
            if not current_user or '_id' not in current_user:
                return jsonify({
                    'success': False,
                    'message': 'Invalid user session'
                }), 401

            # Get user's current balance with error handling
            try:
                user = mongo.db.users.find_one({'_id': current_user['_id']})
                if not user:
                    return jsonify({
                        'success': False,
                        'message': 'User not found'
                    }), 404
                
                current_balance = user.get('ficoreCreditBalance', 0.0)
                if not isinstance(current_balance, (int, float)):
                    current_balance = 0.0
            except Exception as user_error:
                print(f"Error fetching user balance: {str(user_error)}")
                current_balance = 0.0
            
            # Get transaction statistics with error handling
            try:
                total_credits = list(mongo.db.credit_transactions.aggregate([
                    {'$match': {'userId': current_user['_id'], 'type': 'credit'}},
                    {'$group': {'_id': None, 'total': {'$sum': '$amount'}, 'count': {'$sum': 1}}}
                ]))
                credits_amount = total_credits[0]['total'] if total_credits else 0
                credits_count = total_credits[0]['count'] if total_credits else 0
            except Exception as credits_error:
                print(f"Error fetching credits statistics: {str(credits_error)}")
                credits_amount = 0
                credits_count = 0

            try:
                total_debits = list(mongo.db.credit_transactions.aggregate([
                    {'$match': {'userId': current_user['_id'], 'type': 'debit'}},
                    {'$group': {'_id': None, 'total': {'$sum': '$amount'}, 'count': {'$sum': 1}}}
                ]))
                debits_amount = total_debits[0]['total'] if total_debits else 0
                debits_count = total_debits[0]['count'] if total_debits else 0
            except Exception as debits_error:
                print(f"Error fetching debits statistics: {str(debits_error)}")
                debits_amount = 0
                debits_count = 0

            # Get pending requests with error handling
            try:
                pending_requests = mongo.db.credit_requests.count_documents({
                    'userId': current_user['_id'],
                    'status': 'pending'
                })
            except Exception as requests_error:
                print(f"Error fetching pending requests: {str(requests_error)}")
                pending_requests = 0

            # Ensure all values are proper numbers
            credits_amount = float(credits_amount) if credits_amount else 0.0
            debits_amount = float(debits_amount) if debits_amount else 0.0
            current_balance = float(current_balance)

            summary_data = {
                'currentBalance': current_balance,
                'totalCredits': credits_amount,
                'totalDebits': debits_amount,
                'netCredits': credits_amount - debits_amount,
                'transactionCounts': {
                    'credits': int(credits_count),
                    'debits': int(debits_count),
                    'total': int(credits_count + debits_count)
                },
                'pendingRequests': int(pending_requests),
                'lastUpdated': datetime.utcnow().isoformat() + 'Z'
            }

            return jsonify({
                'success': True,
                'data': summary_data,
                'message': 'Credit summary retrieved successfully'
            })

        except Exception as e:
            # Log the error for debugging
            print(f"Error in get_credit_summary: {str(e)}")
            return jsonify({
                'success': False,
                'message': 'Failed to retrieve credit summary',
                'errors': {'general': [str(e)]}
            }), 500

    return credits_bp