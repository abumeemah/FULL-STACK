from flask import Blueprint, request, jsonify
from datetime import datetime, timedelta
from bson import ObjectId
import uuid

def init_debtors_blueprint(mongo, token_required, serialize_doc):
    """Initialize the debtors blueprint with database and auth decorator"""
    debtors_bp = Blueprint('debtors', __name__, url_prefix='/debtors')

    def calculate_overdue_days(next_payment_due):
        """Calculate overdue days from next payment due date"""
        if not next_payment_due:
            return 0
        
        now = datetime.utcnow()
        if next_payment_due < now:
            return (now - next_payment_due).days
        return 0

    def calculate_next_payment_due(payment_terms, custom_days, last_transaction_date):
        """Calculate next payment due date based on payment terms"""
        if not last_transaction_date:
            return None
            
        if payment_terms == '30_days':
            return last_transaction_date + timedelta(days=30)
        elif payment_terms == '60_days':
            return last_transaction_date + timedelta(days=60)
        elif payment_terms == '90_days':
            return last_transaction_date + timedelta(days=90)
        elif payment_terms == 'custom' and custom_days:
            return last_transaction_date + timedelta(days=custom_days)
        
        return last_transaction_date + timedelta(days=30)  # Default to 30 days

    def update_debtor_balance(debtor_id, user_id):
        """Update debtor balance and status based on transactions"""
        try:
            # Get all transactions for this debtor
            transactions = list(mongo.db.debtor_transactions.find({
                'debtorId': debtor_id,
                'userId': user_id,
                'status': 'completed'
            }))
            
            total_debt = 0
            paid_amount = 0
            last_transaction_date = None
            
            for transaction in transactions:
                if transaction['type'] == 'sale':
                    total_debt += transaction['amount']
                elif transaction['type'] == 'payment':
                    paid_amount += transaction['amount']
                elif transaction['type'] == 'adjustment':
                    # Adjustments can be positive or negative
                    total_debt += transaction['amount']
                
                # Track last transaction date
                trans_date = transaction['transactionDate']
                if not last_transaction_date or trans_date > last_transaction_date:
                    last_transaction_date = trans_date
            
            remaining_debt = total_debt - paid_amount
            
            # Get debtor to calculate next payment due
            debtor = mongo.db.debtors.find_one({'_id': debtor_id})
            if not debtor:
                return False
            
            # Calculate next payment due and overdue days
            next_payment_due = calculate_next_payment_due(
                debtor['paymentTerms'], 
                debtor.get('customPaymentDays'),
                last_transaction_date
            )
            
            overdue_days = calculate_overdue_days(next_payment_due)
            
            # Determine status
            if remaining_debt <= 0:
                status = 'paid'
            elif overdue_days > 0:
                status = 'overdue'
            else:
                status = 'active'
            
            # Update debtor record
            mongo.db.debtors.update_one(
                {'_id': debtor_id},
                {
                    '$set': {
                        'totalDebt': total_debt,
                        'paidAmount': paid_amount,
                        'remainingDebt': remaining_debt,
                        'status': status,
                        'lastPaymentDate': last_transaction_date if paid_amount > 0 else None,
                        'nextPaymentDue': next_payment_due,
                        'overdueDays': overdue_days,
                        'updatedAt': datetime.utcnow()
                    }
                }
            )
            
            return True
            
        except Exception as e:
            print(f"Error updating debtor balance: {str(e)}")
            return False

    # ==================== CUSTOMER MANAGEMENT ENDPOINTS ====================

    @debtors_bp.route('/customers', methods=['POST'])
    @token_required
    def add_customer(current_user):
        """Add a new customer"""
        try:
            data = request.get_json()
            
            # Validate required fields
            if not data.get('customerName'):
                return jsonify({
                    'success': False,
                    'message': 'Customer name is required',
                    'errors': {'customerName': ['Customer name is required']}
                }), 400
            
            # Check if customer already exists
            existing_customer = mongo.db.debtors.find_one({
                'userId': current_user['_id'],
                'customerName': data['customerName']
            })
            
            if existing_customer:
                return jsonify({
                    'success': False,
                    'message': 'Customer with this name already exists',
                    'errors': {'customerName': ['Customer already exists']}
                }), 400
            
            # Validate payment terms
            valid_payment_terms = ['30_days', '60_days', '90_days', 'custom']
            payment_terms = data.get('paymentTerms', '30_days')
            if payment_terms not in valid_payment_terms:
                return jsonify({
                    'success': False,
                    'message': 'Invalid payment terms',
                    'errors': {'paymentTerms': ['Invalid payment terms']}
                }), 400
            
            # Validate custom payment days if needed
            custom_payment_days = None
            if payment_terms == 'custom':
                custom_payment_days = data.get('customPaymentDays')
                if not custom_payment_days or custom_payment_days <= 0:
                    return jsonify({
                        'success': False,
                        'message': 'Custom payment days required for custom payment terms',
                        'errors': {'customPaymentDays': ['Custom payment days must be greater than 0']}
                    }), 400
            
            # Create customer record
            customer_data = {
                '_id': ObjectId(),
                'userId': current_user['_id'],
                'customerName': data['customerName'].strip(),
                'customerEmail': data.get('customerEmail', '').strip() or None,
                'customerPhone': data.get('customerPhone', '').strip() or None,
                'customerAddress': data.get('customerAddress', '').strip() or None,
                'totalDebt': 0.0,
                'paidAmount': 0.0,
                'remainingDebt': 0.0,
                'status': 'active',
                'creditLimit': float(data.get('creditLimit', 0)) if data.get('creditLimit') else None,
                'paymentTerms': payment_terms,
                'customPaymentDays': custom_payment_days,
                'lastPaymentDate': None,
                'nextPaymentDue': None,
                'overdueDays': 0,
                'notes': data.get('notes', '').strip() or None,
                'tags': data.get('tags', []) if isinstance(data.get('tags'), list) else [],
                'createdAt': datetime.utcnow(),
                'updatedAt': datetime.utcnow()
            }
            
            result = mongo.db.debtors.insert_one(customer_data)
            
            # Return created customer
            created_customer = mongo.db.debtors.find_one({'_id': result.inserted_id})
            customer_response = serialize_doc(created_customer.copy())
            
            # Format dates
            customer_response['createdAt'] = customer_response.get('createdAt', datetime.utcnow()).isoformat() + 'Z'
            customer_response['updatedAt'] = customer_response.get('updatedAt', datetime.utcnow()).isoformat() + 'Z'
            
            return jsonify({
                'success': True,
                'data': customer_response,
                'message': 'Customer added successfully'
            }), 201
            
        except Exception as e:
            return jsonify({
                'success': False,
                'message': 'Failed to add customer',
                'errors': {'general': [str(e)]}
            }), 500

    @debtors_bp.route('/customers', methods=['GET'])
    @token_required
    def get_customers(current_user):
        """Get all customers with pagination and filtering"""
        try:
            page = int(request.args.get('page', 1))
            limit = int(request.args.get('limit', 10))
            status = request.args.get('status')
            search = request.args.get('search')
            
            # Build query
            query = {'userId': current_user['_id']}
            
            if status:
                query['status'] = status
            
            if search:
                query['$or'] = [
                    {'customerName': {'$regex': search, '$options': 'i'}},
                    {'customerEmail': {'$regex': search, '$options': 'i'}},
                    {'customerPhone': {'$regex': search, '$options': 'i'}}
                ]
            
            # Get customers with pagination
            skip = (page - 1) * limit
            customers = list(mongo.db.debtors.find(query).sort('customerName', 1).skip(skip).limit(limit))
            total = mongo.db.debtors.count_documents(query)
            
            # Serialize customers
            customer_list = []
            for customer in customers:
                customer_data = serialize_doc(customer.copy())
                customer_data['createdAt'] = customer_data.get('createdAt', datetime.utcnow()).isoformat() + 'Z'
                customer_data['updatedAt'] = customer_data.get('updatedAt', datetime.utcnow()).isoformat() + 'Z'
                customer_data['lastPaymentDate'] = customer_data.get('lastPaymentDate').isoformat() + 'Z' if customer_data.get('lastPaymentDate') else None
                customer_data['nextPaymentDue'] = customer_data.get('nextPaymentDue').isoformat() + 'Z' if customer_data.get('nextPaymentDue') else None
                customer_list.append(customer_data)
            
            return jsonify({
                'success': True,
                'data': customer_list,
                'pagination': {
                    'page': page,
                    'limit': limit,
                    'total': total,
                    'pages': (total + limit - 1) // limit
                },
                'message': 'Customers retrieved successfully'
            })
            
        except Exception as e:
            return jsonify({
                'success': False,
                'message': 'Failed to retrieve customers',
                'errors': {'general': [str(e)]}
            }), 500

    @debtors_bp.route('/transactions', methods=['POST'])
    @token_required
    def add_transaction(current_user):
        """Add a new debt transaction (sale, payment, or adjustment)"""
        try:
            data = request.get_json()
            
            # Validate required fields
            required_fields = ['debtorId', 'type', 'amount', 'description']
            for field in required_fields:
                if not data.get(field):
                    return jsonify({
                        'success': False,
                        'message': f'{field} is required',
                        'errors': {field: [f'{field} is required']}
                    }), 400
            
            # Validate debtor ID
            if not ObjectId.is_valid(data['debtorId']):
                return jsonify({
                    'success': False,
                    'message': 'Invalid debtor ID'
                }), 400
            
            # Check if debtor exists
            debtor = mongo.db.debtors.find_one({
                '_id': ObjectId(data['debtorId']),
                'userId': current_user['_id']
            })
            
            if not debtor:
                return jsonify({
                    'success': False,
                    'message': 'Customer not found'
                }), 404
            
            # Validate transaction type
            valid_types = ['sale', 'payment', 'adjustment']
            if data['type'] not in valid_types:
                return jsonify({
                    'success': False,
                    'message': 'Invalid transaction type',
                    'errors': {'type': ['Transaction type must be sale, payment, or adjustment']}
                }), 400
            
            # Validate amount
            try:
                amount = float(data['amount'])
                if amount <= 0:
                    return jsonify({
                        'success': False,
                        'message': 'Amount must be greater than 0',
                        'errors': {'amount': ['Amount must be greater than 0']}
                    }), 400
            except (ValueError, TypeError):
                return jsonify({
                    'success': False,
                    'message': 'Invalid amount',
                    'errors': {'amount': ['Amount must be a valid number']}
                }), 400
            
            # Parse transaction date
            transaction_date = datetime.utcnow()
            if data.get('transactionDate'):
                try:
                    transaction_date = datetime.fromisoformat(data['transactionDate'].replace('Z', ''))
                except ValueError:
                    return jsonify({
                        'success': False,
                        'message': 'Invalid transaction date format',
                        'errors': {'transactionDate': ['Invalid date format']}
                    }), 400
            
            # Calculate balance before transaction
            balance_before = debtor.get('remainingDebt', 0)
            
            # Calculate balance after transaction
            if data['type'] == 'sale':
                balance_after = balance_before + amount
            elif data['type'] == 'payment':
                balance_after = balance_before - amount
            else:  # adjustment
                balance_after = balance_before + amount  # Adjustments can be positive or negative
            
            # Create transaction record
            transaction_data = {
                '_id': ObjectId(),
                'userId': current_user['_id'],
                'debtorId': ObjectId(data['debtorId']),
                'type': data['type'],
                'amount': amount,
                'description': data['description'].strip(),
                'invoiceNumber': data.get('invoiceNumber', '').strip() or None,
                'paymentMethod': data.get('paymentMethod', '').strip() or None,
                'paymentReference': data.get('paymentReference', '').strip() or None,
                'dueDate': None,
                'transactionDate': transaction_date,
                'balanceBefore': balance_before,
                'balanceAfter': balance_after,
                'status': 'completed',
                'notes': data.get('notes', '').strip() or None,
                'createdAt': datetime.utcnow(),
                'updatedAt': datetime.utcnow()
            }
            
            result = mongo.db.debtor_transactions.insert_one(transaction_data)
            
            # Update debtor balance
            update_debtor_balance(ObjectId(data['debtorId']), current_user['_id'])
            
            # Return created transaction
            created_transaction = mongo.db.debtor_transactions.find_one({'_id': result.inserted_id})
            transaction_response = serialize_doc(created_transaction.copy())
            
            # Format dates
            transaction_response['transactionDate'] = transaction_response.get('transactionDate', datetime.utcnow()).isoformat() + 'Z'
            transaction_response['createdAt'] = transaction_response.get('createdAt', datetime.utcnow()).isoformat() + 'Z'
            transaction_response['updatedAt'] = transaction_response.get('updatedAt', datetime.utcnow()).isoformat() + 'Z'
            
            return jsonify({
                'success': True,
                'data': transaction_response,
                'message': 'Transaction added successfully'
            }), 201
            
        except Exception as e:
            return jsonify({
                'success': False,
                'message': 'Failed to add transaction',
                'errors': {'general': [str(e)]}
            }), 500

    @debtors_bp.route('/summary', methods=['GET'])
    @token_required
    def get_summary(current_user):
        """Get debt summary statistics"""
        try:
            # Get all debtors
            debtors = list(mongo.db.debtors.find({'userId': current_user['_id']}))
            
            # Calculate summary statistics
            total_customers = len(debtors)
            total_debt = sum(debtor.get('totalDebt', 0) for debtor in debtors)
            total_paid = sum(debtor.get('paidAmount', 0) for debtor in debtors)
            total_outstanding = sum(debtor.get('remainingDebt', 0) for debtor in debtors)
            
            # Count by status
            active_customers = len([d for d in debtors if d.get('status') == 'active'])
            overdue_customers = len([d for d in debtors if d.get('status') == 'overdue'])
            paid_customers = len([d for d in debtors if d.get('status') == 'paid'])
            
            # Calculate overdue amount
            overdue_amount = sum(debtor.get('remainingDebt', 0) for debtor in debtors if debtor.get('status') == 'overdue')
            
            summary_data = {
                'totalCustomers': total_customers,
                'activeCustomers': active_customers,
                'overdueCustomers': overdue_customers,
                'paidCustomers': paid_customers,
                'totalDebt': total_debt,
                'totalPaid': total_paid,
                'totalOutstanding': total_outstanding,
                'overdueAmount': overdue_amount,
                'collectionRate': (total_paid / total_debt * 100) if total_debt > 0 else 0
            }
            
            return jsonify({
                'success': True,
                'data': summary_data,
                'message': 'Summary retrieved successfully'
            })
            
        except Exception as e:
            return jsonify({
                'success': False,
                'message': 'Failed to retrieve summary',
                'errors': {'general': [str(e)]}
            }), 500

    return debtors_bp