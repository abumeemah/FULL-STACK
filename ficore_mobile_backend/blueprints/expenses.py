from flask import Blueprint, request, jsonify
from datetime import datetime, timedelta
from bson import ObjectId
from utils.payment_utils import normalize_payment_method, validate_payment_method

expenses_bp = Blueprint('expenses', __name__, url_prefix='/expenses')

def init_expenses_blueprint(mongo, token_required, serialize_doc):
    """Initialize the expenses blueprint with database and auth decorator"""
    expenses_bp.mongo = mongo
    expenses_bp.token_required = token_required
    expenses_bp.serialize_doc = serialize_doc
    return expenses_bp

@expenses_bp.route('', methods=['GET'])
def get_expenses():
    @expenses_bp.token_required
    def _get_expenses(current_user):
        try:
            page = int(request.args.get('page', 1))
            limit = int(request.args.get('limit', 10))
            category = request.args.get('category')
            start_date = request.args.get('start_date')
            end_date = request.args.get('end_date')
            
            # Build query
            query = {'userId': current_user['_id']}
            if category:
                query['category'] = category
            if start_date or end_date:
                date_query = {}
                if start_date:
                    date_query['$gte'] = datetime.fromisoformat(start_date.replace('Z', ''))
                if end_date:
                    date_query['$lte'] = datetime.fromisoformat(end_date.replace('Z', ''))
                query['date'] = date_query
            
            # Get expenses with pagination
            skip = (page - 1) * limit
            expenses = list(expenses_bp.mongo.db.expenses.find(query).sort('date', -1).skip(skip).limit(limit))
            total = expenses_bp.mongo.db.expenses.count_documents(query)
            
            # Serialize expenses
            expense_list = []
            for expense in expenses:
                expense_data = expenses_bp.serialize_doc(expense.copy())
                expense_data['date'] = expense_data.get('date', datetime.utcnow()).isoformat() + 'Z'
                expense_data['createdAt'] = expense_data.get('createdAt', datetime.utcnow()).isoformat() + 'Z'
                expense_data['updatedAt'] = expense_data.get('updatedAt', datetime.utcnow()).isoformat() + 'Z' if expense_data.get('updatedAt') else None
                expense_list.append(expense_data)
            
            return jsonify({
                'success': True,
                'data': {
                    'expenses': expense_list,
                    'pagination': {
                        'page': page,
                        'limit': limit,
                        'total': total,
                        'pages': (total + limit - 1) // limit
                    }
                },
                'message': 'Expenses retrieved successfully'
            })
            
        except Exception as e:
            return jsonify({
                'success': False,
                'message': 'Failed to retrieve expenses',
                'errors': {'general': [str(e)]}
            }), 500
    
    return _get_expenses()

@expenses_bp.route('/<expense_id>', methods=['GET'])
def get_expense(expense_id):
    @expenses_bp.token_required
    def _get_expense(current_user):
        try:
            expense = expenses_bp.mongo.db.expenses.find_one({
                '_id': ObjectId(expense_id),
                'userId': current_user['_id']
            })
            
            if not expense:
                return jsonify({
                    'success': False,
                    'message': 'Expense not found'
                }), 404
            
            expense_data = expenses_bp.serialize_doc(expense.copy())
            expense_data['date'] = expense_data.get('date', datetime.utcnow()).isoformat() + 'Z'
            expense_data['createdAt'] = expense_data.get('createdAt', datetime.utcnow()).isoformat() + 'Z'
            expense_data['updatedAt'] = expense_data.get('updatedAt', datetime.utcnow()).isoformat() + 'Z' if expense_data.get('updatedAt') else None
            
            return jsonify({
                'success': True,
                'data': expense_data,
                'message': 'Expense retrieved successfully'
            })
            
        except Exception as e:
            return jsonify({
                'success': False,
                'message': 'Failed to retrieve expense',
                'errors': {'general': [str(e)]}
            }), 500
    
    return _get_expense()

@expenses_bp.route('', methods=['POST'])
def create_expense():
    @expenses_bp.token_required
    def _create_expense(current_user):
        try:
            data = request.get_json()
            
            # Validation
            errors = {}
            if not data.get('amount') or data.get('amount', 0) <= 0:
                errors['amount'] = ['Valid amount is required']
            if not data.get('description'):
                errors['description'] = ['Description is required']
            if not data.get('category'):
                errors['category'] = ['Category is required']
            
            if errors:
                return jsonify({
                    'success': False,
                    'message': 'Validation failed',
                    'errors': errors
                }), 400
            
            # NOTE: Credit checking and deduction is handled by frontend executeWithCredits()
            # No need to check/deduct credits here to avoid double deduction
            
            # Normalize and validate payment method if provided
            raw_payment = data.get('paymentMethod')
            normalized_payment = normalize_payment_method(raw_payment) if raw_payment is not None else 'cash'
            if raw_payment is not None and not validate_payment_method(raw_payment):
                return jsonify({
                    'success': False,
                    'message': 'Invalid payment method',
                    'errors': {'paymentMethod': ['Unrecognized payment method']}
                }), 400

            expense_data = {
                'userId': current_user['_id'],
                'amount': float(data['amount']),
                'description': data['description'],
                'category': data['category'],
                'date': datetime.fromisoformat(data.get('date', datetime.utcnow().isoformat()).replace('Z', '')),
                'budgetId': data.get('budgetId'),
                'tags': data.get('tags', []),
                'paymentMethod': normalized_payment or 'cash',
                'location': data.get('location', ''),
                'notes': data.get('notes', ''),
                'createdAt': datetime.utcnow(),
                'updatedAt': datetime.utcnow()
            }
            
            result = expenses_bp.mongo.db.expenses.insert_one(expense_data)
            expense_id = str(result.inserted_id)
            
            # NOTE: Credit deduction is handled by frontend executeWithCredits()
            # to avoid double deduction
            
            return jsonify({
                'success': True,
                'data': {
                    'id': expense_id,
                    'amount': expense_data['amount'],
                    'description': expense_data['description'],
                    'category': expense_data['category']
                },
                'message': 'Expense created successfully'
            })
            
        except Exception as e:
            return jsonify({
                'success': False,
                'message': 'Failed to create expense',
                'errors': {'general': [str(e)]}
            }), 500
    
    return _create_expense()

@expenses_bp.route('/<expense_id>', methods=['PUT'])
def update_expense(expense_id):
    @expenses_bp.token_required
    def _update_expense(current_user):
        try:
            data = request.get_json()
            
            # Check if expense exists
            expense = expenses_bp.mongo.db.expenses.find_one({
                '_id': ObjectId(expense_id),
                'userId': current_user['_id']
            })
            
            if not expense:
                return jsonify({
                    'success': False,
                    'message': 'Expense not found'
                }), 404
            
            # Update fields
            update_data = {}
            updatable_fields = ['amount', 'description', 'category', 'date', 'budgetId', 'tags', 'paymentMethod', 'location', 'notes']
            
            for field in updatable_fields:
                if field in data:
                    if field == 'amount':
                        update_data[field] = float(data[field])
                    elif field == 'date':
                        update_data[field] = datetime.fromisoformat(data[field].replace('Z', ''))
                    elif field == 'paymentMethod':
                        # Normalize and validate payment method for updates
                        if not validate_payment_method(data[field]):
                            return jsonify({
                                'success': False,
                                'message': 'Invalid payment method',
                                'errors': {'paymentMethod': ['Unrecognized payment method']}
                            }), 400
                        update_data[field] = normalize_payment_method(data[field])
                    else:
                        update_data[field] = data[field]
            
            update_data['updatedAt'] = datetime.utcnow()
            
            expenses_bp.mongo.db.expenses.update_one(
                {'_id': ObjectId(expense_id)},
                {'$set': update_data}
            )
            
            # Get updated expense
            updated_expense = expenses_bp.mongo.db.expenses.find_one({'_id': ObjectId(expense_id)})
            expense_data = expenses_bp.serialize_doc(updated_expense.copy())
            expense_data['date'] = expense_data.get('date', datetime.utcnow()).isoformat() + 'Z'
            expense_data['createdAt'] = expense_data.get('createdAt', datetime.utcnow()).isoformat() + 'Z'
            expense_data['updatedAt'] = expense_data.get('updatedAt', datetime.utcnow()).isoformat() + 'Z'
            
            return jsonify({
                'success': True,
                'data': expense_data,
                'message': 'Expense updated successfully'
            })
            
        except Exception as e:
            return jsonify({
                'success': False,
                'message': 'Failed to update expense',
                'errors': {'general': [str(e)]}
            }), 500
    
    return _update_expense()

@expenses_bp.route('/<expense_id>', methods=['DELETE'])
def delete_expense(expense_id):
    @expenses_bp.token_required
    def _delete_expense(current_user):
        try:
            result = expenses_bp.mongo.db.expenses.delete_one({
                '_id': ObjectId(expense_id),
                'userId': current_user['_id']
            })
            
            if result.deleted_count == 0:
                return jsonify({
                    'success': False,
                    'message': 'Expense not found'
                }), 404
            
            return jsonify({
                'success': True,
                'message': 'Expense deleted successfully'
            })
            
        except Exception as e:
            return jsonify({
                'success': False,
                'message': 'Failed to delete expense',
                'errors': {'general': [str(e)]}
            }), 500
    
    return _delete_expense()

@expenses_bp.route('/summary', methods=['GET'])
def get_expense_summary():
    @expenses_bp.token_required
    def _get_expense_summary(current_user):
        try:
            # Get date ranges
            now = datetime.utcnow()
            start_of_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            start_of_last_month = (start_of_month - timedelta(days=1)).replace(day=1)
            
            # Get expense data
            expenses = list(expenses_bp.mongo.db.expenses.find({'userId': current_user['_id']}))
            
            # Calculate totals
            total_this_month = sum(exp['amount'] for exp in expenses if exp['date'] >= start_of_month)
            total_last_month = sum(exp['amount'] for exp in expenses if start_of_last_month <= exp['date'] < start_of_month)
            
            # Category breakdown
            category_totals = {}
            for expense in expenses:
                if expense['date'] >= start_of_month:
                    category = expense['category']
                    category_totals[category] = category_totals.get(category, 0) + expense['amount']
            
            # Recent expenses
            recent_expenses = sorted(expenses, key=lambda x: x['date'], reverse=True)[:5]
            recent_expenses_data = []
            for expense in recent_expenses:
                expense_data = expenses_bp.serialize_doc(expense.copy())
                expense_data['date'] = expense_data.get('date', datetime.utcnow()).isoformat() + 'Z'
                recent_expenses_data.append(expense_data)
            
            summary_data = {
                'totalThisMonth': total_this_month,
                'totalLastMonth': total_last_month,
                'categoryBreakdown': category_totals,
                'recentExpenses': recent_expenses_data,
                'totalExpenses': len(expenses),
                'averageExpense': sum(exp['amount'] for exp in expenses) / len(expenses) if expenses else 0
            }
            
            return jsonify({
                'success': True,
                'data': summary_data,
                'message': 'Expense summary retrieved successfully'
            })
            
        except Exception as e:
            return jsonify({
                'success': False,
                'message': 'Failed to retrieve expense summary',
                'errors': {'general': [str(e)]}
            }), 500
    
    return _get_expense_summary()

@expenses_bp.route('/categories', methods=['GET'])
def get_expense_categories():
    @expenses_bp.token_required
    def _get_expense_categories(current_user):
        try:
            # Get unique categories from user's expenses
            expenses = list(expenses_bp.mongo.db.expenses.find({'userId': current_user['_id']}))
            categories = set(expense.get('category', '') for expense in expenses)
            
            # Default categories if none exist
            if not categories:
                # Default categories - extended with business-focused categories for tax tracking
                categories = {
                    'Food & Dining', 'Transportation', 'Shopping', 'Entertainment',
                    'Bills & Utilities', 'Healthcare', 'Education', 'Travel',
                    'Personal Care', 'Home & Garden', 'Gifts & Donations',
                    # Business categories
                    'Office & Admin', 'Staff & Wages', 'Business Transport', 'Rent & Utilities',
                    'Marketing & Sales Expenses', 'Cost of Goods Sold - COGS', 'Personal Expenses',
                    'Statutory & Legal Contributions',
                    'Other'
                }
            
            return jsonify({
                'success': True,
                'data': {'categories': sorted(list(categories))},
                'message': 'Expense categories retrieved successfully'
            })
            
        except Exception as e:
            return jsonify({
                'success': False,
                'message': 'Failed to retrieve expense categories',
                'errors': {'general': [str(e)]}
            }), 500
    
    return _get_expense_categories()

@expenses_bp.route('/insights', methods=['GET'])
def get_expense_insights():
    @expenses_bp.token_required
    def _get_expense_insights(current_user):
        try:
            # Get user's expense data for analysis
            expenses = list(expenses_bp.mongo.db.expenses.find({'userId': current_user['_id']}))
            
            if not expenses:
                return jsonify({
                    'success': True,
                    'data': {
                        'insights': [],
                        'message': 'No expense data available for insights'
                    },
                    'message': 'Expense insights retrieved successfully'
                })
            
            # Calculate insights
            insights = []
            
            # Get current month data
            now = datetime.utcnow()
            start_of_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            start_of_last_month = (start_of_month - timedelta(days=1)).replace(day=1)
            
            # Current month expenses
            current_month_expenses = [exp for exp in expenses if exp['date'] >= start_of_month]
            current_month_total = sum(exp['amount'] for exp in current_month_expenses)
            
            # Last month expenses
            last_month_expenses = [exp for exp in expenses if start_of_last_month <= exp['date'] < start_of_month]
            last_month_total = sum(exp['amount'] for exp in last_month_expenses)
            
            # Spending trend insight
            if last_month_total > 0:
                change_rate = ((current_month_total - last_month_total) / last_month_total) * 100
                if change_rate > 15:
                    insights.append({
                        'type': 'increase',
                        'title': 'Spending Increase',
                        'message': f'Your spending increased by {change_rate:.1f}% this month',
                        'value': change_rate,
                        'priority': 'high'
                    })
                elif change_rate < -15:
                    insights.append({
                        'type': 'decrease',
                        'title': 'Spending Reduction',
                        'message': f'Great! You reduced spending by {abs(change_rate):.1f}% this month',
                        'value': change_rate,
                        'priority': 'high'
                    })
            
            # Top spending category
            category_totals = {}
            for expense in current_month_expenses:
                category = expense.get('category', 'Other')
                category_totals[category] = category_totals.get(category, 0) + expense['amount']
            
            if category_totals:
                top_category = max(category_totals.items(), key=lambda x: x[1])
                category_percentage = (top_category[1] / current_month_total) * 100 if current_month_total > 0 else 0
                insights.append({
                    'type': 'top_category',
                    'title': 'Top Spending Category',
                    'message': f'{top_category[0]} accounts for {category_percentage:.1f}% of your spending',
                    'value': top_category[1],
                    'priority': 'medium'
                })
            
            # Average daily spending
            days_in_month = now.day
            avg_daily = current_month_total / days_in_month if days_in_month > 0 else 0
            insights.append({
                'type': 'daily_average',
                'title': 'Daily Average',
                'message': f'You spend an average of ₦{avg_daily:,.0f} per day this month',
                'value': avg_daily,
                'priority': 'low'
            })
            
            # Spending pattern insight
            weekend_expenses = [exp for exp in current_month_expenses 
                              if exp['date'].weekday() >= 5]  # Saturday = 5, Sunday = 6
            weekday_expenses = [exp for exp in current_month_expenses 
                              if exp['date'].weekday() < 5]
            
            weekend_total = sum(exp['amount'] for exp in weekend_expenses)
            weekday_total = sum(exp['amount'] for exp in weekday_expenses)
            
            if weekend_total > 0 and weekday_total > 0:
                weekend_avg = weekend_total / (len(weekend_expenses) if weekend_expenses else 1)
                weekday_avg = weekday_total / (len(weekday_expenses) if weekday_expenses else 1)
                
                if weekend_avg > weekday_avg * 1.5:
                    insights.append({
                        'type': 'weekend_spending',
                        'title': 'Weekend Spending',
                        'message': 'You tend to spend more on weekends',
                        'value': weekend_avg / weekday_avg,
                        'priority': 'medium'
                    })
            
            # Frequent small expenses insight
            small_expenses = [exp for exp in current_month_expenses if exp['amount'] < 1000]  # Less than ₦1000
            if len(small_expenses) > len(current_month_expenses) * 0.6:  # More than 60% are small
                small_total = sum(exp['amount'] for exp in small_expenses)
                insights.append({
                    'type': 'small_expenses',
                    'title': 'Small Expenses Add Up',
                    'message': f'Small expenses (under ₦1,000) total ₦{small_total:,.0f} this month',
                    'value': small_total,
                    'priority': 'medium'
                })
            
            # Monthly budget insight (if applicable)
            if current_month_total > 0:
                # Estimate monthly budget based on historical data
                six_months_ago = now - timedelta(days=180)
                recent_expenses = [exp for exp in expenses if exp['date'] >= six_months_ago]
                if recent_expenses:
                    avg_monthly = sum(exp['amount'] for exp in recent_expenses) / 6
                    if current_month_total > avg_monthly * 1.2:
                        insights.append({
                            'type': 'budget_alert',
                            'title': 'Above Average Spending',
                            'message': f'This month\'s spending is {((current_month_total/avg_monthly-1)*100):.0f}% above your 6-month average',
                            'value': current_month_total / avg_monthly,
                            'priority': 'high'
                        })
            
            return jsonify({
                'success': True,
                'data': {
                    'insights': insights,
                    'summary': {
                        'current_month_total': current_month_total,
                        'last_month_total': last_month_total,
                        'total_categories': len(category_totals),
                        'total_expenses_count': len(current_month_expenses)
                    }
                },
                'message': 'Expense insights retrieved successfully'
            })
            
        except Exception as e:
            return jsonify({
                'success': False,
                'message': 'Failed to retrieve expense insights',
                'errors': {'general': [str(e)]}
            }), 500
    
    return _get_expense_insights()

@expenses_bp.route('/statistics', methods=['GET'])
def get_expense_statistics():
    @expenses_bp.token_required
    def _get_expense_statistics(current_user):
        try:
            # Get query parameters
            start_date = request.args.get('start_date')
            end_date = request.args.get('end_date')
            group_by = request.args.get('group_by', 'month')  # Default to month
            
            # Validate group_by parameter
            valid_groups = ['month', 'category', 'payment_method']
            if group_by not in valid_groups:
                return jsonify({
                    'success': False,
                    'message': 'Invalid group_by parameter',
                    'errors': {'group_by': [f'Must be one of: {", ".join(valid_groups)}']}
                }), 400
            
            # Build query
            query = {'userId': current_user['_id']}
            if start_date or end_date:
                date_query = {}
                if start_date:
                    date_query['$gte'] = datetime.fromisoformat(start_date.replace('Z', ''))
                if end_date:
                    date_query['$lte'] = datetime.fromisoformat(end_date.replace('Z', ''))
                query['date'] = date_query
            
            # Get expense data
            expenses = list(expenses_bp.mongo.db.expenses.find(query))
            
            # Calculate statistics
            from collections import defaultdict
            statistics = defaultdict(float)
            total = 0
            count = len(expenses)
            
            if group_by == 'month':
                for expense in expenses:
                    if expense.get('date'):
                        month_key = expense['date'].strftime('%Y-%m')
                        statistics[month_key] += expense.get('amount', 0)
                        total += expense.get('amount', 0)
            elif group_by == 'category':
                for expense in expenses:
                    category = expense.get('category', 'Unknown')
                    statistics[category] += expense.get('amount', 0)
                    total += expense.get('amount', 0)
            elif group_by == 'payment_method':
                for expense in expenses:
                    payment_method = expense.get('paymentMethod', 'Unknown')
                    statistics[payment_method] += expense.get('amount', 0)
                    total += expense.get('amount', 0)
                
            # Calculate average
            average = total / count if count > 0 else 0
            
            # Prepare summary
            summary = {
                'total': total,
                'average': average,
                'count': count,
                'start_date': start_date or datetime.utcnow().replace(day=1, hour=0, minute=0, second=0, microsecond=0).isoformat() + 'Z',
                'end_date': end_date or datetime.utcnow().isoformat() + 'Z',
                'group_by': group_by
            }
            
            return jsonify({
                'success': True,
                'data': {
                    'statistics': dict(statistics),
                    'summary': summary
                },
                'message': 'Expense statistics retrieved successfully'
            })
            
        except Exception as e:
            return jsonify({
                'success': False,
                'message': 'Failed to retrieve expense statistics',
                'errors': {'general': [str(e)]}
            }), 500
    
    return _get_expense_statistics()
