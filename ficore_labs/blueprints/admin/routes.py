import logging
from bson import ObjectId, errors
from flask import Blueprint, render_template, redirect, url_for, flash, request, session, Response, send_file
from flask_login import login_required, current_user
from flask_wtf import FlaskForm
from wtforms import StringField, FloatField, SelectField, SubmitField, DateField, validators
from wtforms.validators import DataRequired, NumberRange
from translations import trans
import utils
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib.units import inch
from io import BytesIO
import csv
from models import get_records, get_cashflows, get_feedback, to_dict_feedback, get_waitlist_entries, to_dict_waitlist


# Enhanced Admin Functionality Imports
from admin_enhancement_implementation import (
    SystemSettingsForm, EducationModuleForm, NotificationTemplateForm, BulkUserOperationForm,
    get_system_settings, save_system_settings, get_education_modules, save_education_module,
    get_user_analytics, execute_bulk_operation, get_system_health
)
logger = logging.getLogger(__name__)

admin_bp = Blueprint('admin', __name__, template_folder='templates/admin')

# Error Handler
@admin_bp.app_errorhandler(500)
def error_500(error):
    """Handle 500 Internal Server Error."""
    logger.error(f"500 Internal Server Error: {str(error)}",
                 extra={'session_id': session.get('sid', 'no-session-id'), 'user_id': current_user.id if current_user.is_authenticated else 'anonymous'})
    flash(trans('admin_server_error', default='An unexpected error occurred. Please try again later.'), 'danger')
    return render_template('error/500.html'), 500

# Form Definitions
class RoleForm(FlaskForm):
    role = SelectField(trans('user_role', default='Role'), choices=[('trader', 'Trader'), ('startup', 'Startup'), ('admin', 'Admin')], validators=[DataRequired()], render_kw={'class': 'form-select'})
    submit = SubmitField(trans('user_update_role', default='Update Role'), render_kw={'class': 'btn btn-primary'})

class SubscriptionForm(FlaskForm):
    is_subscribed = SelectField(trans('subscription_status', default='Subscription Status'), choices=[('True', 'Subscribed'), ('False', 'Not Subscribed')], validators=[DataRequired()], render_kw={'class': 'form-select'})
    subscription_plan = SelectField(trans('subscription_plan', default='Subscription Plan'), choices=[('', 'None'), ('monthly', 'Monthly (₦1k)'), ('yearly', 'Yearly (₦10k)')], render_kw={'class': 'form-select'})
    subscription_end = DateField(trans('subscription_end', default='Subscription End Date'), format='%Y-%m-%d', validators=[validators.Optional()], render_kw={'class': 'form-control'})
    submit = SubmitField(trans('subscription_update', default='Update Subscription'), render_kw={'class': 'btn btn-primary'})

class TrialForm(FlaskForm):
    is_trial = SelectField(trans('trial_status', default='Trial Status'), choices=[('True', 'Active Trial'), ('False', 'No Trial')], validators=[DataRequired()], render_kw={'class': 'form-select'})
    trial_end = DateField(trans('trial_end', default='Trial End Date'), format='%Y-%m-%d', validators=[validators.Optional()], render_kw={'class': 'form-control'})
    submit = SubmitField(trans('trial_update', default='Update Trial'), render_kw={'class': 'btn btn-primary'})
    bulk_trial_days = SelectField(trans('bulk_trial_days', default='Extend Trial for New Users'), choices=[('', 'Select Days'), ('30', '30 Days'), ('60', '60 Days'), ('90', '90 Days')], validators=[validators.Optional()], render_kw={'class': 'form-select'})
    bulk_trial_start = DateField(trans('bulk_trial_start', default='Registration Start Date'), format='%Y-%m-%d', validators=[validators.Optional()], render_kw={'class': 'form-control'})
    bulk_trial_end = DateField(trans('bulk_trial_end', default='Registration End Date'), format='%Y-%m-%d', validators=[validators.Optional()], render_kw={'class': 'form-control'})
    bulk_submit = SubmitField(trans('bulk_trial_update', default='Apply Bulk Trial'), render_kw={'class': 'btn btn-primary'})

class DebtorForm(FlaskForm):
    name = StringField(trans('debtor_name', default='Debtor Name'), validators=[DataRequired(), validators.Length(min=2, max=100)], render_kw={'class': 'form-control'})
    amount = FloatField(trans('debtor_amount', default='Amount Owed'), validators=[DataRequired(), NumberRange(min=0)], render_kw={'class': 'form-control'})
    due_date = DateField(trans('debtor_due_date', default='Due Date'), validators=[DataRequired()], format='%Y-%m-%d', render_kw={'class': 'form-control'})
    submit = SubmitField(trans('debtor_add', default='Add Debtor'), render_kw={'class': 'btn btn-primary'})

class CreditorForm(FlaskForm):
    name = StringField(trans('creditor_name', default='Creditor Name'), validators=[DataRequired(), validators.Length(min=2, max=100)], render_kw={'class': 'form-control'})
    amount = FloatField(trans('creditor_amount', default='Amount Owed'), validators=[DataRequired(), NumberRange(min=0)], render_kw={'class': 'form-control'})
    due_date = DateField(trans('creditor_due_date', default='Due Date'), validators=[DataRequired()], format='%Y-%m-%d', render_kw={'class': 'form-control'})
    submit = SubmitField(trans('creditor_add', default='Add Creditor'), render_kw={'class': 'btn btn-primary'})


class FeedbackFilterForm(FlaskForm):
    tool_name = SelectField(trans('general_select_tool', default='Select Tool'), 
                           choices=[('', trans('general_all_tools', default='All Tools')),
                                    ('profile', trans('general_profile', default='Profile')),
                                    ('debtors', trans('debtors_dashboard', default='Debtors')),
                                    ('creditors', trans('creditors_dashboard', default='Creditors')),
                                    ('receipts', trans('receipts_dashboard', default='Receipts')),
                                    ('payment', trans('payments_dashboard', default='Payments')),
                                    ('report', trans('reports_dashboard', default='Business Reports')),
                                    ],
                           validators=[validators.Optional()], render_kw={'class': 'form-select'})
    user_id = StringField(trans('admin_user_id', default='User ID'), validators=[validators.Optional()], render_kw={'class': 'form-control'})
    submit = SubmitField(trans('general_filter', default='Filter'), render_kw={'class': 'btn btn-primary'})

# Helper Functions
def log_audit_action(action, details=None):
    """Log an admin action to audit_logs collection."""
    try:
        db = utils.get_mongo_db()
        if db is None:
            raise Exception("Failed to connect to MongoDB")
        db.audit_logs.insert_one({
            'admin_id': str(current_user.id),
            'action': action,
            'details': details or {},
            'timestamp': datetime.now(timezone.utc)
        })
    except Exception as e:
        logger.error(f"Error logging audit action '{action}': {str(e)}",
                     extra={'session_id': session.get('sid', 'no-session-id'), 'user_id': current_user.id})

# Routes
@admin_bp.route('/dashboard', methods=['GET'])
@login_required
@utils.requires_role('admin')
@utils.limiter.limit("50 per hour")
def dashboard():
    """Admin dashboard with system statistics."""
    try:
        db = utils.get_mongo_db()
        if db is None:
            raise Exception("Failed to connect to MongoDB")
        stats = {
            'users': db.users.count_documents({}),
            'records': db.records.count_documents({}),
            'cashflows': db.cashflows.count_documents({}),
            'debtors': db.debtors.count_documents({}),
            'creditors': db.creditors.count_documents({}),
            'funds': db.funds.count_documents({}),
            'audit_logs': db.audit_logs.count_documents({}),
            'feedback': db.feedback.count_documents({})
        }
        recent_users = list(db.users.find().sort('created_at', -1).limit(5))
        for user in recent_users:
            user['_id'] = str(user['_id'])
            trial_end = user.get('trial_end')
            subscription_end = user.get('subscription_end')
            trial_end_aware = trial_end.replace(tzinfo=ZoneInfo("UTC")) if trial_end and trial_end.tzinfo is None else trial_end
            subscription_end_aware = subscription_end.replace(tzinfo=ZoneInfo("UTC")) if subscription_end and subscription_end.tzinfo is None else subscription_end
            user['is_trial_active'] = (
                datetime.now(timezone.utc) <= trial_end_aware if user.get('is_trial') and trial_end_aware
                else user.get('is_subscribed') and subscription_end_aware and datetime.now(timezone.utc) <= subscription_end_aware
            )
        logger.info(f"Admin {current_user.id} accessed dashboard",
                    extra={'session_id': session.get('sid', 'no-session-id'), 'user_id': current_user.id})
        return render_template(
            'admin/dashboard.html',
            stats=stats,
            recent_users=recent_users,
            title=trans('admin_dashboard', default='Admin Dashboard')
        )
    except Exception as e:
        logger.error(f"Error loading admin dashboard for user {current_user.id}: {str(e)}",
                     extra={'session_id': session.get('sid', 'no-session-id'), 'user_id': current_user.id})
        flash(trans('admin_dashboard_error', default='An error occurred while loading the dashboard'), 'danger')
        return render_template('error/500.html'), 500

@admin_bp.route('/users', methods=['GET'])
@login_required
@utils.requires_role('admin')
@utils.limiter.limit("50 per hour")
def manage_users():
    """View and manage users."""
    try:
        db = utils.get_mongo_db()
        if db is None:
            raise Exception("Failed to connect to MongoDB")
        users = list(db.users.find({} if utils.is_admin() else {'role': {'$ne': 'admin'}}).sort('created_at', -1))
        for user in users:
            user['_id'] = str(user['_id'])
            user['username'] = user['_id']
            trial_end = user.get('trial_end')
            subscription_end = user.get('subscription_end')
            trial_end_aware = trial_end.replace(tzinfo=ZoneInfo("UTC")) if trial_end and trial_end.tzinfo is None else trial_end
            subscription_end_aware = subscription_end.replace(tzinfo=ZoneInfo("UTC")) if subscription_end and subscription_end.tzinfo is None else subscription_end
            user['is_trial_active'] = (
                datetime.now(timezone.utc) <= trial_end_aware if user.get('is_trial') and trial_end_aware
                else user.get('is_subscribed') and subscription_end_aware and datetime.now(timezone.utc) <= subscription_end_aware
            )
        return render_template('admin/users.html', users=users, title=trans('admin_manage_users_title', default='Manage Users'))
    except Exception as e:
        logger.error(f"Error fetching users for admin {current_user.id}: {str(e)}",
                     extra={'session_id': session.get('sid', 'no-session-id'), 'user_id': current_user.id})
        flash(trans('admin_database_error', default='An error occurred while accessing the database'), 'danger')
        return render_template('error/500.html'), 500

@admin_bp.route('/users/suspend/<user_id>', methods=['POST'])
@login_required
@utils.requires_role('admin')
@utils.limiter.limit("10 per hour")
def suspend_user(user_id):
    """Suspend a user account."""
    try:
        ObjectId(user_id)
        db = utils.get_mongo_db()
        if db is None:
            raise Exception("Failed to connect to MongoDB")
        user_query = {'_id': ObjectId(user_id)}
        user = db.users.find_one(user_query)
        if user is None:
            flash(trans('admin_user_not_found', default='User not found'), 'danger')
            return redirect(url_for('admin.manage_users'))
        result = db.users.update_one(
            user_query,
            {'$set': {'suspended': True, 'updated_at': datetime.now(timezone.utc)}}
        )
        if result.modified_count == 0:
            flash(trans('admin_user_not_updated', default='User could not be suspended'), 'danger')
        else:
            flash(trans('admin_user_suspended', default='User suspended successfully'), 'success')
            logger.info(f"Admin {current_user.id} suspended user {user_id}",
                        extra={'session_id': session.get('sid', 'no-session-id'), 'user_id': current_user.id})
            log_audit_action('suspend_user', {'user_id': user_id})
        return redirect(url_for('admin.manage_users'))
    except errors.InvalidId:
        logger.error(f"Invalid user_id format: {user_id}",
                     extra={'session_id': session.get('sid', 'no-session-id'), 'user_id': current_user.id})
        flash(trans('admin_invalid_user_id', default='Invalid user ID'), 'danger')
        return redirect(url_for('admin.manage_users'))
    except Exception as e:
        logger.error(f"Error suspending user {user_id}: {str(e)}",
                     extra={'session_id': session.get('sid', 'no-session-id'), 'user_id': current_user.id})
        flash(trans('admin_database_error', default='An error occurred while accessing the database'), 'danger')
        return render_template('error/500.html'), 500

@admin_bp.route('/users/delete/<user_id>', methods=['POST'])
@login_required
@utils.requires_role('admin')
@utils.limiter.limit("5 per hour")
def delete_user(user_id):
    """Delete a user and their data."""
    try:
        ObjectId(user_id)
        db = utils.get_mongo_db()
        if db is None:
            raise Exception("Failed to connect to MongoDB")
        user_query = {'_id': ObjectId(user_id)}
        user = db.users.find_one(user_query)
        if user is None:
            flash(trans('admin_user_not_found', default='User not found'), 'danger')
            return redirect(url_for('admin.manage_users'))
        db.records.delete_many({'user_id': user_id})
        db.cashflows.delete_many({'user_id': user_id})
        db.debtors.delete_many({'user_id': user_id})
        db.creditors.delete_many({'user_id': user_id})
        db.funds.delete_many({'user_id': user_id})
        db.feedback.delete_many({'user_id': user_id})
        db.audit_logs.delete_many({'details.user_id': user_id})
        result = db.users.delete_one(user_query)
        if result.deleted_count == 0:
            flash(trans('admin_user_not_deleted', default='User could not be deleted'), 'danger')
        else:
            flash(trans('admin_user_deleted', default='User deleted successfully'), 'success')
            logger.info(f"Admin {current_user.id} deleted user {user_id}",
                        extra={'session_id': session.get('sid', 'no-session-id'), 'user_id': current_user.id})
            log_audit_action('delete_user', {'user_id': user_id})
        return redirect(url_for('admin.manage_users'))
    except errors.InvalidId:
        logger.error(f"Invalid user_id format: {user_id}",
                     extra={'session_id': session.get('sid', 'no-session-id'), 'user_id': current_user.id})
        flash(trans('admin_invalid_user_id', default='Invalid user ID'), 'danger')
        return redirect(url_for('admin.manage_users'))
    except Exception as e:
        logger.error(f"Error deleting user {user_id}: {str(e)}",
                     extra={'session_id': session.get('sid', 'no-session-id'), 'user_id': current_user.id})
        flash(trans('admin_database_error', default='An error occurred while accessing the database'), 'danger')
        return render_template('error/500.html'), 500

@admin_bp.route('/data/delete/<collection>/<item_id>', methods=['POST'])
@login_required
@utils.requires_role('admin')
@utils.limiter.limit("10 per hour")
def delete_item(collection, item_id):
    """Delete an item from a collection."""
    valid_collections = ['records', 'cashflows', 'debtors', 'creditors', 'funds']
    if collection not in valid_collections:
        flash(trans('admin_invalid_collection', default='Invalid collection selected'), 'danger')
        return redirect(url_for('admin.dashboard'))
    try:
        ObjectId(item_id)
        db = utils.get_mongo_db()
        if db is None:
            raise Exception("Failed to connect to MongoDB")
        result = db[collection].delete_one({'_id': ObjectId(item_id)})
        if result.deleted_count == 0:
            flash(trans('admin_item_not_found', default='Item not found'), 'danger')
        else:
            flash(trans('admin_item_deleted', default='Item deleted successfully'), 'success')
            logger.info(f"Admin {current_user.id} deleted {collection} item {item_id}",
                        extra={'session_id': session.get('sid', 'no-session-id'), 'user_id': current_user.id})
            log_audit_action(f'delete_{collection}_item', {'item_id': item_id, 'collection': collection})
        return redirect(url_for(f'admin.{collection}'))
    except errors.InvalidId:
        logger.error(f"Invalid item_id format for collection {collection}: {item_id}",
                     extra={'session_id': session.get('sid', 'no-session-id'), 'user_id': current_user.id})
        flash(trans('admin_invalid_item_id', default='Invalid item ID'), 'danger')
        return redirect(url_for('admin.dashboard'))
    except Exception as e:
        logger.error(f"Error deleting {collection} item {item_id}: {str(e)}",
                     extra={'session_id': session.get('sid', 'no-session-id'), 'user_id': current_user.id})
        flash(trans('admin_database_error', default='An error occurred while accessing the database'), 'danger')
        return render_template('error/500.html'), 500

@admin_bp.route('/users/roles', methods=['GET', 'POST'])
@login_required
@utils.requires_role('admin')
@utils.limiter.limit("50 per hour")
def manage_user_roles():
    """Manage user roles: list all users and update their roles."""
    try:
        db = utils.get_mongo_db()
        if db is None:
            raise Exception("Failed to connect to MongoDB")
        users = list(db.users.find())
        form = RoleForm()
        if request.method == 'POST' and form.validate_on_submit():
            user_id = request.form.get('user_id')
            try:
                ObjectId(user_id)
                user = db.users.find_one({'_id': ObjectId(user_id)})
                if user is None:
                    flash(trans('user_not_found', default='User not found'), 'danger')
                    return redirect(url_for('admin.manage_user_roles'))
                new_role = form.role.data
                db.users.update_one(
                    {'_id': ObjectId(user_id)},
                    {'$set': {'role': new_role, 'updated_at': datetime.now(timezone.utc)}}
                )
                logger.info(f"User role updated: id={user_id}, new_role={new_role}, admin={current_user.id}",
                            extra={'session_id': session.get('sid', 'no-session-id'), 'user_id': current_user.id})
                log_audit_action('update_user_role', {'user_id': user_id, 'new_role': new_role})
                flash(trans('user_role_updated', default='User role updated successfully'), 'success')
                return redirect(url_for('admin.manage_user_roles'))
            except errors.InvalidId:
                logger.error(f"Invalid user_id format: {user_id}",
                             extra={'session_id': session.get('sid', 'no-session-id'), 'user_id': current_user.id})
                flash(trans('admin_invalid_user_id', default='Invalid user ID'), 'danger')
                return redirect(url_for('admin.manage_user_roles'))
            except Exception as e:
                logger.error(f"Error updating user role {user_id}: {str(e)}",
                             extra={'session_id': session.get('sid', 'no-session-id'), 'user_id': current_user.id})
                flash(trans('admin_database_error', default='An error occurred while accessing the database'), 'danger')
                return render_template('admin/user_roles.html', form=form, users=users, title=trans('admin_manage_user_roles_title', default='Manage User Roles'))
        
        for user in users:
            user['_id'] = str(user['_id'])
            trial_end = user.get('trial_end')
            subscription_end = user.get('subscription_end')
            trial_end_aware = trial_end.replace(tzinfo=ZoneInfo("UTC")) if trial_end and trial_end.tzinfo is None else trial_end
            subscription_end_aware = subscription_end.replace(tzinfo=ZoneInfo("UTC")) if subscription_end and subscription_end.tzinfo is None else subscription_end
            user['is_trial_active'] = (
                datetime.now(timezone.utc) <= trial_end_aware if user.get('is_trial') and trial_end_aware
                else user.get('is_subscribed') and subscription_end_aware and datetime.now(timezone.utc) <= subscription_end_aware
            )
        return render_template('admin/user_roles.html', form=form, users=users, title=trans('admin_manage_user_roles_title', default='Manage User Roles'))
    except Exception as e:
        logger.error(f"Error in manage_user_roles for admin {current_user.id}: {str(e)}",
                     extra={'session_id': session.get('sid', 'no-session-id'), 'user_id': current_user.id})
        flash(trans('admin_database_error', default='An error occurred while accessing the database'), 'danger')
        return render_template('error/500.html'), 500

@admin_bp.route('/users/subscriptions', methods=['GET', 'POST'])
@login_required
@utils.requires_role('admin')
@utils.limiter.limit("50 per hour")
def manage_user_subscriptions():
    """Manage user subscriptions: list all users and update their subscription status."""
    try:
        db = utils.get_mongo_db()
        if db is None:
            raise Exception("Failed to connect to MongoDB")
        users = list(db.users.find())
        form = SubscriptionForm()
        if request.method == 'POST' and form.validate_on_submit():
            user_id = request.form.get('user_id')
            try:
                ObjectId(user_id)
                user = db.users.find_one({'_id': ObjectId(user_id)})
                if user is None:
                    flash(trans('user_not_found', default='User not found'), 'danger')
                    return redirect(url_for('admin.manage_user_subscriptions'))
                plan_durations = {'monthly': 30, 'yearly': 365}
                update_data = {
                    'is_subscribed': form.is_subscribed.data == 'True',
                    'subscription_plan': form.subscription_plan.data or None,
                    'subscription_start': datetime.now(timezone.utc) if form.is_subscribed.data == 'True' else None,
                    'subscription_end': form.subscription_end.data if form.subscription_end.data else None,
                    'updated_at': datetime.now(timezone.utc)
                }
                if form.is_subscribed.data == 'True' and not form.subscription_end.data and form.subscription_plan.data:
                    duration = plan_durations.get(form.subscription_plan.data, 30)
                    update_data['subscription_end'] = datetime.now(timezone.utc) + timedelta(days=duration)
                db.users.update_one(
                    {'_id': ObjectId(user_id)},
                    {'$set': update_data}
                )
                logger.info(f"User subscription updated: id={user_id}, subscribed={update_data['is_subscribed']}, plan={update_data['subscription_plan']}, admin={current_user.id}",
                            extra={'session_id': session.get('sid', 'no-session-id'), 'user_id': current_user.id})
                log_audit_action('update_user_subscription', {
                    'user_id': user_id,
                    'is_subscribed': update_data['is_subscribed'],
                    'subscription_plan': update_data['subscription_plan'],
                    'subscription_end': update_data['subscription_end'].strftime('%Y-%m-%d') if update_data['subscription_end'] else None
                })
                flash(trans('subscription_updated', default='User subscription updated successfully'), 'success')
                return redirect(url_for('admin.manage_user_subscriptions'))
            except errors.InvalidId:
                logger.error(f"Invalid user_id format: {user_id}",
                             extra={'session_id': session.get('sid', 'no-session-id'), 'user_id': current_user.id})
                flash(trans('admin_invalid_user_id', default='Invalid user ID'), 'danger')
                return redirect(url_for('admin.manage_user_subscriptions'))
            except Exception as e:
                logger.error(f"Error updating user subscription {user_id}: {str(e)}",
                             extra={'session_id': session.get('sid', 'no-session-id'), 'user_id': current_user.id})
                flash(trans('admin_database_error', default='An error occurred while accessing the database'), 'danger')
                return render_template('admin/user_subscriptions.html', form=form, users=users, title=trans('admin_manage_user_subscriptions_title', default='Manage User Subscriptions'))
        
        for user in users:
            user['_id'] = str(user['_id'])
            trial_end = user.get('trial_end')
            subscription_end = user.get('subscription_end')
            trial_end_aware = trial_end.replace(tzinfo=ZoneInfo("UTC")) if trial_end and trial_end.tzinfo is None else trial_end
            subscription_end_aware = subscription_end.replace(tzinfo=ZoneInfo("UTC")) if subscription_end and subscription_end.tzinfo is None else subscription_end
            user['is_trial_active'] = (
                datetime.now(timezone.utc) <= trial_end_aware if user.get('is_trial') and trial_end_aware
                else user.get('is_subscribed') and subscription_end_aware and datetime.now(timezone.utc) <= subscription_end_aware
            )
        return render_template('admin/user_subscriptions.html', form=form, users=users, title=trans('admin_manage_user_subscriptions_title', default='Manage User Subscriptions'))
    except Exception as e:
        logger.error(f"Error in manage_user_subscriptions for admin {current_user.id}: {str(e)}",
                     extra={'session_id': session.get('sid', 'no-session-id'), 'user_id': current_user.id})
        flash(trans('admin_database_error', default='An error occurred while accessing the database'), 'danger')
        return render_template('error/500.html'), 500

@admin_bp.route('/receipts', methods=['GET'])
@login_required
@utils.requires_role('admin')
@utils.limiter.limit("50 per hour")
def manage_receipts():
    """View and manage payment receipts."""
    try:
        db = utils.get_mongo_db()
        if db is None:
            raise Exception("Failed to connect to MongoDB")
        
        # Get all payment receipts with user information
        receipts = list(db.payment_receipts.find().sort('uploaded_at', -1))
        
        # Enrich receipts with user information
        for receipt in receipts:
            receipt['_id'] = str(receipt['_id'])
            user = db.users.find_one({'_id': receipt['user_id']})
            receipt['user_email'] = user.get('email', 'Unknown') if user else 'Unknown'
            receipt['user_display_name'] = user.get('display_name', receipt['user_id']) if user else receipt['user_id']
        
        logger.info(f"Admin {current_user.id} accessed receipts management",
                    extra={'session_id': session.get('sid', 'no-session-id'), 'user_id': current_user.id})
        
        return render_template('admin/receipts.html', receipts=receipts, 
                             title=trans('admin_manage_receipts_title', default='Manage Payment Receipts'))
    except Exception as e:
        logger.error(f"Error fetching receipts for admin {current_user.id}: {str(e)}",
                     extra={'session_id': session.get('sid', 'no-session-id'), 'user_id': current_user.id})
        flash(trans('admin_database_error', default='An error occurred while accessing the database'), 'danger')
        return render_template('error/500.html'), 500

@admin_bp.route('/receipts/approve/<receipt_id>', methods=['POST'])
@login_required
@utils.requires_role('admin')
@utils.limiter.limit("10 per hour")
def approve_receipt(receipt_id):
    """Approve a payment receipt and activate user subscription."""
    try:
        from bson import ObjectId
        db = utils.get_mongo_db()
        if db is None:
            raise Exception("Failed to connect to MongoDB")
        
        receipt = db.payment_receipts.find_one({'_id': ObjectId(receipt_id)})
        if not receipt:
            flash(trans('admin_receipt_not_found', default='Receipt not found'), 'danger')
            return redirect(url_for('admin.manage_receipts'))
        
        # Update receipt status
        db.payment_receipts.update_one(
            {'_id': ObjectId(receipt_id)},
            {'$set': {'status': 'approved', 'approved_by': current_user.id, 'approved_at': datetime.now(timezone.utc)}}
        )
        
        # Activate user subscription
        plan_duration = 30 if receipt['plan_type'] == 'monthly' else 365
        subscription_end = datetime.now(timezone.utc) + timedelta(days=plan_duration)
        
        db.users.update_one(
            {'_id': receipt['user_id']},
            {'$set': {
                'is_subscribed': True,
                'subscription_plan': receipt['plan_type'],
                'subscription_start': datetime.now(timezone.utc),
                'subscription_end': subscription_end,
                'updated_at': datetime.now(timezone.utc)
            }}
        )
        
        # Log the action
        log_audit_action('approve_receipt', {
            'receipt_id': receipt_id,
            'user_id': receipt['user_id'],
            'plan_type': receipt['plan_type'],
            'amount': receipt['amount_paid']
        })
        
        logger.info(f"Admin {current_user.id} approved receipt {receipt_id} for user {receipt['user_id']}",
                    extra={'session_id': session.get('sid', 'no-session-id'), 'user_id': current_user.id})
        
        flash(trans('admin_receipt_approved', default='Receipt approved and subscription activated'), 'success')
        return redirect(url_for('admin.manage_receipts'))
        
    except Exception as e:
        logger.error(f"Error approving receipt {receipt_id}: {str(e)}",
                     extra={'session_id': session.get('sid', 'no-session-id'), 'user_id': current_user.id})
        flash(trans('admin_database_error', default='An error occurred while processing the request'), 'danger')
        return redirect(url_for('admin.manage_receipts'))

@admin_bp.route('/receipts/reject/<receipt_id>', methods=['POST'])
@login_required
@utils.requires_role('admin')
@utils.limiter.limit("10 per hour")
def reject_receipt(receipt_id):
    """Reject a payment receipt."""
    try:
        from bson import ObjectId
        db = utils.get_mongo_db()
        if db is None:
            raise Exception("Failed to connect to MongoDB")
        
        receipt = db.payment_receipts.find_one({'_id': ObjectId(receipt_id)})
        if not receipt:
            flash(trans('admin_receipt_not_found', default='Receipt not found'), 'danger')
            return redirect(url_for('admin.manage_receipts'))
        
        # Get rejection reason
        rejection_reason = request.form.get('rejection_reason', '').strip()
        
        # Update receipt status
        db.payment_receipts.update_one(
            {'_id': ObjectId(receipt_id)},
            {'$set': {
                'status': 'rejected',
                'rejected_by': current_user.id,
                'rejected_at': datetime.now(timezone.utc),
                'rejection_reason': rejection_reason
            }}
        )
        
        # Log the action
        log_audit_action('reject_receipt', {
            'receipt_id': receipt_id,
            'user_id': receipt['user_id'],
            'rejection_reason': rejection_reason
        })
        
        logger.info(f"Admin {current_user.id} rejected receipt {receipt_id} for user {receipt['user_id']}",
                    extra={'session_id': session.get('sid', 'no-session-id'), 'user_id': current_user.id})
        
        flash(trans('admin_receipt_rejected', default='Receipt rejected'), 'success')
        return redirect(url_for('admin.manage_receipts'))
        
    except Exception as e:
        logger.error(f"Error rejecting receipt {receipt_id}: {str(e)}",
                     extra={'session_id': session.get('sid', 'no-session-id'), 'user_id': current_user.id})
        flash(trans('admin_database_error', default='An error occurred while processing the request'), 'danger')
        return redirect(url_for('admin.manage_receipts'))

@admin_bp.route('/users/trials', methods=['GET', 'POST'])
@login_required
@utils.requires_role('admin')
@utils.limiter.limit("50 per hour")
def manage_user_trials():
    """Manage user trials: list all users and update their trial status, including bulk updates."""
    try:
        db = utils.get_mongo_db()
        if db is None:
            raise Exception("Failed to connect to MongoDB")
        users = list(db.users.find())
        form = TrialForm()
        if request.method == 'POST' and form.validate_on_submit():
            # Handle individual trial update
            user_id = request.form.get('user_id')
            if user_id:
                try:
                    ObjectId(user_id)
                    user = db.users.find_one({'_id': ObjectId(user_id)})
                    if user is None:
                        flash(trans('user_not_found', default='User not found'), 'danger')
                        return redirect(url_for('admin.manage_user_trials'))
                    update_data = {
                        'is_trial': form.is_trial.data == 'True',
                        'trial_end': form.trial_end.data if form.trial_end.data else None,
                        'updated_at': datetime.now(timezone.utc)
                    }
                    if form.is_trial.data == 'True' and not form.trial_end.data:
                        update_data['trial_end'] = datetime.now(timezone.utc) + timedelta(days=30)
                    db.users.update_one(
                        {'_id': ObjectId(user_id)},
                        {'$set': update_data}
                    )
                    logger.info(f"User trial updated: id={user_id}, is_trial={update_data['is_trial']}, trial_end={update_data['trial_end']}, admin={current_user.id}",
                                extra={'session_id': session.get('sid', 'no-session-id'), 'user_id': current_user.id})
                    log_audit_action('update_user_trial', {
                        'user_id': user_id,
                        'is_trial': update_data['is_trial'],
                        'trial_end': update_data['trial_end'].strftime('%Y-%m-%d') if update_data['trial_end'] else None
                    })
                    flash(trans('trial_updated', default='User trial updated successfully'), 'success')
                    return redirect(url_for('admin.manage_user_trials'))
                except errors.InvalidId:
                    logger.error(f"Invalid user_id format: {user_id}",
                                 extra={'session_id': session.get('sid', 'no-session-id'), 'user_id': current_user.id})
                    flash(trans('admin_invalid_user_id', default='Invalid user ID'), 'danger')
                    return redirect(url_for('admin.manage_user_trials'))
                except Exception as e:
                    logger.error(f"Error updating user trial {user_id}: {str(e)}",
                                 extra={'session_id': session.get('sid', 'no-session-id'), 'user_id': current_user.id})
                    flash(trans('admin_database_error', default='An error occurred while accessing the database'), 'danger')
                    return render_template('admin/user_trials.html', form=form, users=users, title=trans('admin_manage_user_trials_title', default='Manage User Trials'))
            
            # Handle bulk trial update
            if form.bulk_trial_days.data and form.bulk_trial_start.data and form.bulk_trial_end.data:
                try:
                    days = int(form.bulk_trial_days.data)
                    start_date = form.bulk_trial_start.data
                    end_date = form.bulk_trial_end.data
                    if start_date > end_date:
                        flash(trans('admin_invalid_date_range', default='Start date must be before end date'), 'danger')
                        return redirect(url_for('admin.manage_user_trials'))
                    start_date_aware = datetime.combine(start_date, datetime.min.time(), tzinfo=ZoneInfo("UTC"))
                    end_date_aware = datetime.combine(end_date, datetime.max.time(), tzinfo=ZoneInfo("UTC"))
                    trial_end = datetime.now(timezone.utc) + timedelta(days=days)
                    query = {
                        'created_at': {'$gte': start_date_aware, '$lte': end_date_aware},
                        'role': {'$in': ['trader', 'startup']}
                    }
                    update_data = {
                        'is_trial': True,
                        'trial_end': trial_end,
                        'updated_at': datetime.now(timezone.utc)
                    }
                    result = db.users.update_many(query, {'$set': update_data})
                    updated_count = result.modified_count
                    logger.info(f"Bulk trial update: {updated_count} users updated, days={days}, start={start_date}, end={end_date}, admin={current_user.id}",
                                extra={'session_id': session.get('sid', 'no-session-id'), 'user_id': current_user.id})
                    log_audit_action('bulk_trial_update', {
                        'updated_count': updated_count,
                        'trial_days': days,
                        'registration_start': start_date.strftime('%Y-%m-%d'),
                        'registration_end': end_date.strftime('%Y-%m-%d'),
                        'trial_end': trial_end.strftime('%Y-%m-%d')
                    })
                    flash(trans('bulk_trial_updated', default=f'Successfully updated trial for {updated_count} users'), 'success')
                    return redirect(url_for('admin.manage_user_trials'))
                except Exception as e:
                    logger.error(f"Error in bulk trial update: {str(e)}",
                                 extra={'session_id': session.get('sid', 'no-session-id'), 'user_id': current_user.id})
                    flash(trans('admin_database_error', default='An error occurred while accessing the database'), 'danger')
                    return render_template('admin/user_trials.html', form=form, users=users, title=trans('admin_manage_user_trials_title', default='Manage User Trials'))
        
        for user in users:
            user['_id'] = str(user['_id'])
            trial_end = user.get('trial_end')
            subscription_end = user.get('subscription_end')
            trial_end_aware = trial_end.replace(tzinfo=ZoneInfo("UTC")) if trial_end and trial_end.tzinfo is None else trial_end
            subscription_end_aware = subscription_end.replace(tzinfo=ZoneInfo("UTC")) if subscription_end and subscription_end.tzinfo is None else subscription_end
            user['is_trial_active'] = (
                datetime.now(timezone.utc) <= trial_end_aware if user.get('is_trial') and trial_end_aware
                else user.get('is_subscribed') and subscription_end_aware and datetime.now(timezone.utc) <= subscription_end_aware
            )
        return render_template('admin/user_trials.html', form=form, users=users, title=trans('admin_manage_user_trials_title', default='Manage User Trials'))
    except Exception as e:
        logger.error(f"Error in manage_user_trials for admin {current_user.id}: {str(e)}",
                     extra={'session_id': session.get('sid', 'no-session-id'), 'user_id': current_user.id})
        flash(trans('admin_database_error', default='An error occurred while accessing the database'), 'danger')
        return render_template('error/500.html'), 500

@admin_bp.route('/audit', methods=['GET'])
@login_required
@utils.requires_role('admin')
@utils.limiter.limit("50 per hour")
def audit():
    """View audit logs of admin actions."""
    try:
        db = utils.get_mongo_db()
        if db is None:
            raise Exception("Failed to connect to MongoDB")
        logs = list(db.audit_logs.find().sort('timestamp', -1).limit(100))
        for log in logs:
            log['_id'] = str(log['_id'])
        return render_template('admin/audit.html', logs=logs, title=trans('admin_audit_title', default='Audit Logs'))
    except Exception as e:
        logger.error(f"Error fetching audit logs for admin {current_user.id}: {str(e)}",
                     extra={'session_id': session.get('sid', 'no-session-id'), 'user_id': current_user.id})
        flash(trans('admin_database_error', default='An error occurred while accessing the database'), 'danger')
        return render_template('error/500.html'), 500

@admin_bp.route('/feedback', methods=['GET', 'POST'])
@login_required
@utils.requires_role('admin')
@utils.limiter.limit("50 per hour")
def manage_feedback():
    """View and filter user feedback."""
    try:
        db = utils.get_mongo_db()
        if db is None:
            raise Exception("Failed to connect to MongoDB")
        form = FeedbackFilterForm()
        filter_kwargs = {}
        
        if request.method == 'POST' and form.validate_on_submit():
            if form.tool_name.data:
                filter_kwargs['tool_name'] = form.tool_name.data
            if form.user_id.data:
                filter_kwargs['user_id'] = utils.sanitize_input(form.user_id.data, max_length=50)
        
        feedback_list = [to_dict_feedback(fb) for fb in get_feedback(db, filter_kwargs)]
        for feedback in feedback_list:
            feedback['id'] = str(feedback['id'])
            feedback['timestamp'] = (
                feedback['timestamp'].astimezone(ZoneInfo("UTC")).strftime('%Y-%m-%d %H:%M:%S')
                if feedback['timestamp'] and feedback['timestamp'].tzinfo
                else feedback['timestamp'].replace(tzinfo=ZoneInfo("UTC")).strftime('%Y-%m-%d %H:%M:%S')
                if feedback['timestamp']
                else ''
            )
        
        return render_template(
            'admin/feedback.html',
            form=form,
            feedback_list=feedback_list,
            title=trans('admin_feedback_title', default='Manage Feedback')
        )
    except Exception as e:
        logger.error(f"Error fetching feedback for admin {current_user.id}: {str(e)}",
                     extra={'session_id': session.get('sid', 'no-session-id'), 'user_id': current_user.id})
        flash(trans('admin_database_error', default='An error occurred while accessing the database'), 'danger')
        return render_template('error/500.html'), 500

@admin_bp.route('/debtors', methods=['GET', 'POST'])
@login_required
@utils.requires_role('admin')
@utils.limiter.limit("50 per hour")
def manage_debtors():
    """Manage debtors: list all and add new ones."""
    try:
        db = utils.get_mongo_db()
        if db is None:
            raise Exception("Failed to connect to MongoDB")
        form = DebtorForm()
        if request.method == 'POST' and form.validate_on_submit():
            debtor = {
                'name': utils.sanitize_input(form.name.data, max_length=100),
                'amount': utils.clean_currency(form.amount.data),
                'due_date': form.due_date.data,
                'created_by': current_user.id,
                'created_at': datetime.now(timezone.utc)
            }
            result = db.debtors.insert_one(debtor)
            debtor_id = str(result.inserted_id)
            logger.info(f"Debtor added: id={debtor_id}, name={debtor['name']}, admin={current_user.id}",
                        extra={'session_id': session.get('sid', 'no-session-id'), 'user_id': current_user.id})
            log_audit_action('add_debtor', {'debtor_id': debtor_id, 'name': debtor['name']})
            flash(trans('debtor_added', default='Debtor added successfully'), 'success')
            return redirect(url_for('admin.manage_debtors'))
        
        debtors = list(db.debtors.find().sort('created_at', -1))
        for debtor in debtors:
            debtor['_id'] = str(debtor['_id'])
        return render_template('admin/debtors.html', form=form, debtors=debtors, title=trans('admin_debtors_title', default='Manage Debtors'))
    except Exception as e:
        logger.error(f"Error in manage_debtors for admin {current_user.id}: {str(e)}",
                     extra={'session_id': session.get('sid', 'no-session-id'), 'user_id': current_user.id})
        flash(trans('admin_database_error', default='An error occurred while accessing the database'), 'danger')
        return render_template('error/500.html'), 500

@admin_bp.route('/creditors', methods=['GET', 'POST'])
@login_required
@utils.requires_role('admin')
@utils.limiter.limit("50 per hour")
def manage_creditors():
    """Manage creditors: list all and add new ones."""
    try:
        db = utils.get_mongo_db()
        if db is None:
            raise Exception("Failed to connect to MongoDB")
        form = CreditorForm()
        if request.method == 'POST' and form.validate_on_submit():
            creditor = {
                'name': utils.sanitize_input(form.name.data, max_length=100),
                'amount': utils.clean_currency(form.amount.data),
                'due_date': form.due_date.data,
                'created_by': current_user.id,
                'created_at': datetime.now(timezone.utc)
            }
            result = db.creditors.insert_one(creditor)
            creditor_id = str(result.inserted_id)
            logger.info(f"Creditor added: id={creditor_id}, name={creditor['name']}, admin={current_user.id}",
                        extra={'session_id': session.get('sid', 'no-session-id'), 'user_id': current_user.id})
            log_audit_action('add_creditor', {'creditor_id': creditor_id, 'name': creditor['name']})
            flash(trans('creditor_added', default='Creditor added successfully'), 'success')
            return redirect(url_for('admin.manage_creditors'))
        
        creditors = list(db.creditors.find().sort('created_at', -1))
        for creditor in creditors:
            creditor['_id'] = str(creditor['_id'])
        return render_template('admin/creditors.html', form=form, creditors=creditors, title=trans('admin_creditors_title', default='Manage Creditors'))
    except Exception as e:
        logger.error(f"Error in manage_creditors for admin {current_user.id}: {str(e)}",
                     extra={'session_id': session.get('sid', 'no-session-id'), 'user_id': current_user.id})
        flash(trans('admin_database_error', default='An error occurred while accessing the database'), 'danger')
        return render_template('error/500.html'), 500

@admin_bp.route('/records', methods=['GET'])
@login_required
@utils.requires_role('admin')
@utils.limiter.limit("50 per hour")
def manage_records():
    """View all income/receipt records."""
    try:
        db = utils.get_mongo_db()
        if db is None:
            raise Exception("Failed to connect to MongoDB")
        records = list(get_records(db, {}).sort('created_at', -1))
        for record in records:
            record['_id'] = str(record['_id'])
        return render_template('admin/records.html', records=records, title=trans('admin_records_title', default='Manage Income Records'))
    except Exception as e:
        logger.error(f"Error fetching records for admin {current_user.id}: {str(e)}",
                     extra={'session_id': session.get('sid', 'no-session-id'), 'user_id': current_user.id})
        flash(trans('admin_database_error', default='An error occurred while accessing the database'), 'danger')
        return render_template('error/500.html'), 500

@admin_bp.route('/cashflows', methods=['GET'])
@login_required
@utils.requires_role('admin')
@utils.limiter.limit("50 per hour")
def manage_cashflows():
    """View all payment outflow records."""
    try:
        db = utils.get_mongo_db()
        if db is None:
            raise Exception("Failed to connect to MongoDB")
        cashflows = list(get_cashflows(db, {}).sort('created_at', -1))
        for cashflow in cashflows:
            cashflow['_id'] = str(cashflow['_id'])
        return render_template('admin/cashflows.html', cashflows=cashflows, title=trans('admin_cashflows_title', default='Manage Payment Outflows'))
    except Exception as e:
        logger.error(f"Error fetching cashflows for admin {current_user.id}: {str(e)}",
                     extra={'session_id': session.get('sid', 'no-session-id'), 'user_id': current_user.id})
        flash(trans('admin_database_error', default='An error occurred while accessing the database'), 'danger')
        return render_template('error/500.html'), 500

@admin_bp.route('/funds', methods=['GET', 'POST'])
@login_required
@utils.requires_role('admin')
@utils.limiter.limit("50 per hour")
def manage_funds():
    """Manage funding records: list all and add new ones."""
    try:
        db = utils.get_mongo_db()
        if db is None:
            raise Exception("Failed to connect to MongoDB")
        form = FundForm()
        if request.method == 'POST' and form.validate_on_submit():
            fund = {
                'source': utils.sanitize_input(form.source.data, max_length=100),
                'amount': utils.clean_currency(form.amount.data),
                'received_date': form.received_date.data,
                'created_by': current_user.id,
                'created_at': datetime.now(timezone.utc)
            }
            result = db.funds.insert_one(fund)
            fund_id = str(result.inserted_id)
            logger.info(f"Fund added: id={fund_id}, source={fund['source']}, admin={current_user.id}",
                        extra={'session_id': session.get('sid', 'no-session-id'), 'user_id': current_user.id})
            log_audit_action('add_fund', {'fund_id': fund_id, 'source': fund['source']})
            flash(trans('fund_added', default='Fund added successfully'), 'success')
            return redirect(url_for('admin.manage_funds'))
        
        funds = list(db.funds.find().sort('created_at', -1))
        for fund in funds:
            fund['_id'] = str(fund['_id'])
        return render_template('admin/funds.html', form=form, funds=funds, title=trans('admin_funds_title', default='Manage Funds'))
    except Exception as e:
        logger.error(f"Error in manage_funds for admin {current_user.id}: {str(e)}",
                     extra={'session_id': session.get('sid', 'no-session-id'), 'user_id': current_user.id})
        flash(trans('admin_database_error', default='An error occurred while accessing the database'), 'danger')
        return render_template('error/500.html'), 500

@admin_bp.route('/kyc', methods=['GET'])
@login_required
@utils.requires_role('admin')
@utils.limiter.limit("50 per hour")
def manage_kyc():
    """View and manage KYC submissions."""
    try:
        db = utils.get_mongo_db()
        if db is None:
            raise Exception("Failed to connect to MongoDB")
        kyc_records = list(db.kyc_records.find().sort('created_at', -1))
        for record in kyc_records:
            record['_id'] = str(record['_id'])
        return render_template('kyc/admin.html', kyc_records=kyc_records, title=trans('admin_kyc_title', default='Manage KYC Submissions'))
    except Exception as e:
        logger.error(f"Error fetching KYC records for admin {current_user.id}: {str(e)}",
                     extra={'session_id': session.get('sid', 'no-session-id'), 'user_id': current_user.id})
        flash(trans('admin_database_error', default='An error occurred while accessing the database'), 'danger')
        return render_template('error/500.html'), 500

@admin_bp.route('/reports/customers', methods=['GET'])
@login_required
@utils.requires_role('admin')
@utils.limiter.limit("50 per hour")
def customer_reports():
    """Generate customer reports in HTML, PDF, or CSV format."""
    try:
        db = utils.get_mongo_db()
        if db is None:
            raise Exception("Failed to connect to MongoDB")
        format = request.args.get('format', 'html')
        users = list(db.users.find())
        for user in users:
            user['_id'] = str(user['_id'])
            trial_end = user.get('trial_end')
            subscription_end = user.get('subscription_end')
            trial_end_aware = trial_end.replace(tzinfo=ZoneInfo("UTC")) if trial_end and trial_end.tzinfo is None else trial_end
            subscription_end_aware = subscription_end.replace(tzinfo=ZoneInfo("UTC")) if subscription_end and subscription_end.tzinfo is None else subscription_end
            user['is_trial_active'] = (
                datetime.now(timezone.utc) <= trial_end_aware if user.get('is_trial') and trial_end_aware
                else user.get('is_subscribed') and subscription_end_aware and datetime.now(timezone.utc) <= subscription_end_aware
            )
        
        if format == 'pdf':
            return generate_customer_report_pdf(users)
        elif format == 'csv':
            return generate_customer_report_csv(users)
        
        return render_template('admin/customer_reports.html', users=users, title=trans('admin_customer_reports_title', default='Customer Reports'))
    except Exception as e:
        logger.error(f"Error in customer_reports for admin {current_user.id}: {str(e)}",
                     extra={'session_id': session.get('sid', 'no-session-id'), 'user_id': current_user.id})
        flash(trans('admin_database_error', default='An error occurred while accessing the database'), 'danger')
        return render_template('error/500.html'), 500

@admin_bp.route('/reports/investors', methods=['GET'])
@login_required
@utils.requires_role('admin')
@utils.limiter.limit("50 per hour")
def investor_reports():
    """Generate investor reports summarizing financial health."""
    try:
        db = utils.get_mongo_db()
        if db is None:
            raise Exception("Failed to connect to MongoDB")
        format = request.args.get('format', 'html')
        funds = list(db.funds.find())
        total_funds = sum(fund['amount'] for fund in funds) if funds else 0
        debtors = list(db.debtors.find())
        total_debtors = sum(debtor['amount'] for debtor in debtors) if debtors else 0
        creditors = list(db.creditors.find())
        total_creditors = sum(creditor['amount'] for creditor in creditors) if creditors else 0
        report_data = {
            'total_funds': utils.format_currency(total_funds),
            'total_debtors': utils.format_currency(total_debtors),
            'total_creditors': utils.format_currency(total_creditors),
            'net_position': utils.format_currency(total_funds - total_creditors)
        }
        if format == 'pdf':
            return generate_investor_report_pdf(report_data)
        elif format == 'csv':
            return generate_investor_report_csv(report_data)
        
        return render_template('admin/investor_reports.html', report_data=report_data, title=trans('admin_investor_reports_title', default='Investor Reports'))
    except Exception as e:
        logger.error(f"Error in investor_reports for admin {current_user.id}: {str(e)}",
                     extra={'session_id': session.get('sid', 'no-session-id'), 'user_id': current_user.id})
        flash(trans('admin_database_error', default='An error occurred while accessing the database'), 'danger')
        return render_template('error/500.html'), 500

@admin_bp.route('/forecasts', methods=['GET'])
@login_required
@utils.requires_role('admin')
@utils.limiter.limit("50 per hour")
def manage_forecasts():
    """View basic financial forecasts."""
    try:
        db = utils.get_mongo_db()
        if db is None:
            raise Exception("Failed to connect to MongoDB")
        records = list(get_records(db, {}))
        cashflows = list(get_cashflows(db, {}))
        total_income = sum(record['amount'] for record in records if record['type'] == 'income') if records else 0
        total_expenses = sum(cashflow['amount'] for cashflow in cashflows if cashflow['type'] == 'expense') if cashflows else 0
        forecast = {
            'total_income': utils.format_currency(total_income),
            'total_expenses': utils.format_currency(total_expenses),
            'net_cashflow': utils.format_currency(total_income - total_expenses),
            'projected_income': utils.format_currency(total_income * 1.1),
            'projected_expenses': utils.format_currency(total_expenses * 1.1)
        }
        return render_template('admin/forecasts.html', forecast=forecast, title=trans('admin_forecasts_title', default='Financial Forecasts'))
    except Exception as e:
        logger.error(f"Error generating forecasts for admin {current_user.id}: {str(e)}",
                     extra={'session_id': session.get('sid', 'no-session-id'), 'user_id': current_user.id})
        flash(trans('admin_database_error', default='An error occurred while accessing the database'), 'danger')
        return render_template('error/500.html'), 500

@admin_bp.route('/waitlist', methods=['GET'])
@login_required
@utils.requires_role('admin')
def view_waitlist():
    try:
        db = utils.get_mongo_db()
        entries = get_waitlist_entries(db, {})
        return render_template('admin/waitlist.html', entries=[to_dict_waitlist(e) for e in entries])
    except Exception as e:
        logger.error(f"Error viewing waitlist: {str(e)}", exc_info=True)
        flash(trans('general_error', default='An error occurred while loading the waitlist'))
        return redirect(url_for('home'))

@admin_bp.route('/waitlist/export', methods=['GET'])
@login_required
@utils.requires_role('admin')
def export_waitlist():
    try:
        db = utils.get_mongo_db()
        entries = get_waitlist_entries(db, {})
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(['ID', 'Full Name', 'WhatsApp Number', 'Email', 'Business Type', 'Created At', 'Updated At'])
        for entry in entries:
            dict_entry = to_dict_waitlist(entry)
            writer.writerow([
                dict_entry['id'],
                dict_entry['full_name'],
                dict_entry['whatsapp_number'],
                dict_entry['email'],
                dict_entry['business_type'],
                dict_entry['created_at'],
                dict_entry['updated_at']
            ])
        output.seek(0)
        return send_file(
            io.BytesIO(output.getvalue().encode('utf-8')),
            mimetype='text/csv',
            as_attachment=True,
            download_name=f'waitlist_{datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")}.csv'
        )
    except Exception as e:
        logger.error(f"Error exporting waitlist: {str(e)}", exc_info=True)
        flash(trans('general_error', default='An error occurred while exporting the waitlist'))
        return redirect(url_for('admin.view_waitlist'))

@admin_bp.route('/waitlist/contact/<string:entry_id>', methods=['GET', 'POST'])
@login_required
@utils.requires_role('admin')
def contact_waitlist_entry(entry_id):
    """Contact a waitlist entry."""
    try:
        db = utils.get_mongo_db()
        if db is None:
            raise Exception("Failed to connect to MongoDB")
        
        entry = db.waitlist.find_one({'_id': entry_id})
        if not entry:
            flash(trans('admin_waitlist_entry_not_found', default='Waitlist entry not found'), 'danger')
            return redirect(url_for('admin.view_waitlist'))
        
        if request.method == 'POST':
            # Handle contact form submission
            message = request.form.get('message', '')
            if message:
                # Update entry with contact attempt
                db.waitlist.update_one(
                    {'_id': entry_id},
                    {
                        '$set': {
                            'contacted': True,
                            'contact_message': message,
                            'contacted_by': current_user.id,
                            'contacted_at': datetime.now(timezone.utc)
                        }
                    }
                )
                
                log_audit_action('contact_waitlist_entry', {
                    'entry_id': entry_id,
                    'email': entry.get('email'),
                    'message': message
                })
                
                flash(trans('admin_waitlist_contact_sent', default='Contact message recorded successfully'), 'success')
                return redirect(url_for('admin.view_waitlist'))
        
        return render_template('admin/contact.html', entry=entry, 
                             title=trans('admin_contact_waitlist_entry', default='Contact Waitlist Entry'))
    
    except Exception as e:
        logger.error(f"Error contacting waitlist entry {entry_id}: {str(e)}",
                     extra={'session_id': session.get('sid', 'no-session-id'), 'user_id': current_user.id})
        flash(trans('admin_database_error', default='An error occurred while accessing the database'), 'danger')
        return redirect(url_for('admin.view_waitlist'))

# Tax Configuration Management Routes
@admin_bp.route('/tax/config', methods=['GET'])
@login_required
@utils.requires_role('admin')
@utils.limiter.limit("30 per hour")
def tax_config():
    """Tax configuration management dashboard."""
    try:
        from admin_tax_config import get_tax_rates, get_tax_bands, get_tax_exemptions
        
        current_year = datetime.now().year
        
        # Get current tax configurations
        tax_rates = get_tax_rates(current_year)
        tax_bands = get_tax_bands(current_year)
        tax_exemptions = get_tax_exemptions(current_year)
        
        logger.info(f"Admin {current_user.id} accessed tax configuration",
                    extra={'session_id': session.get('sid', 'no-session-id'), 'user_id': current_user.id})
        
        return render_template('admin/tax_config.html',
                             tax_rates=tax_rates,
                             tax_bands=tax_bands,
                             tax_exemptions=tax_exemptions,
                             current_year=current_year,
                             title=trans('admin_tax_config', default='Tax Configuration'))
    
    except Exception as e:
        logger.error(f"Error loading tax configuration for admin {current_user.id}: {str(e)}",
                     extra={'session_id': session.get('sid', 'no-session-id'), 'user_id': current_user.id})
        flash(trans('admin_tax_config_error', default='An error occurred while loading tax configuration'), 'danger')
        return render_template('error/500.html'), 500

@admin_bp.route('/tax/rates', methods=['GET', 'POST'])
@login_required
@utils.requires_role('admin')
@utils.limiter.limit("20 per hour")
def manage_tax_rates():
    """Manage tax rates configuration."""
    try:
        from admin_tax_config import TaxRateForm, get_tax_rates, save_tax_rate
        
        form = TaxRateForm()
        
        if request.method == 'POST' and form.validate_on_submit():
            success = save_tax_rate(
                form.entity_type.data,
                form.tax_year.data,
                form.rate_percentage.data,
                form.description.data,
                current_user.id
            )
            
            if success:
                flash(trans('admin_tax_rate_saved', default='Tax rate saved successfully'), 'success')
                log_audit_action('update_tax_rate', {
                    'entity_type': form.entity_type.data,
                    'tax_year': form.tax_year.data,
                    'rate_percentage': form.rate_percentage.data
                })
            else:
                flash(trans('admin_tax_rate_error', default='Error saving tax rate'), 'danger')
            
            return redirect(url_for('admin.manage_tax_rates'))
        
        # Get all tax rates for display
        tax_rates = get_tax_rates()
        
        return render_template('admin/tax_rates.html',
                             form=form,
                             tax_rates=tax_rates,
                             title=trans('admin_manage_tax_rates', default='Manage Tax Rates'))
    
    except Exception as e:
        logger.error(f"Error managing tax rates for admin {current_user.id}: {str(e)}",
                     extra={'session_id': session.get('sid', 'no-session-id'), 'user_id': current_user.id})
        flash(trans('admin_tax_rates_error', default='An error occurred while managing tax rates'), 'danger')
        return render_template('error/500.html'), 500

@admin_bp.route('/tax/bands', methods=['GET', 'POST'])
@login_required
@utils.requires_role('admin')
@utils.limiter.limit("20 per hour")
def manage_tax_bands():
    """Manage progressive tax bands configuration."""
    try:
        from admin_tax_config import TaxBandForm, get_tax_bands, save_tax_band
        
        form = TaxBandForm()
        
        if request.method == 'POST' and form.validate_on_submit():
            success = save_tax_band(
                form.tax_year.data,
                form.band_min.data,
                form.band_max.data,
                form.rate_percentage.data,
                form.description.data,
                current_user.id
            )
            
            if success:
                flash(trans('admin_tax_band_saved', default='Tax band saved successfully'), 'success')
                log_audit_action('create_tax_band', {
                    'tax_year': form.tax_year.data,
                    'band_min': form.band_min.data,
                    'band_max': form.band_max.data,
                    'rate_percentage': form.rate_percentage.data
                })
            else:
                flash(trans('admin_tax_band_error', default='Error saving tax band'), 'danger')
            
            return redirect(url_for('admin.manage_tax_bands'))
        
        # Get all tax bands for display
        tax_bands = get_tax_bands()
        
        return render_template('admin/tax_bands.html',
                             form=form,
                             tax_bands=tax_bands,
                             title=trans('admin_manage_tax_bands', default='Manage Tax Bands'))
    
    except Exception as e:
        logger.error(f"Error managing tax bands for admin {current_user.id}: {str(e)}",
                     extra={'session_id': session.get('sid', 'no-session-id'), 'user_id': current_user.id})
        flash(trans('admin_tax_bands_error', default='An error occurred while managing tax bands'), 'danger')
        return render_template('error/500.html'), 500

@admin_bp.route('/tax/exemptions', methods=['GET', 'POST'])
@login_required
@utils.requires_role('admin')
@utils.limiter.limit("20 per hour")
def manage_tax_exemptions():
    """Manage tax exemptions configuration."""
    try:
        from admin_tax_config import TaxExemptionForm, get_tax_exemptions, save_tax_exemption
        
        form = TaxExemptionForm()
        
        if request.method == 'POST' and form.validate_on_submit():
            success = save_tax_exemption(
                form.entity_type.data,
                form.tax_year.data,
                form.exemption_threshold.data,
                form.exemption_type.data,
                form.description.data,
                current_user.id
            )
            
            if success:
                flash(trans('admin_tax_exemption_saved', default='Tax exemption saved successfully'), 'success')
                log_audit_action('update_tax_exemption', {
                    'entity_type': form.entity_type.data,
                    'tax_year': form.tax_year.data,
                    'exemption_threshold': form.exemption_threshold.data,
                    'exemption_type': form.exemption_type.data
                })
            else:
                flash(trans('admin_tax_exemption_error', default='Error saving tax exemption'), 'danger')
            
            return redirect(url_for('admin.manage_tax_exemptions'))
        
        # Get all tax exemptions for display
        tax_exemptions = get_tax_exemptions()
        
        return render_template('admin/tax_exemptions.html',
                             form=form,
                             tax_exemptions=tax_exemptions,
                             title=trans('admin_manage_tax_exemptions', default='Manage Tax Exemptions'))
    
    except Exception as e:
        logger.error(f"Error managing tax exemptions for admin {current_user.id}: {str(e)}",
                     extra={'session_id': session.get('sid', 'no-session-id'), 'user_id': current_user.id})
        flash(trans('admin_tax_exemptions_error', default='An error occurred while managing tax exemptions'), 'danger')
        return render_template('error/500.html'), 500

@admin_bp.route('/system/settings', methods=['GET', 'POST'])
@login_required
@utils.requires_role('admin')
@utils.limiter.limit("20 per hour")
def system_settings():
    """System settings management."""
    try:
        db = utils.get_mongo_db()
        if db is None:
            raise Exception("Failed to connect to MongoDB")
        
        if request.method == 'POST':
            # Handle system settings updates
            settings_data = {
                'maintenance_mode': request.form.get('maintenance_mode') == 'on',
                'registration_enabled': request.form.get('registration_enabled') == 'on',
                'trial_duration_days': int(request.form.get('trial_duration_days', 30)),
                'max_users_per_trial': int(request.form.get('max_users_per_trial', 1000)),
                'updated_by': current_user.id,
                'updated_at': datetime.now(timezone.utc)
            }
            
            # Update system settings
            db.system_config.update_one(
                {'_id': 'app_settings'},
                {'$set': settings_data, '$setOnInsert': {'created_at': datetime.now(timezone.utc)}},
                upsert=True
            )
            
            log_audit_action('update_system_settings', settings_data)
            flash(trans('admin_system_settings_saved', default='System settings saved successfully'), 'success')
            return redirect(url_for('admin.system_settings'))
        
        # Get current system settings
        current_settings = db.system_config.find_one({'_id': 'app_settings'}) or {}
        
        return render_template('admin/system_settings.html',
                             settings=current_settings,
                             title=trans('admin_system_settings', default='System Settings'))
    
    except Exception as e:
        logger.error(f"Error managing system settings for admin {current_user.id}: {str(e)}",
                     extra={'session_id': session.get('sid', 'no-session-id'), 'user_id': current_user.id})
        flash(trans('admin_system_settings_error', default='An error occurred while managing system settings'), 'danger')
        return render_template('error/500.html'), 500
def contact_signup(entry_id):
    try:
        db = utils.get_mongo_db()
        entry = db.waitlist.find_one({'_id': ObjectId(entry_id)})
        if not entry:
            flash(trans('general_not_found', default='Waitlist entry not found'))
            return redirect(url_for('admin.view_waitlist'))
        
        dict_entry = to_dict_waitlist(entry)
        
        if request.method == 'POST':
            message = request.form.get('message')
            method = request.form.get('method')  # 'email' or 'whatsapp'
            
            if not message or not method:
                flash(trans('general_missing_fields', default='Missing required fields'))
                return render_template('admin/contact.html', entry=dict_entry)
            
            # Placeholder for sending message
            # Implement actual sending logic here, e.g., using external services
            # For email: send_email(dict_entry['email'], 'Message from Admin', message)
            # For whatsapp: send_whatsapp(dict_entry['whatsapp_number'], message)
            # Assuming send_email and send_whatsapp are defined in utils.py or similar
            
            # Log the action
            audit_data = {
                'admin_id': current_user.id,
                'action': f'Contacted waitlist signup via {method}',
                'details': {'entry_id': entry_id, 'method': method, 'message': message},
                'timestamp': datetime.now(timezone.utc)
            }
            log_audit_action('contact_waitlist', audit_data['details'])
            
            flash(trans('general_message_sent', default='Message sent successfully'))
            return redirect(url_for('admin.view_waitlist'))
        
        return render_template('admin/contact.html', entry=dict_entry)
    except Exception as e:
        logger.error(f"Error contacting waitlist signup {entry_id}: {str(e)}", exc_info=True)
        flash(trans('general_error', default='An error occurred while contacting the signup'))
        return redirect(url_for('admin.view_waitlist'))

def generate_customer_report_pdf(users):
    """Generate a PDF report of customer data."""
    try:
        buffer = BytesIO()
        p = canvas.Canvas(buffer, pagesize=A4)
        p.setFont("Helvetica", 12)
        p.drawString(1 * inch, 10.5 * inch, trans('admin_customer_report_title', default='Customer Report'))
        p.drawString(1 * inch, 10.2 * inch, f"{trans('admin_generated_on', default='Generated on')}: {datetime.now(timezone.utc).strftime('%Y-%m-%d')}")
        y = 9.5 * inch
        p.drawString(1 * inch, y, trans('admin_username', default='Username'))
        p.drawString(2.5 * inch, y, trans('admin_email', default='Email'))
        p.drawString(4 * inch, y, trans('user_role', default='Role'))
        p.drawString(5.5 * inch, y, trans('subscription_status', default='Subscription Status'))
        y -= 0.3 * inch
        for user in users:
            status = 'Subscribed' if user.get('is_subscribed') and user.get('is_trial_active') else 'Trial' if user.get('is_trial') and user.get('is_trial_active') else 'Expired'
            p.drawString(1 * inch, y, user['_id'])
            p.drawString(2.5 * inch, y, user['email'])
            p.drawString(4 * inch, y, user['role'])
            p.drawString(5.5 * inch, y, status)
            y -= 0.3 * inch
            if y < 1 * inch:
                p.showPage()
                p.setFont("Helvetica", 12)
                y = 10.5 * inch
        p.showPage()
        p.save()
        buffer.seek(0)
        return Response(buffer, mimetype='application/pdf', headers={'Content-Disposition': 'attachment;filename=customer_report.pdf'})
    except Exception as e:
        logger.error(f"Error generating customer report PDF: {str(e)}",
                     extra={'session_id': session.get('sid', 'no-session-id'), 'user_id': current_user.id})
        flash(trans('admin_report_error', default='An error occurred while generating the report'), 'danger')
        return render_template('error/500.html'), 500

def generate_customer_report_csv(users):
    """Generate a CSV report of customer data."""
    try:
        output = [[trans('admin_username', default='Username'), trans('admin_email', default='Email'), trans('user_role', default='Role'), trans('subscription_status', default='Subscription Status')]]
        for user in users:
            status = 'Subscribed' if user.get('is_subscribed') and user.get('is_trial_active') else 'Trial' if user.get('is_trial') and user.get('is_trial_active') else 'Expired'
            output.append([user['_id'], user['email'], user['role'], status])
        buffer = BytesIO()
        writer = csv.writer(buffer, lineterminator='\n')
        writer.writerows(output)
        buffer.seek(0)
        return Response(buffer, mimetype='text/csv', headers={'Content-Disposition': 'attachment;filename=customer_report.csv'})
    except Exception as e:
        logger.error(f"Error generating customer report CSV: {str(e)}",
                     extra={'session_id': session.get('sid', 'no-session-id'), 'user_id': current_user.id})
        flash(trans('admin_report_error', default='An error occurred while generating the report'), 'danger')
        return render_template('error/500.html'), 500

def generate_investor_report_pdf(report_data):
    """Generate a PDF report for investors."""
    try:
        buffer = BytesIO()
        p = canvas.Canvas(buffer, pagesize=A4)
        p.setFont("Helvetica", 12)
        p.drawString(1 * inch, 10.5 * inch, trans('admin_investor_report_title', default='Investor Report'))
        p.drawString(1 * inch, 10.2 * inch, f"{trans('admin_generated_on', default='Generated on')}: {datetime.now(timezone.utc).strftime('%Y-%m-%d')}")
        y = 9.5 * inch
        p.drawString(1 * inch, y, trans('fund_total', default='Total Funds'))
        p.drawString(3 * inch, y, report_data['total_funds'])
        y -= 0.3 * inch
        p.drawString(1 * inch, y, trans('debtor_total', default='Total Debtors'))
        p.drawString(3 * inch, y, report_data['total_debtors'])
        y -= 0.3 * inch
        p.drawString(1 * inch, y, trans('creditor_total', default='Total Creditors'))
        p.drawString(3 * inch, y, report_data['total_creditors'])
        y -= 0.3 * inch
        p.drawString(1 * inch, y, trans('net_position', default='Net Position'))
        p.drawString(3 * inch, y, report_data['net_position'])
        p.showPage()
        p.save()
        buffer.seek(0)
        return Response(buffer, mimetype='application/pdf', headers={'Content-Disposition': 'attachment;filename=investor_report.pdf'})
    except Exception as e:
        logger.error(f"Error generating investor report PDF: {str(e)}",
                     extra={'session_id': session.get('sid', 'no-session-id'), 'user_id': current_user.id})
        flash(trans('admin_report_error', default='An error occurred while generating the report'), 'danger')
        return render_template('error/500.html'), 500

def generate_investor_report_csv(report_data):
    """Generate a CSV report for investors."""
    try:
        output = [
            [trans('fund_total', default='Total Funds'), report_data['total_funds']],
            [trans('debtor_total', default='Total Debtors'), report_data['total_debtors']],
            [trans('creditor_total', default='Total Creditors'), report_data['total_creditors']],
            [trans('net_position', default='Net Position'), report_data['net_position']]
        ]
        buffer = BytesIO()
        writer = csv.writer(buffer, lineterminator='\n')
        writer.writerows(output)
        buffer.seek(0)
        return Response(buffer, mimetype='text/csv', headers={'Content-Disposition': 'attachment;filename=investor_report.csv'})
    except Exception as e:
        logger.error(f"Error generating investor report CSV: {str(e)}",
                     extra={'session_id': session.get('sid', 'no-session-id'), 'user_id': current_user.id})
        flash(trans('admin_report_error', default='An error occurred while generating the report'), 'danger')
        return render_template('error/500.html'), 500

# Tax Configuration Management Routes
@admin_bp.route('/tax/config', methods=['GET'])
@login_required
@utils.requires_role('admin')
@utils.limiter.limit("50 per hour")
def tax_config():
    """Tax configuration management dashboard."""
    try:
        from admin_tax_config import get_tax_rates, get_tax_bands, get_tax_exemptions
        
        db = utils.get_mongo_db()
        if db is None:
            raise Exception("Failed to connect to MongoDB")
        
        # Get current tax configuration
        current_year = datetime.now().year
        tax_rates = get_tax_rates(current_year)
        tax_bands = get_tax_bands(current_year)
        tax_exemptions = get_tax_exemptions(current_year)
        
        stats = {
            'tax_rates': len(tax_rates),
            'tax_bands': len(tax_bands),
            'tax_exemptions': len(tax_exemptions),
            'current_year': current_year
        }
        
        logger.info(f"Admin {current_user.id} accessed tax configuration",
                    extra={'session_id': session.get('sid', 'no-session-id'), 'user_id': current_user.id})
        
        return render_template('admin/tax_config.html', 
                             stats=stats,
                             tax_rates=tax_rates,
                             tax_bands=tax_bands,
                             tax_exemptions=tax_exemptions,
                             title=trans('admin_tax_config_title', default='Tax Configuration Management'))
    except Exception as e:
        logger.error(f"Error loading tax configuration for admin {current_user.id}: {str(e)}",
                     extra={'session_id': session.get('sid', 'no-session-id'), 'user_id': current_user.id})
        flash(trans('admin_database_error', default='An error occurred while accessing the database'), 'danger')
        return render_template('error/500.html'), 500

@admin_bp.route('/tax/rates', methods=['GET', 'POST'])
@login_required
@utils.requires_role('admin')
@utils.limiter.limit("50 per hour")
def manage_tax_rates():
    """Manage tax rates configuration."""
    try:
        from admin_tax_config import TaxRateForm, get_tax_rates, save_tax_rate
        
        form = TaxRateForm()
        
        if request.method == 'POST' and form.validate_on_submit():
            success = save_tax_rate(
                form.entity_type.data,
                form.tax_year.data,
                form.rate_percentage.data,
                form.description.data,
                current_user.id
            )
            
            if success:
                flash(trans('admin_tax_rate_saved', default='Tax rate saved successfully'), 'success')
                log_audit_action('save_tax_rate', {
                    'entity_type': form.entity_type.data,
                    'tax_year': form.tax_year.data,
                    'rate_percentage': form.rate_percentage.data
                })
            else:
                flash(trans('admin_tax_rate_error', default='Error saving tax rate'), 'danger')
            
            return redirect(url_for('admin.manage_tax_rates'))
        
        # Get all tax rates
        tax_rates = get_tax_rates()
        
        return render_template('admin/tax_rates.html',
                             form=form,
                             tax_rates=tax_rates,
                             title=trans('admin_manage_tax_rates_title', default='Manage Tax Rates'))
    except Exception as e:
        logger.error(f"Error in manage_tax_rates for admin {current_user.id}: {str(e)}",
                     extra={'session_id': session.get('sid', 'no-session-id'), 'user_id': current_user.id})
        flash(trans('admin_database_error', default='An error occurred while accessing the database'), 'danger')
        return render_template('error/500.html'), 500

@admin_bp.route('/tax/bands', methods=['GET', 'POST'])
@login_required
@utils.requires_role('admin')
@utils.limiter.limit("50 per hour")
def manage_tax_bands():
    """Manage progressive tax bands configuration."""
    try:
        from admin_tax_config import TaxBandForm, get_tax_bands, save_tax_band
        
        form = TaxBandForm()
        
        if request.method == 'POST' and form.validate_on_submit():
            success = save_tax_band(
                form.tax_year.data,
                form.band_min.data,
                form.band_max.data,
                form.rate_percentage.data,
                form.description.data,
                current_user.id
            )
            
            if success:
                flash(trans('admin_tax_band_saved', default='Tax band saved successfully'), 'success')
                log_audit_action('save_tax_band', {
                    'tax_year': form.tax_year.data,
                    'band_min': form.band_min.data,
                    'band_max': form.band_max.data,
                    'rate_percentage': form.rate_percentage.data
                })
            else:
                flash(trans('admin_tax_band_error', default='Error saving tax band'), 'danger')
            
            return redirect(url_for('admin.manage_tax_bands'))
        
        # Get all tax bands
        tax_bands = get_tax_bands()
        
        return render_template('admin/tax_bands.html',
                             form=form,
                             tax_bands=tax_bands,
                             title=trans('admin_manage_tax_bands_title', default='Manage Tax Bands'))
    except Exception as e:
        logger.error(f"Error in manage_tax_bands for admin {current_user.id}: {str(e)}",
                     extra={'session_id': session.get('sid', 'no-session-id'), 'user_id': current_user.id})
        flash(trans('admin_database_error', default='An error occurred while accessing the database'), 'danger')
        return render_template('error/500.html'), 500

@admin_bp.route('/tax/exemptions', methods=['GET', 'POST'])
@login_required
@utils.requires_role('admin')
@utils.limiter.limit("50 per hour")
def manage_tax_exemptions():
    """Manage tax exemptions configuration."""
    try:
        from admin_tax_config import TaxExemptionForm, get_tax_exemptions, save_tax_exemption
        
        form = TaxExemptionForm()
        
        if request.method == 'POST' and form.validate_on_submit():
            success = save_tax_exemption(
                form.entity_type.data,
                form.tax_year.data,
                form.exemption_threshold.data,
                form.exemption_type.data,
                form.description.data,
                current_user.id
            )
            
            if success:
                flash(trans('admin_tax_exemption_saved', default='Tax exemption saved successfully'), 'success')
                log_audit_action('save_tax_exemption', {
                    'entity_type': form.entity_type.data,
                    'tax_year': form.tax_year.data,
                    'exemption_threshold': form.exemption_threshold.data,
                    'exemption_type': form.exemption_type.data
                })
            else:
                flash(trans('admin_tax_exemption_error', default='Error saving tax exemption'), 'danger')
            
            return redirect(url_for('admin.manage_tax_exemptions'))
        
        # Get all tax exemptions
        tax_exemptions = get_tax_exemptions()
        
        return render_template('admin/tax_exemptions.html',
                             form=form,
                             tax_exemptions=tax_exemptions,
                             title=trans('admin_manage_tax_exemptions_title', default='Manage Tax Exemptions'))
    except Exception as e:
        logger.error(f"Error in manage_tax_exemptions for admin {current_user.id}: {str(e)}",
                     extra={'session_id': session.get('sid', 'no-session-id'), 'user_id': current_user.id})
        flash(trans('admin_database_error', default='An error occurred while accessing the database'), 'danger')
        return render_template('error/500.html'), 500

# System Settings Management
@admin_bp.route('/system/settings', methods=['GET', 'POST'])
@login_required
@utils.requires_role('admin')
@utils.limiter.limit("50 per hour")
def system_settings():
    """System settings management."""
    try:
        db = utils.get_mongo_db()
        if db is None:
            raise Exception("Failed to connect to MongoDB")
        
        if request.method == 'POST':
            # Handle system settings updates
            settings_data = {
                'maintenance_mode': request.form.get('maintenance_mode') == 'on',
                'registration_enabled': request.form.get('registration_enabled') == 'on',
                'trial_duration_days': int(request.form.get('trial_duration_days', 30)),
                'max_users_per_trial': int(request.form.get('max_users_per_trial', 1000)),
                'updated_by': current_user.id,
                'updated_at': datetime.now(timezone.utc)
            }
            
            # Update or create system settings
            db.system_settings.update_one(
                {'_id': 'global'},
                {'$set': settings_data},
                upsert=True
            )
            
            log_audit_action('update_system_settings', settings_data)
            flash(trans('admin_system_settings_updated', default='System settings updated successfully'), 'success')
            
            return redirect(url_for('admin.system_settings'))
        
        # Get current system settings
        settings = db.system_settings.find_one({'_id': 'global'}) or {}
        
        # Get system statistics
        stats = {
            'total_users': db.users.count_documents({}),
            'active_trials': db.users.count_documents({'is_trial': True}),
            'active_subscriptions': db.users.count_documents({'is_subscribed': True}),
            'total_records': db.records.count_documents({}),
            'total_feedback': db.feedback.count_documents({}),
            'database_size': len(db.list_collection_names())
        }
        
        logger.info(f"Admin {current_user.id} accessed system settings",
                    extra={'session_id': session.get('sid', 'no-session-id'), 'user_id': current_user.id})
        
        return render_template('admin/system_settings.html',
                             settings=settings,
                             stats=stats,
                             title=trans('admin_system_settings_title', default='System Settings'))
    except Exception as e:
        logger.error(f"Error in system_settings for admin {current_user.id}: {str(e)}",
                     extra={'session_id': session.get('sid', 'no-session-id'), 'user_id': current_user.id})
        flash(trans('admin_database_error', default='An error occurred while accessing the database'), 'danger')
        return render_template('error/500.html'), 500

# Analytics Dashboard
@admin_bp.route('/analytics', methods=['GET'])
@login_required
@utils.requires_role('admin')
@utils.limiter.limit("50 per hour")
def analytics_dashboard():
    """Advanced analytics dashboard."""
    try:
        db = utils.get_mongo_db()
        if db is None:
            raise Exception("Failed to connect to MongoDB")
        
        # Get date range from query parameters
        days = int(request.args.get('days', 30))
        start_date = datetime.now(timezone.utc) - timedelta(days=days)
        
        # User analytics
        user_analytics = {
            'new_registrations': db.users.count_documents({
                'created_at': {'$gte': start_date}
            }),
            'trial_conversions': db.users.count_documents({
                'is_subscribed': True,
                'subscription_start': {'$gte': start_date}
            }),
            'active_users': db.users.count_documents({
                'last_login': {'$gte': start_date}
            }) if 'last_login' in db.users.find_one({}) or {} else 0
        }
        
        # Revenue analytics
        revenue_analytics = {
            'monthly_revenue': db.payment_receipts.count_documents({
                'status': 'approved',
                'plan_type': 'monthly',
                'approved_at': {'$gte': start_date}
            }) * 1000,  # NGN 1,000 per monthly subscription
            'yearly_revenue': db.payment_receipts.count_documents({
                'status': 'approved',
                'plan_type': 'yearly',
                'approved_at': {'$gte': start_date}
            }) * 10000,  # NGN 10,000 per yearly subscription
        }
        revenue_analytics['total_revenue'] = revenue_analytics['monthly_revenue'] + revenue_analytics['yearly_revenue']
        
        # Usage analytics
        usage_analytics = {
            'total_transactions': db.records.count_documents({
                'created_at': {'$gte': start_date}
            }),
            'voice_commands': db.records.count_documents({
                'input_method': 'voice',
                'created_at': {'$gte': start_date}
            }),
            'feedback_submissions': db.feedback.count_documents({
                'timestamp': {'$gte': start_date}
            })
        }
        
        # System performance
        performance_metrics = {
            'database_collections': len(db.list_collection_names()),
            'total_documents': sum(db[collection].count_documents({}) 
                                 for collection in db.list_collection_names()),
            'audit_logs': db.audit_logs.count_documents({
                'timestamp': {'$gte': start_date}
            })
        }
        
        logger.info(f"Admin {current_user.id} accessed analytics dashboard",
                    extra={'session_id': session.get('sid', 'no-session-id'), 'user_id': current_user.id})
        
        return render_template('admin/analytics.html',
                             user_analytics=user_analytics,
                             revenue_analytics=revenue_analytics,
                             usage_analytics=usage_analytics,
                             performance_metrics=performance_metrics,
                             days=days,
                             title=trans('admin_analytics_title', default='Analytics Dashboard'))
    except Exception as e:
        logger.error(f"Error in analytics_dashboard for admin {current_user.id}: {str(e)}",
                     extra={'session_id': session.get('sid', 'no-session-id'), 'user_id': current_user.id})
        flash(trans('admin_database_error', default='An error occurred while accessing the database'), 'danger')
        return render_template('error/500.html'), 500

# Language Management
@admin_bp.route('/language/toggle/<user_id>/<language>', methods=['POST'])
@login_required
@utils.requires_role('admin')
@utils.limiter.limit("10 per hour")
def toggle_user_language(user_id, language):
    """Toggle user language between English and Hausa."""
    try:
        if language not in ['en', 'ha']:
            flash(trans('admin_invalid_language', default='Invalid language selected'), 'danger')
            return redirect(url_for('admin.manage_users'))
        
        db = utils.get_mongo_db()
        if db is None:
            raise Exception("Failed to connect to MongoDB")
        
        # Update user language preference
        result = db.users.update_one(
            {'_id': ObjectId(user_id)},
            {'$set': {
                'language': language,
                'updated_at': datetime.now(timezone.utc)
            }}
        )
        
        if result.modified_count > 0:
            log_audit_action('toggle_user_language', {
                'user_id': user_id,
                'language': language
            })
            flash(trans('admin_language_updated', default=f'User language updated to {language.upper()}'), 'success')
        else:
            flash(trans('admin_user_not_found', default='User not found'), 'danger')
        
        return redirect(url_for('admin.manage_users'))
        
    except Exception as e:
        logger.error(f"Error toggling user language for {user_id}: {str(e)}",
                     extra={'session_id': session.get('sid', 'no-session-id'), 'user_id': current_user.id})
        flash(trans('admin_database_error', default='An error occurred while updating language'), 'danger')
        return redirect(url_for('admin.manage_users'))

# Bulk Operations
@admin_bp.route('/bulk/operations', methods=['GET', 'POST'])
@login_required
@utils.requires_role('admin')
@utils.limiter.limit("10 per hour")
def bulk_operations():
    """Bulk operations for user management."""
    try:
        db = utils.get_mongo_db()
        if db is None:
            raise Exception("Failed to connect to MongoDB")
        
        if request.method == 'POST':
            operation = request.form.get('operation')
            user_ids = request.form.getlist('user_ids')
            
            if not user_ids:
                flash(trans('admin_no_users_selected', default='No users selected'), 'danger')
                return redirect(url_for('admin.bulk_operations'))
            
            results = {'success': 0, 'failed': 0}
            
            for user_id in user_ids:
                try:
                    if operation == 'extend_trial':
                        days = int(request.form.get('trial_days', 30))
                        new_trial_end = datetime.now(timezone.utc) + timedelta(days=days)
                        db.users.update_one(
                            {'_id': ObjectId(user_id)},
                            {'$set': {
                                'is_trial': True,
                                'trial_end': new_trial_end,
                                'updated_at': datetime.now(timezone.utc)
                            }}
                        )
                        results['success'] += 1
                    
                    elif operation == 'suspend_users':
                        db.users.update_one(
                            {'_id': ObjectId(user_id)},
                            {'$set': {
                                'suspended': True,
                                'updated_at': datetime.now(timezone.utc)
                            }}
                        )
                        results['success'] += 1
                    
                    elif operation == 'activate_users':
                        db.users.update_one(
                            {'_id': ObjectId(user_id)},
                            {'$set': {
                                'suspended': False,
                                'updated_at': datetime.now(timezone.utc)
                            }}
                        )
                        results['success'] += 1
                        
                except Exception as e:
                    logger.error(f"Error in bulk operation {operation} for user {user_id}: {str(e)}")
                    results['failed'] += 1
            
            log_audit_action('bulk_operation', {
                'operation': operation,
                'user_count': len(user_ids),
                'success_count': results['success'],
                'failed_count': results['failed']
            })
            
            flash(trans('admin_bulk_operation_complete', 
                       default=f'Bulk operation completed: {results["success"]} successful, {results["failed"]} failed'), 
                  'success' if results['failed'] == 0 else 'warning')
            
            return redirect(url_for('admin.bulk_operations'))
        
        # Get users for bulk operations
        users = list(db.users.find({'role': {'$ne': 'admin'}}).sort('created_at', -1))
        for user in users:
            user['_id'] = str(user['_id'])
        
        return render_template('admin/bulk_operations.html',
                             users=users,
                             title=trans('admin_bulk_operations_title', default='Bulk Operations'))
    except Exception as e:
        logger.error(f"Error in bulk_operations for admin {current_user.id}: {str(e)}",
                     extra={'session_id': session.get('sid', 'no-session-id'), 'user_id': current_user.id})
        flash(trans('admin_database_error', default='An error occurred while accessing the database'), 'danger')
        return render_template('error/500.html'), 500

# Enhanced Admin Routes
@admin_bp.route('/analytics/enhanced', methods=['GET'])
@login_required
@utils.requires_role('admin')
@utils.limiter.limit("30 per hour")
def enhanced_analytics_dashboard():
    """Enhanced analytics dashboard with comprehensive metrics"""
    try:
        db = utils.get_mongo_db()
        if db is None:
            raise Exception("Failed to connect to MongoDB")
        
        analytics = get_user_analytics()
        system_health = get_system_health()
        
        recent_actions = list(db.audit_logs.find().sort('timestamp', -1).limit(10))
        for action in recent_actions:
            action['_id'] = str(action['_id'])
        
        logger.info(f"Admin {current_user.id} accessed enhanced analytics dashboard")
        
        return render_template(
            'admin/enhanced_analytics.html',
            analytics=analytics,
            system_health=system_health,
            recent_actions=recent_actions,
            title=trans('admin_enhanced_analytics', default='Enhanced Analytics Dashboard')
        )
    except Exception as e:
        logger.error(f"Error loading enhanced analytics for admin {current_user.id}: {str(e)}")
        flash(trans('admin_analytics_error', default='Error loading analytics dashboard'), 'danger')
        return redirect(url_for('admin.dashboard'))

@admin_bp.route('/system/settings', methods=['GET', 'POST'])
@login_required
@utils.requires_role('admin')
@utils.limiter.limit("20 per hour")
def system_settings():
    """System settings management"""
    try:
        db = utils.get_mongo_db()
        if db is None:
            raise Exception("Failed to connect to MongoDB")
        
        form = SystemSettingsForm()
        current_settings = get_system_settings()
        
        if request.method == 'POST' and form.validate_on_submit():
            settings_data = {
                'app_name': form.app_name.data,
                'maintenance_mode': form.maintenance_mode.data,
                'max_trial_days': form.max_trial_days.data,
                'monthly_subscription_price': form.monthly_subscription_price.data,
                'yearly_subscription_price': form.yearly_subscription_price.data
            }
            
            if save_system_settings(settings_data, current_user.id):
                flash(trans('admin_settings_saved', default='System settings saved successfully'), 'success')
                logger.info(f"Admin {current_user.id} updated system settings")
                return redirect(url_for('admin.system_settings'))
            else:
                flash(trans('admin_settings_error', default='Error saving system settings'), 'danger')
        
        # Pre-populate form with current settings
        if current_settings and request.method == 'GET':
            form.app_name.data = current_settings.get('app_name', 'Ficore Africa')
            form.maintenance_mode.data = current_settings.get('maintenance_mode', False)
            form.max_trial_days.data = current_settings.get('max_trial_days', 30)
            form.monthly_subscription_price.data = current_settings.get('monthly_subscription_price', 1000.0)
            form.yearly_subscription_price.data = current_settings.get('yearly_subscription_price', 10000.0)
        
        return render_template(
            'admin/system_settings.html',
            form=form,
            current_settings=current_settings,
            title=trans('admin_system_settings', default='System Settings')
        )
    except Exception as e:
        logger.error(f"Error in system settings for admin {current_user.id}: {str(e)}")
        flash(trans('admin_database_error', default='Database error occurred'), 'danger')
        return redirect(url_for('admin.dashboard'))

@admin_bp.route('/education/management', methods=['GET', 'POST'])
@login_required
@utils.requires_role('admin')
@utils.limiter.limit("30 per hour")
def education_management():
    """Education module management"""
    try:
        db = utils.get_mongo_db()
        if db is None:
            raise Exception("Failed to connect to MongoDB")
        
        modules = get_education_modules()
        form = EducationModuleForm()
        
        if request.method == 'POST' and form.validate_on_submit():
            module_data = {
                'module_name': form.module_name.data,
                'module_description': form.module_description.data,
                'module_content': form.module_content.data,
                'module_order': form.module_order.data,
                'is_active': form.is_active.data
            }
            
            module_id = request.form.get('module_id')
            if module_id:
                module_data['_id'] = module_id
            
            if save_education_module(module_data, current_user.id):
                action = 'updated' if module_id else 'created'
                flash(trans(f'admin_module_{action}', default=f'Education module {action} successfully'), 'success')
                logger.info(f"Admin {current_user.id} {action} education module")
                return redirect(url_for('admin.education_management'))
            else:
                flash(trans('admin_module_error', default='Error saving education module'), 'danger')
        
        return render_template(
            'admin/education_management.html',
            modules=modules,
            form=form,
            title=trans('admin_education_management', default='Education Module Management')
        )
    except Exception as e:
        logger.error(f"Error in education management for admin {current_user.id}: {str(e)}")
        flash(trans('admin_database_error', default='Database error occurred'), 'danger')
        return redirect(url_for('admin.dashboard'))

@admin_bp.route('/bulk/operations', methods=['GET', 'POST'])
@login_required
@utils.requires_role('admin')
@utils.limiter.limit("10 per hour")
def bulk_operations():
    """Bulk user operations"""
    try:
        db = utils.get_mongo_db()
        if db is None:
            raise Exception("Failed to connect to MongoDB")
        
        form = BulkUserOperationForm()
        operation_result = None
        
        if request.method == 'POST' and form.validate_on_submit():
            operation_type = form.operation_type.data
            user_filter = form.user_filter.data
            operation_value = form.operation_value.data or ''
            
            operation_result = execute_bulk_operation(
                operation_type, user_filter, operation_value, current_user.id
            )
            
            if operation_result['success']:
                flash(operation_result['message'], 'success')
                logger.info(f"Admin {current_user.id} executed bulk operation: {operation_type}")
            else:
                flash(operation_result['message'], 'danger')
        
        from datetime import timedelta
        user_counts = {
            'all': db.users.count_documents({}),
            'trial_users': db.users.count_documents({'is_trial': True}),
            'subscribed_users': db.users.count_documents({'is_subscribed': True}),
            'expired_users': db.users.count_documents({
                '$or': [
                    {'is_trial': True, 'trial_end': {'$lt': datetime.now(timezone.utc)}},
                    {'is_subscribed': True, 'subscription_end': {'$lt': datetime.now(timezone.utc)}}
                ]
            }),
            'new_users': db.users.count_documents({
                'created_at': {'$gte': datetime.now(timezone.utc) - timedelta(days=30)}
            })
        }
        
        return render_template(
            'admin/bulk_operations.html',
            form=form,
            operation_result=operation_result,
            user_counts=user_counts,
            title=trans('admin_bulk_operations', default='Bulk User Operations')
        )
    except Exception as e:
        logger.error(f"Error in bulk operations for admin {current_user.id}: {str(e)}")
        flash(trans('admin_database_error', default='Database error occurred'), 'danger')
        return redirect(url_for('admin.dashboard'))

@admin_bp.route('/language/toggle/<user_id>/<language>', methods=['POST'])
@login_required
@utils.requires_role('admin')
@utils.limiter.limit("5 per hour")
def toggle_user_language(user_id, language):
    """Toggle user language preference"""
    try:
        from bson import ObjectId
        db = utils.get_mongo_db()
        if db is None:
            raise Exception("Failed to connect to MongoDB")
        
        if language not in ['en', 'ha']:
            flash(trans('admin_invalid_language', default='Invalid language selected'), 'danger')
            return redirect(url_for('admin.manage_users'))
        
        result = db.users.update_one(
            {'_id': ObjectId(user_id)},
            {'$set': {'language': language, 'updated_at': datetime.now(timezone.utc)}}
        )
        
        if result.modified_count > 0:
            log_audit_action('toggle_user_language', {'user_id': user_id, 'new_language': language})
            flash(trans('admin_language_updated', default=f'User language updated to {language.upper()}'), 'success')
            logger.info(f"Admin {current_user.id} updated language for user {user_id} to {language}")
        else:
            flash(trans('admin_user_not_found', default='User not found'), 'danger')
        
        return redirect(url_for('admin.manage_users'))
    except Exception as e:
        logger.error(f"Error toggling user language: {str(e)}")
        flash(trans('admin_database_error', default='Database error occurred'), 'danger')
        return redirect(url_for('admin.manage_users'))

@admin_bp.route('/system/health', methods=['GET'])
@login_required
@utils.requires_role('admin')
@utils.limiter.limit("30 per hour")
def system_health_monitor():
    """System health monitoring dashboard"""
    try:
        system_health = get_system_health()
        
        return render_template(
            'admin/system_health.html',
            health_data=system_health,
            title=trans('admin_system_health', default='System Health Monitor')
        )
    except Exception as e:
        logger.error(f"Error loading system health: {str(e)}")
        flash(trans('admin_health_error', default='Error loading system health data'), 'danger')
        return redirect(url_for('admin.dashboard'))
