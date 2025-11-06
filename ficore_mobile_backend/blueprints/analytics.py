from flask import Blueprint, request, jsonify
from datetime import datetime, timedelta
from bson import ObjectId
from typing import Dict, Any, List
import calendar
import logging

logger = logging.getLogger(__name__)

def init_analytics_blueprint(mongo, token_required, serialize_doc):
    """Initialize the analytics blueprint with comprehensive business metrics"""
    analytics_bp = Blueprint('analytics', __name__, url_prefix='/api/analytics')
    
    class AnalyticsService:
        """Service class for comprehensive business analytics"""
        
        def __init__(self, mongo_db):
            self.db = mongo_db
        
        def get_date_range(self, period: str) -> tuple:
            """Get start and end dates for the specified period"""
            now = datetime.utcnow()
            
            if period == '7d':
                start_date = now - timedelta(days=7)
            elif period == '30d':
                start_date = now - timedelta(days=30)
            elif period == '90d':
                start_date = now - timedelta(days=90)
            elif period == '1y':
                start_date = now - timedelta(days=365)
            else:
                start_date = now - timedelta(days=30)  # Default to 30 days
            
            return start_date, now
        
        def get_previous_period_range(self, period: str) -> tuple:
            """Get the previous period for comparison calculations"""
            current_start, current_end = self.get_date_range(period)
            period_length = current_end - current_start
            
            previous_end = current_start
            previous_start = previous_end - period_length
            
            return previous_start, previous_end
        
        def calculate_key_metrics(self, user_id: ObjectId, period: str) -> Dict[str, Any]:
            """Calculate key business metrics for the specified period"""
            try:
                current_start, current_end = self.get_date_range(period)
                previous_start, previous_end = self.get_previous_period_range(period)
                
                # Current period data
                current_metrics = self._get_period_metrics(user_id, current_start, current_end)
                
                # Previous period data for comparison
                previous_metrics = self._get_period_metrics(user_id, previous_start, previous_end)
                
                # Calculate percentage changes
                revenue_growth = self._calculate_percentage_change(
                    current_metrics['total_revenue'], 
                    previous_metrics['total_revenue']
                )
                
                profit_growth = self._calculate_percentage_change(
                    current_metrics['net_profit'], 
                    previous_metrics['net_profit']
                )
                
                customer_growth = self._calculate_percentage_change(
                    current_metrics['active_customers'], 
                    previous_metrics['active_customers']
                )
                
                order_value_growth = self._calculate_percentage_change(
                    current_metrics['avg_order_value'], 
                    previous_metrics['avg_order_value']
                )
                
                return {
                    'totalRevenue': current_metrics['total_revenue'],
                    'netProfit': current_metrics['net_profit'],
                    'activeCustomers': current_metrics['active_customers'],
                    'avgOrderValue': current_metrics['avg_order_value'],
                    'revenueGrowth': revenue_growth,
                    'profitGrowth': profit_growth,
                    'customerGrowth': customer_growth,
                    'orderValueGrowth': order_value_growth,
                    'period': period,
                    'periodStart': current_start.isoformat() + 'Z',
                    'periodEnd': current_end.isoformat() + 'Z',
                    'comparisonPeriod': f"vs. previous {period}",
                    'lastCalculated': datetime.utcnow().isoformat() + 'Z'
                }
                
            except Exception as e:
                logger.error(f"Error calculating key metrics: {str(e)}")
                return self._get_empty_metrics(period)
        
        def _get_period_metrics(self, user_id: ObjectId, start_date: datetime, end_date: datetime) -> Dict[str, Any]:
            """Get metrics for a specific period"""
            # Income aggregation
            income_pipeline = [
                {
                    '$match': {
                        'userId': user_id,
                        'dateReceived': {'$gte': start_date, '$lte': end_date}
                    }
                },
                {
                    '$group': {
                        '_id': None,
                        'totalRevenue': {'$sum': '$amount'},
                        'transactionCount': {'$sum': 1},
                        'avgAmount': {'$avg': '$amount'}
                    }
                }
            ]
            
            # Expense aggregation
            expense_pipeline = [
                {
                    '$match': {
                        'userId': user_id,
                        'date': {'$gte': start_date, '$lte': end_date}
                    }
                },
                {
                    '$group': {
                        '_id': None,
                        'totalExpenses': {'$sum': '$amount'},
                        'transactionCount': {'$sum': 1}
                    }
                }
            ]
            
            # Execute aggregations
            income_result = list(self.db.incomes.aggregate(income_pipeline))
            expense_result = list(self.db.expenses.aggregate(expense_pipeline))
            
            # Extract results
            income_data = income_result[0] if income_result else {}
            expense_data = expense_result[0] if expense_result else {}
            
            total_revenue = income_data.get('totalRevenue', 0.0)
            total_expenses = expense_data.get('totalExpenses', 0.0)
            income_transactions = income_data.get('transactionCount', 0)
            avg_transaction_amount = income_data.get('avgAmount', 0.0)
            
            # Calculate derived metrics
            net_profit = total_revenue - total_expenses
            
            # Estimate active customers (unique income sources or transactions/average frequency)
            active_customers = max(1, income_transactions // 3) if income_transactions > 0 else 0
            
            # Average order value
            avg_order_value = avg_transaction_amount if avg_transaction_amount > 0 else 0.0
            
            return {
                'total_revenue': total_revenue,
                'total_expenses': total_expenses,
                'net_profit': net_profit,
                'active_customers': active_customers,
                'avg_order_value': avg_order_value,
                'income_transactions': income_transactions
            }
        
        def _calculate_percentage_change(self, current: float, previous: float) -> float:
            """Calculate percentage change between two values"""
            if previous == 0:
                return 100.0 if current > 0 else 0.0
            
            return ((current - previous) / abs(previous)) * 100
        
        def _get_empty_metrics(self, period: str) -> Dict[str, Any]:
            """Return empty metrics structure for error cases"""
            return {
                'totalRevenue': 0.0,
                'netProfit': 0.0,
                'activeCustomers': 0,
                'avgOrderValue': 0.0,
                'revenueGrowth': 0.0,
                'profitGrowth': 0.0,
                'customerGrowth': 0.0,
                'orderValueGrowth': 0.0,
                'period': period,
                'periodStart': datetime.utcnow().isoformat() + 'Z',
                'periodEnd': datetime.utcnow().isoformat() + 'Z',
                'comparisonPeriod': f"vs. previous {period}",
                'lastCalculated': datetime.utcnow().isoformat() + 'Z'
            }
        
        def get_trend_data(self, user_id: ObjectId, period: str) -> Dict[str, Any]:
            """Get trend data for sparkline charts"""
            try:
                current_start, current_end = self.get_date_range(period)
                
                # Determine interval based on period
                if period == '7d':
                    interval_days = 1  # Daily data points
                    data_points = 7
                elif period == '30d':
                    interval_days = 3  # Every 3 days
                    data_points = 10
                elif period == '90d':
                    interval_days = 9  # Every 9 days
                    data_points = 10
                else:  # 1y
                    interval_days = 30  # Monthly data points
                    data_points = 12
                
                trend_data = []
                
                for i in range(data_points):
                    point_end = current_end - timedelta(days=i * interval_days)
                    point_start = point_end - timedelta(days=interval_days)
                    
                    metrics = self._get_period_metrics(user_id, point_start, point_end)
                    
                    trend_data.append({
                        'date': point_end.strftime('%Y-%m-%d'),
                        'revenue': metrics['total_revenue'],
                        'profit': metrics['net_profit'],
                        'customers': metrics['active_customers'],
                        'orderValue': metrics['avg_order_value']
                    })
                
                # Reverse to get chronological order
                trend_data.reverse()
                
                return {
                    'period': period,
                    'dataPoints': trend_data,
                    'intervalDays': interval_days,
                    'generatedAt': datetime.utcnow().isoformat() + 'Z'
                }
                
            except Exception as e:
                logger.error(f"Error getting trend data: {str(e)}")
                return {
                    'period': period,
                    'dataPoints': [],
                    'intervalDays': 1,
                    'generatedAt': datetime.utcnow().isoformat() + 'Z'
                }
        
        def get_business_health_score(self, user_id: ObjectId) -> Dict[str, Any]:
            """Calculate business health score based on multiple factors"""
            try:
                # Get 30-day metrics for health calculation
                current_start, current_end = self.get_date_range('30d')
                metrics = self._get_period_metrics(user_id, current_start, current_end)
                
                # Health factors (0-100 each)
                revenue_health = min(100, (metrics['total_revenue'] / 10000) * 100)  # Scale based on ₦10k target
                profit_health = 100 if metrics['net_profit'] > 0 else max(0, 50 + (metrics['net_profit'] / 1000) * 50)
                activity_health = min(100, (metrics['income_transactions'] / 10) * 100)  # Scale based on 10 transactions
                
                # Overall health score (weighted average)
                overall_score = (revenue_health * 0.4 + profit_health * 0.4 + activity_health * 0.2)
                
                # Determine health status
                if overall_score >= 80:
                    status = 'excellent'
                    status_color = '#4CAF50'
                elif overall_score >= 60:
                    status = 'good'
                    status_color = '#8BC34A'
                elif overall_score >= 40:
                    status = 'fair'
                    status_color = '#FF9800'
                else:
                    status = 'needs_attention'
                    status_color = '#F44336'
                
                return {
                    'overallScore': round(overall_score, 1),
                    'status': status,
                    'statusColor': status_color,
                    'factors': {
                        'revenueHealth': round(revenue_health, 1),
                        'profitHealth': round(profit_health, 1),
                        'activityHealth': round(activity_health, 1)
                    },
                    'recommendations': self._get_health_recommendations(overall_score, metrics),
                    'calculatedAt': datetime.utcnow().isoformat() + 'Z'
                }
                
            except Exception as e:
                logger.error(f"Error calculating business health score: {str(e)}")
                return {
                    'overallScore': 0.0,
                    'status': 'unknown',
                    'statusColor': '#9E9E9E',
                    'factors': {
                        'revenueHealth': 0.0,
                        'profitHealth': 0.0,
                        'activityHealth': 0.0
                    },
                    'recommendations': [],
                    'calculatedAt': datetime.utcnow().isoformat() + 'Z'
                }
        
        def _get_health_recommendations(self, score: float, metrics: Dict[str, Any]) -> List[str]:
            """Generate health recommendations based on score and metrics"""
            recommendations = []
            
            if score < 40:
                recommendations.append("Focus on increasing revenue through marketing or new products")
                if metrics['net_profit'] <= 0:
                    recommendations.append("Review and reduce expenses to improve profitability")
            elif score < 60:
                recommendations.append("Consider diversifying income sources")
                recommendations.append("Monitor cash flow closely")
            elif score < 80:
                recommendations.append("Explore opportunities for growth")
                recommendations.append("Optimize operational efficiency")
            else:
                recommendations.append("Maintain current performance")
                recommendations.append("Consider expansion opportunities")
            
            return recommendations
    
    # Initialize service
    analytics_service = AnalyticsService(mongo.db)
    
    @analytics_bp.route('/key-metrics', methods=['GET'])
    @token_required
    def get_key_metrics(current_user):
        """
        GET /api/analytics/key-metrics?period=7d|30d|90d|1y
        
        Returns key business metrics with comparison data
        """
        try:
            period = request.args.get('period', '30d')
            
            # Validate period
            valid_periods = ['7d', '30d', '90d', '1y']
            if period not in valid_periods:
                return jsonify({
                    'success': False,
                    'message': 'Invalid period parameter',
                    'errors': {'validation': [f'Period must be one of: {", ".join(valid_periods)}']}
                }), 400
            
            metrics = analytics_service.calculate_key_metrics(current_user['_id'], period)
            
            return jsonify({
                'success': True,
                'data': metrics,
                'message': 'Key metrics retrieved successfully'
            })
            
        except Exception as e:
            logger.error(f"Error in get_key_metrics: {str(e)}")
            return jsonify({
                'success': False,
                'message': 'Failed to retrieve key metrics',
                'errors': {'general': [str(e)]}
            }), 500
    
    @analytics_bp.route('/trends', methods=['GET'])
    @token_required
    def get_trend_data(current_user):
        """
        GET /api/analytics/trends?period=7d|30d|90d|1y
        
        Returns trend data for sparkline charts
        """
        try:
            period = request.args.get('period', '30d')
            
            # Validate period
            valid_periods = ['7d', '30d', '90d', '1y']
            if period not in valid_periods:
                return jsonify({
                    'success': False,
                    'message': 'Invalid period parameter',
                    'errors': {'validation': [f'Period must be one of: {", ".join(valid_periods)}']}
                }), 400
            
            trend_data = analytics_service.get_trend_data(current_user['_id'], period)
            
            return jsonify({
                'success': True,
                'data': trend_data,
                'message': 'Trend data retrieved successfully'
            })
            
        except Exception as e:
            logger.error(f"Error in get_trend_data: {str(e)}")
            return jsonify({
                'success': False,
                'message': 'Failed to retrieve trend data',
                'errors': {'general': [str(e)]}
            }), 500
    
    @analytics_bp.route('/business-health', methods=['GET'])
    @token_required
    def get_business_health(current_user):
        """
        GET /api/analytics/business-health
        
        Returns business health score and recommendations
        """
        try:
            health_data = analytics_service.get_business_health_score(current_user['_id'])
            
            return jsonify({
                'success': True,
                'data': health_data,
                'message': 'Business health score retrieved successfully'
            })
            
        except Exception as e:
            logger.error(f"Error in get_business_health: {str(e)}")
            return jsonify({
                'success': False,
                'message': 'Failed to retrieve business health score',
                'errors': {'general': [str(e)]}
            }), 500
    
    @analytics_bp.route('/refresh', methods=['POST'])
    @token_required
    def refresh_analytics(current_user):
        """
        POST /api/analytics/refresh
        
        Forces refresh of all analytics data
        """
        try:
            user_id = current_user['_id']
            
            # Get fresh data for all periods
            periods = ['7d', '30d', '90d', '1y']
            refreshed_data = {}
            
            for period in periods:
                refreshed_data[period] = {
                    'keyMetrics': analytics_service.calculate_key_metrics(user_id, period),
                    'trends': analytics_service.get_trend_data(user_id, period)
                }
            
            # Get business health
            refreshed_data['businessHealth'] = analytics_service.get_business_health_score(user_id)
            
            return jsonify({
                'success': True,
                'data': {
                    'analytics': refreshed_data,
                    'refreshedAt': datetime.utcnow().isoformat() + 'Z'
                },
                'message': 'Analytics data refreshed successfully'
            })
            
        except Exception as e:
            logger.error(f"Error in refresh_analytics: {str(e)}")
            return jsonify({
                'success': False,
                'message': 'Failed to refresh analytics data',
                'errors': {'general': [str(e)]}
            }), 500
    
    return analytics_bp