from flask import Blueprint, request, jsonify
from datetime import datetime, timedelta
from bson import ObjectId

def init_summaries_blueprint(mongo, token_required, serialize_doc):
    """Initialize the summaries blueprint with database and dependencies"""
    summaries_bp = Blueprint('summaries', __name__, url_prefix='/summaries')

    @summaries_bp.route('/recent_activity', methods=['GET'])
    @token_required
    def get_recent_activity(current_user):
        """Get recent user activities across all modules"""
        try:
            # Validate database connection
            if mongo is None or mongo.db is None:
                return jsonify({
                    'success': False,
                    'message': 'Database connection error',
                    'errors': {'general': ['Database not available']}
                }), 500

            # Get query parameters
            limit = min(int(request.args.get('limit', 10)), 50)  # Cap at 50
            
            activities = []
            
            # Get recent expenses
            try:
                recent_expenses = list(mongo.db.expenses.find({
                    'userId': current_user['_id']
                }).sort('createdAt', -1).limit(limit))
                
                for expense in recent_expenses:
                    activity = {
                        'id': str(expense['_id']),
                        'type': 'expense',
                        'title': expense.get('title', expense.get('description', 'Expense')),
                        'description': f"Spent ₦{expense.get('amount', 0):,.2f} on {expense.get('category', 'Unknown')}",
                        'amount': expense.get('amount', 0),
                        'category': expense.get('category', 'Unknown'),
                        'date': expense.get('date', expense.get('createdAt', datetime.utcnow())).isoformat() + 'Z',
                        'icon': 'expense',
                        'color': 'red'
                    }
                    activities.append(activity)
            except Exception as e:
                print(f"Error fetching expenses: {e}")

            # FIXED: Get recent incomes - ONLY actual received incomes
            try:
                now = datetime.utcnow()
                recent_incomes = list(mongo.db.incomes.find({
                    'userId': current_user['_id'],
                    'dateReceived': {'$lte': now}  # Only past and present incomes
                }).sort('createdAt', -1).limit(limit))
                
                for income in recent_incomes:
                    activity = {
                        'id': str(income['_id']),
                        'type': 'income',
                        'title': income.get('title', income.get('source', 'Income')),
                        'description': f"Received ₦{income.get('amount', 0):,.2f} from {income.get('source', 'Unknown')}",
                        'amount': income.get('amount', 0),
                        'source': income.get('source', 'Unknown'),
                        'date': income.get('dateReceived', income.get('createdAt', datetime.utcnow())).isoformat() + 'Z',
                        'icon': 'income',
                        'color': 'green'
                    }
                    activities.append(activity)
            except Exception as e:
                print(f"Error fetching incomes: {e}")

            # Sort all activities by date (most recent first)
            activities.sort(key=lambda x: x['date'], reverse=True)
            
            # Limit to requested number
            activities = activities[:limit]

            return jsonify({
                'success': True,
                'data': {
                    'activities': activities,
                    'total': len(activities),
                    'lastUpdated': datetime.utcnow().isoformat() + 'Z'
                },
                'message': 'Recent activities retrieved successfully'
            })

        except Exception as e:
            print(f"Error in get_recent_activity: {e}")
            return jsonify({
                'success': False,
                'message': 'Failed to retrieve recent activities',
                'errors': {'general': [str(e)]}
            }), 500

    @summaries_bp.route('/all_activities', methods=['GET'])
    @token_required
    def get_all_activities(current_user):
        """Get all user activities with pagination"""
        try:
            # Get query parameters
            page = int(request.args.get('page', 1))
            limit = min(int(request.args.get('limit', 20)), 100)
            activity_type = request.args.get('type', 'all')  # all, expense, income
            
            activities = []
            
            # Get activities based on type filter
            if activity_type in ['all', 'expense']:
                try:
                    expenses = list(mongo.db.expenses.find({
                        'userId': current_user['_id']
                    }).sort('createdAt', -1))
                    
                    for expense in expenses:
                        activity = {
                            'id': str(expense['_id']),
                            'type': 'expense',
                            'title': expense.get('title', expense.get('description', 'Expense')),
                            'description': f"Spent ₦{expense.get('amount', 0):,.2f} on {expense.get('category', 'Unknown')}",
                            'amount': expense.get('amount', 0),
                            'category': expense.get('category', 'Unknown'),
                            'date': expense.get('date', expense.get('createdAt', datetime.utcnow())).isoformat() + 'Z',
                            'icon': 'expense',
                            'color': 'red'
                        }
                        activities.append(activity)
                except Exception as e:
                    print(f"Error fetching expenses: {e}")

            if activity_type in ['all', 'income']:
                try:
                    # FIXED: Only get actual received incomes, no projections
                    now = datetime.utcnow()
                    incomes = list(mongo.db.incomes.find({
                        'userId': current_user['_id'],
                        'dateReceived': {'$lte': now}  # Only past and present incomes
                    }).sort('createdAt', -1))
                    
                    for income in incomes:
                        activity = {
                            'id': str(income['_id']),
                            'type': 'income',
                            'title': income.get('title', income.get('source', 'Income')),
                            'description': f"Received ₦{income.get('amount', 0):,.2f} from {income.get('source', 'Unknown')}",
                            'amount': income.get('amount', 0),
                            'source': income.get('source', 'Unknown'),
                            'date': income.get('dateReceived', income.get('createdAt', datetime.utcnow())).isoformat() + 'Z',
                            'icon': 'income',
                            'color': 'green'
                        }
                        activities.append(activity)
                except Exception as e:
                    print(f"Error fetching incomes: {e}")

            # Sort all activities by date (most recent first)
            activities.sort(key=lambda x: x['date'], reverse=True)
            
            # Apply pagination
            total_count = len(activities)
            start_index = (page - 1) * limit
            end_index = start_index + limit
            paginated_activities = activities[start_index:end_index]

            return jsonify({
                'success': True,
                'data': {
                    'activities': paginated_activities,
                    'pagination': {
                        'page': page,
                        'limit': limit,
                        'total': total_count,
                        'pages': (total_count + limit - 1) // limit,
                        'hasNext': end_index < total_count,
                        'hasPrev': page > 1
                    }
                },
                'message': 'All activities retrieved successfully'
            })

        except Exception as e:
            print(f"Error in get_all_activities: {e}")
            return jsonify({
                'success': False,
                'message': 'Failed to retrieve activities',
                'errors': {'general': [str(e)]}
            }), 500

    @summaries_bp.route('/dashboard_summary', methods=['GET'])
    @token_required
    def get_dashboard_summary(current_user):
        """Get comprehensive dashboard summary"""
        try:
            # Get current month data
            now = datetime.utcnow()
            start_of_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            
            summary_data = {
                'totalIncome': 0,
                'totalExpenses': 0,
                'creditBalance': 0,
                'recentActivitiesCount': 0,
                'monthlyStats': {
                    'income': 0,
                    'expenses': 0
                }
            }
            
            # Get user's credit balance
            try:
                user = mongo.db.users.find_one({'_id': current_user['_id']})
                if user:
                    summary_data['creditBalance'] = user.get('ficoreCreditBalance', 0.0)
            except Exception as e:
                print(f"Error fetching user balance: {e}")
            
            # FIXED: Get income data - ONLY actual received incomes, no projections
            try:
                now = datetime.utcnow()
                incomes = list(mongo.db.incomes.find({
                    'userId': current_user['_id'],
                    'dateReceived': {'$lte': now}  # Only past and present incomes
                }))
                
                # CRITICAL DEBUG: Log dashboard summary calculation
                print(f"DEBUG DASHBOARD SUMMARY - User: {current_user['_id']}")
                print(f"DEBUG: Total incomes for dashboard: {len(incomes)}")
                for i, inc in enumerate(incomes):
                    print(f"DEBUG Dashboard Income {i+1}: Amount={inc.get('amount')}, DateReceived={inc.get('dateReceived')}")
                
                # FIXED: Simple sum of actual amounts only
                total_income = sum(inc.get('amount', 0) for inc in incomes)
                summary_data['totalIncome'] = total_income
                print(f"DEBUG: CALCULATED dashboard totalIncome = {total_income}")
                
                monthly_incomes = [inc for inc in incomes if inc.get('dateReceived', datetime.utcnow()) >= start_of_month]
                monthly_income_total = sum(inc.get('amount', 0) for inc in monthly_incomes)
                summary_data['monthlyStats']['income'] = monthly_income_total
                print(f"DEBUG: CALCULATED dashboard monthly income = {monthly_income_total}")
            except Exception as e:
                print(f"Error fetching incomes: {e}")
            
            # Get expense data
            try:
                expenses = list(mongo.db.expenses.find({'userId': current_user['_id']}))
                summary_data['totalExpenses'] = sum(exp.get('amount', 0) for exp in expenses)
                
                monthly_expenses = [exp for exp in expenses if exp.get('date', datetime.utcnow()) >= start_of_month]
                summary_data['monthlyStats']['expenses'] = sum(exp.get('amount', 0) for exp in monthly_expenses)
            except Exception as e:
                print(f"Error fetching expenses: {e}")
            
            # Get recent activities count
            try:
                recent_activities_count = (
                    mongo.db.expenses.count_documents({
                        'userId': current_user['_id'],
                        'createdAt': {'$gte': start_of_month}
                    }) +
                    mongo.db.incomes.count_documents({
                        'userId': current_user['_id'],
                        'createdAt': {'$gte': start_of_month}
                    })
                )
                summary_data['recentActivitiesCount'] = recent_activities_count
            except Exception as e:
                print(f"Error counting recent activities: {e}")

            return jsonify({
                'success': True,
                'data': summary_data,
                'message': 'Dashboard summary retrieved successfully'
            })

        except Exception as e:
            print(f"Error in get_dashboard_summary: {e}")
            return jsonify({
                'success': False,
                'message': 'Failed to retrieve dashboard summary',
                'errors': {'general': [str(e)]}
            }), 500

    return summaries_bp