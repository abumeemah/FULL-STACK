#!/usr/bin/env python3
"""
Admin Management Oversight Functionality Enhancement
Implements missing admin features for comprehensive management oversight
"""

from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required, current_user
from flask_wtf import FlaskForm
from wtforms import (
    StringField, TextAreaField, SelectField, BooleanField, 
    IntegerField, FloatField, SubmitField, DateField
)
from wtforms.validators import DataRequired, Length, NumberRange, Optional
from datetime import datetime, timezone, timedelta
from bson import ObjectId
import logging
from utils import get_mongo_db, requires_role
from translations import trans

logger = logging.getLogger(__name__)

# Enhanced Admin Forms
class SystemSettingsForm(FlaskForm):
    """Form for managing system-wide settings"""
    app_name = StringField(
        'Application Name',
        validators=[DataRequired(), Length(max=100)],
        render_kw={'class': 'form-control'}
    )
    maintenance_mode = BooleanField(
        'Maintenance Mode',
        render_kw={'class': 'form-check-input'}
    )
    max_trial_days = IntegerField(
        'Default Trial Days',
        validators=[DataRequired(), NumberRange(min=1, max=365)],
        render_kw={'class': 'form-control'}
    )
    monthly_subscription_price = FloatField(
        'Monthly Subscription Price (₦)',
        validators=[DataRequired(), NumberRange(min=0)],
        render_kw={'class': 'form-control'}
    )
    yearly_subscription_price = FloatField(
        'Yearly Subscription Price (₦)',
        validators=[DataRequired(), NumberRange(min=0)],
        render_kw={'class': 'form-control'}
    )
    submit = SubmitField('Save Settings', render_kw={'class': 'btn btn-primary'})

class EducationModuleForm(FlaskForm):
    """Form for managing education modules"""
    module_name = StringField(
        'Module Name',
        validators=[DataRequired(), Length(max=200)],
        render_kw={'class': 'form-control'}
    )
    module_description = TextAreaField(
        'Module Description',
        validators=[DataRequired(), Length(max=1000)],
        render_kw={'class': 'form-control', 'rows': 4}
    )
    module_content = TextAreaField(
        'Module Content',
        validators=[DataRequired()],
        render_kw={'class': 'form-control', 'rows': 10}
    )
    module_order = IntegerField(
        'Display Order',
        validators=[DataRequired(), NumberRange(min=1)],
        render_kw={'class': 'form-control'}
    )
    is_active = BooleanField(
        'Active',
        default=True,
        render_kw={'class': 'form-check-input'}
    )
    submit = SubmitField('Save Module', render_kw={'class': 'btn btn-primary'})

class NotificationTemplateForm(FlaskForm):
    """Form for managing notification templates"""
    template_name = StringField(
        'Template Name',
        validators=[DataRequired(), Length(max=100)],
        render_kw={'class': 'form-control'}
    )
    template_type = SelectField(
        'Template Type',
        choices=[
            ('email', 'Email'),
            ('sms', 'SMS'),
            ('whatsapp', 'WhatsApp'),
            ('in_app', 'In-App Notification')
        ],
        validators=[DataRequired()],
        render_kw={'class': 'form-select'}
    )
    subject = StringField(
        'Subject/Title',
        validators=[Length(max=200)],
        render_kw={'class': 'form-control'}
    )
    content = TextAreaField(
        'Content',
        validators=[DataRequired()],
        render_kw={'class': 'form-control', 'rows': 8}
    )
    is_active = BooleanField(
        'Active',
        default=True,
        render_kw={'class': 'form-check-input'}
    )
    submit = SubmitField('Save Template', render_kw={'class': 'btn btn-primary'})

class BulkUserOperationForm(FlaskForm):
    """Form for bulk user operations"""
    operation_type = SelectField(
        'Operation Type',
        choices=[
            ('extend_trial', 'Extend Trial'),
            ('activate_subscription', 'Activate Subscription'),
            ('send_notification', 'Send Notification'),
            ('update_role', 'Update Role'),
            ('export_data', 'Export User Data')
        ],
        validators=[DataRequired()],
        render_kw={'class': 'form-select'}
    )
    user_filter = SelectField(
        'User Filter',
        choices=[
            ('all', 'All Users'),
            ('trial_users', 'Trial Users'),
            ('subscribed_users', 'Subscribed Users'),
            ('expired_users', 'Expired Users'),
            ('new_users', 'New Users (Last 30 days)')
        ],
        validators=[DataRequired()],
        render_kw={'class': 'form-select'}
    )
    operation_value = StringField(
        'Operation Value',
        render_kw={'class': 'form-control', 'placeholder': 'e.g., 30 (for days), admin (for role)'}
    )
    submit = SubmitField('Execute Operation', render_kw={'class': 'btn btn-warning'})

# Enhanced Admin Functions
def get_system_settings():
    """Get current system settings"""
    try:
        db = get_mongo_db()
        settings = db.system_settings.find_one({'_id': 'global'})
        
        if not settings:
            # Initialize default settings
            default_settings = {
                '_id': 'global',
                'app_name': 'Ficore Africa',
                'maintenance_mode': False,
                'max_trial_days': 30,
                'monthly_subscription_price': 1000.0,
                'yearly_subscription_price': 10000.0,
                'created_at': datetime.now(timezone.utc),
                'updated_at': datetime.now(timezone.utc)
            }
            db.system_settings.insert_one(default_settings)
            return default_settings
        
        return settings
    except Exception as e:
        logger.error(f"Error getting system settings: {str(e)}")
        return {}

def save_system_settings(settings_data, admin_id):
    """Save system settings"""
    try:
        db = get_mongo_db()
        
        settings_data.update({
            'updated_at': datetime.now(timezone.utc),
            'updated_by': admin_id
        })
        
        result = db.system_settings.update_one(
            {'_id': 'global'},
            {'$set': settings_data},
            upsert=True
        )
        
        # Log the action
        db.audit_logs.insert_one({
            'admin_id': admin_id,
            'action': 'update_system_settings',
            'details': settings_data,
            'timestamp': datetime.now(timezone.utc)
        })
        
        return True
    except Exception as e:
        logger.error(f"Error saving system settings: {str(e)}")
        return False

def get_education_modules():
    """Get all education modules"""
    try:
        db = get_mongo_db()
        modules = list(db.education_modules.find().sort('module_order', 1))
        
        # Initialize default modules if none exist
        if not modules:
            default_modules = [
                {
                    'module_name': 'Understanding Tax Types',
                    'module_description': 'Learn about different types of taxes in Nigeria',
                    'module_content': 'This module covers PIT, CIT, VAT, and other tax types...',
                    'module_order': 1,
                    'is_active': True,
                    'created_at': datetime.now(timezone.utc)
                },
                {
                    'module_name': 'Filing vs. Paying',
                    'module_description': 'Understand the difference between filing and paying taxes',
                    'module_content': 'This module explains when to file vs when to pay...',
                    'module_order': 2,
                    'is_active': True,
                    'created_at': datetime.now(timezone.utc)
                },
                {
                    'module_name': 'Deductions & Reliefs',
                    'module_description': 'Learn about available tax deductions and reliefs',
                    'module_content': 'This module covers statutory deductions, rent relief...',
                    'module_order': 3,
                    'is_active': True,
                    'created_at': datetime.now(timezone.utc)
                },
                {
                    'module_name': 'Tracking for Compliance',
                    'module_description': 'Best practices for maintaining tax compliance',
                    'module_content': 'This module teaches record keeping and compliance...',
                    'module_order': 4,
                    'is_active': True,
                    'created_at': datetime.now(timezone.utc)
                },
                {
                    'module_name': 'Next Steps',
                    'module_description': 'Advanced tax planning and next steps',
                    'module_content': 'This module covers advanced strategies...',
                    'module_order': 5,
                    'is_active': True,
                    'created_at': datetime.now(timezone.utc)
                }
            ]
            
            db.education_modules.insert_many(default_modules)
            modules = list(db.education_modules.find().sort('module_order', 1))
        
        return modules
    except Exception as e:
        logger.error(f"Error getting education modules: {str(e)}")
        return []

def save_education_module(module_data, admin_id):
    """Save education module"""
    try:
        db = get_mongo_db()
        
        module_data.update({
            'updated_at': datetime.now(timezone.utc),
            'updated_by': admin_id
        })
        
        if '_id' in module_data:
            # Update existing module
            module_id = module_data.pop('_id')
            result = db.education_modules.update_one(
                {'_id': ObjectId(module_id)},
                {'$set': module_data}
            )
        else:
            # Create new module
            module_data['created_at'] = datetime.now(timezone.utc)
            result = db.education_modules.insert_one(module_data)
        
        # Log the action
        db.audit_logs.insert_one({
            'admin_id': admin_id,
            'action': 'save_education_module',
            'details': module_data,
            'timestamp': datetime.now(timezone.utc)
        })
        
        return True
    except Exception as e:
        logger.error(f"Error saving education module: {str(e)}")
        return False

def get_user_analytics():
    """Get comprehensive user analytics"""
    try:
        db = get_mongo_db()
        
        # Basic user counts
        total_users = db.users.count_documents({})
        active_trials = db.users.count_documents({
            'is_trial': True,
            'trial_end': {'$gte': datetime.now(timezone.utc)}
        })
        active_subscriptions = db.users.count_documents({
            'is_subscribed': True,
            'subscription_end': {'$gte': datetime.now(timezone.utc)}
        })
        
        # New users in last 30 days
        thirty_days_ago = datetime.now(timezone.utc) - timedelta(days=30)
        new_users = db.users.count_documents({
            'created_at': {'$gte': thirty_days_ago}
        })
        
        # Revenue analytics
        monthly_revenue = active_subscriptions * 1000  # Simplified calculation
        
        # Usage analytics
        total_records = db.records.count_documents({})
        total_cashflows = db.cashflows.count_documents({})
        
        # Recent activity
        recent_logins = db.users.count_documents({
            'last_login': {'$gte': datetime.now(timezone.utc) - timedelta(days=7)}
        })
        
        return {
            'total_users': total_users,
            'active_trials': active_trials,
            'active_subscriptions': active_subscriptions,
            'new_users': new_users,
            'monthly_revenue': monthly_revenue,
            'total_records': total_records,
            'total_cashflows': total_cashflows,
            'recent_logins': recent_logins,
            'conversion_rate': (active_subscriptions / total_users * 100) if total_users > 0 else 0
        }
    except Exception as e:
        logger.error(f"Error getting user analytics: {str(e)}")
        return {}

def execute_bulk_operation(operation_type, user_filter, operation_value, admin_id):
    """Execute bulk operations on users"""
    try:
        db = get_mongo_db()
        
        # Build user query based on filter
        query = {}
        if user_filter == 'trial_users':
            query = {'is_trial': True}
        elif user_filter == 'subscribed_users':
            query = {'is_subscribed': True}
        elif user_filter == 'expired_users':
            query = {
                '$or': [
                    {'is_trial': True, 'trial_end': {'$lt': datetime.now(timezone.utc)}},
                    {'is_subscribed': True, 'subscription_end': {'$lt': datetime.now(timezone.utc)}}
                ]
            }
        elif user_filter == 'new_users':
            thirty_days_ago = datetime.now(timezone.utc) - timedelta(days=30)
            query = {'created_at': {'$gte': thirty_days_ago}}
        
        # Execute operation
        result = {'success': False, 'affected_users': 0, 'message': ''}
        
        if operation_type == 'extend_trial':
            days = int(operation_value) if operation_value.isdigit() else 30
            new_trial_end = datetime.now(timezone.utc) + timedelta(days=days)
            
            update_result = db.users.update_many(
                query,
                {
                    '$set': {
                        'is_trial': True,
                        'trial_end': new_trial_end,
                        'updated_at': datetime.now(timezone.utc)
                    }
                }
            )
            result['affected_users'] = update_result.modified_count
            result['message'] = f'Extended trial by {days} days for {update_result.modified_count} users'
            result['success'] = True
            
        elif operation_type == 'update_role':
            if operation_value in ['trader', 'startup', 'admin']:
                update_result = db.users.update_many(
                    query,
                    {
                        '$set': {
                            'role': operation_value,
                            'updated_at': datetime.now(timezone.utc)
                        }
                    }
                )
                result['affected_users'] = update_result.modified_count
                result['message'] = f'Updated role to {operation_value} for {update_result.modified_count} users'
                result['success'] = True
        
        # Log the bulk operation
        if result['success']:
            db.audit_logs.insert_one({
                'admin_id': admin_id,
                'action': 'bulk_operation',
                'details': {
                    'operation_type': operation_type,
                    'user_filter': user_filter,
                    'operation_value': operation_value,
                    'affected_users': result['affected_users']
                },
                'timestamp': datetime.now(timezone.utc)
            })
        
        return result
    except Exception as e:
        logger.error(f"Error executing bulk operation: {str(e)}")
        return {'success': False, 'affected_users': 0, 'message': f'Error: {str(e)}'}

def get_system_health():
    """Get system health metrics"""
    try:
        db = get_mongo_db()
        
        # Database health
        collections = db.list_collection_names()
        collection_stats = {}
        
        for collection in ['users', 'records', 'cashflows', 'audit_logs']:
            if collection in collections:
                collection_stats[collection] = db[collection].count_documents({})
        
        # Recent activity
        recent_activity = {
            'new_users_today': db.users.count_documents({
                'created_at': {'$gte': datetime.now(timezone.utc).replace(hour=0, minute=0, second=0)}
            }),
            'records_today': db.records.count_documents({
                'created_at': {'$gte': datetime.now(timezone.utc).replace(hour=0, minute=0, second=0)}
            }),
            'admin_actions_today': db.audit_logs.count_documents({
                'timestamp': {'$gte': datetime.now(timezone.utc).replace(hour=0, minute=0, second=0)}
            })
        }
        
        return {
            'database_status': 'healthy',
            'collection_stats': collection_stats,
            'recent_activity': recent_activity,
            'last_updated': datetime.now(timezone.utc).isoformat()
        }
    except Exception as e:
        logger.error(f"Error getting system health: {str(e)}")
        return {'database_status': 'error', 'error': str(e)}

if __name__ == "__main__":
    print("Admin Enhancement Implementation Module")
    print("This module provides enhanced admin functionality for:")
    print("- System settings management")
    print("- Education module management") 
    print("- User analytics and reporting")
    print("- Bulk user operations")
    print("- System health monitoring")