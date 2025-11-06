from flask import Blueprint, request, jsonify
from datetime import datetime, timedelta
from bson import ObjectId
import os
import requests
import hmac
import hashlib
import traceback

def init_subscription_blueprint(mongo, token_required, serialize_doc):
    subscription_bp = Blueprint('subscription', __name__, url_prefix='/subscription')
    
    # Paystack configuration
    PAYSTACK_SECRET_KEY = os.getenv('PAYSTACK_SECRET_KEY', 'sk_test_your_secret_key')
    PAYSTACK_PUBLIC_KEY = os.getenv('PAYSTACK_PUBLIC_KEY', 'pk_test_your_public_key')
    PAYSTACK_BASE_URL = 'https://api.paystack.co'
    
    # Subscription plans configuration
    SUBSCRIPTION_PLANS = {
        'monthly': {
            'name': 'Monthly Premium',
            'price': 2500.0,  # ₦2,500 per month
            'duration_days': 30,
            'paystack_plan_code': 'PLN_monthly_premium',
            'description': 'Unlimited operations for 30 days',
            'features': [
                'Unlimited Income/Expense entries',
                'Unlimited PDF exports',
                'All premium features',
                'Priority support',
                'No FC costs for any operations'
            ]
        },
        'annually': {
            'name': 'Annual Premium',
            'price': 25000.0,  # ₦25,000 per year (2.5 months free)
            'duration_days': 365,
            'paystack_plan_code': 'PLN_annual_premium',
            'description': 'Unlimited operations for 365 days (Save 2.5 months!)',
            'features': [
                'Unlimited Income/Expense entries',
                'Unlimited PDF exports',
                'All premium features',
                'Priority support',
                'No FC costs for any operations',
                'Save ₦5,000 compared to monthly'
            ]
        }
    }

    def _make_paystack_request(endpoint, method='GET', data=None):
        """Make authenticated request to Paystack API"""
        headers = {
            'Authorization': f'Bearer {PAYSTACK_SECRET_KEY}',
            'Content-Type': 'application/json'
        }
        
        url = f"{PAYSTACK_BASE_URL}{endpoint}"
        
        try:
            if method == 'GET':
                response = requests.get(url, headers=headers)
            elif method == 'POST':
                response = requests.post(url, headers=headers, json=data)
            elif method == 'PUT':
                response = requests.put(url, headers=headers, json=data)
            else:
                raise ValueError(f"Unsupported HTTP method: {method}")
            
            return response.json()
        except Exception as e:
            print(f"Paystack API error: {str(e)}")
            return {'status': False, 'message': f'Payment service error: {str(e)}'}

    @subscription_bp.route('/plans', methods=['GET'])
    @token_required
    def get_subscription_plans(current_user):
        """Get available subscription plans"""
        try:
            # Get user's current subscription status
            user = mongo.db.users.find_one({'_id': current_user['_id']})
            is_subscribed = user.get('isSubscribed', False)
            current_plan = user.get('subscriptionType')
            
            plans = []
            for plan_id, plan_data in SUBSCRIPTION_PLANS.items():
                plan_info = {
                    'id': plan_id,
                    'name': plan_data['name'],
                    'price': plan_data['price'],
                    'duration_days': plan_data['duration_days'],
                    'description': plan_data['description'],
                    'features': plan_data['features'],
                    'is_current': is_subscribed and current_plan == plan_id,
                    'savings': None
                }
                
                # Calculate savings for annual plan
                if plan_id == 'annually':
                    monthly_yearly_cost = SUBSCRIPTION_PLANS['monthly']['price'] * 12
                    savings = monthly_yearly_cost - plan_data['price']
                    plan_info['savings'] = savings
                
                plans.append(plan_info)
            
            return jsonify({
                'success': True,
                'data': {
                    'plans': plans,
                    'current_subscription': {
                        'is_subscribed': is_subscribed,
                        'plan_type': current_plan,
                        'end_date': user.get('subscriptionEndDate')
                    }
                },
                'message': 'Subscription plans retrieved successfully'
            })

        except Exception as e:
            return jsonify({
                'success': False,
                'message': 'Failed to retrieve subscription plans',
                'errors': {'general': [str(e)]}
            }), 500

    @subscription_bp.route('/initialize', methods=['POST'])
    @token_required
    def initialize_subscription(current_user):
        """Initialize subscription payment with Paystack"""
        try:
            data = request.get_json()
            
            # Validate required fields
            if 'plan_type' not in data:
                return jsonify({
                    'success': False,
                    'message': 'Missing required field: plan_type'
                }), 400
            
            plan_type = data['plan_type']
            if plan_type not in SUBSCRIPTION_PLANS:
                return jsonify({
                    'success': False,
                    'message': 'Invalid subscription plan'
                }), 400
            
            plan = SUBSCRIPTION_PLANS[plan_type]
            user = mongo.db.users.find_one({'_id': current_user['_id']})
            
            # Check if user is already subscribed
            if user.get('isSubscribed', False):
                end_date = user.get('subscriptionEndDate')
                if end_date and end_date > datetime.utcnow():
                    return jsonify({
                        'success': False,
                        'message': 'You already have an active subscription'
                    }), 400
            
            # Initialize Paystack transaction
            paystack_data = {
                'email': user['email'],
                'amount': int(plan['price'] * 100),  # Paystack expects kobo
                'currency': 'NGN',
                'reference': f"sub_{current_user['_id']}_{plan_type}_{int(datetime.utcnow().timestamp())}",
                'callback_url': f"{request.host_url}subscription/verify",
                'metadata': {
                    'user_id': str(current_user['_id']),
                    'plan_type': plan_type,
                    'plan_name': plan['name']
                }
            }
            
            paystack_response = _make_paystack_request('/transaction/initialize', 'POST', paystack_data)
            
            if paystack_response.get('status'):
                # Store pending subscription
                pending_subscription = {
                    '_id': ObjectId(),
                    'userId': current_user['_id'],
                    'reference': paystack_data['reference'],
                    'planType': plan_type,
                    'amount': plan['price'],
                    'status': 'pending',
                    'createdAt': datetime.utcnow(),
                    'paystackData': paystack_response['data']
                }
                
                mongo.db.pending_subscriptions.insert_one(pending_subscription)
                
                return jsonify({
                    'success': True,
                    'data': {
                        'authorization_url': paystack_response['data']['authorization_url'],
                        'access_code': paystack_response['data']['access_code'],
                        'reference': paystack_data['reference']
                    },
                    'message': 'Payment initialized successfully'
                })
            else:
                return jsonify({
                    'success': False,
                    'message': paystack_response.get('message', 'Failed to initialize payment')
                }), 400

        except Exception as e:
            return jsonify({
                'success': False,
                'message': 'Failed to initialize subscription',
                'errors': {'general': [str(e)]}
            }), 500

    @subscription_bp.route('/verify/<reference>', methods=['GET'])
    @token_required
    def verify_subscription_payment(current_user, reference):
        """Verify subscription payment with Paystack"""
        try:
            # Verify with Paystack
            paystack_response = _make_paystack_request(f'/transaction/verify/{reference}')
            
            if not paystack_response.get('status'):
                return jsonify({
                    'success': False,
                    'message': 'Payment verification failed'
                }), 400
            
            transaction_data = paystack_response['data']
            
            # Check if payment was successful
            if transaction_data['status'] != 'success':
                return jsonify({
                    'success': False,
                    'message': f"Payment {transaction_data['status']}"
                }), 400
            
            # Find pending subscription
            pending_sub = mongo.db.pending_subscriptions.find_one({
                'reference': reference,
                'userId': current_user['_id']
            })
            
            if not pending_sub:
                return jsonify({
                    'success': False,
                    'message': 'Subscription record not found'
                }), 404
            
            plan_type = pending_sub['planType']
            plan = SUBSCRIPTION_PLANS[plan_type]
            
            # Activate subscription
            start_date = datetime.utcnow()
            end_date = start_date + timedelta(days=plan['duration_days'])
            
            # Update user subscription
            mongo.db.users.update_one(
                {'_id': current_user['_id']},
                {
                    '$set': {
                        'isSubscribed': True,
                        'subscriptionType': plan_type,
                        'subscriptionStartDate': start_date,
                        'subscriptionEndDate': end_date,
                        'subscriptionAutoRenew': True,
                        'paymentMethodDetails': {
                            'last4': transaction_data.get('authorization', {}).get('last4', ''),
                            'brand': transaction_data.get('authorization', {}).get('brand', ''),
                            'authorization_code': transaction_data.get('authorization', {}).get('authorization_code', '')
                        }
                    }
                }
            )
            
            # Create subscription record
            subscription_record = {
                '_id': ObjectId(),
                'userId': current_user['_id'],
                'planType': plan_type,
                'amount': plan['price'],
                'startDate': start_date,
                'endDate': end_date,
                'status': 'active',
                'paymentReference': reference,
                'paystackTransactionId': transaction_data['id'],
                'createdAt': datetime.utcnow()
            }
            
            mongo.db.subscriptions.insert_one(subscription_record)
            
            # Update pending subscription status
            mongo.db.pending_subscriptions.update_one(
                {'_id': pending_sub['_id']},
                {'$set': {'status': 'completed', 'completedAt': datetime.utcnow()}}
            )
            
            return jsonify({
                'success': True,
                'data': {
                    'subscription_type': plan_type,
                    'start_date': start_date.isoformat() + 'Z',
                    'end_date': end_date.isoformat() + 'Z',
                    'plan_name': plan['name']
                },
                'message': f'Subscription activated successfully! Welcome to {plan["name"]}!'
            })

        except Exception as e:
            return jsonify({
                'success': False,
                'message': 'Failed to verify subscription payment',
                'errors': {'general': [str(e)]}
            }), 500

    @subscription_bp.route('/status', methods=['GET'])
    @token_required
    def get_subscription_status(current_user):
        """Get user's current subscription status"""
        try:
            user = mongo.db.users.find_one({'_id': current_user['_id']})
            
            is_subscribed = user.get('isSubscribed', False)
            subscription_type = user.get('subscriptionType')
            start_date = user.get('subscriptionStartDate')
            end_date = user.get('subscriptionEndDate')
            auto_renew = user.get('subscriptionAutoRenew', False)
            
            # Check if subscription is actually active
            if is_subscribed and end_date:
                if end_date <= datetime.utcnow():
                    # Subscription expired, update status
                    mongo.db.users.update_one(
                        {'_id': current_user['_id']},
                        {'$set': {'isSubscribed': False}}
                    )
                    is_subscribed = False
            
            status_data = {
                'is_subscribed': is_subscribed,
                'subscription_type': subscription_type,
                'start_date': start_date.isoformat() + 'Z' if start_date else None,
                'end_date': end_date.isoformat() + 'Z' if end_date else None,
                'auto_renew': auto_renew,
                'days_remaining': None,
                'plan_details': None
            }
            
            if is_subscribed and end_date:
                days_remaining = (end_date - datetime.utcnow()).days
                status_data['days_remaining'] = max(0, days_remaining)
                
                if subscription_type in SUBSCRIPTION_PLANS:
                    status_data['plan_details'] = SUBSCRIPTION_PLANS[subscription_type]
            
            return jsonify({
                'success': True,
                'data': status_data,
                'message': 'Subscription status retrieved successfully'
            })

        except Exception as e:
            return jsonify({
                'success': False,
                'message': 'Failed to retrieve subscription status',
                'errors': {'general': [str(e)]}
            }), 500

    @subscription_bp.route('/manage', methods=['PUT'])
    @token_required
    def manage_subscription(current_user):
        """Manage subscription settings (auto-renew, etc.)"""
        try:
            data = request.get_json()
            
            user = mongo.db.users.find_one({'_id': current_user['_id']})
            if not user.get('isSubscribed', False):
                return jsonify({
                    'success': False,
                    'message': 'No active subscription found'
                }), 404
            
            update_data = {}
            
            if 'auto_renew' in data:
                update_data['subscriptionAutoRenew'] = bool(data['auto_renew'])
            
            if update_data:
                mongo.db.users.update_one(
                    {'_id': current_user['_id']},
                    {'$set': update_data}
                )
                
                return jsonify({
                    'success': True,
                    'message': 'Subscription settings updated successfully'
                })
            else:
                return jsonify({
                    'success': False,
                    'message': 'No valid fields to update'
                }), 400

        except Exception as e:
            return jsonify({
                'success': False,
                'message': 'Failed to update subscription settings',
                'errors': {'general': [str(e)]}
            }), 500

    @subscription_bp.route('/cancel', methods=['POST'])
    @token_required
    def cancel_subscription(current_user):
        """Cancel subscription (disable auto-renew)"""
        try:
            user = mongo.db.users.find_one({'_id': current_user['_id']})
            if not user.get('isSubscribed', False):
                return jsonify({
                    'success': False,
                    'message': 'No active subscription found'
                }), 404
            
            # Disable auto-renew (subscription remains active until end date)
            mongo.db.users.update_one(
                {'_id': current_user['_id']},
                {'$set': {'subscriptionAutoRenew': False}}
            )
            
            end_date = user.get('subscriptionEndDate')
            
            return jsonify({
                'success': True,
                'data': {
                    'end_date': end_date.isoformat() + 'Z' if end_date else None,
                    'message': 'Your subscription will not auto-renew and will expire on the end date.'
                },
                'message': 'Subscription cancelled successfully'
            })

        except Exception as e:
            return jsonify({
                'success': False,
                'message': 'Failed to cancel subscription',
                'errors': {'general': [str(e)]}
            }), 500

    @subscription_bp.route('/webhook', methods=['POST'])
    def paystack_webhook():
        """Handle Paystack webhooks for subscription events"""
        try:
            # Verify webhook signature
            signature = request.headers.get('x-paystack-signature')
            if not signature:
                return jsonify({'status': 'error', 'message': 'No signature'}), 400
            
            payload = request.get_data()
            expected_signature = hmac.new(
                PAYSTACK_SECRET_KEY.encode('utf-8'),
                payload,
                hashlib.sha512
            ).hexdigest()
            
            if not hmac.compare_digest(signature, expected_signature):
                return jsonify({'status': 'error', 'message': 'Invalid signature'}), 400
            
            event = request.get_json()
            event_type = event.get('event')
            
            if event_type == 'charge.success':
                # Handle successful payment
                data = event['data']
                reference = data.get('reference')
                
                if reference and reference.startswith('sub_'):
                    # This is a subscription payment
                    print(f"Subscription payment successful: {reference}")
                    # Additional processing can be added here
            
            elif event_type == 'subscription.create':
                # Handle subscription creation
                print(f"Subscription created: {event['data']}")
            
            elif event_type == 'subscription.disable':
                # Handle subscription cancellation
                print(f"Subscription disabled: {event['data']}")
            
            return jsonify({'status': 'success'}), 200

        except Exception as e:
            print(f"Webhook error: {str(e)}")
            return jsonify({'status': 'error', 'message': str(e)}), 500

    return subscription_bp