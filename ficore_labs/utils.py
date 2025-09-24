import re
import logging
import uuid
import os
import certifi
from datetime import datetime, timedelta, date
from zoneinfo import ZoneInfo
from flask import session, has_request_context, current_app, url_for, request
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from pymongo import MongoClient
from pymongo.errors import ConnectionFailure, ServerSelectionTimeoutError
from werkzeug.routing import BuildError
from wtforms import ValidationError
from flask_login import current_user

# Import performance monitoring (will be created)
try:
    from query_performance_monitor import monitor_query_performance
except ImportError:
    # Fallback decorator if monitoring module not available
    def monitor_query_performance(operation_name):
        def decorator(func):
            return func
        return decorator

# Initialize extensions
limiter = Limiter(
    key_func=get_remote_address,
    default_limits=['5000 per day', '500 per hour'],
    storage_uri=os.getenv('REDIS_URI', 'memory://')  # Use Redis for production
)

# Set up logging
root_logger = logging.getLogger('bizcore_app')
root_logger.setLevel(logging.INFO)

class SessionFormatter(logging.Formatter):
    def format(self, record):
        record.session_id = getattr(record, 'session_id', 'no-session-id')
        record.ip_address = getattr(record, 'ip_address', 'unknown')
        record.user_role = getattr(record, 'user_role', 'anonymous')
        return super().format(record)

handler = logging.StreamHandler()
handler.setFormatter(SessionFormatter(
    '[%(asctime)s] %(levelname)s in %(name)s: %(message)s [session: %(session_id)s, role: %(user_role)s, ip: %(ip_address)s]'
))
root_logger.handlers = []
root_logger.addHandler(handler)

class SessionAdapter(logging.LoggerAdapter):
    def process(self, msg, kwargs):
        kwargs['extra'] = kwargs.get('extra', {})
        session_id = 'no-session-id'
        ip_address = 'unknown'
        user_role = 'anonymous'
        try:
            if has_request_context():
                session_id = session.get('sid', 'no-session-id')
                ip_address = request.remote_addr
                user_role = current_user.role if current_user.is_authenticated else 'anonymous'
            else:
                session_id = f'non-request-{str(uuid.uuid4())[:8]}'
        except Exception as e:
            session_id = f'session-error-{str(uuid.uuid4())[:8]}'
            kwargs['extra']['session_error'] = str(e)
        kwargs['extra']['session_id'] = session_id
        kwargs['extra']['ip_address'] = ip_address
        kwargs['extra']['user_role'] = user_role
        return msg, kwargs

logger = SessionAdapter(root_logger, {})

# Navigation lists
TRADER_TOOLS = [
    {
        "endpoint": "dashboard.index",
        "label": "Dashboard",
        "label_key": "dashboard_summary",
        "description_key": "dashboard_summary_desc",
        "tooltip_key": "dashboard_tooltip",
        "icon": "bi-bar-chart-line"
    },  
    {
        "endpoint": "receipts.index",
        "label": "Receipts",
        "label_key": "receipts_dashboard",
        "description_key": "receipts_dashboard_desc",
        "tooltip_key": "receipts_tooltip",
        "icon": "bi-cash-coin"
    },
    {
        "endpoint": "debtors.index",
        "label": "Debtors",
        "label_key": "debtors_dashboard",
        "description_key": "debtors_dashboard_desc",
        "tooltip_key": "debtors_tooltip",
        "icon": "bi-person-plus"
    },
    {
        "endpoint": "creditors.index",
        "label": "Creditors",
        "label_key": "creditors_dashboard",
        "description_key": "creditors_dashboard_desc",
        "tooltip_key": "creditors_tooltip",
        "icon": "bi-arrow-up-circle"
    },
    {
        "endpoint": "inventory.index",
        "label": "Inventory",
        "label_key": "inventory_dashboard",
        "description_key": "inventory_dashboard_desc",
        "tooltip_key": "inventory_tooltip",
        "icon": "bi-box-seam"
    },
    {
        "endpoint": "payments.index",
        "label": "Payments",
        "label_key": "payments_dashboard",
        "description_key": "payments_dashboard_desc",
        "tooltip_key": "payments_tooltip",
        "icon": "bi-calculator"
    },
    {
        "endpoint": "tax.tax_calculator",
        "label": "Tax Calculator",
        "label_key": "tax_calculator",
        "description_key": "tax_calculator_desc",
        "tooltip_key": "tax_calculator_tooltip",
        "icon": "bi-percent"
    },
    {
        "endpoint": "reports.index",
        "label": "Profit Summary",
        "label_key": "profit_summary",
        "description_key": "profit_summary_desc",
        "tooltip_key": "profit_summary_tooltip",
        "icon": "bi-graph-up-arrow"
    }
]

TRADER_NAV = [
        {
        "endpoint": "receipts.index",
        "label": "Receipts",
        "label_key": "receipts_dashboard",
        "description_key": "receipts_dashboard_desc",
        "tooltip_key": "receipts_tooltip",
        "icon": "bi-cash-coin"
    },
    {
        "endpoint": "debtors.index",
        "label": "Debtors",
        "label_key": "debtors_dashboard",
        "description_key": "debtors_dashboard_desc",
        "tooltip_key": "debtors_tooltip",
        "icon": "bi-person-plus"
    },
    {
        "endpoint": "tax.tax_calculator",
        "label": "Tax Calculator",
        "label_key": "tax_calculator",
        "description_key": "tax_calculator_desc",
        "tooltip_key": "tax_calculator_tooltip",
        "icon": "bi-percent"
    },
    {
        "endpoint": "education.education_home",
        "label": "Tax Education",
        "label_key": "tax_education",
        "description_key": "tax_education_desc",
        "tooltip_key": "tax_education_tooltip",
        "icon": "bi-mortarboard"
    },
    {
        "endpoint": "reports.index",
        "label": "Profit Summary",
        "label_key": "profit_summary",
        "description_key": "profit_summary_desc",
        "tooltip_key": "profit_summary_tooltip",
        "icon": "bi-graph-up-arrow"
    },
    {
        "endpoint": "settings.profile",
        "label": "Profile",
        "label_key": "profile_settings",
        "description_key": "profile_settings_desc",
        "tooltip_key": "profile_tooltip",
        "icon": "bi-person"
    }
]

ADMIN_TOOLS = [
    {
        "endpoint": "dashboard.index",
        "label": "Dashboard",
        "label_key": "dashboard_summary",
        "description_key": "dashboard_summary_desc",
        "tooltip_key": "dashboard_tooltip",
        "icon": "bi-bar-chart-line"
    },
    {
        "endpoint": "admin.dashboard",
        "label": "Dashboard",
        "label_key": "admin_dashboard",
        "description_key": "admin_dashboard_desc",
        "tooltip_key": "admin_dashboard_tooltip",
        "icon": "bi-speedometer"
    },
    {
        "endpoint": "admin.manage_users",
        "label": "Manage Users",
        "label_key": "admin_manage_users",
        "description_key": "admin_manage_users_desc",
        "tooltip_key": "admin_manage_users_tooltip",
        "icon": "bi-people"
    }
]

ADMIN_NAV = [
    {
        "endpoint": "admin.dashboard",
        "label": "Dashboard",
        "label_key": "admin_dashboard",
        "description_key": "admin_dashboard_desc",
        "tooltip_key": "admin_dashboard_tooltip",
        "icon": "bi-speedometer"
    },
    {
        "endpoint": "admin.manage_users",
        "label": "Users",
        "label_key": "admin_manage_users",
        "description_key": "admin_manage_users_desc",
        "tooltip_key": "admin_manage_users_tooltip",
        "icon": "bi-people"
    }
]

ALL_TOOLS = []

def initialize_tools_with_urls(app):
    global TRADER_TOOLS, TRADER_NAV, ADMIN_TOOLS, ADMIN_NAV, ALL_TOOLS
    try:
        with app.app_context():
            TRADER_TOOLS = generate_tools_with_urls(TRADER_TOOLS)
            TRADER_NAV = generate_tools_with_urls(TRADER_NAV)
            ADMIN_TOOLS = generate_tools_with_urls(ADMIN_TOOLS)
            ADMIN_NAV = generate_tools_with_urls(ADMIN_NAV)
            ALL_TOOLS = TRADER_TOOLS + ADMIN_TOOLS
            logger.info('Initialized tools and navigation with resolved URLs', extra={'session_id': 'no-session-id'})
    except Exception as e:
        logger.error(f'Error initializing tools with URLs: {str(e)}', extra={'session_id': 'no-session-id'})
        raise

def generate_tools_with_urls(tools):
    result = []
    for tool in tools:
        try:
            if not tool.get('endpoint'):
                logger.error(f"Missing endpoint for tool {tool.get('label', 'unknown')}", extra={'session_id': 'no-session-id'})
                continue
            url = url_for(tool['endpoint'], _external=True)
            icon = tool.get('icon', 'bi-question-circle')
            if not icon or not icon.startswith('bi-'):
                logger.warning(f"Invalid icon for tool {tool.get('label', 'unknown')}: {icon}", extra={'session_id': 'no-session-id'})
                icon = 'bi-question-circle'
            result.append({**tool, 'url': url, 'icon': icon})
        except BuildError as e:
            logger.error(f"Failed to generate URL for endpoint {tool.get('endpoint', 'unknown')}: {str(e)}", extra={'session_id': 'no-session-id'})
            result.append({**tool, 'url': '#', 'icon': tool.get('icon', 'bi-question-circle')})
    return result

def get_explore_features():
    try:
        features = []
        user_role = 'unauthenticated'
        if has_request_context() and current_user.is_authenticated:
            user_role = current_user.role

        if user_role == 'unauthenticated':
            business_tool_keys = ["debtors_dashboard", "receipts_dashboard", "profit_summary"]  # Removed "business_reports"
            for tool in TRADER_TOOLS:
                if tool["label_key"] in business_tool_keys:
                    features.append({
                        "category": "Business",
                        "label_key": tool["label_key"],
                        "description_key": tool["description_key"],
                        "label": tool["label"],
                        "description": tool.get("description", "Description not available"),
                        "url": tool["url"] if tool["url"] != "#" else url_for("users.login", _external=True)
                    })
        elif user_role == 'trader':
            for tool in TRADER_TOOLS:
                features.append({
                    "category": "Business",
                    "label_key": tool["label_key"],
                    "description_key": tool["description_key"],
                    "label": tool["label"],
                    "description": tool.get("description", "Description not available"),
                    "url": tool["url"]
                })
        elif user_role == 'admin':
            for tool in ADMIN_TOOLS:
                features.append({
                    "category": "Admin",
                    "label_key": tool["label_key"],
                    "description_key": tool["description_key"],
                    "label": tool["label"],
                    "description": tool.get("description", "Description not available"),
                    "url": tool["url"]
                })

        logger.info(f"Retrieved explore features for role: {user_role}", extra={'session_id': session.get('sid', 'no-session-id'), 'user_role': user_role})
        return features
    except Exception as e:
        logger.error(f"Error retrieving explore features for role {user_role}: {str(e)}", extra={'session_id': session.get('sid', 'no-session-id'), 'user_role': user_role})
        return []

def get_limiter():
    return limiter

def format_percentage(value):
    """Format a decimal as a percentage (e.g., 0.25 -> 25%)."""
    try:
        return "{:.2f}%".format(float(value) * 100)
    except (ValueError, TypeError):
        return "0.00%"

def log_tool_usage(action, tool_name=None, details=None, user_id=None, db=None, session_id=None):
    try:
        if db is None:
            db = get_mongo_db()
        if not action or not isinstance(action, str):
            raise ValueError("Action must be a non-empty string")
        effective_session_id = session_id or session.get('sid', 'no-session-id') if has_request_context() else 'no-session-id'
        log_entry = {
            'tool_name': tool_name or action,
            'user_id': str(user_id) if user_id else None,
            'session_id': effective_session_id,
            'action': details.get('action') if details else None,
            'timestamp': datetime.now(ZoneInfo("UTC")),
            'ip_address': request.remote_addr if has_request_context() else 'unknown',
            'user_agent': request.headers.get('User-Agent') if has_request_context() else 'unknown'
        }
        db.tool_usage.insert_one(log_entry)
        logger.info(f"Logged tool usage: {action}", extra={'session_id': effective_session_id, 'user_id': user_id or 'none'})
    except Exception as e:
        logger.error(f"Failed to log tool usage for action {action}: {str(e)}", extra={'session_id': session_id or 'no-session-id'})
        raise RuntimeError(f"Failed to log tool usage: {str(e)}")

def create_anonymous_session():
    try:
        with current_app.app_context():
            session['sid'] = str(uuid.uuid4())
            session['is_anonymous'] = True
            session['created_at'] = datetime.now(ZoneInfo("UTC")).isoformat()
            if 'lang' not in session:
                session['lang'] = 'en'
            session.modified = True
            logger.info(f"Created anonymous session: {session['sid']}", extra={'session_id': session['sid']})
    except Exception as e:
        logger.error(f"Error creating anonymous session: {str(e)}", extra={'session_id': 'error-session'})
        session['sid'] = f'error-{str(uuid.uuid4())[:8]}'
        session['is_anonymous'] = True
        session.modified = True

def clean_currency(value, max_value=10000000000):
    try:
        if value is None or (isinstance(value, str) and value.strip() == ''):
            return 0.0
        if isinstance(value, (int, float)):
            value = float(value)
            if value > max_value:
                raise ValidationError(f"Input cannot exceed {max_value:,}")
            if value < 0:
                raise ValidationError("Negative currency values are not allowed")
            return value
        value_str = str(value).strip()
        cleaned = re.sub(r'[^\d.]', '', value_str.replace('NGN', '').replace('₦', '').replace('$', '').replace('€', '').replace('£', '').replace(',', ''))
        parts = cleaned.split('.')
        if len(parts) > 2 or cleaned.count('-') > 1 or (cleaned.count('-') == 1 and not cleaned.startswith('-')):
            raise ValidationError('Invalid currency format')
        if not cleaned or cleaned == '.':
            raise ValidationError('Invalid currency format')
        result = float(cleaned)
        if result < 0:
            raise ValidationError('Negative currency values are not allowed')
        if result > max_value:
            raise ValidationError(f"Input cannot exceed {max_value:,}")
        return result
    except Exception as e:
        logger.error(f"Error in clean_currency for value '{value}': {str(e)}", extra={'session_id': session.get('sid', 'no-session-id')})
        raise ValidationError('Invalid currency format')

def is_valid_email(email):
    if not email or not isinstance(email, str):
        return False
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return re.match(pattern, email.strip()) is not None

def get_mongo_db():
    try:
        with current_app.app_context():
            if 'mongo' not in current_app.extensions:
                mongo_uri = os.getenv('MONGO_URI')
                if not mongo_uri:
                    logger.error("MONGO_URI environment variable not set", extra={'session_id': 'no-session-id'})
                    raise RuntimeError("MONGO_URI environment variable not set")
                client = MongoClient(
                    mongo_uri,
                    serverSelectionTimeoutMS=5000,
                    tls=True,
                    tlsCAFile=certifi.where(),
                    maxPoolSize=50,
                    minPoolSize=5,
                    connect=False  # Defer connection for fork-safety
                )
                client.admin.command('ping')  # Force connection here
                current_app.extensions['mongo'] = client
                logger.info("MongoClient initialized for worker", extra={'session_id': 'no-session-id'})
            db = current_app.extensions['mongo']['bizdb']
            db.command('ping')
            return db
    except (ConnectionFailure, ServerSelectionTimeoutError) as e:
        logger.error(f"Failed to connect to MongoDB: {str(e)}", extra={'session_id': 'no-session-id'})
        raise RuntimeError(f"Failed to connect to MongoDB: {str(e)}")

def requires_role(role):
    def decorator(f):
        from functools import wraps
        from flask import redirect, url_for, flash
        @wraps(f)
        def decorated_function(*args, **kwargs):
            with current_app.app_context():
                if not current_user.is_authenticated:
                    flash('Please log in to access this page.', 'warning')
                    return redirect(url_for('users.login'))
                if is_admin():
                    return f(*args, **kwargs)
                allowed_roles = role if isinstance(role, list) else [role]
                if current_user.role not in allowed_roles:
                    flash('You do not have permission to access this page.', 'danger')
                    return redirect(url_for('dashboard.index'))
                if not current_user.is_trial_active():
                    logger.info(f"User {current_user.id} trial expired, redirecting to subscription", extra={'session_id': session.get('sid', 'no-session-id'), 'user_id': current_user.id})
                    return redirect(url_for('subscribe_bp.subscription_required'))
                return f(*args, **kwargs)
        return decorated_function
    return decorator

def is_admin():
    try:
        with current_app.app_context():
            return current_user.is_authenticated and current_user.role == 'admin'
    except Exception:
        return False

def can_user_interact(user):
    try:
        with current_app.app_context():
            if not user or not user.is_authenticated:
                logger.info("User interaction denied: No authenticated user", extra={'session_id': session.get('sid', 'no-session-id')})
                return False
            if user.role == 'admin':
                logger.info(f"User {user.id} allowed to interact: Admin role", extra={'session_id': session.get('sid', 'no-session-id'), 'user_id': user.id})
                return True
            if user.get('is_subscribed', False):
                subscription_end = user.get('subscription_end')
                if subscription_end:
                    subscription_end_aware = (
                        subscription_end.replace(tzinfo=ZoneInfo("UTC"))
                        if subscription_end.tzinfo is None
                        else subscription_end
                    )
                    if subscription_end_aware > datetime.now(ZoneInfo("UTC")):
                        logger.info(f"User {user.id} allowed to interact: Active subscription", extra={'session_id': session.get('sid', 'no-session-id'), 'user_id': user.id})
                        return True
                    logger.info(f"User {user.id} subscription expired: {subscription_end_aware}", extra={'session_id': session.get('sid', 'no-session-id'), 'user_id': user.id})
                else:
                    logger.info(f"User {user.id} allowed to interact: Active subscription (no end date)", extra={'session_id': session.get('sid', 'no-session-id'), 'user_id': user.id})
                    return True
            if user.get('is_trial', False):
                trial_end = user.get('trial_end')
                if trial_end:
                    trial_end_aware = (
                        trial_end.replace(tzinfo=ZoneInfo("UTC"))
                        if trial_end.tzinfo is None
                        else trial_end
                    )
                    if trial_end_aware > datetime.now(ZoneInfo("UTC")):
                        logger.info(f"User {user.id} allowed to interact: Active trial", extra={'session_id': session.get('sid', 'no-session-id'), 'user_id': user.id})
                        return True
                    logger.info(f"User {user.id} trial expired: {trial_end_aware}", extra={'session_id': session.get('sid', 'no-session-id'), 'user_id': user.id})
            logger.info(f"User {user.id} interaction denied: No active subscription or trial", extra={'session_id': session.get('sid', 'no-session-id'), 'user_id': user.id})
            return False
    except Exception as e:
        logger.error(f"Error checking user interaction for user {user.get('id', 'unknown')}: {str(e)}", extra={'session_id': session.get('sid', 'no-session-id')})
        return False

def should_show_subscription_banner(user):
    try:
        with current_app.app_context():
            if not user or not user.is_authenticated:
                return False
            if user.role == 'admin':
                return False
            if user.get('is_subscribed', False):
                subscription_end = user.get('subscription_end')
                if subscription_end:
                    subscription_end_aware = (
                        subscription_end.replace(tzinfo=ZoneInfo("UTC"))
                        if subscription_end.tzinfo is None
                        else subscription_end
                    )
                    if subscription_end_aware > datetime.now(ZoneInfo("UTC")):
                        return False
                else:
                    return False
            if user.get('is_trial', False):
                trial_end = user.get('trial_end')
                if trial_end:
                    trial_end_aware = (
                        trial_end.replace(tzinfo=ZoneInfo("UTC"))
                        if trial_end.tzinfo is None
                        else trial_end
                    )
                    if trial_end_aware > datetime.now(ZoneInfo("UTC")):
                        return False
            return True
    except Exception as e:
        logger.error(f"Error checking subscription banner for user {user.get('id', 'unknown')}: {str(e)}", extra={'session_id': session.get('sid', 'no-session-id')})
        return False

def format_currency(amount, currency='₦', lang=None, include_symbol=True):
    try:
        with current_app.app_context():
            if lang is None:
                lang = session.get('lang', 'en') if has_request_context() else 'en'
            if amount is None or amount == '':
                amount = 0
            if isinstance(amount, str):
                amount = clean_currency(amount)
            else:
                amount = float(amount)
            if amount.is_integer():
                formatted = f"{int(amount):,}"
            else:
                formatted = f"{amount:,.2f}"
            return f"{currency}{formatted}" if include_symbol else formatted
    except Exception as e:
        logger.warning(f"Error formatting currency {amount}: {str(e)}", extra={'session_id': session.get('sid', 'no-session-id')})
        return f"{currency}0" if include_symbol else "0"

def format_date(date_obj, lang=None, format_type='short'):
    try:
        with current_app.app_context():
            if lang is None:
                lang = session.get('lang', 'en') if has_request_context() else 'en'
            if not date_obj:
                return ''
            if isinstance(date_obj, str):
                try:
                    date_obj = datetime.strptime(date_obj, '%Y-%m-%d')
                except ValueError:
                    try:
                        date_obj = datetime.fromisoformat(date_obj.replace('Z', '+00:00'))
                    except ValueError:
                        logger.warning(f"Invalid date format for input: {date_obj}", extra={'session_id': session.get('sid', 'no-session-id')})
                        return date_obj
            date_obj_aware = date_obj.replace(tzinfo=ZoneInfo("UTC")) if date_obj.tzinfo is None else date_obj
            if format_type == 'iso':
                return date_obj_aware.strftime('%Y-%m-%d')
            elif format_type == 'long':
                return date_obj_aware.strftime('%d %B %Y' if lang == 'ha' else '%B %d, %Y')
            else:
                return date_obj_aware.strftime('%d/%m/%Y' if lang == 'ha' else '%m/%d/%Y')
    except Exception as e:
        logger.warning(f"Error formatting date {date_obj}: {str(e)}", extra={'session_id': session.get('sid', 'no-session-id')})
        return str(date_obj) if date_obj else ''

def sanitize_input(input_string, max_length=None):
    if not input_string:
        return ''
    sanitized = str(input_string).strip()
    sanitized = re.sub(r'[<>"\']', '', sanitized)
    if re.search(r'[<>]', sanitized):
        logger.warning(f"Potential malicious input detected: {sanitized}", extra={'session_id': session.get('sid', 'no-session-id')})
    if max_length and len(sanitized) > max_length:
        sanitized = sanitized[:max_length]
    return sanitized

def generate_unique_id(prefix=''):
    return f"{prefix}_{str(uuid.uuid4())}" if prefix else str(uuid.uuid4())

def validate_required_fields(data, required_fields):
    missing_fields = [field for field in required_fields if field not in data or not data[field] or str(data[field]).strip() == '']
    return len(missing_fields) == 0, missing_fields

def get_user_language():
    try:
        with current_app.app_context():
            return session.get('lang', 'en') if has_request_context() else 'en'
    except Exception:
        return 'en'

def log_user_action(action, details=None, user_id=None):
    try:
        with current_app.app_context():
            if user_id is None and current_user.is_authenticated:
                user_id = current_user.id
            session_id = session.get('sid', 'no-session-id') if has_request_context() else 'no-session-id'
            log_entry = {
                'user_id': user_id,
                'session_id': session_id,
                'action': action,
                'details': details or {},
                'timestamp': datetime.now(ZoneInfo("UTC")),
                'ip_address': request.remote_addr if has_request_context() else None,
                'user_agent': request.headers.get('User-Agent') if has_request_context() else None
            }
            db = get_mongo_db()
            db.audit_logs.insert_one(log_entry)
            logger.info(f"User action logged: {action} by user {user_id}", extra={'session_id': session_id, 'user_id': user_id or 'none'})
    except Exception as e:
        logger.error(f"Error logging user action: {str(e)}", extra={'session_id': session_id or 'no-session-id'})
        raise

def track_user_activity(activity_type, description, amount=None, related_id=None, user_id=None):
    try:
        with current_app.app_context():
            if user_id is None and current_user.is_authenticated:
                user_id = current_user.id
            if not user_id:
                logger.warning("Cannot track activity: no user ID provided")
                return
            session_id = session.get('sid', 'no-session-id') if has_request_context() else 'no-session-id'
            activity_entry = {
                'user_id': user_id,
                'session_id': session_id,
                'type': activity_type,
                'description': description,
                'amount': amount,
                'related_id': related_id,
                'timestamp': datetime.now(ZoneInfo("UTC")),
                'ip_address': request.remote_addr if has_request_context() else None
            }
            db = get_mongo_db()
            db.user_activities.insert_one(activity_entry)
            log_user_action(f"activity_{activity_type}", {
                'description': description,
                'amount': amount,
                'related_id': related_id
            }, user_id)
            logger.info(f"User activity tracked: {activity_type} for user {user_id}", 
                       extra={'session_id': session_id, 'user_id': user_id})
    except Exception as e:
        logger.error(f"Error tracking user activity: {str(e)}", 
                    extra={'session_id': session.get('sid', 'no-session-id') if has_request_context() else 'no-session-id'})
        # Don't raise to avoid breaking main functionality

# Expense Category System Constants
EXPENSE_CATEGORIES = {
    'office_admin': {
        'name': 'Office & Admin',
        'tax_deductible': True,
        'is_personal': False,
        'is_statutory': False,
        'description': 'Office supplies, stationery, internet/data, utility bills',
        'examples': ['Office supplies', 'Stationery', 'Internet/Data', 'Electricity']
    },
    'staff_wages': {
        'name': 'Staff & Wages',
        'tax_deductible': True,
        'is_personal': False,
        'is_statutory': False,
        'description': 'Employee salaries, wages, and related costs',
        'examples': ['Salaries', 'Wages', 'Staff benefits', 'Payroll costs']
    },
    'business_travel': {
        'name': 'Business Travel & Transport',
        'tax_deductible': True,
        'is_personal': False,
        'is_statutory': False,
        'description': 'Fuel, vehicle maintenance, and travel expenses for business',
        'examples': ['Fuel', 'Vehicle maintenance', 'Business travel', 'Transport costs']
    },
    'rent_utilities': {
        'name': 'Rent & Utilities',
        'tax_deductible': True,
        'is_personal': False,
        'is_statutory': False,
        'description': 'Rent for shop or business office',
        'examples': ['Shop rent', 'Office rent', 'Business premises rent']
    },
    'marketing_sales': {
        'name': 'Marketing & Sales',
        'tax_deductible': True,
        'is_personal': False,
        'is_statutory': False,
        'description': 'Advertising, social media promotion, business cards',
        'examples': ['Advertising', 'Social media promotion', 'Business cards']
    },
    'cogs': {
        'name': 'Cost of Goods Sold (COGS)',
        'tax_deductible': True,
        'is_personal': False,
        'is_statutory': False,
        'description': 'Direct costs of producing goods or services',
        'examples': ['Raw materials', 'Manufacturing costs', 'Direct labor']
    },
    'personal_expenses': {
        'name': 'Personal Expenses',
        'tax_deductible': False,
        'is_personal': True,
        'is_statutory': False,
        'description': 'Personal expenses not related to business',
        'examples': ['Personal meals', 'Personal shopping', 'Family expenses']
    },
    'statutory_legal': {
        'name': 'Statutory & Legal Contributions',
        'tax_deductible': True,
        'is_personal': False,
        'is_statutory': True,
        'description': 'Accounting, legal, and consulting fees directly related to business',
        'examples': ['Accounting fees', 'Legal fees', 'Consulting fees']
    }
}

# Category validation and utility functions
def validate_expense_category(category_key):
    """
    Validate if the provided category key exists in the expense categories.
    
    Args:
        category_key (str): The category key to validate
        
    Returns:
        bool: True if category is valid, False otherwise
    """
    try:
        if not category_key or not isinstance(category_key, str):
            logger.warning(f"Invalid category key type: {type(category_key)}", 
                         extra={'session_id': session.get('sid', 'no-session-id') if has_request_context() else 'no-session-id'})
            return False
        
        is_valid = category_key.strip() in EXPENSE_CATEGORIES
        if not is_valid:
            logger.warning(f"Invalid expense category: {category_key}", 
                         extra={'session_id': session.get('sid', 'no-session-id') if has_request_context() else 'no-session-id'})
        
        return is_valid
    except Exception as e:
        logger.error(f"Error validating expense category '{category_key}': {str(e)}", 
                    extra={'session_id': session.get('sid', 'no-session-id') if has_request_context() else 'no-session-id'})
        return False

def get_category_metadata(category_key):
    """
    Get metadata for a specific expense category.
    
    Args:
        category_key (str): The category key to get metadata for
        
    Returns:
        dict: Category metadata or empty dict if category doesn't exist
    """
    try:
        if not validate_expense_category(category_key):
            logger.warning(f"Attempted to get metadata for invalid category: {category_key}", 
                         extra={'session_id': session.get('sid', 'no-session-id') if has_request_context() else 'no-session-id'})
            return {}
        
        return EXPENSE_CATEGORIES.get(category_key, {}).copy()
    except Exception as e:
        logger.error(f"Error getting category metadata for '{category_key}': {str(e)}", 
                    extra={'session_id': session.get('sid', 'no-session-id') if has_request_context() else 'no-session-id'})
        return {}

def is_category_tax_deductible(category_key):
    """
    Determine if a category is tax deductible.
    
    Args:
        category_key (str): The category key to check
        
    Returns:
        bool: True if tax deductible, False otherwise
    """
    try:
        if not validate_expense_category(category_key):
            return False
        
        category_data = EXPENSE_CATEGORIES.get(category_key, {})
        return category_data.get('tax_deductible', False)
    except Exception as e:
        logger.error(f"Error checking tax deductibility for category '{category_key}': {str(e)}", 
                    extra={'session_id': session.get('sid', 'no-session-id') if has_request_context() else 'no-session-id'})
        return False

def is_category_personal(category_key):
    """
    Determine if a category is for personal expenses.
    
    Args:
        category_key (str): The category key to check
        
    Returns:
        bool: True if personal category, False otherwise
    """
    try:
        if not validate_expense_category(category_key):
            return False
        
        category_data = EXPENSE_CATEGORIES.get(category_key, {})
        return category_data.get('is_personal', False)
    except Exception as e:
        logger.error(f"Error checking if category is personal '{category_key}': {str(e)}", 
                    extra={'session_id': session.get('sid', 'no-session-id') if has_request_context() else 'no-session-id'})
        return False

def is_category_statutory(category_key):
    """
    Determine if a category is for statutory/legal contributions.
    
    Args:
        category_key (str): The category key to check
        
    Returns:
        bool: True if statutory category, False otherwise
    """
    try:
        if not validate_expense_category(category_key):
            return False
        
        category_data = EXPENSE_CATEGORIES.get(category_key, {})
        return category_data.get('is_statutory', False)
    except Exception as e:
        logger.error(f"Error checking if category is statutory '{category_key}': {str(e)}", 
                    extra={'session_id': session.get('sid', 'no-session-id') if has_request_context() else 'no-session-id'})
        return False

def get_all_expense_categories():
    """
    Get all expense categories with their metadata.
    
    Returns:
        dict: All expense categories with their metadata
    """
    try:
        return EXPENSE_CATEGORIES.copy()
    except Exception as e:
        logger.error(f"Error getting all expense categories: {str(e)}", 
                    extra={'session_id': session.get('sid', 'no-session-id') if has_request_context() else 'no-session-id'})
        return {}

def get_tax_deductible_categories():
    """
    Get all tax deductible expense categories.
    
    Returns:
        list: List of category keys that are tax deductible
    """
    try:
        return [key for key, data in EXPENSE_CATEGORIES.items() if data.get('tax_deductible', False)]
    except Exception as e:
        logger.error(f"Error getting tax deductible categories: {str(e)}", 
                    extra={'session_id': session.get('sid', 'no-session-id') if has_request_context() else 'no-session-id'})
        return []

def get_category_choices_for_forms():
    """
    Get expense categories formatted for form choices (SelectField).
    
    Returns:
        list: List of tuples (category_key, display_name) for form choices
    """
    try:
        choices = []
        for key, data in EXPENSE_CATEGORIES.items():
            display_name = data.get('name', key)
            if data.get('is_personal', False):
                display_name += ' (Not Tax Deductible)'
            choices.append((key, display_name))
        
        return sorted(choices, key=lambda x: x[1])
    except Exception as e:
        logger.error(f"Error getting category choices for forms: {str(e)}", 
                    extra={'session_id': session.get('sid', 'no-session-id') if has_request_context() else 'no-session-id'})
        return []

def validate_category_assignment(category_key, amount, description=None):
    """
    Validate a complete category assignment for an expense.
    
    Args:
        category_key (str): The category key to validate
        amount (float): The expense amount
        description (str, optional): The expense description
        
    Returns:
        tuple: (is_valid, error_messages)
    """
    try:
        errors = []
        
        # Validate category
        if not validate_expense_category(category_key):
            errors.append(f"Invalid expense category: {category_key}")
        
        # Validate amount
        if not isinstance(amount, (int, float)) or amount < 0:
            errors.append("Amount must be a positive number")
        elif amount == 0:
            errors.append("Amount cannot be zero")
        elif amount > 999999999.99:  # Reasonable upper limit
            errors.append("Amount is too large (maximum: ₦999,999,999.99)")
        
        # Validate description if provided
        if description is not None:
            if len(str(description).strip()) > 1000:
                errors.append("Description cannot exceed 1000 characters")
        
        return len(errors) == 0, errors
    except Exception as e:
        logger.error(f"Error validating category assignment: {str(e)}", 
                    extra={'session_id': session.get('sid', 'no-session-id') if has_request_context() else 'no-session-id'})
        return False, ["Validation error occurred"]

def validate_payment_form_data(form_data):
    """
    Comprehensive validation for payment form data.
    
    Args:
        form_data (dict): Form data to validate
        
    Returns:
        tuple: (is_valid, error_messages_dict)
    """
    try:
        errors = {}
        
        # Required fields validation
        required_fields = ['party_name', 'date', 'amount', 'expense_category']
        for field in required_fields:
            if not form_data.get(field) or str(form_data[field]).strip() == '':
                errors[field] = f"{field.replace('_', ' ').title()} is required"
        
        # Party name validation
        if form_data.get('party_name'):
            party_name = str(form_data['party_name']).strip()
            if len(party_name) < 2:
                errors['party_name'] = "Party name must be at least 2 characters long"
            elif len(party_name) > 100:
                errors['party_name'] = "Party name cannot exceed 100 characters"
            elif not re.match(r'^[a-zA-Z0-9\s\-\.\,\'&]+$', party_name):
                errors['party_name'] = "Party name contains invalid characters"
        
        # Date validation
        if form_data.get('date'):
            try:
                if isinstance(form_data['date'], str):
                    date_obj = datetime.strptime(form_data['date'], '%Y-%m-%d').date()
                else:
                    date_obj = form_data['date']
                
                # Check if date is not in the future
                if date_obj > date.today():
                    errors['date'] = "Date cannot be in the future"
                
                # Check if date is not too far in the past (e.g., more than 10 years)
                ten_years_ago = date.today().replace(year=date.today().year - 10)
                if date_obj < ten_years_ago:
                    errors['date'] = "Date cannot be more than 10 years in the past"
                    
            except (ValueError, TypeError):
                errors['date'] = "Invalid date format"
        
        # Amount validation
        if form_data.get('amount') is not None:
            try:
                amount = float(form_data['amount'])
                if amount <= 0:
                    errors['amount'] = "Amount must be greater than zero"
                elif amount > 999999999.99:
                    errors['amount'] = "Amount is too large (maximum: ₦999,999,999.99)"
                elif len(str(amount).split('.')[-1]) > 2:
                    errors['amount'] = "Amount cannot have more than 2 decimal places"
            except (ValueError, TypeError):
                errors['amount'] = "Amount must be a valid number"
        
        # Expense category validation
        if form_data.get('expense_category'):
            if not validate_expense_category(form_data['expense_category']):
                errors['expense_category'] = "Please select a valid expense category"
        
        # Payment method validation (optional field)
        if form_data.get('method'):
            valid_methods = ['cash', 'card', 'bank']
            if form_data['method'] not in valid_methods:
                errors['method'] = "Please select a valid payment method"
        
        # Contact validation (optional field)
        if form_data.get('contact'):
            contact = str(form_data['contact']).strip()
            if len(contact) > 100:
                errors['contact'] = "Contact cannot exceed 100 characters"
            elif contact and not re.match(r'^[a-zA-Z0-9\s\-\.\,\+\(\)@]+$', contact):
                errors['contact'] = "Contact contains invalid characters"
        
        # Description validation (optional field)
        if form_data.get('description'):
            description = str(form_data['description']).strip()
            if len(description) > 1000:
                errors['description'] = "Description cannot exceed 1000 characters"
        
        return len(errors) == 0, errors
    except Exception as e:
        logger.error(f"Error validating payment form data: {str(e)}", 
                    extra={'session_id': session.get('sid', 'no-session-id') if has_request_context() else 'no-session-id'})
        return False, {'general': 'Validation error occurred. Please try again.'}

def validate_tax_calculation_input(input_data):
    """
    Validate input data for tax calculations.
    
    Args:
        input_data (dict): Tax calculation input data
        
    Returns:
        tuple: (is_valid, error_messages_dict)
    """
    try:
        errors = {}
        
        # Total income validation
        if 'total_income' not in input_data:
            errors['total_income'] = "Total income is required"
        else:
            try:
                income = float(input_data['total_income'])
                if income < 0:
                    errors['total_income'] = "Income cannot be negative"
                elif income > 9999999999.99:  # 10 billion limit
                    errors['total_income'] = "Income amount is unreasonably large"
            except (ValueError, TypeError):
                errors['total_income'] = "Income must be a valid number"
        
        # Annual rent validation (optional)
        if input_data.get('annual_rent') is not None:
            try:
                rent = float(input_data['annual_rent'])
                if rent < 0:
                    errors['annual_rent'] = "Annual rent cannot be negative"
                elif rent > 999999999.99:
                    errors['annual_rent'] = "Annual rent amount is unreasonably large"
            except (ValueError, TypeError):
                errors['annual_rent'] = "Annual rent must be a valid number"
        
        # Expenses validation
        if 'expenses' in input_data and isinstance(input_data['expenses'], dict):
            for category, amount in input_data['expenses'].items():
                if amount is not None and str(amount).strip() != '':
                    try:
                        expense_amount = float(amount)
                        if expense_amount < 0:
                            errors[f'expenses_{category}'] = f"Expense amount for {category} cannot be negative"
                        elif expense_amount > 999999999.99:
                            errors[f'expenses_{category}'] = f"Expense amount for {category} is unreasonably large"
                        
                        # Validate category exists
                        if not validate_expense_category(category):
                            errors[f'expenses_{category}'] = f"Invalid expense category: {category}"
                            
                    except (ValueError, TypeError):
                        errors[f'expenses_{category}'] = f"Expense amount for {category} must be a valid number"
        
        return len(errors) == 0, errors
    except Exception as e:
        logger.error(f"Error validating tax calculation input: {str(e)}", 
                    extra={'session_id': session.get('sid', 'no-session-id') if has_request_context() else 'no-session-id'})
        return False, {'general': 'Validation error occurred. Please try again.'}

def get_user_friendly_error_message(field_name, error_type):
    """
    Get user-friendly error messages for form validation.
    
    Args:
        field_name (str): The field that has an error
        error_type (str): The type of error
        
    Returns:
        str: User-friendly error message
    """
    error_messages = {
        'party_name': {
            'required': 'Please enter the recipient name',
            'too_short': 'Recipient name must be at least 2 characters',
            'too_long': 'Recipient name is too long (maximum 100 characters)',
            'invalid_chars': 'Recipient name contains invalid characters'
        },
        'date': {
            'required': 'Please select a date',
            'invalid_format': 'Please enter a valid date',
            'future_date': 'Date cannot be in the future',
            'too_old': 'Date cannot be more than 10 years ago'
        },
        'amount': {
            'required': 'Please enter an amount',
            'invalid_number': 'Please enter a valid amount',
            'negative': 'Amount must be greater than zero',
            'too_large': 'Amount is too large',
            'too_many_decimals': 'Amount cannot have more than 2 decimal places'
        },
        'expense_category': {
            'required': 'Please select an expense category',
            'invalid': 'Please select a valid expense category'
        },
        'method': {
            'invalid': 'Please select a valid payment method'
        },
        'contact': {
            'too_long': 'Contact information is too long (maximum 100 characters)',
            'invalid_chars': 'Contact contains invalid characters'
        },
        'description': {
            'too_long': 'Description is too long (maximum 1000 characters)'
        }
    }
    
    field_errors = error_messages.get(field_name, {})
    return field_errors.get(error_type, f"Invalid {field_name.replace('_', ' ')}")

def format_validation_errors_for_flash(errors_dict):
    """
    Format validation errors for flash messages.
    
    Args:
        errors_dict (dict): Dictionary of field errors
        
    Returns:
        list: List of formatted error messages
    """
    try:
        formatted_errors = []
        for field, error in errors_dict.items():
            if field.startswith('expenses_'):
                category = field.replace('expenses_', '')
                category_name = get_category_metadata(category).get('name', category)
                formatted_errors.append(f"{category_name}: {error}")
            else:
                field_display = field.replace('_', ' ').title()
                formatted_errors.append(f"{field_display}: {error}")
        
        return formatted_errors
    except Exception as e:
        logger.error(f"Error formatting validation errors: {str(e)}")
        return ["Validation errors occurred. Please check your input and try again."]
        # Validate amount
        if not amount or amount <= 0:
            errors.append("Expense amount must be greater than zero")
        
        # Additional validation for specific categories
        if category_key == 'personal_expenses' and description:
            # Log warning for personal expenses to help users understand tax implications
            logger.info(f"Personal expense logged (not tax deductible): {description}", 
                       extra={'session_id': session.get('sid', 'no-session-id') if has_request_context() else 'no-session-id'})
        
        return len(errors) == 0, errors
    except Exception as e:
        logger.error(f"Error validating category assignment: {str(e)}", 
                    extra={'session_id': session.get('sid', 'no-session-id') if has_request_context() else 'no-session-id'})
        return False, [f"Validation error: {str(e)}"]

def extract_tax_year_from_date(date_obj):
    """
    Extract tax year from a date object.
    
    Args:
        date_obj (datetime): Date object to extract year from
        
    Returns:
        int: Tax year or None if invalid date
    """
    try:
        if not date_obj:
            return None
        
        if isinstance(date_obj, str):
            try:
                date_obj = datetime.fromisoformat(date_obj.replace('Z', '+00:00'))
            except ValueError:
                logger.warning(f"Invalid date format for tax year extraction: {date_obj}", 
                             extra={'session_id': session.get('sid', 'no-session-id') if has_request_context() else 'no-session-id'})
                return None
        
        return date_obj.year
    except Exception as e:
        logger.error(f"Error extracting tax year from date {date_obj}: {str(e)}", 
                    extra={'session_id': session.get('sid', 'no-session-id') if has_request_context() else 'no-session-id'})
        return None


# Four-Step Tax Calculation Engine

def get_total_income(user_id, tax_year):
    """
    Retrieve total income for a user in a specific tax year.
    
    Args:
        user_id (str): User ID
        tax_year (int): Tax year to calculate for
        
    Returns:
        float: Total income amount
    """
    try:
        db = get_mongo_db()
        
        # Query for receipt records (income) in the specified tax year
        income_query = {
            'user_id': user_id,
            'type': 'receipt',
            'tax_year': tax_year
        }
        
        income_records = db.cashflows.find(income_query)
        total_income = sum(record.get('amount', 0) for record in income_records)
        
        logger.info(f"Retrieved total income for user {user_id} in {tax_year}: {total_income}", 
                   extra={'session_id': session.get('sid', 'no-session-id') if has_request_context() else 'no-session-id'})
        
        return float(total_income)
    except Exception as e:
        logger.error(f"Error retrieving total income for user {user_id} in {tax_year}: {str(e)}", 
                    extra={'session_id': session.get('sid', 'no-session-id') if has_request_context() else 'no-session-id'})
        return 0.0

@monitor_query_performance('expenses_by_categories')
def get_expenses_by_categories(user_id, tax_year, category_list):
    """
    Retrieve expenses aggregated by categories for a specific tax year.
    Uses optimized MongoDB aggregation pipeline for better performance.
    
    Args:
        user_id (str): User ID
        tax_year (int): Tax year to calculate for
        category_list (list): List of category keys to include
        
    Returns:
        dict: Dictionary with category keys and their total amounts
    """
    try:
        db = get_mongo_db()
        
        # Use optimized aggregation pipeline for better performance
        pipeline = [
            {
                '$match': {
                    'user_id': user_id,
                    'type': 'payment',
                    'tax_year': tax_year,
                    'expense_category': {'$in': category_list}
                }
            },
            {
                '$group': {
                    '_id': '$expense_category',
                    'total_amount': {'$sum': '$amount'},
                    'count': {'$sum': 1}
                }
            }
        ]
        
        # Execute aggregation pipeline
        results = list(db.cashflows.aggregate(pipeline))
        
        # Format results
        category_totals = {category: 0.0 for category in category_list}
        for result in results:
            category = result['_id']
            if category in category_totals:
                category_totals[category] = float(result['total_amount'])
        
        logger.info(f"Retrieved expenses by categories for user {user_id} in {tax_year}: {category_totals}", 
                   extra={'session_id': session.get('sid', 'no-session-id') if has_request_context() else 'no-session-id'})
        
        return category_totals
        
    except Exception as e:
        logger.error(f"Error retrieving expenses by categories for user {user_id} in {tax_year}: {str(e)}", 
                    extra={'session_id': session.get('sid', 'no-session-id') if has_request_context() else 'no-session-id'})
        
        # Fallback to basic query if aggregation fails
        try:
            expense_query = {
                'user_id': user_id,
                'type': 'payment',
                'tax_year': tax_year,
                'expense_category': {'$in': category_list}
            }
            
            expense_records = db.cashflows.find(expense_query)
            category_totals = {category: 0.0 for category in category_list}
            
            for record in expense_records:
                category = record.get('expense_category')
                amount = record.get('amount', 0)
                if category in category_totals:
                    category_totals[category] += float(amount)
            
            return category_totals
            
        except Exception as fallback_error:
            logger.error(f"Fallback query also failed for user {user_id} in {tax_year}: {str(fallback_error)}", 
                        extra={'session_id': session.get('sid', 'no-session-id') if has_request_context() else 'no-session-id'})
            return {category: 0.0 for category in category_list}

@monitor_query_performance('optimized_tax_calculation_data')
def get_optimized_tax_calculation_data(user_id, tax_year):
    """
    Optimized data retrieval for tax calculations using single aggregation pipeline.
    Retrieves all necessary data for both PIT and CIT calculations in one query.
    
    Args:
        user_id (str): User ID
        tax_year (int): Tax year to calculate for
        
    Returns:
        dict: Dictionary containing all tax calculation data including:
              - total_income: Total income from receipts
              - expenses_by_category: Breakdown of expenses by category
              - deductible_expenses: Total deductible expenses
              - non_deductible_expenses: Total non-deductible expenses
              - statutory_expenses: Statutory & legal contributions
              - rent_utilities_expenses: Rent & utilities expenses
    """
    try:
        db = get_mongo_db()
        
        # Single aggregation pipeline to get all tax calculation data
        pipeline = [
            {
                '$match': {
                    'user_id': user_id,
                    'tax_year': tax_year
                }
            },
            {
                '$group': {
                    '_id': {
                        'type': '$type',
                        'expense_category': '$expense_category',
                        'is_tax_deductible': '$is_tax_deductible'
                    },
                    'total_amount': {'$sum': '$amount'},
                    'count': {'$sum': 1}
                }
            },
            {
                '$group': {
                    '_id': None,
                    'data': {
                        '$push': {
                            'type': '$_id.type',
                            'expense_category': '$_id.expense_category',
                            'is_tax_deductible': '$_id.is_tax_deductible',
                            'total_amount': '$total_amount',
                            'count': '$count'
                        }
                    }
                }
            }
        ]
        
        results = list(db.cashflows.aggregate(pipeline))
        
        # Process results
        tax_data = {
            'total_income': 0.0,
            'expenses_by_category': {},
            'deductible_expenses': 0.0,
            'non_deductible_expenses': 0.0,
            'statutory_expenses': 0.0,
            'rent_utilities_expenses': 0.0,
            'total_expenses': 0.0,
            'expense_count': 0,
            'income_count': 0
        }
        
        if results and results[0]['data']:
            for item in results[0]['data']:
                if item['type'] == 'receipt':
                    tax_data['total_income'] += float(item['total_amount'])
                    tax_data['income_count'] += item['count']
                elif item['type'] == 'payment':
                    category = item['expense_category']
                    amount = float(item['total_amount'])
                    
                    tax_data['total_expenses'] += amount
                    tax_data['expense_count'] += item['count']
                    
                    if category:
                        tax_data['expenses_by_category'][category] = amount
                        
                        # Categorize for tax calculations
                        if item['is_tax_deductible']:
                            tax_data['deductible_expenses'] += amount
                            
                            if category == 'statutory_legal':
                                tax_data['statutory_expenses'] += amount
                            elif category == 'rent_utilities':
                                tax_data['rent_utilities_expenses'] += amount
                        else:
                            tax_data['non_deductible_expenses'] += amount
        
        logger.info(f"Optimized tax calculation data retrieval for user {user_id} in {tax_year}: Income={tax_data['total_income']}, Deductible={tax_data['deductible_expenses']}", 
                   extra={'session_id': session.get('sid', 'no-session-id') if has_request_context() else 'no-session-id'})
        
        return tax_data
        
    except Exception as e:
        logger.error(f"Error in optimized tax calculation data retrieval for user {user_id} in {tax_year}: {str(e)}", 
                    extra={'session_id': session.get('sid', 'no-session-id') if has_request_context() else 'no-session-id'})
        
        # Fallback to individual queries
        try:
            fallback_data = {
                'total_income': get_total_income(user_id, tax_year),
                'expenses_by_category': {},
                'deductible_expenses': 0.0,
                'non_deductible_expenses': 0.0,
                'statutory_expenses': 0.0,
                'rent_utilities_expenses': 0.0,
                'total_expenses': 0.0,
                'expense_count': 0,
                'income_count': 0
            }
            
            # Get all expense categories
            all_categories = ['office_admin', 'staff_wages', 'business_travel', 'rent_utilities', 
                            'marketing_sales', 'cogs', 'personal_expenses', 'statutory_legal']
            
            expenses = get_expenses_by_categories(user_id, tax_year, all_categories)
            fallback_data['expenses_by_category'] = expenses
            
            for category, amount in expenses.items():
                fallback_data['total_expenses'] += amount
                
                if is_category_tax_deductible(category):
                    fallback_data['deductible_expenses'] += amount
                    
                    if category == 'statutory_legal':
                        fallback_data['statutory_expenses'] += amount
                    elif category == 'rent_utilities':
                        fallback_data['rent_utilities_expenses'] += amount
                else:
                    fallback_data['non_deductible_expenses'] += amount
            
            return fallback_data
            
        except Exception as fallback_error:
            logger.error(f"Fallback tax calculation data retrieval also failed for user {user_id} in {tax_year}: {str(fallback_error)}", 
                        extra={'session_id': session.get('sid', 'no-session-id') if has_request_context() else 'no-session-id'})
            return {
                'total_income': 0.0,
                'expenses_by_category': {},
                'deductible_expenses': 0.0,
                'non_deductible_expenses': 0.0,
                'statutory_expenses': 0.0,
                'rent_utilities_expenses': 0.0,
                'total_expenses': 0.0,
                'expense_count': 0,
                'income_count': 0
            }

def calculate_payment_category_stats(payments):
    """
    Calculate category-based summary statistics for a list of payments.
    
    Args:
        payments (list): List of payment records
        
    Returns:
        dict: Dictionary with category statistics including totals by category,
              tax deductible vs non-deductible amounts, and category counts
    """
    try:
        stats = {
            'total_payments': len(payments),
            'total_amount': 0.0,
            'tax_deductible_amount': 0.0,
            'non_deductible_amount': 0.0,
            'category_totals': {},
            'category_counts': {}
        }
        
        # Initialize category totals and counts
        expense_categories = get_expense_categories()
        for category_key, category_data in expense_categories.items():
            stats['category_totals'][category_key] = 0.0
            stats['category_counts'][category_key] = 0
        
        # Process each payment
        for payment in payments:
            amount = float(payment.get('amount', 0))
            category = payment.get('expense_category', 'office_admin')  # Default fallback
            is_tax_deductible = payment.get('is_tax_deductible', True)
            
            # Update totals
            stats['total_amount'] += amount
            
            if is_tax_deductible:
                stats['tax_deductible_amount'] += amount
            else:
                stats['non_deductible_amount'] += amount
            
            # Update category-specific stats
            if category in stats['category_totals']:
                stats['category_totals'][category] += amount
                stats['category_counts'][category] += 1
        
        logger.info(f"Calculated payment category stats: {stats['total_payments']} payments, "
                   f"₦{stats['total_amount']:.2f} total", 
                   extra={'session_id': session.get('sid', 'no-session-id') if has_request_context() else 'no-session-id'})
        
        return stats
    except Exception as e:
        logger.error(f"Error calculating payment category stats: {str(e)}", 
                    extra={'session_id': session.get('sid', 'no-session-id') if has_request_context() else 'no-session-id'})
        return {
            'total_payments': 0,
            'total_amount': 0.0,
            'tax_deductible_amount': 0.0,
            'non_deductible_amount': 0.0,
            'category_totals': {},
            'category_counts': {}
        }

def calculate_net_business_profit(user_id, tax_year):
    """
    Step 1: Calculate net business profit using only 6 deductible categories.
    Excludes Personal Expenses and Statutory & Legal Contributions.
    
    Args:
        user_id (str): User ID
        tax_year (int): Tax year to calculate for
        
    Returns:
        dict: Detailed breakdown of net business profit calculation
    """
    try:
        # Define the 6 deductible categories for Step 1
        deductible_categories = [
            'office_admin', 'staff_wages', 'business_travel', 
            'rent_utilities', 'marketing_sales', 'cogs'
        ]
        
        # Get total income
        total_income = get_total_income(user_id, tax_year)
        
        # Get expenses by deductible categories
        deductible_expenses = get_expenses_by_categories(user_id, tax_year, deductible_categories)
        
        # Calculate total deductible expenses
        total_deductible_expenses = sum(deductible_expenses.values())
        
        # Calculate net business profit
        net_business_profit = total_income - total_deductible_expenses
        
        # Create detailed breakdown
        breakdown = {
            'step': 1,
            'step_name': 'Net Business Profit Calculation',
            'total_income': total_income,
            'deductible_categories': deductible_categories,
            'expense_breakdown': deductible_expenses,
            'total_deductible_expenses': total_deductible_expenses,
            'net_business_profit': net_business_profit,
            'calculation_formula': 'Total Income - Sum of 6 Deductible Categories'
        }
        
        logger.info(f"Calculated net business profit for user {user_id} in {tax_year}: {net_business_profit}", 
                   extra={'session_id': session.get('sid', 'no-session-id') if has_request_context() else 'no-session-id'})
        
        return breakdown
    except Exception as e:
        logger.error(f"Error calculating net business profit for user {user_id} in {tax_year}: {str(e)}", 
                    extra={'session_id': session.get('sid', 'no-session-id') if has_request_context() else 'no-session-id'})
        return {
            'step': 1,
            'step_name': 'Net Business Profit Calculation',
            'total_income': 0.0,
            'deductible_categories': [],
            'expense_breakdown': {},
            'total_deductible_expenses': 0.0,
            'net_business_profit': 0.0,
            'error': str(e)
        }

def apply_statutory_deductions(net_business_profit, user_id, tax_year):
    """
    Step 2: Apply Statutory & Legal Contributions deduction.
    Subtracts statutory expenses from net business profit as a separate step.
    
    Args:
        net_business_profit (float): Net business profit from Step 1
        user_id (str): User ID
        tax_year (int): Tax year to calculate for
        
    Returns:
        dict: Detailed breakdown of statutory deductions application
    """
    try:
        # Get statutory & legal contributions expenses
        statutory_expenses = get_expenses_by_categories(user_id, tax_year, ['statutory_legal'])
        statutory_amount = statutory_expenses.get('statutory_legal', 0.0)
        
        # Apply statutory deduction
        adjusted_profit = net_business_profit - statutory_amount
        
        # Create detailed breakdown
        breakdown = {
            'step': 2,
            'step_name': 'Statutory & Legal Contributions Deduction',
            'net_business_profit_input': net_business_profit,
            'statutory_legal_expenses': statutory_amount,
            'adjusted_profit_after_statutory': adjusted_profit,
            'calculation_formula': 'Net Business Profit - Statutory & Legal Contributions'
        }
        
        logger.info(f"Applied statutory deductions for user {user_id} in {tax_year}: {statutory_amount}, adjusted profit: {adjusted_profit}", 
                   extra={'session_id': session.get('sid', 'no-session-id') if has_request_context() else 'no-session-id'})
        
        return breakdown
    except Exception as e:
        logger.error(f"Error applying statutory deductions for user {user_id} in {tax_year}: {str(e)}", 
                    extra={'session_id': session.get('sid', 'no-session-id') if has_request_context() else 'no-session-id'})
        return {
            'step': 2,
            'step_name': 'Statutory & Legal Contributions Deduction',
            'net_business_profit_input': net_business_profit,
            'statutory_legal_expenses': 0.0,
            'adjusted_profit_after_statutory': net_business_profit,
            'error': str(e)
        }

def apply_rent_relief(adjusted_profit_after_statutory, user_id, tax_year):
    """
    Step 3: Apply Rent Relief calculation and application.
    Calculates rent relief as lesser of 20% of rent expenses or NGN 500,000.
    
    Args:
        adjusted_profit_after_statutory (float): Adjusted profit from Step 2
        user_id (str): User ID
        tax_year (int): Tax year to calculate for
        
    Returns:
        dict: Detailed breakdown of rent relief calculation and application
    """
    try:
        # Get rent & utilities expenses
        rent_expenses = get_expenses_by_categories(user_id, tax_year, ['rent_utilities'])
        annual_rent_expenses = rent_expenses.get('rent_utilities', 0.0)
        
        # Calculate rent relief
        if annual_rent_expenses <= 0:
            rent_relief = 0.0
            rent_relief_calculation = "No rent expenses found"
        else:
            twenty_percent_rent = annual_rent_expenses * 0.20
            max_rent_relief = 500000.0  # NGN 500,000 maximum
            rent_relief = min(twenty_percent_rent, max_rent_relief)
            rent_relief_calculation = f"min(20% of {annual_rent_expenses:,.2f}, NGN 500,000) = min({twenty_percent_rent:,.2f}, {max_rent_relief:,.2f}) = {rent_relief:,.2f}"
        
        # Apply rent relief
        taxable_income_after_rent_relief = adjusted_profit_after_statutory - rent_relief
        
        # Create detailed breakdown
        breakdown = {
            'step': 3,
            'step_name': 'Rent Relief Calculation and Application',
            'adjusted_profit_input': adjusted_profit_after_statutory,
            'annual_rent_utilities_expenses': annual_rent_expenses,
            'twenty_percent_of_rent': annual_rent_expenses * 0.20 if annual_rent_expenses > 0 else 0.0,
            'max_rent_relief_cap': 500000.0,
            'calculated_rent_relief': rent_relief,
            'rent_relief_calculation': rent_relief_calculation,
            'taxable_income_after_rent_relief': taxable_income_after_rent_relief,
            'calculation_formula': 'Adjusted Profit - min(20% of Rent Expenses, NGN 500,000)'
        }
        
        logger.info(f"Applied rent relief for user {user_id} in {tax_year}: {rent_relief}, taxable income: {taxable_income_after_rent_relief}", 
                   extra={'session_id': session.get('sid', 'no-session-id') if has_request_context() else 'no-session-id'})
        
        return breakdown
    except Exception as e:
        logger.error(f"Error applying rent relief for user {user_id} in {tax_year}: {str(e)}", 
                    extra={'session_id': session.get('sid', 'no-session-id') if has_request_context() else 'no-session-id'})
        return {
            'step': 3,
            'step_name': 'Rent Relief Calculation and Application',
            'adjusted_profit_input': adjusted_profit_after_statutory,
            'annual_rent_utilities_expenses': 0.0,
            'twenty_percent_of_rent': 0.0,
            'max_rent_relief_cap': 500000.0,
            'calculated_rent_relief': 0.0,
            'taxable_income_after_rent_relief': adjusted_profit_after_statutory,
            'error': str(e)
        }

def apply_progressive_tax_bands(taxable_income):
    """
    Step 4: Apply NTA 2025 progressive tax band calculation.
    Calculates tax using progressive tax bands with detailed breakdown.
    
    Args:
        taxable_income (float): Taxable income after all deductions
        
    Returns:
        dict: Detailed breakdown of progressive tax calculation
    """
    try:
        # NTA 2025 Progressive Tax Bands
        tax_bands = [
            {'min': 0, 'max': 800000, 'rate': 0.0, 'description': 'First NGN 800,000 (Tax-free)'},
            {'min': 800001, 'max': 3000000, 'rate': 0.15, 'description': 'Next NGN 2,200,000 (15%)'},
            {'min': 3000001, 'max': 12000000, 'rate': 0.18, 'description': 'Next NGN 9,000,000 (18%)'},
            {'min': 12000001, 'max': 25000000, 'rate': 0.21, 'description': 'Next NGN 13,000,000 (21%)'},
            {'min': 25000001, 'max': 50000000, 'rate': 0.23, 'description': 'Next NGN 25,000,000 (23%)'},
            {'min': 50000001, 'max': float('inf'), 'rate': 0.25, 'description': 'Above NGN 50,000,000 (25%)'}
        ]
        
        # Handle zero or negative taxable income
        if taxable_income <= 0:
            return {
                'step': 4,
                'step_name': 'Progressive Tax Band Application',
                'taxable_income': taxable_income,
                'total_tax_liability': 0.0,
                'effective_tax_rate': 0.0,
                'tax_band_breakdown': [],
                'calculation_note': 'No tax liability due to zero or negative taxable income'
            }
        
        total_tax = 0.0
        tax_band_breakdown = []
        
        for band in tax_bands:
            band_min = band['min']
            band_max = band['max']
            rate = band['rate']
            description = band['description']
            
            # Skip if income is below this band
            if taxable_income < band_min:
                continue
            
            # Calculate taxable amount in this band
            if taxable_income <= band_max:
                # All remaining income falls in this band
                taxable_in_band = taxable_income - band_min + 1
            else:
                # Only part of income falls in this band
                taxable_in_band = band_max - band_min + 1
            
            # Apply tax rate to this band
            tax_in_band = taxable_in_band * rate
            total_tax += tax_in_band
            
            # Add to breakdown
            tax_band_breakdown.append({
                'band_description': description,
                'band_min': band_min,
                'band_max': band_max if band_max != float('inf') else None,
                'tax_rate': rate,
                'taxable_amount_in_band': taxable_in_band,
                'tax_in_band': tax_in_band,
                'band_formula': f"{taxable_in_band:,.2f} × {rate:.1%} = {tax_in_band:,.2f}"
            })
        
        # Calculate effective tax rate
        effective_tax_rate = (total_tax / taxable_income * 100) if taxable_income > 0 else 0.0
        
        # Create detailed breakdown
        breakdown = {
            'step': 4,
            'step_name': 'Progressive Tax Band Application',
            'taxable_income': taxable_income,
            'total_tax_liability': total_tax,
            'effective_tax_rate': effective_tax_rate,
            'tax_band_breakdown': tax_band_breakdown,
            'calculation_formula': 'Progressive tax bands applied to taxable income'
        }
        
        logger.info(f"Applied progressive tax bands to taxable income {taxable_income}: total tax {total_tax}", 
                   extra={'session_id': session.get('sid', 'no-session-id') if has_request_context() else 'no-session-id'})
        
        return breakdown
    except Exception as e:
        logger.error(f"Error applying progressive tax bands to taxable income {taxable_income}: {str(e)}", 
                    extra={'session_id': session.get('sid', 'no-session-id') if has_request_context() else 'no-session-id'})
        return {
            'step': 4,
            'step_name': 'Progressive Tax Band Application',
            'taxable_income': taxable_income,
            'total_tax_liability': 0.0,
            'effective_tax_rate': 0.0,
            'tax_band_breakdown': [],
            'error': str(e)
        }

def calculate_four_step_tax_liability(user_id, tax_year):
    """
    Complete four-step tax calculation engine that orchestrates all steps.
    
    Args:
        user_id (str): User ID
        tax_year (int): Tax year to calculate for
        
    Returns:
        dict: Complete tax calculation with all four steps
    """
    try:
        # Step 1: Calculate Net Business Profit
        step1_result = calculate_net_business_profit(user_id, tax_year)
        net_business_profit = step1_result.get('net_business_profit', 0.0)
        
        # Step 2: Apply Statutory & Legal Contributions deduction
        step2_result = apply_statutory_deductions(net_business_profit, user_id, tax_year)
        adjusted_profit_after_statutory = step2_result.get('adjusted_profit_after_statutory', 0.0)
        
        # Step 3: Apply Rent Relief
        step3_result = apply_rent_relief(adjusted_profit_after_statutory, user_id, tax_year)
        taxable_income = step3_result.get('taxable_income_after_rent_relief', 0.0)
        
        # Step 4: Apply Progressive Tax Bands
        step4_result = apply_progressive_tax_bands(taxable_income)
        final_tax_liability = step4_result.get('total_tax_liability', 0.0)
        
        # Compile complete calculation
        complete_calculation = {
            'user_id': user_id,
            'tax_year': tax_year,
            'calculation_timestamp': datetime.now(ZoneInfo("UTC")).isoformat(),
            'step1_net_business_profit': step1_result,
            'step2_statutory_deductions': step2_result,
            'step3_rent_relief': step3_result,
            'step4_progressive_tax': step4_result,
            'final_tax_liability': final_tax_liability,
            'effective_tax_rate': step4_result.get('effective_tax_rate', 0.0),
            'summary': {
                'total_income': step1_result.get('total_income', 0.0),
                'total_deductible_expenses': step1_result.get('total_deductible_expenses', 0.0),
                'statutory_expenses': step2_result.get('statutory_legal_expenses', 0.0),
                'rent_relief': step3_result.get('calculated_rent_relief', 0.0),
                'taxable_income': taxable_income,
                'final_tax_liability': final_tax_liability
            }
        }
        
        logger.info(f"Completed four-step tax calculation for user {user_id} in {tax_year}: final tax {final_tax_liability}", 
                   extra={'session_id': session.get('sid', 'no-session-id') if has_request_context() else 'no-session-id'})
        
        return complete_calculation
    except Exception as e:
        logger.error(f"Error in four-step tax calculation for user {user_id} in {tax_year}: {str(e)}", 
                    extra={'session_id': session.get('sid', 'no-session-id') if has_request_context() else 'no-session-id'})
        return {
            'user_id': user_id,
            'tax_year': tax_year,
            'calculation_timestamp': datetime.now(ZoneInfo("UTC")).isoformat(),
            'error': str(e),
            'final_tax_liability': 0.0,
            'effective_tax_rate': 0.0
        }

