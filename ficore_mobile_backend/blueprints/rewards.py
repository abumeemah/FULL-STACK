from flask import Blueprint, request, jsonify
from datetime import datetime, timedelta
from bson import ObjectId
import traceback

def init_rewards_blueprint(mongo, token_required, serialize_doc, limiter=None):
    rewards_bp = Blueprint('rewards', __name__, url_prefix='/rewards')
    
    # Reward configuration - FC costs for exclusive benefits
    REWARD_CONFIG = {
        # Regular rewards (available to all users)
        'free_income_expense_bundle_10': {
            'name': '10 Free Income/Expense Entries',
            'description': 'Get 10 entries for Income or Expense tracking without using your regular FCs. Save 5 FCs compared to individual entries!',
            'cost': 15.0,
            'category': 'bundle',
            'benefit_type': 'free_entries',
            'benefit_amount': 10,
            'subscriber_only': False
        },
        'temp_fc_discount_24h': {
            'name': '50% Off All FC Costs for 24 Hours',
            'description': 'Halve the FC cost for all features for a full day! Perfect for heavy usage periods.',
            'cost': 30.0,
            'category': 'discount',
            'benefit_type': 'temp_discount',
            'benefit_amount': 50,  # 50% discount
            'subscriber_only': False
        },
        'trial_extension_7d': {
            'name': '7-Day Trial Extension',
            'description': 'Extend your trial period by 7 days to explore more features without time pressure.',
            'cost': 20.0,
            'category': 'extension',
            'benefit_type': 'trial_extension',
            'benefit_amount': 7,  # 7 days
            'subscriber_only': False
        },
        'free_pdf_export_month': {
            'name': '1 Month Free PDF Exports',
            'description': 'Generate unlimited PDF exports for 30 days. Perfect for reporting periods!',
            'cost': 40.0,
            'category': 'premium',
            'benefit_type': 'free_pdf_exports',
            'benefit_amount': 30,  # 30 days
            'subscriber_only': False
        },
        
        # Subscriber-exclusive rewards
        'premium_report_templates': {
            'name': 'Premium Report Templates Pack',
            'description': 'Unlock a collection of advanced, customizable report templates with professional designs.',
            'cost': 25.0,
            'category': 'exclusive_feature',
            'benefit_type': 'unlock_feature',
            'feature_key': 'premium_templates',
            'subscriber_only': True
        },
        'priority_support_token': {
            'name': 'Priority Support Token',
            'description': 'Redeem for one instance of priority customer support with faster response times.',
            'cost': 20.0,
            'category': 'exclusive_service',
            'benefit_type': 'add_item',
            'item_key': 'priority_support_tokens',
            'item_amount': 1,
            'subscriber_only': True
        },
        'exclusive_content_access': {
            'name': 'Exclusive Content Access',
            'description': 'Gain access to premium financial management webinars and exclusive e-books.',
            'cost': 40.0,
            'category': 'exclusive_content',
            'benefit_type': 'unlock_feature',
            'feature_key': 'exclusive_webinars',
            'subscriber_only': True
        },
        'increased_storage_500mb': {
            'name': '500MB Additional Storage',
            'description': 'Increase your cloud storage by 500MB for documents and files.',
            'cost': 30.0,
            'category': 'exclusive_utility',
            'benefit_type': 'increase_limit',
            'limit_key': 'storage_mb',
            'limit_amount': 500,
            'subscriber_only': True
        },
        'advanced_analytics_access': {
            'name': 'Advanced Analytics Dashboard',
            'description': 'Unlock advanced business intelligence and detailed financial analytics.',
            'cost': 35.0,
            'category': 'exclusive_feature',
            'benefit_type': 'unlock_feature',
            'feature_key': 'advanced_analytics',
            'subscriber_only': True
        },
        'custom_branding_pack': {
            'name': 'Custom Branding Pack',
            'description': 'Add your business logo and branding to reports and exports.',
            'cost': 45.0,
            'category': 'exclusive_feature',
            'benefit_type': 'unlock_feature',
            'feature_key': 'custom_branding',
            'subscriber_only': True
        }
    }
    
    # Earning milestones configuration
    EARNING_CONFIG = {
        'streak_milestones': {
            7: {'amount': 10.0, 'flag': 'earned_7day_streak_bonus'},
            30: {'amount': 25.0, 'flag': 'earned_30day_streak_bonus'},
            90: {'amount': 50.0, 'flag': 'earned_90day_streak_bonus'}
        },
        'exploration_bonuses': {
            'first_debtors_access': {'amount': 2.0, 'flag': 'earned_first_debtors_access_bonus'},
            'first_creditors_access': {'amount': 2.0, 'flag': 'earned_first_creditors_access_bonus'},
            'first_inventory_access': {'amount': 2.0, 'flag': 'earned_first_inventory_access_bonus'},
            'first_advanced_report': {'amount': 5.0, 'flag': 'earned_first_advanced_report_bonus'},
            'profile_completion': {'amount': 10.0, 'flag': 'earned_profile_complete_bonus'}
        }
    }

    @rewards_bp.route('/', methods=['GET'])
    @token_required
    def get_rewards_dashboard(current_user):
        """Get user's rewards status, streak, and available rewards"""
        try:
            # Validate user exists
            if not current_user or '_id' not in current_user:
                return jsonify({
                    'success': False,
                    'message': 'Invalid user session'
                }), 401

            # Get user data with rewards fields
            user = mongo.db.users.find_one({'_id': current_user['_id']})
            if not user:
                return jsonify({
                    'success': False,
                    'message': 'User not found'
                }), 404

            # Get or create rewards record
            rewards_record = mongo.db.rewards.find_one({'user_id': current_user['_id']})
            if not rewards_record:
                # Create initial rewards record
                rewards_record = {
                    '_id': ObjectId(),
                    'user_id': current_user['_id'],
                    'streak': 0,
                    'last_active_date': None,
                    'created_at': datetime.utcnow(),
                    'updated_at': datetime.utcnow()
                }
                mongo.db.rewards.insert_one(rewards_record)

            # Get current streak and last active date (don't update just by viewing rewards)
            current_streak = rewards_record.get('streak', 0)
            last_active = rewards_record.get('last_active_date')
            
            # Don't update activity just by viewing rewards - only update via track-activity endpoint

            # Check for streak milestone rewards (with error handling)
            try:
                _check_and_award_streak_milestones(mongo, current_user, current_streak, user)
                # Get updated user data (in case FC balance was updated)
                user = mongo.db.users.find_one({'_id': current_user['_id']})
            except Exception as e:
                print(f"Error checking streak milestones: {str(e)}")
                # Continue without failing the entire request
            
            # Calculate next milestone
            next_milestone = 7
            if current_streak >= 90:
                next_milestone = None  # Max milestone reached
            elif current_streak >= 30:
                next_milestone = 90
            elif current_streak >= 7:
                next_milestone = 30

            # Get active benefits (with error handling)
            try:
                active_benefits = _get_active_benefits(user)
            except Exception as e:
                print(f"Error getting active benefits: {str(e)}")
                active_benefits = []
            
            # Get earning opportunities (with error handling)
            try:
                earning_opportunities = _get_earning_opportunities(user)
            except Exception as e:
                print(f"Error getting earning opportunities: {str(e)}")
                earning_opportunities = []

            return jsonify({
                'success': True,
                'data': {
                    'fc_balance': float(user.get('ficoreCreditBalance', 0.0)),
                    'streak': current_streak,
                    'next_milestone': next_milestone,
                    'last_active_date': rewards_record.get('last_active_date', datetime.utcnow()).isoformat() + 'Z',
                    'active_benefits': active_benefits,
                    'earned_bonuses': {
                        'earned_7day_streak_bonus': user.get('earned_7day_streak_bonus', False),
                        'earned_30day_streak_bonus': user.get('earned_30day_streak_bonus', False),
                        'earned_90day_streak_bonus': user.get('earned_90day_streak_bonus', False),
                        'earned_first_debtors_access_bonus': user.get('earned_first_debtors_access_bonus', False),
                        'earned_first_creditors_access_bonus': user.get('earned_first_creditors_access_bonus', False),
                        'earned_first_inventory_access_bonus': user.get('earned_first_inventory_access_bonus', False),
                        'earned_first_advanced_report_bonus': user.get('earned_first_advanced_report_bonus', False),
                        'earned_profile_complete_bonus': user.get('earned_profile_complete_bonus', False),
                    },
                    'earning_opportunities': earning_opportunities,
                    'available_rewards': list(REWARD_CONFIG.keys())
                },
                'message': 'Rewards dashboard retrieved successfully'
            })

        except Exception as e:
            print(f"Error in get_rewards_dashboard: {str(e)}")
            return jsonify({
                'success': False,
                'message': 'Failed to retrieve rewards dashboard',
                'errors': {'general': [str(e)]}
            }), 500

    @rewards_bp.route('/track-activity', methods=['POST'])
    @token_required
    def track_user_activity(current_user):
        """Track user activity for rewards and streak management"""
        try:
            data = request.get_json()
            
            # Validate required fields
            if 'action' not in data or 'module' not in data:
                return jsonify({
                    'success': False,
                    'message': 'Missing required fields: action, module'
                }), 400

            action = data['action']
            module = data['module']
            
            # Prevent duplicate activity tracking within a short time window (5 minutes)
            activity_key = f"{action}_{module}"
            current_time = datetime.utcnow()
            
            # Check for recent activity tracking
            recent_activity = mongo.db.activity_tracking.find_one({
                'user_id': current_user['_id'],
                'activity_key': activity_key,
                'timestamp': {'$gte': current_time - timedelta(minutes=5)}
            })
            
            if recent_activity:
                # Return success without processing to avoid duplicate tracking
                return jsonify({
                    'success': True,
                    'message': 'Activity already tracked recently',
                    'duplicate_prevented': True
                })
            
            # Record this activity tracking attempt
            mongo.db.activity_tracking.insert_one({
                '_id': ObjectId(),
                'user_id': current_user['_id'],
                'activity_key': activity_key,
                'action': action,
                'module': module,
                'timestamp': current_time
            })
            
            # Clean up old activity tracking records (older than 1 hour) to prevent collection bloat
            try:
                cleanup_threshold = current_time - timedelta(hours=1)
                mongo.db.activity_tracking.delete_many({
                    'timestamp': {'$lt': cleanup_threshold}
                })
            except Exception as cleanup_error:
                # Don't fail the request if cleanup fails
                print(f"Activity tracking cleanup error: {str(cleanup_error)}")
            
            # Get or create rewards record
            rewards_record = mongo.db.rewards.find_one({'user_id': current_user['_id']})
            if not rewards_record:
                rewards_record = {
                    '_id': ObjectId(),
                    'user_id': current_user['_id'],
                    'streak': 1,
                    'last_active_date': datetime.utcnow(),
                    'created_at': datetime.utcnow(),
                    'updated_at': datetime.utcnow()
                }
                mongo.db.rewards.insert_one(rewards_record)
            else:
                # Calculate streak based on actual activity tracking
                today = datetime.utcnow().date()
                last_active = rewards_record.get('last_active_date')
                current_streak = rewards_record.get('streak', 0)
                
                if last_active:
                    last_active_date = last_active.date() if isinstance(last_active, datetime) else last_active
                    yesterday = today - timedelta(days=1)
                    
                    if last_active_date == today:
                        # Already active today, keep current streak
                        pass
                    elif last_active_date == yesterday:
                        # Continue streak - user was active yesterday and is active today
                        current_streak += 1
                    else:
                        # Gap in activity, reset streak to 1 (today's activity)
                        current_streak = 1
                else:
                    # First time activity
                    current_streak = 1
                
                # Update rewards record with proper streak calculation
                mongo.db.rewards.update_one(
                    {'_id': rewards_record['_id']},
                    {
                        '$set': {
                            'streak': current_streak,
                            'last_active_date': datetime.utcnow(),
                            'updated_at': datetime.utcnow()
                        }
                    }
                )

            # Check for exploration bonuses
            user = mongo.db.users.find_one({'_id': current_user['_id']})
            _check_and_award_exploration_bonuses(mongo, current_user, action, module, user)

            return jsonify({
                'success': True,
                'message': 'Activity tracked successfully'
            })

        except Exception as e:
            print(f"Error in track_user_activity: {str(e)}")
            return jsonify({
                'success': False,
                'message': 'Failed to track activity',
                'errors': {'general': [str(e)]}
            }), 500

    @rewards_bp.route('/redeem', methods=['POST'])
    @token_required
    def redeem_reward(current_user):
        """Redeem FC reward for exclusive benefits"""
        try:
            data = request.get_json()
            
            # Validate required fields
            if 'reward_id' not in data:
                return jsonify({
                    'success': False,
                    'message': 'Missing required field: reward_id'
                }), 400

            reward_id = data['reward_id']
            
            # Validate reward exists
            if reward_id not in REWARD_CONFIG:
                return jsonify({
                    'success': False,
                    'message': 'Invalid reward ID'
                }), 400

            reward_config = REWARD_CONFIG[reward_id]
            cost = reward_config['cost']
            
            # Get user data
            user = mongo.db.users.find_one({'_id': current_user['_id']})
            current_balance = user.get('ficoreCreditBalance', 0.0)
            is_subscribed = user.get('isSubscribed', False)
            
            # Check if subscription is actually active
            if is_subscribed:
                end_date = user.get('subscriptionEndDate')
                if end_date and end_date <= datetime.utcnow():
                    is_subscribed = False
            
            # Check if reward requires subscription
            if reward_config.get('subscriber_only', False) and not is_subscribed:
                return jsonify({
                    'success': False,
                    'message': 'This reward is exclusive to premium subscribers',
                    'data': {
                        'requires_subscription': True,
                        'reward_name': reward_config['name']
                    }
                }), 403  # Forbidden
            
            # Check sufficient balance
            if current_balance < cost:
                return jsonify({
                    'success': False,
                    'message': 'Insufficient FiCore Credits',
                    'data': {
                        'current_balance': current_balance,
                        'required_amount': cost,
                        'shortfall': cost - current_balance
                    }
                }), 402  # Payment Required

            # Check for conflicting active benefits
            if _has_conflicting_benefit(user, reward_config):
                return jsonify({
                    'success': False,
                    'message': 'You already have an active benefit of this type'
                }), 400

            # Deduct credits using existing credits system
            from datetime import datetime
            new_balance = current_balance - cost
            mongo.db.users.update_one(
                {'_id': current_user['_id']},
                {'$set': {'ficoreCreditBalance': new_balance}}
            )

            # Create transaction record
            transaction = {
                '_id': ObjectId(),
                'userId': current_user['_id'],
                'type': 'debit',
                'amount': cost,
                'description': f'Redeemed reward: {reward_config["name"]}',
                'operation': f'redeem_{reward_id}',
                'balanceBefore': current_balance,
                'balanceAfter': new_balance,
                'status': 'completed',
                'createdAt': datetime.utcnow(),
                'metadata': {
                    'reward_id': reward_id,
                    'reward_name': reward_config['name'],
                    'redemption_type': 'exclusive_reward'
                }
            }
            mongo.db.credit_transactions.insert_one(transaction)

            # Apply reward benefit
            benefit_applied = _apply_reward_benefit(mongo, current_user['_id'], reward_config)
            
            if not benefit_applied:
                # Rollback the credit deduction if benefit application fails
                mongo.db.users.update_one(
                    {'_id': current_user['_id']},
                    {'$set': {'ficoreCreditBalance': current_balance}}
                )
                # Remove the transaction record
                mongo.db.credit_transactions.delete_one({'_id': transaction['_id']})
                
                return jsonify({
                    'success': False,
                    'message': 'Failed to apply reward benefit. Credits have been refunded.'
                }), 500

            return jsonify({
                'success': True,
                'data': {
                    'reward_id': reward_id,
                    'reward_name': reward_config['name'],
                    'cost_deducted': cost,
                    'new_balance': new_balance,
                    'benefit_applied': reward_config['benefit_type'],
                    'benefit_details': _get_benefit_details(reward_config)
                },
                'message': f'Successfully redeemed {reward_config["name"]}! 🎉'
            })

        except Exception as e:
            print(f"Error in redeem_reward: {str(e)}")
            return jsonify({
                'success': False,
                'message': 'Failed to redeem reward',
                'errors': {'general': [str(e)]}
            }), 500

    @rewards_bp.route('/available', methods=['GET'])
    @token_required
    def get_available_rewards(current_user):
        """Get list of available rewards with costs and availability"""
        try:
            # Get user data
            user = mongo.db.users.find_one({'_id': current_user['_id']})
            current_balance = user.get('ficoreCreditBalance', 0.0)
            is_subscribed = user.get('isSubscribed', False)
            
            # Check if subscription is actually active
            if is_subscribed:
                end_date = user.get('subscriptionEndDate')
                if end_date and end_date <= datetime.utcnow():
                    is_subscribed = False
            
            # Build available rewards list
            available_rewards = []
            subscriber_exclusive_rewards = []
            
            for reward_id, config in REWARD_CONFIG.items():
                is_subscriber_only = config.get('subscriber_only', False)
                
                # Skip subscriber-only rewards for non-subscribers
                if is_subscriber_only and not is_subscribed:
                    # Add to subscriber exclusive list for display purposes
                    reward_data = {
                        'id': reward_id,
                        'name': config['name'],
                        'description': config['description'],
                        'cost': config['cost'],
                        'category': config['category'],
                        'is_available': False,
                        'insufficient_credits': False,
                        'has_active_benefit': False,
                        'subscriber_only': True,
                        'requires_subscription': True
                    }
                    subscriber_exclusive_rewards.append(reward_data)
                    continue
                
                is_available = current_balance >= config['cost']
                has_conflict = _has_conflicting_benefit(user, config)
                
                reward_data = {
                    'id': reward_id,
                    'name': config['name'],
                    'description': config['description'],
                    'cost': config['cost'],
                    'category': config['category'],
                    'is_available': is_available and not has_conflict,
                    'insufficient_credits': not is_available,
                    'has_active_benefit': has_conflict,
                    'subscriber_only': is_subscriber_only,
                    'requires_subscription': False
                }
                available_rewards.append(reward_data)

            return jsonify({
                'success': True,
                'data': {
                    'rewards': available_rewards,
                    'subscriber_exclusive_rewards': subscriber_exclusive_rewards,
                    'user_balance': current_balance,
                    'is_subscribed': is_subscribed,
                    'subscription_status': {
                        'is_subscribed': is_subscribed,
                        'subscription_type': user.get('subscriptionType'),
                        'end_date': user.get('subscriptionEndDate').isoformat() + 'Z' if user.get('subscriptionEndDate') else None
                    }
                },
                'message': 'Available rewards retrieved successfully'
            })

        except Exception as e:
            print(f"Error in get_available_rewards: {str(e)}")
            return jsonify({
                'success': False,
                'message': 'Failed to retrieve available rewards',
                'errors': {'general': [str(e)]}
            }), 500

    # Helper functions
    def _get_active_benefits(user):
        """Get user's active benefits"""
        try:
            active_benefits = []
            
            # Check for temporary discount
            if user.get('hasTemporaryDiscount', False):
                discount_expires = user.get('tempDiscountExpires')
                if discount_expires and datetime.utcnow() < discount_expires:
                    active_benefits.append({
                        'type': 'temp_discount',
                        'name': '50% Off All FC Costs',
                        'description': f"{user.get('discountPercentage', 50)}% discount on all features",
                        'expires_at': discount_expires.isoformat() + 'Z' if discount_expires else None
                    })
            
            # Check for free entries
            if user.get('freeEntriesCount', 0) > 0:
                active_benefits.append({
                    'type': 'free_entries',
                    'name': 'Free Income/Expense Entries',
                    'description': f"{user.get('freeEntriesCount', 0)} free entries remaining",
                    'count': user.get('freeEntriesCount', 0)
                })
            
            # Check for free PDF exports
            if user.get('hasFreePdfExports', False):
                pdf_expires = user.get('freePdfExportsExpires')
                if pdf_expires and datetime.utcnow() < pdf_expires:
                    active_benefits.append({
                        'type': 'free_pdf_exports',
                        'name': 'Free PDF Exports',
                        'description': 'Unlimited PDF exports',
                        'expires_at': pdf_expires.isoformat() + 'Z' if pdf_expires else None
                    })
            
            return active_benefits
        except Exception as e:
            print(f"Error getting active benefits: {str(e)}")
            return []

    def _get_earning_opportunities(user):
        """Get available earning opportunities for the user"""
        try:
            opportunities = []
            
            # Check for unclaimed exploration bonuses
            for bonus_key, config in EARNING_CONFIG['exploration_bonuses'].items():
                if not user.get(config['flag'], False):
                    opportunities.append({
                        'type': 'exploration',
                        'key': bonus_key,
                        'name': bonus_key.replace('_', ' ').title(),
                        'amount': config['amount'],
                        'description': f"Earn {config['amount']} FCs by exploring this feature"
                    })
            
            # Check for unclaimed streak milestones
            current_streak = user.get('current_streak', 0)
            for milestone, config in EARNING_CONFIG['streak_milestones'].items():
                if current_streak < milestone and not user.get(config['flag'], False):
                    days_needed = milestone - current_streak
                    opportunities.append({
                        'type': 'streak_milestone',
                        'key': f'streak_{milestone}d',
                        'name': f'{milestone}-Day Streak Milestone',
                        'amount': config['amount'],
                        'description': f"Earn {config['amount']} FCs by maintaining a {milestone}-day streak ({days_needed} more days needed)"
                    })
                    break  # Only show the next milestone
            
            return opportunities
        except Exception as e:
            print(f"Error getting earning opportunities: {str(e)}")
            return []

    def _check_and_award_streak_milestones(mongo, current_user, streak, user):
        """Check and award streak milestone bonuses"""
        try:
            for milestone, config in EARNING_CONFIG['streak_milestones'].items():
                if streak >= milestone and not user.get(config['flag'], False):
                    # Award milestone bonus
                    current_balance = user.get('ficoreCreditBalance', 0.0)
                    new_balance = current_balance + config['amount']
                    
                    # Update user balance and flag
                    mongo.db.users.update_one(
                        {'_id': current_user['_id']},
                        {
                            '$set': {
                                'ficoreCreditBalance': new_balance,
                                config['flag']: True
                            }
                        }
                    )
                    
                    # Create transaction record
                    transaction = {
                        '_id': ObjectId(),
                        'userId': current_user['_id'],
                        'type': 'credit',
                        'amount': config['amount'],
                        'description': f'Streak milestone bonus - {milestone} days',
                        'operation': f'streak_milestone_{milestone}d',
                        'balanceBefore': current_balance,
                        'balanceAfter': new_balance,
                        'status': 'completed',
                        'createdAt': datetime.utcnow(),
                        'metadata': {
                            'milestone': milestone,
                            'streak_bonus': True
                        }
                    }
                    mongo.db.credit_transactions.insert_one(transaction)
                    
                    print(f"Awarded {config['amount']} FCs for {milestone}-day streak milestone")
        except Exception as e:
            print(f"Error awarding streak milestones: {str(e)}")

    def _check_and_award_exploration_bonuses(mongo, current_user, action, module, user):
        """Check and award exploration bonuses"""
        try:
            bonus_key = None
            
            # Map actions to bonus keys
            if action == 'access_module' and module == 'debtors':
                bonus_key = 'first_debtors_access'
            elif action == 'access_module' and module == 'creditors':
                bonus_key = 'first_creditors_access'
            elif action == 'access_module' and module == 'inventory':
                bonus_key = 'first_inventory_access'
            elif action == 'generate_report' and 'advanced' in module:
                bonus_key = 'first_advanced_report'
            elif action == 'complete_profile':
                bonus_key = 'profile_completion'
            
            if bonus_key and bonus_key in EARNING_CONFIG['exploration_bonuses']:
                config = EARNING_CONFIG['exploration_bonuses'][bonus_key]
                
                if not user.get(config['flag'], False):
                    # Award exploration bonus
                    current_balance = user.get('ficoreCreditBalance', 0.0)
                    new_balance = current_balance + config['amount']
                    
                    # Update user balance and flag
                    mongo.db.users.update_one(
                        {'_id': current_user['_id']},
                        {
                            '$set': {
                                'ficoreCreditBalance': new_balance,
                                config['flag']: True
                            }
                        }
                    )
                    
                    # Create transaction record
                    transaction = {
                        '_id': ObjectId(),
                        'userId': current_user['_id'],
                        'type': 'credit',
                        'amount': config['amount'],
                        'description': f'Exploration bonus - {bonus_key.replace("_", " ").title()}',
                        'operation': f'exploration_{bonus_key}',
                        'balanceBefore': current_balance,
                        'balanceAfter': new_balance,
                        'status': 'completed',
                        'createdAt': datetime.utcnow(),
                        'metadata': {
                            'exploration_bonus': True,
                            'bonus_type': bonus_key
                        }
                    }
                    mongo.db.credit_transactions.insert_one(transaction)
                    
                    print(f"Awarded {config['amount']} FCs for {bonus_key} exploration bonus")
        except Exception as e:
            print(f"Error awarding exploration bonuses: {str(e)}")

    def _get_active_benefits(user):
        """Get user's currently active benefits"""
        active_benefits = {}
        
        # Check free entries
        free_entries = user.get('free_income_expense_entries', 0)
        if free_entries > 0:
            active_benefits['free_income_expense_entries'] = free_entries
        
        # Check temporary discount
        if user.get('temp_fc_discount_active', False):
            expiry = user.get('temp_fc_discount_expiry')
            if expiry and datetime.utcnow() < expiry:
                active_benefits['temp_fc_discount'] = {
                    'percentage': user.get('temp_fc_discount_percentage', 0),
                    'expiry': expiry.isoformat() + 'Z'
                }
            else:
                # Expired, clean up
                mongo.db.users.update_one(
                    {'_id': user['_id']},
                    {
                        '$set': {
                            'temp_fc_discount_active': False,
                            'temp_fc_discount_percentage': 0,
                            'temp_fc_discount_expiry': None
                        }
                    }
                )
        
        # Check free PDF exports
        if user.get('free_pdf_export_active', False):
            expiry = user.get('free_pdf_export_expiry')
            if expiry and datetime.utcnow() < expiry:
                active_benefits['free_pdf_exports'] = {
                    'expiry': expiry.isoformat() + 'Z'
                }
            else:
                # Expired, clean up
                mongo.db.users.update_one(
                    {'_id': user['_id']},
                    {
                        '$set': {
                            'free_pdf_export_active': False,
                            'free_pdf_export_expiry': None
                        }
                    }
                )
        
        return active_benefits

    def _get_earning_opportunities(user):
        """Get available earning opportunities for the user"""
        opportunities = []
        
        # Check exploration bonuses
        for bonus_key, config in EARNING_CONFIG['exploration_bonuses'].items():
            if not user.get(config['flag'], False):
                opportunity = {
                    'type': 'exploration',
                    'key': bonus_key,
                    'amount': config['amount'],
                    'description': f"Earn {config['amount']} FCs by {bonus_key.replace('_', ' ')}"
                }
                opportunities.append(opportunity)
        
        # Check streak milestones
        rewards_record = mongo.db.rewards.find_one({'user_id': user['_id']})
        current_streak = rewards_record.get('streak', 0) if rewards_record else 0
        
        for milestone, config in EARNING_CONFIG['streak_milestones'].items():
            if not user.get(config['flag'], False) and current_streak < milestone:
                days_needed = milestone - current_streak
                opportunity = {
                    'type': 'streak',
                    'key': f'streak_{milestone}d',
                    'amount': config['amount'],
                    'description': f"Earn {config['amount']} FCs by reaching {milestone}-day streak ({days_needed} more days)"
                }
                opportunities.append(opportunity)
        
        return opportunities

    def _has_conflicting_benefit(user, reward_config):
        """Check if user has conflicting active benefit"""
        benefit_type = reward_config['benefit_type']
        
        if benefit_type == 'temp_discount':
            return user.get('temp_fc_discount_active', False)
        elif benefit_type == 'free_pdf_exports':
            return user.get('free_pdf_export_active', False)
        
        return False

    def _apply_reward_benefit(mongo, user_id, reward_config):
        """Apply the reward benefit to user account"""
        try:
            benefit_type = reward_config['benefit_type']
            
            update_data = {}
            
            if benefit_type == 'free_entries':
                amount = reward_config['benefit_amount']
                # Add to existing free entries instead of replacing
                user = mongo.db.users.find_one({'_id': user_id})
                current_entries = user.get('free_income_expense_entries', 0)
                update_data['free_income_expense_entries'] = current_entries + amount
            elif benefit_type == 'temp_discount':
                amount = reward_config['benefit_amount']
                update_data.update({
                    'temp_fc_discount_active': True,
                    'temp_fc_discount_percentage': amount,
                    'temp_fc_discount_expiry': datetime.utcnow() + timedelta(hours=24)
                })
            elif benefit_type == 'trial_extension':
                amount = reward_config['benefit_amount']
                # Extend trial by specified days
                user = mongo.db.users.find_one({'_id': user_id})
                current_expiry = user.get('trial_expiry_date', datetime.utcnow())
                if isinstance(current_expiry, str):
                    current_expiry = datetime.fromisoformat(current_expiry.replace('Z', ''))
                new_expiry = current_expiry + timedelta(days=amount)
                update_data['trial_expiry_date'] = new_expiry
            elif benefit_type == 'free_pdf_exports':
                amount = reward_config['benefit_amount']
                update_data.update({
                    'free_pdf_export_active': True,
                    'free_pdf_export_expiry': datetime.utcnow() + timedelta(days=amount)
                })
            elif benefit_type == 'unlock_feature':
                # Unlock premium features for subscribers
                feature_key = reward_config['feature_key']
                user = mongo.db.users.find_one({'_id': user_id})
                current_features = user.get('unlocked_features', {})
                current_features[feature_key] = True
                update_data['unlocked_features'] = current_features
            elif benefit_type == 'add_item':
                # Add items like priority support tokens
                item_key = reward_config['item_key']
                item_amount = reward_config['item_amount']
                user = mongo.db.users.find_one({'_id': user_id})
                current_amount = user.get(item_key, 0)
                update_data[item_key] = current_amount + item_amount
            elif benefit_type == 'increase_limit':
                # Increase limits like storage
                limit_key = reward_config['limit_key']
                limit_amount = reward_config['limit_amount']
                user = mongo.db.users.find_one({'_id': user_id})
                current_limit = user.get(limit_key, 0)
                update_data[limit_key] = current_limit + limit_amount
            
            if update_data:
                result = mongo.db.users.update_one(
                    {'_id': user_id},
                    {'$set': update_data}
                )
                return result.modified_count > 0
            
            return False
        except Exception as e:
            print(f"Error applying reward benefit: {str(e)}")
            return False

    def _get_benefit_details(reward_config):
        """Get human-readable benefit details"""
        benefit_type = reward_config['benefit_type']
        
        if benefit_type == 'free_entries':
            return f"{reward_config['benefit_amount']} free income/expense entries added to your account"
        elif benefit_type == 'temp_discount':
            return f"{reward_config['benefit_amount']}% discount on all FC costs for 24 hours"
        elif benefit_type == 'trial_extension':
            return f"Trial extended by {reward_config['benefit_amount']} days"
        elif benefit_type == 'free_pdf_exports':
            return f"Free PDF exports for {reward_config['benefit_amount']} days"
        elif benefit_type == 'unlock_feature':
            return f"Unlocked premium feature: {reward_config['feature_key']}"
        elif benefit_type == 'add_item':
            return f"Added {reward_config['item_amount']} {reward_config['item_key']} to your account"
        elif benefit_type == 'increase_limit':
            return f"Increased {reward_config['limit_key']} by {reward_config['limit_amount']}"
        
        return "Benefit applied successfully"

    def _ensure_activity_tracking_indexes(mongo):
        """Ensure proper indexes exist for activity tracking collection"""
        try:
            # Create compound index for efficient duplicate checking
            mongo.db.activity_tracking.create_index([
                ('user_id', 1),
                ('activity_key', 1),
                ('timestamp', -1)
            ])
            
            # Create TTL index to automatically clean up old records after 2 hours
            mongo.db.activity_tracking.create_index(
                'timestamp',
                expireAfterSeconds=7200  # 2 hours in seconds
            )
        except Exception as e:
            print(f"Error creating activity tracking indexes: {str(e)}")
    
    # Ensure indexes are created when blueprint is initialized
    try:
        _ensure_activity_tracking_indexes(mongo)
    except Exception as e:
        print(f"Error during index initialization: {str(e)}")

    return rewards_bp
