# Education Section

## Overview

The Education section provides comprehensive tax literacy content for Nigerian businesses and individuals. It addresses the critical pain point of lack of tax knowledge among informal businesses by providing clear, actionable information tailored to different user types.

## Features

### 1. User-Type Based Navigation 🧭
- **Employee**: Focus on PAYE, deductions, and reliefs
- **Entrepreneur (Unregistered)**: Formalization benefits, TIN registration, Presumptive Tax
- **Sole Proprietor**: PIT requirements, deductible expenses, filing requirements
- **Company**: CIT overview, compliance requirements for incorporated businesses

### 2. Education Modules 📚

#### Module A: Understanding Tax Types
- **PIT (Personal Income Tax)**: ₦800,000 exemption under NTA 2025
- **PAYE (Pay-As-You-Earn)**: Employee tax deductions
- **CIT (Companies Income Tax)**: 0% rate for small companies (≤ ₦50M turnover AND < ₦250M fixed assets) under NTA 2025
- **Development Levy**: New 4% levy for companies above small company threshold
- **VAT Threshold**: ₦100M exemption under NTAA 2025 (separate from CIT)

#### Module B: Filing vs. Paying
- Why filing is required even with 0% tax liability
- Consequences of non-compliance
- Penalties and assessments

#### Module C: Deductions & Reliefs
- **Allowable Business Expenses**: "wholly and exclusively" incurred (NTA 2025 removes "reasonable" and "necessary" tests)
- **Personal Reliefs**: Pension, NHIS, life assurance, rent relief (20% or ₦500K max)
- **Non-Deductible**: Personal expenses like groceries, school fees

#### Module D: Tracking for Compliance
- Digital record keeping benefits
- Expense categorization for tax filing
- Audit trail maintenance

#### Module E: Next Steps
- **TIN Registration**: Linked to NIN, mandatory for all taxpayers
- **Filing Tools**: FIRS portal, mobile apps, authorized consultants
- **Professional Help**: When to seek tax advice

### 3. Interactive Features

#### Contextual Prompts
- In-app tooltips after expense logging: "Did you know some expenses are tax-deductible?"
- Periodic reminders for filing deadlines
- Educational tips based on user actions

#### Search & Discovery
- Full-text search across all modules
- Glossary with key tax terms
- Popular topics quick access

#### Progress Tracking
- Module completion tracking
- Learning progress visualization
- Personalized recommendations

## Technical Implementation

### File Structure
```
blueprints/education/
├── __init__.py              # Blueprint initialization
├── routes.py                # Route handlers and content
└── README.md               # This documentation

templates/education/
├── home.html               # User type selection
├── user_type.html          # Module listing for user type
├── module.html             # Individual module content
├── glossary.html           # Tax glossary
├── search.html             # Search interface
└── progress.html           # Progress tracking

helpers/
└── education_helpers.py    # Contextual prompts and utilities

translations/general_features/
└── education_translations.py # Multi-language support
```

### Database Schema
```python
education_progress: {
    'user_id': str,           # User identifier
    'module_id': str,         # Module identifier
    'last_viewed': datetime,  # Last access time
    'view_count': int,        # Number of views
    'total_views': int,       # Total view count
    'completed': bool,        # Completion status
    'completed_at': datetime  # Completion timestamp
}
```

### Routes
- `GET /education/` - Home page with user type selection
- `GET /education/user-type/<type>` - Modules for specific user type
- `GET /education/module/<id>` - Individual module content
- `GET /education/glossary` - Tax glossary
- `GET /education/search` - Search interface
- `GET /education/progress` - User progress dashboard
- `POST /education/api/track-completion` - Mark module as complete

## Key Legal Updates (NTA 2025)

### Personal Income Tax (PIT)
- **New Exemption**: ₦800,000 annual threshold (up from previous limits)
- **Progressive Rates**: 15%, 18%, 21%, 23%, 25%
- **Filing Requirement**: Mandatory even if no tax due

### Companies Income Tax (CIT) - NTA 2025
- **Small Company Relief**: 0% rate for companies with turnover ≤ ₦50 million AND fixed assets < ₦250 million
- **Development Levy**: 4% levy applies to companies above small company threshold
- **Filing Requirement**: Annual returns still mandatory regardless of tax liability

### VAT Registration - NTAA 2025
- **Small Business Exemption**: ₦100 million turnover threshold (separate from CIT)
- **No Registration Required**: Below threshold businesses exempt from VAT registration and filing

### New Reliefs and Changes
- **Rent Relief**: 20% of annual rent or ₦500,000 (whichever lower)
- **Bond Interest**: 5-year tax exemption on government securities
- **Simplified Deduction Test**: "Wholly and exclusively" standard (removes "reasonable" and "necessary")
- **Development Levy**: New 4% levy for larger companies
- **Dual Threshold System**: NTA 2025 (₦50M for CIT) vs NTAA 2025 (₦100M for VAT)

## Integration Points

### With Tax Calculator
- Direct links from education modules to calculator
- Contextual examples using calculator functionality
- Practice scenarios for learning

### With Expense Tracking
- Contextual prompts when logging expenses
- Category explanations linked to education content
- Deduction optimization suggestions

### With Compliance Features
- Filing deadline reminders with educational content
- TIN registration guidance
- Record-keeping best practices

## Multilingual Support

Currently supports:
- **English**: Complete translations
- **Hausa**: Basic translations (expandable)

Translation keys follow the pattern:
- `education_*` for general education terms
- `module_*` for module-specific content
- `glossary_*` for tax terminology

## Future Enhancements

1. **Interactive Quizzes**: Test understanding after each module
2. **Video Content**: Visual explanations of complex concepts
3. **Case Studies**: Real-world examples for different business types
4. **Certification**: Completion certificates for learning paths
5. **Expert Q&A**: Integration with tax professionals
6. **Mobile Optimization**: Dedicated mobile learning experience

## Usage Analytics

Track user engagement through:
- Module completion rates
- Time spent per module
- Search query analysis
- Most accessed content
- User journey mapping

This data helps optimize content and identify knowledge gaps.