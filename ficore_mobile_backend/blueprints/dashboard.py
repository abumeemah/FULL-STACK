from flask import Blueprint, request, jsonify
from datetime import datetime, timedelta
from bson import ObjectId
from collections import defaultdict

def init_dashboard_blueprint(mongo, token_required, serialize_doc):
    """Initialize the enhanced dashboard blueprint with database and auth decorator"""
    dashboard_bp = Blueprint('dashboard', __name__, url_prefix='/dashboard')

    def get_date_range(period='monthly'):
        """Get date range for analytics"""
        now = datetime.utcnow()
        
        if period == 'weekly':
            start_date = now - timedelta(days=7)
        elif period == 'monthly':
            start_date = now - timedelta(days=30)
        elif period == 'quarterly':
            start_date = now - timedelta(days=90)
        elif period == 'yearly':
            start_date = now - timedelta(days=365)
        else:
            start_date = now - timedelta(days=30)  # Default to monthly
        
        return start_date, now

    def calculate_profit_metrics(user_id, start_date, end_date):
        """Calculate comprehensive profit metrics including COGS"""
        try:
            # Get income data
            incomes = list(mongo.db.incomes.find({
                'userId': user_id,
                'dateReceived': {'$gte': start_date, '$lte': end_date}
            }))
            
            # Get expense data
            expenses = list(mongo.db.expenses.find({
                'userId': user_id,
                'date': {'$gte': start_date, '$lte': end_date}
            }))
            
            # Calculate totals
            total_revenue = sum(income['amount'] for income in incomes)
            total_expenses = sum(expense['amount'] for expense in expenses)
            
            # Separate COGS from other expenses
            cogs_expenses = [exp for exp in expenses if exp.get('category') == 'Cost of Goods Sold']
            other_expenses = [exp for exp in expenses if exp.get('category') != 'Cost of Goods Sold']
            
            total_cogs = sum(exp['amount'] for exp in cogs_expenses)
            total_operating_expenses = sum(exp['amount'] for exp in other_expenses)
            
            # Calculate profit metrics
            gross_profit = total_revenue - total_cogs
            net_profit = total_revenue - total_expenses
            
            # Calculate margins
            gross_margin = (gross_profit / total_revenue * 100) if total_revenue > 0 else 0
            net_margin = (net_profit / total_revenue * 100) if total_revenue > 0 else 0
            
            return {
                'totalRevenue': total_revenue,
                'totalCogs': total_cogs,
                'totalOperatingExpenses': total_operating_expenses,
                'totalExpenses': total_expenses,
                'grossProfit': gross_profit,
                'netProfit': net_profit,
                'grossMargin': round(gross_margin, 2),
                'netMargin': round(net_margin, 2)
            }
            
        except Exception as e:
            print(f"Error calculating profit metrics: {str(e)}")
            return {
                'totalRevenue': 0,
                'totalCogs': 0,
                'totalOperatingExpenses': 0,
                'totalExpenses': 0,
                'grossProfit': 0,
                'netProfit': 0,
                'grossMargin': 0,
                'netMargin': 0
            }

    def get_alerts_and_reminders(user_id):
        """Get system alerts and reminders"""
        alerts = []
        
        try:
            # Low stock alerts
            low_stock_items = list(mongo.db.inventory_items.find({
                'userId': user_id,
                '$expr': {'$lte': ['$currentStock', '$minimumStock']}
            }))
            
            for item in low_stock_items:
                alerts.append({
                    'type': 'low_stock',
                    'severity': 'warning' if item['currentStock'] > 0 else 'critical',
                    'title': 'Low Stock Alert',
                    'message': f"{item['itemName']} is running low (Stock: {item['currentStock']}, Min: {item['minimumStock']})",
                    'itemId': str(item['_id']),
                    'itemName': item['itemName'],
                    'currentStock': item['currentStock'],
                    'minimumStock': item['minimumStock']
                })
            
            # Overdue debtors
            overdue_debtors = list(mongo.db.debtors.find({
                'userId': user_id,
                'status': 'overdue',
                'remainingDebt': {'$gt': 0}
            }))
            
            for debtor in overdue_debtors:
                alerts.append({
                    'type': 'overdue_debt',
                    'severity': 'high' if debtor.get('overdueDays', 0) > 30 else 'medium',
                    'title': 'Overdue Payment',
                    'message': f"{debtor['customerName']} payment is {debtor.get('overdueDays', 0)} days overdue (₦{debtor['remainingDebt']:,.2f})",
                    'debtorId': str(debtor['_id']),
                    'customerName': debtor['customerName'],
                    'remainingDebt': debtor['remainingDebt'],
                    'overdueDays': debtor.get('overdueDays', 0)
                })
            
            # Overdue creditors (payments we owe)
            overdue_creditors = list(mongo.db.creditors.find({
                'userId': user_id,
                'status': 'overdue',
                'remainingOwed': {'$gt': 0}
            }))
            
            for creditor in overdue_creditors:
                alerts.append({
                    'type': 'overdue_payment',
                    'severity': 'high' if creditor.get('overdueDays', 0) > 30 else 'medium',
                    'title': 'Payment Due',
                    'message': f"Payment to {creditor['vendorName']} is {creditor.get('overdueDays', 0)} days overdue (₦{creditor['remainingOwed']:,.2f})",
                    'creditorId': str(creditor['_id']),
                    'vendorName': creditor['vendorName'],
                    'remainingOwed': creditor['remainingOwed'],
                    'overdueDays': creditor.get('overdueDays', 0)
                })
            
            # Expiring inventory
            thirty_days_from_now = datetime.utcnow() + timedelta(days=30)
            expiring_items = list(mongo.db.inventory_items.find({
                'userId': user_id,
                'expiryDate': {
                    '$gte': datetime.utcnow(),
                    '$lte': thirty_days_from_now
                },
                'currentStock': {'$gt': 0}
            }))
            
            for item in expiring_items:
                days_to_expiry = (item['expiryDate'] - datetime.utcnow()).days
                alerts.append({
                    'type': 'expiring_inventory',
                    'severity': 'warning' if days_to_expiry > 7 else 'high',
                    'title': 'Expiring Inventory',
                    'message': f"{item['itemName']} expires in {days_to_expiry} days (Stock: {item['currentStock']})",
                    'itemId': str(item['_id']),
                    'itemName': item['itemName'],
                    'expiryDate': item['expiryDate'].isoformat() + 'Z',
                    'daysToExpiry': days_to_expiry,
                    'currentStock': item['currentStock']
                })
            
            # Sort alerts by severity
            severity_order = {'critical': 0, 'high': 1, 'medium': 2, 'warning': 3, 'info': 4}
            alerts.sort(key=lambda x: severity_order.get(x['severity'], 5))
            
            return alerts
            
        except Exception as e:
            print(f"Error getting alerts: {str(e)}")
            return []

    def get_recent_activity(user_id, limit=20):
        """Get recent activity across all modules"""
        activities = []
        
        try:
            # Recent income transactions
            recent_incomes = list(mongo.db.incomes.find({
                'userId': user_id
            }).sort('dateReceived', -1).limit(limit // 4))
            
            for income in recent_incomes:
                activities.append({
                    'type': 'income',
                    'title': f'Income: {income["source"]}',
                    'description': income.get('description', ''),
                    'amount': income['amount'],
                    'date': income['dateReceived'],
                    'category': income.get('category', ''),
                    'id': str(income['_id'])
                })
            
            # Recent expense transactions
            recent_expenses = list(mongo.db.expenses.find({
                'userId': user_id
            }).sort('date', -1).limit(limit // 4))
            
            for expense in recent_expenses:
                activities.append({
                    'type': 'expense',
                    'title': f'Expense: {expense.get("title", expense["description"])}',
                    'description': expense['description'],
                    'amount': expense['amount'],
                    'date': expense['date'],
                    'category': expense.get('category', ''),
                    'id': str(expense['_id'])
                })
            
            # Recent debtor transactions
            recent_debtor_transactions = list(mongo.db.debtor_transactions.find({
                'userId': user_id
            }).sort('transactionDate', -1).limit(limit // 4))
            
            # Get debtor names
            debtor_ids = [trans['debtorId'] for trans in recent_debtor_transactions]
            debtors = {debtor['_id']: debtor['customerName'] for debtor in mongo.db.debtors.find({'_id': {'$in': debtor_ids}})}
            
            for transaction in recent_debtor_transactions:
                customer_name = debtors.get(transaction['debtorId'], 'Unknown Customer')
                activities.append({
                    'type': 'debtor_transaction',
                    'title': f'{transaction["type"].title()}: {customer_name}',
                    'description': transaction['description'],
                    'amount': transaction['amount'],
                    'date': transaction['transactionDate'],
                    'transactionType': transaction['type'],
                    'customerName': customer_name,
                    'id': str(transaction['_id'])
                })
            
            # Recent inventory movements
            recent_movements = list(mongo.db.inventory_movements.find({
                'userId': user_id
            }).sort('movementDate', -1).limit(limit // 4))
            
            # Get item names
            item_ids = [movement['itemId'] for movement in recent_movements]
            items = {item['_id']: item['itemName'] for item in mongo.db.inventory_items.find({'_id': {'$in': item_ids}})}
            
            for movement in recent_movements:
                item_name = items.get(movement['itemId'], 'Unknown Item')
                activities.append({
                    'type': 'inventory_movement',
                    'title': f'Stock {movement["movementType"].title()}: {item_name}',
                    'description': f'{movement["reason"]} - {movement["quantity"]} units',
                    'amount': movement.get('totalCost', 0),
                    'date': movement['movementDate'],
                    'movementType': movement['movementType'],
                    'quantity': movement['quantity'],
                    'itemName': item_name,
                    'id': str(movement['_id'])
                })
            
            # Sort all activities by date (most recent first)
            activities.sort(key=lambda x: x['date'], reverse=True)
            
            # Format dates and limit results
            for activity in activities[:limit]:
                activity['date'] = activity['date'].isoformat() + 'Z'
            
            return activities[:limit]
            
        except Exception as e:
            print(f"Error getting recent activity: {str(e)}")
            return []

    # ==================== DASHBOARD ENDPOINTS ====================

    @dashboard_bp.route('/overview', methods=['GET'])
    @token_required
    def get_overview(current_user):
        """Get comprehensive dashboard overview"""
        try:
            period = request.args.get('period', 'monthly')
            start_date, end_date = get_date_range(period)
            
            # Get profit metrics
            profit_metrics = calculate_profit_metrics(current_user['_id'], start_date, end_date)
            
            # Get module summaries
            # Income summary
            total_income = mongo.db.incomes.aggregate([
                {'$match': {'userId': current_user['_id']}},
                {'$group': {'_id': None, 'total': {'$sum': '$amount'}}}
            ])
            total_income = list(total_income)
            total_income_amount = total_income[0]['total'] if total_income else 0
            
            # Expense summary
            total_expenses = mongo.db.expenses.aggregate([
                {'$match': {'userId': current_user['_id']}},
                {'$group': {'_id': None, 'total': {'$sum': '$amount'}}}
            ])
            total_expenses = list(total_expenses)
            total_expenses_amount = total_expenses[0]['total'] if total_expenses else 0
            
            # Debtors summary
            debtors_summary = mongo.db.debtors.aggregate([
                {'$match': {'userId': current_user['_id']}},
                {'$group': {
                    '_id': None,
                    'totalCustomers': {'$sum': 1},
                    'totalDebt': {'$sum': '$totalDebt'},
                    'totalOutstanding': {'$sum': '$remainingDebt'},
                    'overdueCustomers': {
                        '$sum': {'$cond': [{'$eq': ['$status', 'overdue']}, 1, 0]}
                    }
                }}
            ])
            debtors_summary = list(debtors_summary)
            debtors_data = debtors_summary[0] if debtors_summary else {
                'totalCustomers': 0, 'totalDebt': 0, 'totalOutstanding': 0, 'overdueCustomers': 0
            }
            
            # Creditors summary
            creditors_summary = mongo.db.creditors.aggregate([
                {'$match': {'userId': current_user['_id']}},
                {'$group': {
                    '_id': None,
                    'totalVendors': {'$sum': 1},
                    'totalOwed': {'$sum': '$totalOwed'},
                    'totalOutstanding': {'$sum': '$remainingOwed'},
                    'overdueVendors': {
                        '$sum': {'$cond': [{'$eq': ['$status', 'overdue']}, 1, 0]}
                    }
                }}
            ])
            creditors_summary = list(creditors_summary)
            creditors_data = creditors_summary[0] if creditors_summary else {
                'totalVendors': 0, 'totalOwed': 0, 'totalOutstanding': 0, 'overdueVendors': 0
            }
            
            # Inventory summary
            inventory_summary = mongo.db.inventory_items.aggregate([
                {'$match': {'userId': current_user['_id']}},
                {'$group': {
                    '_id': None,
                    'totalItems': {'$sum': 1},
                    'totalValue': {'$sum': {'$multiply': ['$currentStock', '$costPrice']}},
                    'lowStockItems': {
                        '$sum': {'$cond': [{'$lte': ['$currentStock', '$minimumStock']}, 1, 0]}
                    },
                    'outOfStockItems': {
                        '$sum': {'$cond': [{'$eq': ['$currentStock', 0]}, 1, 0]}
                    }
                }}
            ])
            inventory_summary = list(inventory_summary)
            inventory_data = inventory_summary[0] if inventory_summary else {
                'totalItems': 0, 'totalValue': 0, 'lowStockItems': 0, 'outOfStockItems': 0
            }
            
            # Get alerts
            alerts = get_alerts_and_reminders(current_user['_id'])
            
            # Get recent activity
            recent_activity = get_recent_activity(current_user['_id'], 10)
            
            # Calculate key performance indicators
            kpis = {
                'totalRevenue': profit_metrics['totalRevenue'],
                'totalProfit': profit_metrics['netProfit'],
                'profitMargin': profit_metrics['netMargin'],
                'totalCustomers': debtors_data['totalCustomers'],
                'totalVendors': creditors_data['totalVendors'],
                'totalInventoryValue': inventory_data['totalValue'],
                'outstandingReceivables': debtors_data['totalOutstanding'],
                'outstandingPayables': creditors_data['totalOutstanding'],
                'alertsCount': len(alerts),
                'criticalAlertsCount': len([a for a in alerts if a['severity'] in ['critical', 'high']])
            }
            
            overview_data = {
                'period': period,
                'dateRange': {
                    'startDate': start_date.isoformat() + 'Z',
                    'endDate': end_date.isoformat() + 'Z'
                },
                'kpis': kpis,
                'profitMetrics': profit_metrics,
                'moduleSummaries': {
                    'income': {
                        'totalAmount': total_income_amount,
                        'periodAmount': profit_metrics['totalRevenue']
                    },
                    'expenses': {
                        'totalAmount': total_expenses_amount,
                        'periodAmount': profit_metrics['totalExpenses']
                    },
                    'debtors': debtors_data,
                    'creditors': creditors_data,
                    'inventory': inventory_data
                },
                'alerts': alerts[:5],  # Top 5 alerts
                'recentActivity': recent_activity
            }
            
            return jsonify({
                'success': True,
                'data': overview_data,
                'message': 'Dashboard overview retrieved successfully'
            })
            
        except Exception as e:
            return jsonify({
                'success': False,
                'message': 'Failed to retrieve dashboard overview',
                'errors': {'general': [str(e)]}
            }), 500

    @dashboard_bp.route('/alerts', methods=['GET'])
    @token_required
    def get_alerts(current_user):
        """Get all system alerts and notifications"""
        try:
            alerts = get_alerts_and_reminders(current_user['_id'])
            
            # Group alerts by type
            alerts_by_type = defaultdict(list)
            for alert in alerts:
                alerts_by_type[alert['type']].append(alert)
            
            # Count alerts by severity
            severity_counts = defaultdict(int)
            for alert in alerts:
                severity_counts[alert['severity']] += 1
            
            alerts_data = {
                'totalAlerts': len(alerts),
                'severityCounts': dict(severity_counts),
                'alertsByType': dict(alerts_by_type),
                'allAlerts': alerts
            }
            
            return jsonify({
                'success': True,
                'data': alerts_data,
                'message': 'Alerts retrieved successfully'
            })
            
        except Exception as e:
            return jsonify({
                'success': False,
                'message': 'Failed to retrieve alerts',
                'errors': {'general': [str(e)]}
            }), 500

    @dashboard_bp.route('/recent-activity', methods=['GET'])
    @token_required
    def get_recent_activity_endpoint(current_user):
        """Get recent activity feed"""
        try:
            limit = int(request.args.get('limit', 20))
            activity_type = request.args.get('type')  # Filter by activity type
            
            activities = get_recent_activity(current_user['_id'], limit * 2)  # Get more to filter
            
            # Filter by type if specified
            if activity_type:
                activities = [a for a in activities if a['type'] == activity_type]
            
            # Limit results
            activities = activities[:limit]
            
            return jsonify({
                'success': True,
                'data': activities,
                'message': 'Recent activity retrieved successfully'
            })
            
        except Exception as e:
            return jsonify({
                'success': False,
                'message': 'Failed to retrieve recent activity',
                'errors': {'general': [str(e)]}
            }), 500

    @dashboard_bp.route('/reminders', methods=['GET'])
    @token_required
    def get_reminders(current_user):
        """Get payment reminders and due dates"""
        try:
            now = datetime.utcnow()
            next_30_days = now + timedelta(days=30)
            
            reminders = []
            
            # Debtor payment reminders
            upcoming_debtor_payments = list(mongo.db.debtors.find({
                'userId': current_user['_id'],
                'nextPaymentDue': {
                    '$gte': now,
                    '$lte': next_30_days
                },
                'remainingDebt': {'$gt': 0}
            }).sort('nextPaymentDue', 1))
            
            for debtor in upcoming_debtor_payments:
                days_until_due = (debtor['nextPaymentDue'] - now).days
                reminders.append({
                    'type': 'debtor_payment_due',
                    'title': f'Payment Due: {debtor["customerName"]}',
                    'description': f'Payment of ₦{debtor["remainingDebt"]:,.2f} due in {days_until_due} days',
                    'dueDate': debtor['nextPaymentDue'].isoformat() + 'Z',
                    'daysUntilDue': days_until_due,
                    'amount': debtor['remainingDebt'],
                    'customerName': debtor['customerName'],
                    'debtorId': str(debtor['_id']),
                    'priority': 'high' if days_until_due <= 7 else 'medium'
                })
            
            # Creditor payment reminders
            upcoming_creditor_payments = list(mongo.db.creditors.find({
                'userId': current_user['_id'],
                'nextPaymentDue': {
                    '$gte': now,
                    '$lte': next_30_days
                },
                'remainingOwed': {'$gt': 0}
            }).sort('nextPaymentDue', 1))
            
            for creditor in upcoming_creditor_payments:
                days_until_due = (creditor['nextPaymentDue'] - now).days
                reminders.append({
                    'type': 'creditor_payment_due',
                    'title': f'Payment Due: {creditor["vendorName"]}',
                    'description': f'Payment of ₦{creditor["remainingOwed"]:,.2f} due in {days_until_due} days',
                    'dueDate': creditor['nextPaymentDue'].isoformat() + 'Z',
                    'daysUntilDue': days_until_due,
                    'amount': creditor['remainingOwed'],
                    'vendorName': creditor['vendorName'],
                    'creditorId': str(creditor['_id']),
                    'priority': 'high' if days_until_due <= 7 else 'medium'
                })
            
            # Sort by due date
            reminders.sort(key=lambda x: x['daysUntilDue'])
            
            return jsonify({
                'success': True,
                'data': reminders,
                'message': 'Reminders retrieved successfully'
            })
            
        except Exception as e:
            return jsonify({
                'success': False,
                'message': 'Failed to retrieve reminders',
                'errors': {'general': [str(e)]}
            }), 500

    @dashboard_bp.route('/profit-analysis', methods=['GET'])
    @token_required
    def get_profit_analysis(current_user):
        """Get detailed profit analysis with trends"""
        try:
            period = request.args.get('period', 'monthly')
            
            # Get data for different time periods for comparison
            periods = {
                'current': get_date_range(period),
                'previous': None
            }
            
            # Calculate previous period
            current_start, current_end = periods['current']
            period_length = current_end - current_start
            previous_end = current_start
            previous_start = previous_end - period_length
            periods['previous'] = (previous_start, previous_end)
            
            analysis_data = {}
            
            for period_name, (start_date, end_date) in periods.items():
                metrics = calculate_profit_metrics(current_user['_id'], start_date, end_date)
                analysis_data[period_name] = {
                    'dateRange': {
                        'startDate': start_date.isoformat() + 'Z',
                        'endDate': end_date.isoformat() + 'Z'
                    },
                    'metrics': metrics
                }
            
            # Calculate growth rates
            current_metrics = analysis_data['current']['metrics']
            previous_metrics = analysis_data['previous']['metrics']
            
            growth_rates = {}
            for key in ['totalRevenue', 'grossProfit', 'netProfit']:
                current_value = current_metrics[key]
                previous_value = previous_metrics[key]
                
                if previous_value != 0:
                    growth_rate = ((current_value - previous_value) / previous_value) * 100
                else:
                    growth_rate = 100 if current_value > 0 else 0
                
                growth_rates[key] = round(growth_rate, 2)
            
            # Get monthly trends for the last 12 months
            monthly_trends = []
            for i in range(12):
                month_end = datetime.utcnow().replace(day=1) - timedelta(days=i*30)
                month_start = month_end - timedelta(days=30)
                
                month_metrics = calculate_profit_metrics(current_user['_id'], month_start, month_end)
                monthly_trends.append({
                    'month': month_start.strftime('%Y-%m'),
                    'revenue': month_metrics['totalRevenue'],
                    'grossProfit': month_metrics['grossProfit'],
                    'netProfit': month_metrics['netProfit'],
                    'grossMargin': month_metrics['grossMargin'],
                    'netMargin': month_metrics['netMargin']
                })
            
            monthly_trends.reverse()  # Oldest to newest
            
            profit_analysis = {
                'currentPeriod': analysis_data['current'],
                'previousPeriod': analysis_data['previous'],
                'growthRates': growth_rates,
                'monthlyTrends': monthly_trends,
                'insights': {
                    'revenueGrowth': growth_rates['totalRevenue'],
                    'profitabilityTrend': 'improving' if growth_rates['netProfit'] > 0 else 'declining',
                    'marginTrend': 'improving' if current_metrics['netMargin'] > previous_metrics['netMargin'] else 'declining'
                }
            }
            
            return jsonify({
                'success': True,
                'data': profit_analysis,
                'message': 'Profit analysis retrieved successfully'
            })
            
        except Exception as e:
            return jsonify({
                'success': False,
                'message': 'Failed to retrieve profit analysis',
                'errors': {'general': [str(e)]}
            }), 500

    # ==================== MODULE-SPECIFIC SUMMARY ENDPOINTS ====================

    @dashboard_bp.route('/income-summary', methods=['GET'])
    @token_required
    def get_income_summary(current_user):
        """Get income module summary for dashboard"""
        try:
            period = request.args.get('period', 'monthly')
            start_date, end_date = get_date_range(period)
            
            # Get income data for period
            incomes = list(mongo.db.incomes.find({
                'userId': current_user['_id'],
                'dateReceived': {'$gte': start_date, '$lte': end_date}
            }))
            
            # Calculate summary
            total_income = sum(income['amount'] for income in incomes)
            income_count = len(incomes)
            
            # Group by source
            income_by_source = defaultdict(float)
            for income in incomes:
                income_by_source[income['source']] += income['amount']
            
            # Group by category
            income_by_category = defaultdict(float)
            for income in incomes:
                income_by_category[income.get('category', 'Other')] += income['amount']
            
            # Recent incomes
            recent_incomes = sorted(incomes, key=lambda x: x['dateReceived'], reverse=True)[:5]
            recent_income_data = []
            for income in recent_incomes:
                income_data = serialize_doc(income.copy())
                income_data['dateReceived'] = income_data.get('dateReceived', datetime.utcnow()).isoformat() + 'Z'
                recent_income_data.append(income_data)
            
            summary_data = {
                'period': period,
                'totalIncome': total_income,
                'incomeCount': income_count,
                'averageIncome': total_income / income_count if income_count > 0 else 0,
                'incomeBySource': dict(income_by_source),
                'incomeByCategory': dict(income_by_category),
                'recentIncomes': recent_income_data
            }
            
            return jsonify({
                'success': True,
                'data': summary_data,
                'message': 'Income summary retrieved successfully'
            })
            
        except Exception as e:
            return jsonify({
                'success': False,
                'message': 'Failed to retrieve income summary',
                'errors': {'general': [str(e)]}
            }), 500

    return dashboard_bp