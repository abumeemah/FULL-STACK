# Ficore Labs (DIICE) - Full Stack Business Management Platform

## Overview

Ficore Labs (DIICE) is a comprehensive, modern business management platform designed specifically for African entrepreneurs and traders. It provides daily-use incentives, actionable insights, and a robust set of tools to help users manage finances, inventory, compliance, taxation, and business growth—all in a secure, mobile-friendly, and extensible environment.

The platform features a streamlined user experience for entrepreneurs/traders with dedicated admin capabilities for system management, comprehensive tax calculation tools, and educational resources to help users understand Nigerian tax compliance.

## Key Features

### 🎯 Core Business Management
- **Smart Reminders**: Daily log reminders with customizable debt aging alerts
- **Quick Log Buttons**: Fast entry for sales, expenses, and inventory transactions
- **Visual Progress & Charts**: Dashboard with profit/loss tracking, streaks, and financial health visualization (Chart.js)
- **Streaks & Gamification**: Track daily usage streaks with rewards (up to 30% discount on 100-day streaks)
- **Profit Summary PDF**: Downloadable profit/loss reports with detailed breakdowns (ReportLab)

### 💰 Advanced Financial Management
- **Expense Categorization System**: 8 comprehensive expense categories with tax deductibility tracking:
  - Office & Admin (tax-deductible)
  - Staff & Wages (tax-deductible)
  - Business Travel & Transport (tax-deductible)
  - Rent & Utilities (tax-deductible)
  - Marketing & Sales (tax-deductible)
  - Cost of Goods Sold - COGS (tax-deductible)
  - Personal Expenses (non-deductible)
  - Statutory & Legal Contributions (tax-deductible, special handling)

- **Debt & Credit Tracking**: Comprehensive alerts for unpaid debts/credits with quick management links
- **Tax Preparation Mode**: Toggle to show only true profit for accurate tax calculations
- **Inventory Loss Detection**: Smart alerts when inventory costs exceed expected margins

### 🧮 Tax Calculation Engine
- **Dual Entity Type Support**: 
  - Sole Proprietor (Personal Income Tax - PIT)
  - Limited Liability Company (Companies Income Tax - CIT)
- **Four-Step PIT Calculation**:
  1. Net Business Profit calculation using 6 deductible categories
  2. Statutory & Legal Contributions deduction
  3. Rent Relief calculation (lesser of 20% rent or ₦500,000)
  4. Progressive tax band application (NTA 2025 rates: 15%, 18%, 21%, 24%, 25%)
- **CIT Calculation**: 0% for companies ≤₦50M revenue, 30% for >₦50M revenue
- **Real-time Tax Calculator**: Interactive interface with detailed breakdown displays

### 📚 Education & Compliance
- **Tax Education System**: Personalized learning paths based on user type:
  - Employee (PAYE focus)
  - Entrepreneur Unregistered (formalization benefits)
  - Sole Proprietor (PIT requirements)
  - Company (CIT requirements)
- **Interactive Learning Modules**: Understanding tax types, filing requirements, deductions & reliefs
- **Compliance Tracking**: Tools to help users stay compliant with Nigerian tax regulations

### 📊 Inventory & Operations
- **Full Inventory Management**: Complete CRUD operations with dedicated module and UI
- **Loss Detection**: Automated alerts for inventory cost anomalies
- **Margin Tracking**: Monitor profitability across inventory items

### 👥 User Management & Security
- **Secure Authentication**: Flask-Login with session management
- **Trial/Subscription Logic**: Flexible subscription system with trial periods
- **Admin Dashboard**: Dedicated admin account for user monitoring, KYC management, and system oversight
- **Role-based Access Control**: Separate interfaces for traders and administrators

### 🌍 Internationalization & Accessibility
- **Multi-language Support**: English and Hausa translations (Flask-Babel)
- **PWA Support**: Installable, offline-capable web app with manifest and service worker
- **Responsive Design**: Mobile-first, Bootstrap 5-based interface
- **Accessibility Compliance**: ARIA labels, keyboard navigation, screen reader support

### 🔔 Notifications & Engagement
- **In-app Notifications**: Real-time alerts for key events and reminders
- **Engagement Banners**: Contextual prompts to encourage platform usage
- **Reward System**: Streak-based incentives and discount programs

### 📋 Compliance & Documentation
- **KYC Management**: Upload and manage compliance documents
- **Audit Logging**: Comprehensive activity tracking for compliance
- **Report Generation**: Detailed financial reports for tax and business purposes

## Tech Stack

### Backend
- **Python 3** with **Flask** framework
- **Flask Extensions**: Login, Session, Babel, Limiter, CORS, WTF, Compress
- **Database**: MongoDB with PyMongo driver
- **Authentication**: Flask-Login with secure session management
- **PDF Generation**: ReportLab for financial reports

### Frontend
- **Templates**: Jinja2 with Bootstrap 5
- **Charts**: Chart.js for financial visualizations
- **PWA**: Manifest.json and Service Worker (sw.js)
- **Styling**: Custom CSS with responsive design

### Infrastructure
- **Deployment**: WSGI (wsgi.py) compatible with Render.com/Heroku/Cloud platforms
- **Configuration**: Environment variables with dotenv
- **Logging**: Comprehensive logging with session tracking
- **Security**: CSRF protection, CORS handling, rate limiting

## Application Modules

### Core Modules
- **Dashboard**: Central hub with reminders, charts, streaks, and financial alerts
- **Payments & Receipts**: Record and manage all cashflows with expense categorization
- **Inventory**: Add, view, and manage inventory items with loss detection
- **Debtors & Creditors**: Track receivables and payables with aging alerts

### Financial & Tax Modules
- **Tax Calculator**: Interactive tax calculation with entity type support
- **Reports**: Generate and download comprehensive profit/loss summaries
- **Education**: Tax education system with personalized learning paths

### Management Modules
- **Admin**: User monitoring, KYC management, subscription oversight (admin only)
- **Settings**: User profile, preferences, language selection, entity type management
- **KYC & Compliance**: Document upload and compliance management
- **Subscribe**: Trial and subscription plan management

### Engagement Modules
- **Notifications**: In-app alerts and reminder system
- **Rewards**: Streak tracking and reward management

## Directory Structure

```
ficore_labs/
├── app.py                 # App factory and blueprint registration
├── models.py              # Data models and database initialization
├── utils.py               # Utility functions (DB, logging, expense categories)
├── tax_calculation_engine.py  # Tax calculation logic for PIT and CIT
├── wsgi.py               # WSGI entry point
├── requirements.txt      # Python dependencies
├── blueprints/           # Flask blueprints for modular architecture
│   ├── admin/           # Admin management interface
│   ├── business/        # Business logic and operations
│   ├── creditors/       # Creditor management
│   ├── dashboard/       # Main dashboard
│   ├── debtors/         # Debtor management
│   ├── education/       # Tax education system
│   ├── general/         # General pages and landing
│   ├── inventory/       # Inventory management
│   ├── kyc/            # KYC and compliance
│   ├── payments/        # Payment processing with categories
│   ├── receipts/        # Receipt management
│   ├── reports/         # Financial reporting
│   ├── rewards/         # Reward and streak system
│   ├── settings/        # User settings and preferences
│   ├── subscribe/       # Subscription management
│   ├── tax/            # Tax calculator interface
│   └── users/          # User authentication and management
├── helpers/             # Custom business logic
├── templates/           # Jinja2 templates (modular by section)
├── static/             # CSS, JS, images, manifest, service worker
├── translations/        # Multi-language support files
└── notifications/       # Notification system
```

## Getting Started

### Prerequisites
- Python 3.8+
- MongoDB database
- Environment variables for configuration

### Installation

1. **Clone the repository**
   ```bash
   git clone <repository-url>
   cd ficore_labs
   ```

2. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

3. **Set up environment variables**
   Create a `.env` file with:
   ```
   SECRET_KEY=your_secret_key_here
   MONGO_URI=your_mongodb_connection_string
   FLASK_ENV=development
   ```

4. **Run the application**
   ```bash
   python -m ficore_labs.app
   # or
   flask run
   ```

5. **Access the application**
   Open http://localhost:5000 in your browser

### Default Admin Account
- **Username**: admin
- **Password**: Admin123!

This account is auto-created for system management, user monitoring, KYC oversight, and subscription management. All other users are entrepreneurs/traders by default.

## Key Features in Detail

### Expense Categorization System
The platform includes a sophisticated 8-category expense system designed for Nigerian tax compliance:

- **6 Tax-Deductible Categories**: Office & Admin, Staff & Wages, Business Travel, Rent & Utilities, Marketing & Sales, COGS
- **1 Non-Deductible Category**: Personal Expenses
- **1 Special Category**: Statutory & Legal Contributions (handled separately in tax calculations)

### Tax Calculation Engine
- **Automatic Entity Type Detection**: Routes calculations based on user's business structure
- **PIT Four-Step Process**: Compliant with Nigeria Tax Act 2025
- **CIT Revenue Threshold**: Automatic 0% vs 30% rate application
- **Rent Relief Calculation**: Automatic application of rent relief benefits
- **Progressive Tax Bands**: Accurate application of multiple tax rates

### Education System
- **Personalized Learning**: Content adapts based on user's business type
- **Interactive Modules**: Step-by-step guidance through tax concepts
- **Practical Examples**: Real-world scenarios relevant to Nigerian businesses
- **Compliance Tracking**: Tools to help users stay compliant

## Contributing

We welcome contributions! Please follow these guidelines:

1. **Code Style**: Follow PEP8 standards
2. **Modular Design**: Keep features modular using the blueprint system
3. **Translations**: Update relevant files in `translations/` for new features
4. **Testing**: Include tests for new functionality
5. **Documentation**: Update README and inline documentation

### Adding New Blueprints
1. Create blueprint under `blueprints/<name>/`
2. Import in `app.py`: `from blueprints.<name>.routes import <name>_bp`
3. Register: `app.register_blueprint(<name>_bp, url_prefix='/<name>')`

### Translation Updates
- Update files in `translations/general_features/` and `translations/trader/`
- Use translation keys in templates: `{{ trans('key_name', default='Default Text') }}`

## Deployment

The application is designed for easy deployment on cloud platforms:

- **Render.com**: Use `wsgi.py` as entry point
- **Heroku**: Compatible with Heroku's Python buildpack
- **Cloud Platforms**: Standard WSGI deployment

### Environment Configuration
Ensure these environment variables are set in production:
- `SECRET_KEY`: Strong secret key for session security
- `MONGO_URI`: MongoDB connection string
- `FLASK_ENV`: Set to 'production'
- `SERVER_NAME`: Your domain name
- `PREFERRED_URL_SCHEME`: 'https' for production

## License

This project is proprietary software developed by Ficore Labs for African entrepreneurs and traders.

## Support

For support, feature requests, or bug reports, please contact the development team or create an issue in the project repository.

---

**Ficore Labs** - Empowering African entrepreneurs with modern business management tools and tax compliance education.