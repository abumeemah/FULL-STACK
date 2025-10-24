from flask import Flask, request, jsonify, Response, redirect, url_for, send_from_directory
from flask_cors import CORS
from flask_pymongo import PyMongo
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from datetime import datetime, timedelta
import jwt
import os
from bson import ObjectId
from functools import wraps
from werkzeug.security import generate_password_hash

# Import blueprints
from blueprints.auth import auth_bp, init_auth_blueprint
from blueprints.users import users_bp, init_users_blueprint
from blueprints.income import init_income_blueprint
from blueprints.expenses import expenses_bp, init_expenses_blueprint
from blueprints.tracking import init_tracking_blueprint
from blueprints.credits import init_credits_blueprint
from blueprints.summaries import init_summaries_blueprint
from blueprints.admin import init_admin_blueprint
from blueprints.tax import init_tax_blueprint
from blueprints.debtors import init_debtors_blueprint
from blueprints.creditors import init_creditors_blueprint
from blueprints.inventory import init_inventory_blueprint
from blueprints.dashboard import init_dashboard_blueprint

# Import database models
from models import DatabaseInitializer

app = Flask(__name__)

# Configuration
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'ficore-mobile-secret-key-2025')
app.config['MONGO_URI'] = os.environ.get('MONGO_URI', 'mongodb://localhost:27017/ficore_mobile')
app.config['JWT_EXPIRATION_DELTA'] = timedelta(hours=24)

# Initialize extensions
CORS(app, origins=['*'])
mongo = PyMongo(app)

# Initialize rate limiter
limiter = Limiter(
    app=app,
    key_func=get_remote_address,
    default_limits=["200 per day", "50 per hour"],
    storage_uri="memory://",
)

# Initialize admin user on startup
def initialize_admin_user():
    """Create admin user if it doesn't exist - safe for deployment"""
    try:
        admin_email = "admin@ficore.com"
        
        # Check if admin already exists
        existing_admin = mongo.db.users.find_one({"email": admin_email})
        if existing_admin:
            # Ensure existing user has admin role
            if existing_admin.get('role') != 'admin':
                mongo.db.users.update_one(
                    {"_id": existing_admin['_id']},
                    {"$set": {"role": "admin", "updatedAt": datetime.utcnow()}}
                )
                print(f"✅ Updated existing user {admin_email} to admin role")
            else:
                print(f"✅ Admin user {admin_email} already exists")
            return existing_admin['_id']
        
        # Create new admin user
        admin_user = {
            "_id": ObjectId(),
            "email": admin_email,
            "password": generate_password_hash("admin123"),
            "firstName": "System",
            "lastName": "Administrator",
            "displayName": "System Administrator",
            "role": "admin",
            "ficoreCreditBalance": 0.0,
            "setupComplete": True,
            "isActive": True,
            "language": "en",
            "currency": "NGN",
            "createdAt": datetime.utcnow(),
            "updatedAt": datetime.utcnow(),
            "settings": {
                "notifications": {
                    "push": True,
                    "email": True,
                    "expenseAlerts": True
                },
                "privacy": {
                    "profileVisibility": "private",
                    "dataSharing": False
                },
                "preferences": {
                    "currency": "NGN",
                    "language": "en",
                    "theme": "light",
                    "dateFormat": "DD/MM/YYYY"
                }
            }
        }
        
        result = mongo.db.users.insert_one(admin_user)
        print(f"✅ Created admin user: {admin_email} (ID: {result.inserted_id})")
        return result.inserted_id
        
    except Exception as e:
        print(f"⚠️  Admin initialization error: {str(e)}")
        return None

# Initialize database and admin on app startup
with app.app_context():
    # Initialize database collections and indexes
    print("\n" + "="*60)
    print("Initializing FiCore Mobile Database...")
    print("="*60)
    db_initializer = DatabaseInitializer(mongo.db)
    db_results = db_initializer.initialize_collections()
    
    if db_results['created']:
        print(f"✅ Created {len(db_results['created'])} new collections")
    if db_results['existing']:
        print(f"✅ Verified {len(db_results['existing'])} existing collections")
    if db_results['errors']:
        print(f"⚠️  {len(db_results['errors'])} errors during initialization")
    print("="*60 + "\n")
    
    # Initialize admin user
    initialize_admin_user()

# Helper function to convert ObjectId to string
def serialize_doc(doc):
    if not doc:
        return doc
    
    # Make a copy to avoid modifying the original
    if isinstance(doc, dict):
        doc = doc.copy()
    
    # Handle _id field
    if '_id' in doc:
        doc['id'] = str(doc['_id'])
        del doc['_id']
    
    # Handle other ObjectId fields recursively
    for key, value in list(doc.items()):  # Use list() to avoid dict changed size during iteration
        if isinstance(value, ObjectId):
            doc[key] = str(value)
        elif isinstance(value, list):
            # Handle lists that might contain ObjectIds or nested documents
            new_list = []
            for item in value:
                if isinstance(item, ObjectId):
                    new_list.append(str(item))
                elif isinstance(item, dict):
                    new_list.append(serialize_doc(item))
                else:
                    new_list.append(item)
            doc[key] = new_list
        elif isinstance(value, dict):
            # Recursively handle nested documents
            doc[key] = serialize_doc(value)
    
    # Final check for any remaining ObjectIds (debugging)
    def check_for_objectids(obj, path=""):
        if isinstance(obj, ObjectId):
            print(f"WARNING: ObjectId found at path '{path}': {obj}")
            return str(obj)
        elif isinstance(obj, dict):
            for k, v in obj.items():
                obj[k] = check_for_objectids(v, f"{path}.{k}" if path else k)
        elif isinstance(obj, list):
            for i, item in enumerate(obj):
                obj[i] = check_for_objectids(item, f"{path}[{i}]")
        return obj
    
    doc = check_for_objectids(doc)
    return doc

# JWT token decorator
def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = request.headers.get('Authorization')
        if not token:
            return jsonify({'success': False, 'message': 'Token is missing'}), 401
        
        try:
            if token.startswith('Bearer '):
                token = token[7:]
            data = jwt.decode(token, app.config['SECRET_KEY'], algorithms=['HS256'])
            
            # Validate user_id exists in token
            if 'user_id' not in data:
                return jsonify({'success': False, 'message': 'Invalid token format'}), 401
            
            # Find user with error handling
            try:
                current_user = mongo.db.users.find_one({'_id': ObjectId(data['user_id'])})
                if not current_user:
                    return jsonify({'success': False, 'message': 'User not found'}), 401
            except Exception as db_error:
                print(f"Database error in token validation: {str(db_error)}")
                return jsonify({'success': False, 'message': 'Database connection error'}), 500
                
        except jwt.ExpiredSignatureError:
            return jsonify({'success': False, 'message': 'Token has expired'}), 401
        except jwt.InvalidTokenError:
            return jsonify({'success': False, 'message': 'Invalid token'}), 401
        except Exception as e:
            print(f"Unexpected error in token validation: {str(e)}")
            return jsonify({'success': False, 'message': 'Authentication error'}), 500
        
        return f(current_user, *args, **kwargs)
    return decorated

# Admin required decorator
def admin_required(f):
    @wraps(f)
    def decorated(current_user, *args, **kwargs):
        if current_user.get('role') != 'admin':
            return jsonify({'success': False, 'message': 'Admin access required'}), 403
        return f(current_user, *args, **kwargs)
    return decorated

# Make limiter available to the app
app.limiter = limiter

# Initialize and register blueprints
auth_blueprint = init_auth_blueprint(mongo, app.config)
users_blueprint = init_users_blueprint(mongo, token_required)
income_blueprint = init_income_blueprint(mongo, token_required, serialize_doc)
expenses_blueprint = init_expenses_blueprint(mongo, token_required, serialize_doc)
tracking_blueprint = init_tracking_blueprint(mongo, token_required, serialize_doc)
credits_blueprint = init_credits_blueprint(mongo, token_required, serialize_doc)
summaries_blueprint = init_summaries_blueprint(mongo, token_required, serialize_doc)
admin_blueprint = init_admin_blueprint(mongo, token_required, admin_required, serialize_doc)
tax_blueprint = init_tax_blueprint(mongo, token_required, serialize_doc)
debtors_blueprint = init_debtors_blueprint(mongo, token_required, serialize_doc)
creditors_blueprint = init_creditors_blueprint(mongo, token_required, serialize_doc)
inventory_blueprint = init_inventory_blueprint(mongo, token_required, serialize_doc)
dashboard_blueprint = init_dashboard_blueprint(mongo, token_required, serialize_doc)

app.register_blueprint(auth_blueprint)
app.register_blueprint(users_blueprint)
app.register_blueprint(income_blueprint)
app.register_blueprint(expenses_blueprint)
app.register_blueprint(tracking_blueprint)
app.register_blueprint(credits_blueprint)
app.register_blueprint(summaries_blueprint)
app.register_blueprint(admin_blueprint)
app.register_blueprint(tax_blueprint)
app.register_blueprint(debtors_blueprint)
app.register_blueprint(creditors_blueprint)
app.register_blueprint(inventory_blueprint)
app.register_blueprint(dashboard_blueprint)

# Health check endpoint
@app.route('/health', methods=['GET'])
def health_check():
    return jsonify({
        'success': True,
        'message': 'FiCore Mobile Backend is running',
        'timestamp': datetime.utcnow().isoformat() + 'Z',
        'version': '1.0.0'
    })

# Admin web interface route - serves the admin dashboard HTML
@app.route('/admin', methods=['GET'])
def admin_index():
    """Serve the admin web interface"""
    try:
        admin_html_path = os.path.join(os.path.dirname(__file__), 'admin_web_app', 'index.html')
        if not os.path.exists(admin_html_path):
            raise FileNotFoundError(f"Admin HTML file not found at {admin_html_path}")
        with open(admin_html_path, 'r', encoding='utf-8') as f:
            html_content = f.read()
        return Response(html_content, mimetype='text/html')
    except FileNotFoundError as e:
        print(f"Error: {str(e)}")  # Log for debugging
        return jsonify({
            'success': False,
            'message': 'Admin interface not found',
            'error': 'Admin web app files are missing'
        }), 404
    except Exception as e:
        print(f"Error: {str(e)}")
        return jsonify({
            'success': False,
            'message': 'Failed to load admin interface',
            'error': str(e)
        }), 500

@app.route('/admin/<path:filename>')
def serve_admin_static(filename):
    """Serve static files for the admin interface"""
    try:
        admin_static_path = os.path.join(os.path.dirname(__file__), 'admin_web_app')
        return send_from_directory(admin_static_path, filename)
    except FileNotFoundError:
        return jsonify({
            'success': False,
            'message': f'Static file {filename} not found'
        }), 404

@app.route('/uploads/<path:filename>')
def serve_uploaded_file(filename):
    """Serve uploaded files (receipts, documents, etc.)"""
    try:
        uploads_path = os.path.join(os.path.dirname(__file__), 'uploads')
        return send_from_directory(uploads_path, filename)
    except FileNotFoundError:
        return jsonify({
            'success': False,
            'message': f'File {filename} not found'
        }), 404
    except Exception as e:
        return jsonify({
            'success': False,
            'message': 'Failed to serve file',
            'error': str(e)
        }), 500

@app.route('/favicon.ico')
def favicon():
    """Serve favicon"""
    try:
        return send_from_directory(os.path.join(os.path.dirname(__file__), 'admin_web_app'), 'favicon.png')
    except FileNotFoundError:
        return jsonify({
            'success': False,
            'message': 'Favicon not found'
        }), 404

# Root endpoint - redirects to admin for web access
@app.route('/', methods=['GET'])
def root():
    """Root endpoint - redirect to admin interface for web access"""
    # Check if request is from a browser (has Accept header with text/html)
    accept_header = request.headers.get('Accept', '')
    if 'text/html' in accept_header:
        # Browser request - redirect to admin interface
        from flask import redirect, url_for
        return redirect(url_for('admin_index'))
    
    # API request - return JSON response
    return jsonify({
        'success': True,
        'message': 'Welcome to FiCore Mobile Backend API',
        'version': '1.0.0',
        'webInterface': '/admin',
        'endpoints': {
            'auth': '/auth/*',
            'users': '/users/*',
            'income': '/income/*',
            'expenses': '/expenses/*',
            'tracking': '/tracking/*',
            'credits': '/credits/*',
            'tax': '/tax/*',
            'debtors': '/debtors/*',
            'creditors': '/creditors/*',
            'inventory': '/inventory/*',
            'dashboard': '/dashboard/*',
            'admin': '/admin/*'
        }
    })

# Dashboard endpoint that combines data from all modules
@app.route('/dashboard', methods=['GET'])
@token_required
def get_dashboard(current_user):
    try:
        # Get current month data
        now = datetime.utcnow()
        start_of_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        
        # Get income data
        incomes = list(mongo.db.incomes.find({'userId': current_user['_id']}))
        total_income_this_month = sum(inc['amount'] for inc in incomes if inc['dateReceived'] >= start_of_month)
        
        # Get expense data
        expenses = list(mongo.db.expenses.find({'userId': current_user['_id']}))
        total_expenses_this_month = sum(exp['amount'] for exp in expenses if exp['date'] >= start_of_month)
        
        # Calculate financial health metrics
        net_income = total_income_this_month - total_expenses_this_month
        savings_rate = (net_income / total_income_this_month * 100) if total_income_this_month > 0 else 0
        
        # Recent transactions (combined income and expenses)
        recent_incomes = sorted(incomes, key=lambda x: x['dateReceived'], reverse=True)[:3]
        recent_expenses = sorted(expenses, key=lambda x: x['date'], reverse=True)[:3]
        
        # Serialize recent transactions
        recent_income_data = []
        for income in recent_incomes:
            income_data = serialize_doc(income.copy())
            income_data['dateReceived'] = income_data.get('dateReceived', datetime.utcnow()).isoformat() + 'Z'
            income_data['type'] = 'income'
            recent_income_data.append(income_data)
        
        recent_expense_data = []
        for expense in recent_expenses:
            expense_data = serialize_doc(expense.copy())
            expense_data['date'] = expense_data.get('date', datetime.utcnow()).isoformat() + 'Z'
            expense_data['type'] = 'expense'
            recent_expense_data.append(expense_data)
        
        # Category breakdown for expenses
        expense_categories = {}
        for expense in expenses:
            if expense['date'] >= start_of_month:
                category = expense['category']
                expense_categories[category] = expense_categories.get(category, 0) + expense['amount']
        
        # Income sources breakdown
        income_sources = {}
        for income in incomes:
            if income['dateReceived'] >= start_of_month:
                source = income['source']
                income_sources[source] = income_sources.get(source, 0) + income['amount']
        
        dashboard_data = {
            'financialSummary': {
                'totalIncome': total_income_this_month,
                'totalExpenses': total_expenses_this_month,
                'netIncome': net_income,
                'savingsRate': savings_rate
            },
            'recentTransactions': {
                'incomes': recent_income_data,
                'expenses': recent_expense_data
            },
            'categoryBreakdown': {
                'expenses': expense_categories,
                'incomeSources': income_sources
            },
            'insights': {
                'topExpenseCategory': max(expense_categories.items(), key=lambda x: x[1])[0] if expense_categories else 'None',
                'topIncomeSource': max(income_sources.items(), key=lambda x: x[1])[0] if income_sources else 'None',
                'monthlyGrowth': 0  # Placeholder for month-over-month growth
            }
        }
        
        return jsonify({
            'success': True,
            'data': dashboard_data,
            'message': 'Dashboard data retrieved successfully'
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'message': 'Failed to retrieve dashboard data',
            'errors': {'general': [str(e)]}
        }), 500

# Analytics endpoint
@app.route('/analytics', methods=['GET'])
@token_required
def get_analytics(current_user):
    try:
        period = request.args.get('period', 'monthly')  # monthly, yearly
        
        # Get all user data
        incomes = list(mongo.db.incomes.find({'userId': current_user['_id']}))
        expenses = list(mongo.db.expenses.find({'userId': current_user['_id']}))
        
        # Calculate trends over time
        now = datetime.utcnow()
        trends = []
        
        for i in range(12):  # Last 12 months
            month_start = (now - timedelta(days=30*i)).replace(day=1)
            month_end = (month_start + timedelta(days=32)).replace(day=1) - timedelta(days=1)
            
            month_incomes = [inc for inc in incomes if month_start <= inc['dateReceived'] <= month_end]
            month_expenses = [exp for exp in expenses if month_start <= exp['date'] <= month_end]
            
            trends.append({
                'month': month_start.strftime('%Y-%m'),
                'income': sum(inc['amount'] for inc in month_incomes),
                'expenses': sum(exp['amount'] for exp in month_expenses),
                'net': sum(inc['amount'] for inc in month_incomes) - sum(exp['amount'] for exp in month_expenses)
            })
        
        # Financial ratios and metrics
        total_income = sum(inc['amount'] for inc in incomes)
        total_expenses = sum(exp['amount'] for exp in expenses)
        
        analytics_data = {
            'trends': trends,
            'totals': {
                'income': total_income,
                'expenses': total_expenses,
                'net': total_income - total_expenses
            },
            'ratios': {
                'savingsRate': ((total_income - total_expenses) / total_income * 100) if total_income > 0 else 0,
                'expenseRatio': (total_expenses / total_income * 100) if total_income > 0 else 0
            },
            'counts': {
                'incomes': len(incomes),
                'expenses': len(expenses)
            }
        }
        
        return jsonify({
            'success': True,
            'data': analytics_data,
            'message': 'Analytics data retrieved successfully'
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'message': 'Failed to retrieve analytics data',
            'errors': {'general': [str(e)]}
        }), 500

# Error handlers
@app.errorhandler(404)
def not_found(error):
    return jsonify({
        'success': False,
        'message': 'Endpoint not found',
        'error': 'The requested resource was not found on this server.'
    }), 404

@app.errorhandler(500)
def internal_error(error):
    return jsonify({
        'success': False,
        'message': 'Internal server error',
        'error': 'An unexpected error occurred. Please try again later.'
    }), 500

@app.errorhandler(400)
def bad_request(error):
    return jsonify({
        'success': False,
        'message': 'Bad request',
        'error': 'The request could not be understood by the server.'
    }), 400

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)


