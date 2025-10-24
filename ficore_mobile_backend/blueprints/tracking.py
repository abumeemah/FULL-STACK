from flask import Blueprint, request, jsonify
from datetime import datetime, timedelta
from bson import ObjectId

def init_tracking_blueprint(mongo, token_required, serialize_doc):
    """Initialize the tracking blueprint with database and dependencies"""
    tracking_bp = Blueprint('tracking', __name__, url_prefix='/tracking')

    @tracking_bp.route('', methods=['GET'])
    @token_required
    def get_transactions(current_user):
        try:
            # Validate database connection
            if mongo is None or mongo.db is None:
                return jsonify({
                    'success': False,
                    'message': 'Database connection error',
                    'errors': {'general': ['Database not available']}
                }), 500
            
            # Get query parameters with safe defaults
            try:
                limit = min(int(request.args.get('limit', 50)), 100)  # Cap at 100
                offset = max(int(request.args.get('offset', 0)), 0)
                sort_by = request.args.get('sort_by', 'date')
                sort_order = request.args.get('sort_order', 'desc')
                start_date = request.args.get('start_date')
                end_date = request.args.get('end_date')
                transaction_type = request.args.get('type')  # 'income', 'expense', or None for both
            except (ValueError, TypeError) as param_error:
                return jsonify({
                    'success': False,
                    'message': 'Invalid query parameters',
                    'errors': {'general': [str(param_error)]}
                }), 400
            
            # Build date filter with error handling
            date_filter = {}
            if start_date:
                try:
                    start_dt = datetime.fromisoformat(start_date.replace('Z', '+00:00'))
                    date_filter['$gte'] = start_dt
                except (ValueError, TypeError):
                    return jsonify({
                        'success': False,
                        'message': 'Invalid start_date format',
                        'errors': {'start_date': ['Use ISO format: YYYY-MM-DDTHH:MM:SS']}
                    }), 400
            
            if end_date:
                try:
                    end_dt = datetime.fromisoformat(end_date.replace('Z', '+00:00'))
                    date_filter['$lte'] = end_dt
                except (ValueError, TypeError):
                    return jsonify({
                        'success': False,
                        'message': 'Invalid end_date format',
                        'errors': {'end_date': ['Use ISO format: YYYY-MM-DDTHH:MM:SS']}
                    }), 400
            
            transactions = []
            
            # Get expenses with error handling
            if not transaction_type or transaction_type == 'expense':
                try:
                    expense_filter = {'userId': current_user['_id']}
                    if date_filter:
                        expense_filter['date'] = date_filter
                    
                    expenses = list(mongo.db.expenses.find(expense_filter))
                    for expense in expenses:
                        if expense.get('date'):  # Only include if date exists
                            expense_data = serialize_doc(expense.copy())
                            expense_data['type'] = 'expense'
                            expense_data['date'] = expense_data.get('date', datetime.utcnow()).isoformat() + 'Z'
                            transactions.append(expense_data)
                except Exception as expense_error:
                    print(f"Expense query error: {expense_error}")
                    # Continue without expenses rather than failing completely
            
            # CRITICAL FIX: Get incomes with error handling - ONLY actual received incomes
            if not transaction_type or transaction_type == 'income':
                try:
                    now = datetime.utcnow()
                    income_filter = {
                        'userId': current_user['_id'],
                        'dateReceived': {'$lte': now}  # FIXED: Only past and present incomes
                    }
                    if date_filter:
                        # Combine with existing date filter
                        if '$gte' in date_filter:
                            income_filter['dateReceived']['$gte'] = date_filter['$gte']
                        if '$lte' in date_filter:
                            # Use the more restrictive date (earlier of now or end_date)
                            income_filter['dateReceived']['$lte'] = min(now, date_filter['$lte'])
                    
                    incomes = list(mongo.db.incomes.find(income_filter))
                    print(f"DEBUG TRACKING: Found {len(incomes)} incomes for user {current_user['_id']}")
                    for income in incomes:
                        if income.get('dateReceived'):  # Only include if date exists
                            income_data = serialize_doc(income.copy())
                            income_data['type'] = 'income'
                            income_data['date'] = income_data.get('dateReceived', datetime.utcnow()).isoformat() + 'Z'
                            transactions.append(income_data)
                except Exception as income_error:
                    print(f"Income query error: {income_error}")
                    # Continue without incomes rather than failing completely
            
            # Sort transactions with error handling
            try:
                sort_key = 'date'
                reverse_sort = sort_order == 'desc'
                transactions.sort(key=lambda x: x.get(sort_key, ''), reverse=reverse_sort)
            except Exception as sort_error:
                print(f"Sort error: {sort_error}")
                # Use default sorting
                transactions.sort(key=lambda x: x.get('date', ''), reverse=True)
            
            # Apply pagination
            total_count = len(transactions)
            paginated_transactions = transactions[offset:offset + limit]
            
            return jsonify({
                'success': True,
                'data': {
                    'transactions': paginated_transactions,
                    'pagination': {
                        'total': total_count,
                        'limit': limit,
                        'offset': offset,
                        'hasMore': offset + limit < total_count
                    }
                },
                'message': 'Transactions retrieved successfully'
            })
            
        except Exception as e:
            return jsonify({
                'success': False,
                'message': 'Failed to retrieve transactions',
                'errors': {'general': [str(e)]}
            }), 500

    @tracking_bp.route('', methods=['POST'])
    @token_required
    def create_expense(current_user):
        try:
            data = request.get_json()
            
            # Validation
            errors = {}
            if not data.get('amount') or data.get('amount', 0) <= 0:
                errors['amount'] = ['Valid amount is required']
            if not data.get('title') and not data.get('description'):
                errors['title'] = ['Title or description is required']
            if not data.get('category'):
                errors['category'] = ['Category is required']
            
            if errors:
                return jsonify({
                    'success': False,
                    'message': 'Validation failed',
                    'errors': errors
                }), 400
            
            expense_data = {
                'userId': current_user['_id'],
                'title': data.get('title', data.get('description', '')),
                'description': data.get('description', data.get('title', '')),
                'amount': float(data['amount']),
                'category': data['category'],
                'date': datetime.fromisoformat(data.get('date', datetime.utcnow().isoformat()).replace('Z', '')),
                'tags': data.get('tags', []),
                'paymentMethod': data.get('paymentMethod', 'cash'),
                'location': data.get('location', ''),
                'notes': data.get('notes', ''),
                'createdAt': datetime.utcnow(),
                'updatedAt': datetime.utcnow()
            }
            
            result = mongo.db.expenses.insert_one(expense_data)
            expense_id = str(result.inserted_id)
            
            # Return the created expense data
            created_expense = serialize_doc(expense_data.copy())
            created_expense['id'] = expense_id
            created_expense['date'] = created_expense.get('date', datetime.utcnow()).isoformat() + 'Z'
            created_expense['createdAt'] = created_expense.get('createdAt', datetime.utcnow()).isoformat() + 'Z'
            created_expense['updatedAt'] = created_expense.get('updatedAt', datetime.utcnow()).isoformat() + 'Z'
            
            return jsonify({
                'success': True,
                'data': created_expense,
                'message': 'Expense created successfully'
            })
            
        except Exception as e:
            return jsonify({
                'success': False,
                'message': 'Failed to create expense',
                'errors': {'general': [str(e)]}
            }), 500

    @tracking_bp.route('/summary', methods=['GET'])
    @token_required
    def get_summary(current_user):
        try:
            # Get query parameters
            transaction_type = request.args.get('type', 'expense')  # 'income' or 'expense'
            group_by = request.args.get('group_by', 'category')  # 'category', 'month', 'source'
            start_date = request.args.get('start_date')
            end_date = request.args.get('end_date')
            
            # Build date filter
            date_filter = {}
            if start_date:
                try:
                    start_dt = datetime.fromisoformat(start_date.replace('Z', '+00:00'))
                    date_filter['$gte'] = start_dt
                except ValueError:
                    pass
            
            if end_date:
                try:
                    end_dt = datetime.fromisoformat(end_date.replace('Z', '+00:00'))
                    date_filter['$lte'] = end_dt
                except ValueError:
                    pass
            
            summary_data = {}
            
            if transaction_type == 'expense':
                # Get expense summary
                expense_filter = {'userId': current_user['_id']}
                if date_filter:
                    expense_filter['date'] = date_filter
                
                expenses = list(mongo.db.expenses.find(expense_filter))
                
                if group_by == 'category':
                    for expense in expenses:
                        category = expense.get('category', 'Uncategorized')
                        if category not in summary_data:
                            summary_data[category] = {'total': 0, 'count': 0}
                        summary_data[category]['total'] += expense.get('amount', 0)
                        summary_data[category]['count'] += 1
                
                elif group_by == 'month':
                    for expense in expenses:
                        date = expense.get('date', datetime.utcnow())
                        month_key = date.strftime('%Y-%m')
                        if month_key not in summary_data:
                            summary_data[month_key] = {'total': 0, 'count': 0}
                        summary_data[month_key]['total'] += expense.get('amount', 0)
                        summary_data[month_key]['count'] += 1
            
            elif transaction_type == 'income':
                # CRITICAL FIX: Get income summary - ONLY actual received incomes
                now = datetime.utcnow()
                income_filter = {
                    'userId': current_user['_id'],
                    'dateReceived': {'$lte': now}  # FIXED: Only past and present incomes
                }
                if date_filter:
                    # Combine with existing date filter
                    if '$gte' in date_filter:
                        income_filter['dateReceived']['$gte'] = date_filter['$gte']
                    if '$lte' in date_filter:
                        # Use the more restrictive date (earlier of now or end_date)
                        income_filter['dateReceived']['$lte'] = min(now, date_filter['$lte'])
                
                incomes = list(mongo.db.incomes.find(income_filter))
                print(f"DEBUG TRACKING SUMMARY: Found {len(incomes)} incomes for user {current_user['_id']}")
                
                if group_by == 'source':
                    for income in incomes:
                        source = income.get('source', 'Unknown')
                        if source not in summary_data:
                            summary_data[source] = {'total': 0, 'count': 0}
                        summary_data[source]['total'] += income.get('amount', 0)
                        summary_data[source]['count'] += 1
                
                elif group_by == 'month':
                    for income in incomes:
                        date = income.get('dateReceived', datetime.utcnow())
                        month_key = date.strftime('%Y-%m')
                        if month_key not in summary_data:
                            summary_data[month_key] = {'total': 0, 'count': 0}
                        summary_data[month_key]['total'] += income.get('amount', 0)
                        summary_data[month_key]['count'] += 1
            
            # Convert to list format for easier consumption
            summary_list = []
            for key, data in summary_data.items():
                summary_list.append({
                    'label': key,
                    'total': data['total'],
                    'count': data['count']
                })
            
            # Sort by total amount descending
            summary_list.sort(key=lambda x: x['total'], reverse=True)
            
            return jsonify({
                'success': True,
                'data': {
                    'summary': summary_list,
                    'type': transaction_type,
                    'groupBy': group_by,
                    'totalAmount': sum(item['total'] for item in summary_list),
                    'totalCount': sum(item['count'] for item in summary_list)
                },
                'message': 'Summary retrieved successfully'
            })
            
        except Exception as e:
            return jsonify({
                'success': False,
                'message': 'Failed to retrieve summary',
                'errors': {'general': [str(e)]}
            }), 500

    @tracking_bp.route('/statistics', methods=['GET'])
    @token_required
    def get_statistics(current_user):
        try:
            # Get query parameters
            transaction_type = request.args.get('type', 'expense')  # 'income' or 'expense'
            start_date = request.args.get('start_date')
            end_date = request.args.get('end_date')
            
            # Build date filter
            date_filter = {}
            if start_date:
                try:
                    start_dt = datetime.fromisoformat(start_date.replace('Z', '+00:00'))
                    date_filter['$gte'] = start_dt
                except ValueError:
                    pass
            
            if end_date:
                try:
                    end_dt = datetime.fromisoformat(end_date.replace('Z', '+00:00'))
                    date_filter['$lte'] = end_dt
                except ValueError:
                    pass
            
            statistics_data = {}
            
            if transaction_type == 'expense':
                # Get expense statistics
                expense_filter = {'userId': current_user['_id']}
                if date_filter:
                    expense_filter['date'] = date_filter
                
                expenses = list(mongo.db.expenses.find(expense_filter))
                
                if expenses:
                    amounts = [exp.get('amount', 0) for exp in expenses]
                    total_amount = sum(amounts)
                    avg_amount = total_amount / len(amounts)
                    max_amount = max(amounts)
                    min_amount = min(amounts)
                    
                    # Category breakdown
                    categories = {}
                    for expense in expenses:
                        cat = expense.get('category', 'Uncategorized')
                        categories[cat] = categories.get(cat, 0) + expense.get('amount', 0)
                    
                    # Monthly breakdown
                    monthly = {}
                    for expense in expenses:
                        date = expense.get('date', datetime.utcnow())
                        month_key = date.strftime('%Y-%m')
                        monthly[month_key] = monthly.get(month_key, 0) + expense.get('amount', 0)
                    
                    statistics_data = {
                        'totals': {
                            'count': len(expenses),
                            'totalAmount': total_amount,
                            'averageAmount': avg_amount,
                            'maxAmount': max_amount,
                            'minAmount': min_amount
                        },
                        'breakdown': {
                            'byCategory': categories,
                            'byMonth': monthly
                        },
                        'insights': {
                            'topCategory': max(categories.items(), key=lambda x: x[1])[0] if categories else 'None',
                            'topCategoryAmount': max(categories.values()) if categories else 0,
                            'categoriesCount': len(categories)
                        }
                    }
                else:
                    statistics_data = {
                        'totals': {
                            'count': 0,
                            'totalAmount': 0,
                            'averageAmount': 0,
                            'maxAmount': 0,
                            'minAmount': 0
                        },
                        'breakdown': {
                            'byCategory': {},
                            'byMonth': {}
                        },
                        'insights': {
                            'topCategory': 'None',
                            'topCategoryAmount': 0,
                            'categoriesCount': 0
                        }
                    }
            
            elif transaction_type == 'income':
                # CRITICAL FIX: Get income statistics - ONLY actual received incomes
                now = datetime.utcnow()
                income_filter = {
                    'userId': current_user['_id'],
                    'dateReceived': {'$lte': now}  # FIXED: Only past and present incomes
                }
                if date_filter:
                    # Combine with existing date filter
                    if '$gte' in date_filter:
                        income_filter['dateReceived']['$gte'] = date_filter['$gte']
                    if '$lte' in date_filter:
                        # Use the more restrictive date (earlier of now or end_date)
                        income_filter['dateReceived']['$lte'] = min(now, date_filter['$lte'])
                
                incomes = list(mongo.db.incomes.find(income_filter))
                print(f"DEBUG TRACKING STATISTICS: Found {len(incomes)} incomes for user {current_user['_id']}")
                
                # DEBUG: Log each income amount
                for i, inc in enumerate(incomes):
                    print(f"DEBUG TRACKING Income {i+1}: Amount={inc.get('amount')}, DateReceived={inc.get('dateReceived')}")
                
                if incomes:
                    amounts = [inc.get('amount', 0) for inc in incomes]
                    total_amount = sum(amounts)
                    avg_amount = total_amount / len(amounts)
                    max_amount = max(amounts)
                    min_amount = min(amounts)
                    
                    # Source breakdown
                    sources = {}
                    for income in incomes:
                        source = income.get('source', 'Unknown')
                        sources[source] = sources.get(source, 0) + income.get('amount', 0)
                    
                    # Monthly breakdown
                    monthly = {}
                    for income in incomes:
                        date = income.get('dateReceived', datetime.utcnow())
                        month_key = date.strftime('%Y-%m')
                        monthly[month_key] = monthly.get(month_key, 0) + income.get('amount', 0)
                    
                    statistics_data = {
                        'totals': {
                            'count': len(incomes),
                            'totalAmount': total_amount,
                            'averageAmount': avg_amount,
                            'maxAmount': max_amount,
                            'minAmount': min_amount
                        },
                        'breakdown': {
                            'bySource': sources,
                            'byMonth': monthly
                        },
                        'insights': {
                            'topSource': max(sources.items(), key=lambda x: x[1])[0] if sources else 'None',
                            'topSourceAmount': max(sources.values()) if sources else 0,
                            'sourcesCount': len(sources)
                        }
                    }
                else:
                    statistics_data = {
                        'totals': {
                            'count': 0,
                            'totalAmount': 0,
                            'averageAmount': 0,
                            'maxAmount': 0,
                            'minAmount': 0
                        },
                        'breakdown': {
                            'bySource': {},
                            'byMonth': {}
                        },
                        'insights': {
                            'topSource': 'None',
                            'topSourceAmount': 0,
                            'sourcesCount': 0
                        }
                    }
            
            return jsonify({
                'success': True,
                'data': {
                    'statistics': statistics_data,
                    'type': transaction_type,
                    'period': {
                        'startDate': start_date,
                        'endDate': end_date
                    }
                },
                'message': 'Statistics retrieved successfully'
            })
            
        except Exception as e:
            return jsonify({
                'success': False,
                'message': 'Failed to retrieve statistics',
                'errors': {'general': [str(e)]}
            }), 500

    return tracking_bp