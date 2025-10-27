from flask import Blueprint, request, jsonify, make_response
from datetime import datetime, timedelta
from bson import ObjectId
import csv
import io
from collections import defaultdict
from utils.payment_utils import normalize_sales_type, validate_sales_type

def init_income_blueprint(mongo, token_required, serialize_doc):
    """Initialize the income blueprint with database and auth decorator"""
    income_bp = Blueprint('income', __name__, url_prefix='/income')

    @income_bp.route('', methods=['GET'])
    @token_required
    def get_incomes(current_user):
        try:
            page = int(request.args.get('page', 1))
            limit = int(request.args.get('limit', 10))
            category = request.args.get('category')
            frequency = request.args.get('frequency')
            start_date = request.args.get('start_date')
            end_date = request.args.get('end_date')
            
            # Build query
            query = {'userId': current_user['_id']}
            if category:
                query['category'] = category
            if frequency:
                query['frequency'] = frequency
            if start_date or end_date:
                date_query = {}
                if start_date:
                    date_query['$gte'] = datetime.fromisoformat(start_date.replace('Z', ''))
                if end_date:
                    date_query['$lte'] = datetime.fromisoformat(end_date.replace('Z', ''))
                query['dateReceived'] = date_query
            
            # Get incomes with pagination
            skip = (page - 1) * limit
            incomes = list(mongo.db.incomes.find(query).sort('dateReceived', -1).skip(skip).limit(limit))
            total = mongo.db.incomes.count_documents(query)
            
            # Serialize incomes
            income_list = []
            for income in incomes:
                income_data = serialize_doc(income.copy())
                income_data['dateReceived'] = income_data.get('dateReceived', datetime.utcnow()).isoformat() + 'Z'
                income_data['createdAt'] = income_data.get('createdAt', datetime.utcnow()).isoformat() + 'Z'
                income_data['updatedAt'] = income_data.get('updatedAt', datetime.utcnow()).isoformat() + 'Z' if income_data.get('updatedAt') else None
                # Removed recurring date logic - simplified income tracking
                income_data['nextRecurringDate'] = None
                income_list.append(income_data)
            
            return jsonify({
                'success': True,
                'data': {
                    'incomes': income_list,
                    'pagination': {
                        'page': page,
                        'limit': limit,
                        'total': total,
                        'pages': (total + limit - 1) // limit
                    }
                },
                'message': 'Income records retrieved successfully'
            })
            
        except Exception as e:
            return jsonify({
                'success': False,
                'message': 'Failed to retrieve income records',
                'errors': {'general': [str(e)]}
            }), 500

    @income_bp.route('/<income_id>', methods=['GET'])
    @token_required
    def get_income(current_user, income_id):
        try:
            income = mongo.db.incomes.find_one({
                '_id': ObjectId(income_id),
                'userId': current_user['_id']
            })
            
            if not income:
                return jsonify({
                    'success': False,
                    'message': 'Income record not found'
                }), 404
            
            income_data = serialize_doc(income.copy())
            income_data['dateReceived'] = income_data.get('dateReceived', datetime.utcnow()).isoformat() + 'Z'
            income_data['createdAt'] = income_data.get('createdAt', datetime.utcnow()).isoformat() + 'Z'
            income_data['updatedAt'] = income_data.get('updatedAt', datetime.utcnow()).isoformat() + 'Z' if income_data.get('updatedAt') else None
            # Removed recurring date logic - simplified income tracking
            income_data['nextRecurringDate'] = None
            
            return jsonify({
                'success': True,
                'data': income_data,
                'message': 'Income record retrieved successfully'
            })
            
        except Exception as e:
            return jsonify({
                'success': False,
                'message': 'Failed to retrieve income record',
                'errors': {'general': [str(e)]}
            }), 500

    @income_bp.route('', methods=['POST'])
    @token_required
    def create_income(current_user):
        try:
            data = request.get_json()
            
            # Validation
            errors = {}
            if not data.get('amount') or data.get('amount', 0) <= 0:
                errors['amount'] = ['Valid amount is required']
            if not data.get('source'):
                errors['source'] = ['Income source is required']
            if not data.get('category'):
                errors['category'] = ['Income category is required']
            # salesType is optional but when provided should be either 'cash' or 'credit'
            if data.get('salesType') and not validate_sales_type(data.get('salesType')):
                errors['salesType'] = ['Invalid salesType value']
            if not data.get('frequency'):
                errors['frequency'] = ['Income frequency is required']
            
            if errors:
                return jsonify({
                    'success': False,
                    'message': 'Validation failed',
                    'errors': errors
                }), 400
            
            # NOTE: Credit checking and deduction is handled by frontend executeWithCredits()
            # No need to check/deduct credits here to avoid double deduction
            
            # Simplified: No recurring logic - all incomes are one-time entries
            
            # CRITICAL FIX: Ensure amount is stored exactly as provided, no multipliers
            raw_amount = float(data['amount'])
            
            # Normalize salesType if present
            normalized_sales_type = normalize_sales_type(data.get('salesType')) if data.get('salesType') else None

            income_data = {
                'userId': current_user['_id'],
                'amount': raw_amount,  # Store exact amount, no calculations
                'source': data['source'],
                'description': data.get('description', ''),
                'category': data['category'],
                'salesType': normalized_sales_type,
                'frequency': 'one_time',  # Always one-time now
                'dateReceived': datetime.fromisoformat(data.get('dateReceived', datetime.utcnow().isoformat()).replace('Z', '')),
                'isRecurring': False,  # Always false now
                'nextRecurringDate': None,  # Always null now
                'metadata': data.get('metadata', {}),
                'createdAt': datetime.utcnow(),
                'updatedAt': datetime.utcnow()
            }
            
            # DEBUG: Log the exact amount being stored
            print(f"DEBUG: Creating income record with amount: {raw_amount} for user: {current_user['_id']}")
            
            result = mongo.db.incomes.insert_one(income_data)
            income_id = str(result.inserted_id)
            
            # NOTE: Credit deduction is handled by frontend executeWithCredits()
            # to avoid double deduction
            
            return jsonify({
                'success': True,
                'data': {
                    'id': income_id,
                    'amount': income_data['amount'],
                    'source': income_data['source'],
                    'salesType': income_data.get('salesType'),
                    'category': income_data['category'],
                    'frequency': income_data['frequency']
                },
                'message': 'Income record created successfully'
            })
            
        except Exception as e:
            return jsonify({
                'success': False,
                'message': 'Failed to create income record',
                'errors': {'general': [str(e)]}
            }), 500

    @income_bp.route('/summary', methods=['GET'])
    @token_required
    def get_income_summary(current_user):
        try:
            # Validate database connection
            if mongo is None or mongo.db is None:
                return jsonify({
                    'success': False,
                    'message': 'Database connection error',
                    'errors': {'general': ['Database not available']}
                }), 500
            
            # Get date ranges with error handling
            try:
                now = datetime.utcnow()
                start_of_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
                start_of_last_month = (start_of_month - timedelta(days=1)).replace(day=1)
                start_of_year = now.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
            except Exception as date_error:
                return jsonify({
                    'success': False,
                    'message': 'Date calculation error',
                    'errors': {'general': [str(date_error)]}
                }), 500
            
            # Get income data with error handling - ONLY actual received incomes
            try:
                # CRITICAL FIX: Only get incomes where dateReceived <= now (no future projections)
                incomes = list(mongo.db.incomes.find({
                    'userId': current_user['_id'],
                    'dateReceived': {'$lte': now}  # Only past and present incomes
                }))
            except Exception as db_error:
                return jsonify({
                    'success': False,
                    'message': 'Database query error',
                    'errors': {'general': [str(db_error)]}
                }), 500
            
            # Calculate totals with safe operations - NO RECURRING PROJECTIONS
            try:
                # CRITICAL DEBUG: Log all income data for investigation
                print(f"DEBUG INCOME SUMMARY - User: {current_user['_id']}")
                print(f"DEBUG: Total incomes retrieved: {len(incomes)}")
                print(f"DEBUG: Date ranges - Start of month: {start_of_month}, Start of year: {start_of_year}")
                
                # Debug each income record
                for i, inc in enumerate(incomes):
                    print(f"DEBUG Income {i+1}: ID={inc.get('_id')}, Amount={inc.get('amount')}, DateReceived={inc.get('dateReceived')}, Source={inc.get('source')}")
                
                # FIXED: Simple sum of actual amounts only, no multipliers or projections
                this_month_incomes = [inc for inc in incomes if inc.get('dateReceived') and inc['dateReceived'] >= start_of_month]
                print(f"DEBUG: This month incomes count: {len(this_month_incomes)}")
                for i, inc in enumerate(this_month_incomes):
                    print(f"DEBUG This Month Income {i+1}: Amount={inc.get('amount')}, DateReceived={inc.get('dateReceived')}")
                
                total_this_month = sum(inc.get('amount', 0) for inc in this_month_incomes)
                print(f"DEBUG: CALCULATED total_this_month = {total_this_month}")
                
                last_month_incomes = [inc for inc in incomes if inc.get('dateReceived') and start_of_last_month <= inc['dateReceived'] < start_of_month]
                total_last_month = sum(inc.get('amount', 0) for inc in last_month_incomes)
                print(f"DEBUG: CALCULATED total_last_month = {total_last_month}")
                
                year_incomes = [inc for inc in incomes if inc.get('dateReceived') and inc['dateReceived'] >= start_of_year]
                year_to_date = sum(inc.get('amount', 0) for inc in year_incomes)
                print(f"DEBUG: CALCULATED year_to_date = {year_to_date}")
                
                # FIXED: Calculate average monthly based on actual received amounts only
                twelve_months_ago = now - timedelta(days=365)
                recent_incomes = [inc for inc in incomes 
                                if inc.get('dateReceived') and inc['dateReceived'] >= twelve_months_ago]
                # Calculate actual average based on received amounts, not projected
                total_recent_amount = sum(inc.get('amount', 0) for inc in recent_incomes)
                average_monthly = total_recent_amount / 12 if recent_incomes else 0
                
                # Get recent incomes (last 5)
                recent_incomes_list = sorted([inc for inc in incomes if inc.get('dateReceived')], 
                                           key=lambda x: x['dateReceived'], reverse=True)[:5]
                recent_incomes_data = []
                for income in recent_incomes_list:
                    income_data = serialize_doc(income.copy())
                    income_data['dateReceived'] = income_data.get('dateReceived', datetime.utcnow()).isoformat() + 'Z'
                    recent_incomes_data.append(income_data)
                
                # Top sources with safe operations
                source_totals = defaultdict(float)
                for income in incomes:
                    if income.get('source') and income.get('amount'):
                        source_totals[income['source']] += income['amount']
                top_sources = dict(sorted(source_totals.items(), key=lambda x: x[1], reverse=True)[:5])
                
                # Growth percentage
                growth_percentage = 0
                if total_last_month > 0:
                    growth_percentage = ((total_this_month - total_last_month) / total_last_month) * 100
                
                summary_data = {
                    'total_this_month': total_this_month,
                    'total_last_month': total_last_month,
                    'average_monthly': average_monthly,
                    'year_to_date': year_to_date,
                    'total_records': len(incomes),
                    'recent_incomes': recent_incomes_data,
                    'top_sources': top_sources,
                    'growth_percentage': growth_percentage
                }
                
                # CRITICAL DEBUG: Log the final response
                print(f"DEBUG: FINAL INCOME SUMMARY RESPONSE:")
                print(f"  total_this_month: {total_this_month}")
                print(f"  total_last_month: {total_last_month}")
                print(f"  year_to_date: {year_to_date}")
                print(f"  total_records: {len(incomes)}")
                
                return jsonify({
                    'success': True,
                    'data': summary_data,
                    'message': 'Income summary retrieved successfully'
                })
                
            except Exception as calc_error:
                return jsonify({
                    'success': False,
                    'message': 'Calculation error in income summary',
                    'errors': {'general': [str(calc_error)]}
                }), 500
            
        except Exception as e:
            return jsonify({
                'success': False,
                'message': 'Failed to retrieve income summary',
                'errors': {'general': [str(e)]}
            }), 500

    @income_bp.route('/insights', methods=['GET'])
    @token_required
    def get_income_insights(current_user):
        try:
            # FIXED: Get user's income data for analysis - ONLY actual received incomes
            now = datetime.utcnow()
            incomes = list(mongo.db.incomes.find({
                'userId': current_user['_id'],
                'dateReceived': {'$lte': now}  # Only past and present incomes, no projections
            }))
            
            if not incomes:
                return jsonify({
                    'success': True,
                    'data': {
                        'insights': [],
                        'message': 'No income data available for insights'
                    },
                    'message': 'Income insights retrieved successfully'
                })
            
            # Calculate insights based on ACTUAL received amounts only
            insights = []
            
            # Get current month data
            start_of_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            start_of_last_month = (start_of_month - timedelta(days=1)).replace(day=1)
            
            # Current month income
            current_month_incomes = [inc for inc in incomes if inc['dateReceived'] >= start_of_month]
            current_month_total = sum(inc['amount'] for inc in current_month_incomes)
            
            # Last month income
            last_month_incomes = [inc for inc in incomes if start_of_last_month <= inc['dateReceived'] < start_of_month]
            last_month_total = sum(inc['amount'] for inc in last_month_incomes)
            
            # Growth insight
            if last_month_total > 0:
                growth_rate = ((current_month_total - last_month_total) / last_month_total) * 100
                if growth_rate > 10:
                    insights.append({
                        'type': 'growth',
                        'title': 'Income Growth',
                        'message': f'Your income increased by {growth_rate:.1f}% this month!',
                        'value': growth_rate,
                        'priority': 'high'
                    })
                elif growth_rate < -10:
                    insights.append({
                        'type': 'decline',
                        'title': 'Income Decline',
                        'message': f'Your income decreased by {abs(growth_rate):.1f}% this month.',
                        'value': growth_rate,
                        'priority': 'medium'
                    })
            
            # Top income source
            source_totals = defaultdict(float)
            for income in current_month_incomes:
                source_totals[income['source']] += income['amount']
            
            if source_totals:
                top_source = max(source_totals.items(), key=lambda x: x[1])
                insights.append({
                    'type': 'top_source',
                    'title': 'Top Income Source',
                    'message': f'{top_source[0]} is your highest income source this month',
                    'value': top_source[1],
                    'priority': 'low'
                })
            
            # Removed recurring income insight - simplified tracking
            
            # Average monthly income
            twelve_months_ago = now - timedelta(days=365)
            recent_incomes = [inc for inc in incomes if inc['dateReceived'] >= twelve_months_ago]
            if recent_incomes:
                avg_monthly = sum(inc['amount'] for inc in recent_incomes) / 12
                insights.append({
                    'type': 'average',
                    'title': 'Monthly Average',
                    'message': f'Your average monthly income is ₦{avg_monthly:,.0f}',
                    'value': avg_monthly,
                    'priority': 'low'
                })
            
            # Income consistency insight
            monthly_totals = []
            for i in range(6):  # Last 6 months
                month_start = (now - timedelta(days=30*i)).replace(day=1)
                month_end = (month_start + timedelta(days=32)).replace(day=1) - timedelta(days=1)
                month_incomes = [inc for inc in incomes if month_start <= inc['dateReceived'] <= month_end]
                monthly_totals.append(sum(inc['amount'] for inc in month_incomes))
            
            if len(monthly_totals) >= 3:
                avg_monthly = sum(monthly_totals) / len(monthly_totals)
                variance = sum((x - avg_monthly) ** 2 for x in monthly_totals) / len(monthly_totals)
                std_dev = variance ** 0.5
                consistency_score = max(0, 100 - (std_dev / avg_monthly * 100)) if avg_monthly > 0 else 0
                
                if consistency_score > 80:
                    insights.append({
                        'type': 'consistency',
                        'title': 'Stable Income',
                        'message': f'Your income is very consistent ({consistency_score:.0f}% stability)',
                        'value': consistency_score,
                        'priority': 'medium'
                    })
                elif consistency_score < 50:
                    insights.append({
                        'type': 'volatility',
                        'title': 'Variable Income',
                        'message': 'Your income varies significantly month to month',
                        'value': consistency_score,
                        'priority': 'medium'
                    })
            
            return jsonify({
                'success': True,
                'data': {
                    'insights': insights,
                    'summary': {
                        'current_month_total': current_month_total,
                        'last_month_total': last_month_total,
                        'total_sources': len(source_totals)
                    }
                },
                'message': 'Income insights retrieved successfully'
            })
            
        except Exception as e:
            return jsonify({
                'success': False,
                'message': 'Failed to retrieve income insights',
                'errors': {'general': [str(e)]}
            }), 500

    @income_bp.route('/<income_id>', methods=['PUT'])
    @token_required
    def update_income(current_user, income_id):
        try:
            # Validate income_id
            if not ObjectId.is_valid(income_id):
                return jsonify({
                    'success': False,
                    'message': 'Invalid income ID'
                }), 400

            # Get request data
            data = request.get_json()
            if not data:
                return jsonify({
                    'success': False,
                    'message': 'No data provided'
                }), 400

            # Find existing income record
            existing_income = mongo.db.incomes.find_one({
                '_id': ObjectId(income_id),
                'userId': current_user['_id']
            })

            if not existing_income:
                return jsonify({
                    'success': False,
                    'message': 'Income record not found'
                }), 404

            # Validation
            errors = {}
            if 'amount' in data and (not data.get('amount') or data.get('amount', 0) <= 0):
                errors['amount'] = ['Valid amount is required']
            if 'source' in data and not data.get('source'):
                errors['source'] = ['Income source is required']
            if 'category' in data and not data.get('category'):
                errors['category'] = ['Income category is required']
            if 'frequency' in data and not data.get('frequency'):
                errors['frequency'] = ['Income frequency is required']

            if errors:
                return jsonify({
                    'success': False,
                    'message': 'Validation failed',
                    'errors': errors
                }), 400

            # Prepare update data
            update_data = {'updatedAt': datetime.utcnow()}
            
            # CRITICAL FIX: Update fields if provided - ensure exact amounts
            if 'amount' in data:
                raw_amount = float(data['amount'])
                update_data['amount'] = raw_amount  # Store exact amount, no calculations
                # DEBUG: Log the exact amount being updated
                print(f"DEBUG: Updating income record {income_id} with amount: {raw_amount} for user: {current_user['_id']}")
            if 'source' in data:
                update_data['source'] = data['source']
            if 'description' in data:
                update_data['description'] = data['description']
            if 'category' in data:
                update_data['category'] = data['category']
            if 'frequency' in data:
                update_data['frequency'] = data['frequency']
            if 'dateReceived' in data:
                update_data['dateReceived'] = datetime.fromisoformat(data['dateReceived'].replace('Z', ''))
            if 'metadata' in data:
                update_data['metadata'] = data['metadata']

            # Simplified: Always set to non-recurring
            update_data['isRecurring'] = False
            update_data['nextRecurringDate'] = None
            if 'frequency' in data:
                update_data['frequency'] = 'one_time'  # Always one-time now

            # Update the income record
            result = mongo.db.incomes.update_one(
                {'_id': ObjectId(income_id), 'userId': current_user['_id']},
                {'$set': update_data}
            )

            if result.matched_count == 0:
                return jsonify({
                    'success': False,
                    'message': 'Income record not found'
                }), 404

            # Get updated income record
            updated_income = mongo.db.incomes.find_one({
                '_id': ObjectId(income_id),
                'userId': current_user['_id']
            })

            # Serialize the updated income
            income_data = serialize_doc(updated_income.copy())
            income_data['dateReceived'] = income_data.get('dateReceived', datetime.utcnow()).isoformat() + 'Z'
            income_data['createdAt'] = income_data.get('createdAt', datetime.utcnow()).isoformat() + 'Z'
            income_data['updatedAt'] = income_data.get('updatedAt', datetime.utcnow()).isoformat() + 'Z'
            next_recurring = income_data.get('nextRecurringDate')
            income_data['nextRecurringDate'] = next_recurring.isoformat() + 'Z' if next_recurring else None

            return jsonify({
                'success': True,
                'data': income_data,
                'message': 'Income record updated successfully'
            })

        except Exception as e:
            return jsonify({
                'success': False,
                'message': 'Failed to update income record',
                'errors': {'general': [str(e)]}
            }), 500

    @income_bp.route('/<income_id>', methods=['PATCH'])
    @token_required
    def patch_income(current_user, income_id):
        """Partial update of income record (alias for PUT)"""
        return update_income(current_user, income_id)

    @income_bp.route('/<income_id>', methods=['DELETE'])
    @token_required
    def delete_income(current_user, income_id):
        try:
            # Validate income_id
            if not ObjectId.is_valid(income_id):
                return jsonify({
                    'success': False,
                    'message': 'Invalid income ID'
                }), 400

            # Find and delete the income record
            result = mongo.db.incomes.delete_one({
                '_id': ObjectId(income_id),
                'userId': current_user['_id']
            })

            # Check if a document was deleted
            if result.deleted_count == 0:
                return jsonify({
                    'success': False,
                    'message': 'Income record not found or you do not have permission to delete it'
                }), 404

            return jsonify({
                'success': True,
                'message': 'Income record deleted successfully'
            })
            
        except Exception as e:
            return jsonify({
                'success': False,
                'message': 'Failed to delete income record',
                'errors': {'general': [str(e)]}
            }), 500

    @income_bp.route('/statistics', methods=['GET'])
    @token_required
    def get_income_statistics(current_user):
        try:
            # Validate database connection
            if mongo is None or mongo.db is None:
                return jsonify({
                    'success': False,
                    'message': 'Database connection error',
                    'errors': {'general': ['Database not available']}
                }), 500

            # Get query parameters
            start_date = request.args.get('start_date')
            end_date = request.args.get('end_date')
            group_by = request.args.get('group_by', 'month')  # Default to month

            # Validate group_by parameter
            valid_groups = ['month', 'category', 'source']
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
                query['dateReceived'] = date_query

            # Get income data
            incomes = list(mongo.db.incomes.find(query))

            # Calculate statistics
            statistics = defaultdict(float)
            total = 0
            count = len(incomes)

            if group_by == 'month':
                for income in incomes:
                    if income.get('dateReceived'):
                        month_key = income['dateReceived'].strftime('%Y-%m')
                        statistics[month_key] += income.get('amount', 0)
                        total += income.get('amount', 0)
            elif group_by == 'category':
                for income in incomes:
                    category = income.get('category', 'Unknown')
                    statistics[category] += income.get('amount', 0)
                    total += income.get('amount', 0)
            elif group_by == 'source':
                for income in incomes:
                    source = income.get('source', 'Unknown')
                    statistics[source] += income.get('amount', 0)
                    total += income.get('amount', 0)

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
                'message': 'Income statistics retrieved successfully'
            })

        except Exception as e:
            return jsonify({
                'success': False,
                'message': 'Failed to retrieve income statistics',
                'errors': {'general': [str(e)]}
            }), 500

    return income_bp

