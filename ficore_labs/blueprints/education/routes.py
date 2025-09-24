from flask import render_template, request, jsonify, flash, redirect, url_for, session
from flask_login import login_required, current_user
from . import education_bp
from utils import get_mongo_db, logger
from translations import trans
from datetime import datetime, timezone
import json

# User types and their corresponding education paths
USER_TYPES = {
    'employee': {
        'name': trans('user_type_employee', default='Employee'),
        'description': trans('user_type_employee_desc', default='I work for someone else and receive a salary'),
        'modules': ['understanding_tax_types', 'paye_basics', 'deductions_reliefs', 'next_steps']
    },
    'entrepreneur_unregistered': {
        'name': trans('user_type_entrepreneur', default='Entrepreneur (Unregistered)'),
        'description': trans('user_type_entrepreneur_desc', default='I run a business but haven\'t registered it formally'),
        'modules': ['understanding_tax_types', 'formalization_benefits', 'presumptive_tax', 'deductions_reliefs', 'tracking_compliance', 'next_steps']
    },
    'sole_proprietor': {
        'name': trans('user_type_sole_proprietor', default='Sole Proprietor (Business Name)'),
        'description': trans('user_type_sole_proprietor_desc', default='I have a registered business name but not a company'),
        'modules': ['understanding_tax_types', 'pit_requirements', 'filing_vs_paying', 'deductions_reliefs', 'tracking_compliance', 'next_steps']
    },
    'company': {
        'name': trans('user_type_company', default='Company (Limited Liability)'),
        'description': trans('user_type_company_desc', default='I have a registered limited liability company'),
        'modules': ['understanding_tax_types', 'cit_requirements', 'filing_vs_paying', 'deductions_reliefs', 'tracking_compliance', 'next_steps']
    }
}

# Education modules content
EDUCATION_MODULES = {
    'understanding_tax_types': {
        'title': trans('module_tax_types_title', default='Understanding Tax Types'),
        'description': trans('module_tax_types_desc', default='Learn which taxes apply to your situation under the Nigeria Tax Act 2025'),
        'content': {
            'pit': {
                'title': trans('pit_title', default='Personal Income Tax (PIT)'),
                'content': trans('pit_content', default='Applies to individuals and sole proprietors. Under NTA 2025, individuals earning ₦800,000 or less per year are exempt from PIT.'),
                'key_points': [
                    trans('pit_point1', default='₦800,000 annual exemption threshold'),
                    trans('pit_point2', default='Applies to sole proprietors and individuals'),
                    trans('pit_point3', default='Progressive tax rates from 15% to 25%')
                ]
            },
            'paye': {
                'title': trans('paye_title', default='Pay-As-You-Earn (PAYE)'),
                'content': trans('paye_content', default='Tax deducted by employers from employee salaries. Your employer handles the calculation and remittance.'),
                'key_points': [
                    trans('paye_point1', default='Automatically deducted by employers'),
                    trans('paye_point2', default='Based on your salary and allowances'),
                    trans('paye_point3', default='Includes pension and NHIS contributions')
                ]
            },
            'cit': {
                'title': trans('cit_title', default='Companies Income Tax (CIT)'),
                'content': trans('cit_content', default='Applies to registered companies. Small companies with turnover ≤ ₦50 million AND total fixed assets < ₦250 million pay 0% CIT under NTA 2025.'),
                'key_points': [
                    trans('cit_point1', default='0% rate for small companies (NTA 2025 criteria)'),
                    trans('cit_point2', default='Turnover ≤ ₦50 million AND fixed assets < ₦250 million'),
                    trans('cit_point3', default='Must still file returns even if no tax is due')
                ]
            },
            'development_levy': {
                'title': trans('development_levy_title', default='Development Levy'),
                'content': trans('development_levy_content', default='New 4% Development Levy applies to companies above the small company threshold under NTA 2025.'),
                'key_points': [
                    trans('dev_levy_point1', default='4% levy on companies above ₦50 million turnover'),
                    trans('dev_levy_point2', default='Applies when fixed assets ≥ ₦250 million'),
                    trans('dev_levy_point3', default='New requirement under NTA 2025')
                ]
            },
            'vat_threshold': {
                'title': trans('vat_threshold_title', default='VAT Registration Threshold'),
                'content': trans('vat_threshold_content', default='Under NTAA 2025, businesses with turnover ≤ ₦100 million are exempt from VAT registration.'),
                'key_points': [
                    trans('vat_point1', default='₦100 million threshold under NTAA 2025'),
                    trans('vat_point2', default='Separate from CIT small company definition'),
                    trans('vat_point3', default='No VAT registration or filing required below threshold')
                ]
            }
        }
    },
    'paye_basics': {
        'title': trans('module_paye_title', default='PAYE Basics for Employees'),
        'description': trans('module_paye_desc', default='Understanding how PAYE works and your rights as an employee'),
        'content': {
            'how_paye_works': {
                'title': trans('paye_how_title', default='How PAYE Works'),
                'content': trans('paye_how_content', default='Your employer calculates and deducts tax from your salary based on current tax rates and your total income.'),
                'key_points': [
                    trans('paye_how_point1', default='Calculated monthly on cumulative basis'),
                    trans('paye_how_point2', default='Includes basic salary and taxable allowances'),
                    trans('paye_how_point3', default='Employer remits to FIRS on your behalf')
                ]
            },
            'employee_reliefs': {
                'title': trans('employee_reliefs_title', default='Available Reliefs'),
                'content': trans('employee_reliefs_content', default='As an employee, you\'re entitled to various reliefs that reduce your taxable income.'),
                'key_points': [
                    trans('employee_relief_point1', default='Pension contributions (minimum 8% of basic salary)'),
                    trans('employee_relief_point2', default='NHIS contributions'),
                    trans('employee_relief_point3', default='Life assurance premiums'),
                    trans('employee_relief_point4', default='Rent relief: 20% of annual rent or ₦500,000 (whichever is lower)')
                ]
            }
        }
    }
}

# Add more modules
EDUCATION_MODULES.update({
    'formalization_benefits': {
        'title': trans('module_formalization_title', default='Benefits of Business Formalization'),
        'description': trans('module_formalization_desc', default='Why registering your business is important and beneficial'),
        'content': {
            'legal_protection': {
                'title': trans('legal_protection_title', default='Legal Protection'),
                'content': trans('legal_protection_content', default='Formal registration provides legal protection and credibility for your business.'),
                'key_points': [
                    trans('legal_point1', default='Protection of business name'),
                    trans('legal_point2', default='Access to formal banking services'),
                    trans('legal_point3', default='Ability to enter into contracts'),
                    trans('legal_point4', default='Limited liability protection (for companies)')
                ]
            },
            'tax_benefits': {
                'title': trans('tax_benefits_title', default='Tax Benefits'),
                'content': trans('tax_benefits_content', default='Formal businesses can access various tax incentives and reliefs.'),
                'key_points': [
                    trans('tax_benefit_point1', default='Access to tax reliefs and deductions'),
                    trans('tax_benefit_point2', default='Ability to claim business expenses'),
                    trans('tax_benefit_point3', default='Eligibility for government incentives'),
                    trans('tax_benefit_point4', default='Simplified tax compliance options')
                ]
            }
        }
    },
    'presumptive_tax': {
        'title': trans('module_presumptive_title', default='Presumptive Tax Option'),
        'description': trans('module_presumptive_desc', default='Alternative to detailed record-keeping for small businesses'),
        'content': {
            'what_is_presumptive': {
                'title': trans('presumptive_what_title', default='What is Presumptive Tax?'),
                'content': trans('presumptive_what_content', default='A simplified tax system where tax is calculated based on estimated income rather than detailed records.'),
                'key_points': [
                    trans('presumptive_point1', default='Based on business type and location'),
                    trans('presumptive_point2', default='No need for detailed bookkeeping'),
                    trans('presumptive_point3', default='Fixed annual amount'),
                    trans('presumptive_point4', default='Suitable for small informal businesses')
                ]
            }
        }
    }
})

# Add remaining modules
EDUCATION_MODULES.update({
    'deductions_reliefs': {
        'title': trans('module_deductions_title', default='Deductions & Reliefs'),
        'description': trans('module_deductions_desc', default='Legal ways to reduce your tax liability'),
        'content': {
            'business_expenses': {
                'title': trans('business_expenses_title', default='Allowable Business Expenses'),
                'content': trans('business_expenses_content', default='Under NTA 2025, expenses that are wholly and exclusively incurred for business purposes are deductible. The "reasonable" and "necessary" tests have been removed.'),
                'key_points': [
                    trans('business_exp_point1', default='Office rent and utilities'),
                    trans('business_exp_point2', default='Staff salaries and benefits'),
                    trans('business_exp_point3', default='Marketing and advertising costs'),
                    trans('business_exp_point4', default='Professional fees and licenses')
                ]
            },
            'personal_reliefs': {
                'title': trans('personal_reliefs_title', default='Personal Reliefs'),
                'content': trans('personal_reliefs_content', default='Reliefs available to reduce your taxable income.'),
                'key_points': [
                    trans('personal_relief_point1', default='Pension contributions'),
                    trans('personal_relief_point2', default='NHIS contributions'),
                    trans('personal_relief_point3', default='Life assurance premiums'),
                    trans('personal_relief_point4', default='Rent relief: 20% of annual rent or ₦500,000')
                ]
            }
        }
    },
    'next_steps': {
        'title': trans('module_next_steps_title', default='Next Steps'),
        'description': trans('module_next_steps_desc', default='Practical steps to ensure tax compliance'),
        'content': {
            'tin_registration': {
                'title': trans('tin_registration_title', default='TIN Registration'),
                'content': trans('tin_registration_content', default='Tax Identification Number is mandatory for all taxable individuals and businesses.'),
                'key_points': [
                    trans('tin_point1', default='Linked to your National Identification Number (NIN)'),
                    trans('tin_point2', default='Required for opening business bank accounts'),
                    trans('tin_point3', default='Needed for government contracts and services'),
                    trans('tin_point4', default='Free registration through FIRS portal')
                ]
            }
        }
    },
    'cit_requirements': {
        'title': trans('module_cit_title', default='Companies Income Tax Requirements'),
        'description': trans('module_cit_desc', default='Understanding CIT obligations for limited liability companies'),
        'content': {
            'cit_rates': {
                'title': trans('cit_rates_title', default='CIT Rates Under NTA 2025'),
                'content': trans('cit_rates_content', default='New favorable rates for small companies with specific criteria under NTA 2025.'),
                'key_points': [
                    trans('cit_rates_point1', default='0% CIT for small companies under NTA 2025'),
                    trans('cit_rates_point2', default='Criteria: Turnover ≤ ₦50 million AND fixed assets < ₦250 million'),
                    trans('cit_rates_point3', default='4% Development Levy applies above threshold'),
                    trans('cit_rates_point4', default='Standard CIT rate for larger companies')
                ]
            },
            'nta_vs_ntaa': {
                'title': trans('nta_vs_ntaa_title', default='NTA vs NTAA: Understanding the Difference'),
                'content': trans('nta_vs_ntaa_content', default='Two separate acts govern different aspects of taxation with different thresholds.'),
                'key_points': [
                    trans('nta_ntaa_point1', default='NTA 2025: ₦50 million threshold for CIT exemption'),
                    trans('nta_ntaa_point2', default='NTAA 2025: ₦100 million threshold for VAT exemption'),
                    trans('nta_ntaa_point3', default='Different acts, different purposes, different thresholds'),
                    trans('nta_ntaa_point4', default='Both must be considered for full compliance')
                ]
            },
            'compliance': {
                'title': trans('cit_compliance_title', default='Compliance Requirements'),
                'content': trans('cit_compliance_content', default='Companies must maintain proper records and file annual returns regardless of tax liability.'),
                'key_points': [
                    trans('cit_compliance_point1', default='Annual filing by June 30th'),
                    trans('cit_compliance_point2', default='Quarterly advance payments (if applicable)'),
                    trans('cit_compliance_point3', default='Audited financial statements (for larger companies)'),
                    trans('cit_compliance_point4', default='Development Levy filing for companies above threshold')
                ]
            }
        }
    },
    'pit_requirements': {
        'title': trans('module_pit_title', default='Personal Income Tax Requirements'),
        'description': trans('module_pit_desc', default='Understanding PIT obligations for sole proprietors'),
        'content': {
            'pit_calculation': {
                'title': trans('pit_calc_title', default='How PIT is Calculated'),
                'content': trans('pit_calc_content', default='PIT is calculated on your net business profit after allowable deductions under NTA 2025.'),
                'key_points': [
                    trans('pit_calc_point1', default='Based on annual business profit'),
                    trans('pit_calc_point2', default='Progressive rates: 15%, 18%, 21%, 23%, 25%'),
                    trans('pit_calc_point3', default='₦800,000 exemption threshold under NTA 2025'),
                    trans('pit_calc_point4', default='Allowable business expenses reduce taxable income')
                ]
            },
            'filing_requirements': {
                'title': trans('pit_filing_title', default='Filing Requirements'),
                'content': trans('pit_filing_content', default='Annual filing is required even if no tax is due under NTA 2025.'),
                'key_points': [
                    trans('pit_filing_point1', default='File by March 31st each year'),
                    trans('pit_filing_point2', default='Required even if income is below ₦800,000'),
                    trans('pit_filing_point3', default='Use FIRS online portal'),
                    trans('pit_filing_point4', default='Keep records for at least 6 years')
                ]
            }
        }
    },
    'filing_vs_paying': {
        'title': trans('module_filing_title', default='Filing vs. Paying Tax'),
        'description': trans('module_filing_desc', default='Understanding the difference between filing returns and paying tax'),
        'content': {
            'why_file': {
                'title': trans('why_file_title', default='Why Filing is Required'),
                'content': trans('why_file_content', default='Filing tax returns is mandatory under both NTA and NTAA 2025, even when no tax is due.'),
                'key_points': [
                    trans('why_file_point1', default='Legal requirement under tax law'),
                    trans('why_file_point2', default='Maintains good standing with FIRS'),
                    trans('why_file_point3', default='Required for accessing government services'),
                    trans('why_file_point4', default='Enables claiming of reliefs and exemptions')
                ]
            },
            'consequences': {
                'title': trans('consequences_title', default='Consequences of Non-Filing'),
                'content': trans('consequences_content', default='Failure to file can result in penalties and assessments under both acts.'),
                'key_points': [
                    trans('consequences_point1', default='Penalties and interest charges'),
                    trans('consequences_point2', default='FIRS may make estimated assessments'),
                    trans('consequences_point3', default='Difficulty accessing loans and contracts'),
                    trans('consequences_point4', default='Potential audit and investigation')
                ]
            }
        }
    },
    'tracking_compliance': {
        'title': trans('module_tracking_title', default='Tracking for Compliance'),
        'description': trans('module_tracking_desc', default='How proper record-keeping supports tax compliance'),
        'content': {
            'digital_records': {
                'title': trans('digital_records_title', default='Digital Record Keeping'),
                'content': trans('digital_records_content', default='Modern tools make it easier to maintain accurate business records for compliance.'),
                'key_points': [
                    trans('digital_point1', default='Automatic categorization of expenses'),
                    trans('digital_point2', default='Digital receipts and invoices'),
                    trans('digital_point3', default='Real-time financial reporting'),
                    trans('digital_point4', default='Audit trail for all transactions')
                ]
            },
            'categorization': {
                'title': trans('categorization_title', default='Expense Categorization'),
                'content': trans('categorization_content', default='Proper categorization using the "wholly and exclusively" test simplifies tax filing.'),
                'key_points': [
                    trans('categorization_point1', default='Separate business and personal expenses'),
                    trans('categorization_point2', default='Apply "wholly and exclusively" test'),
                    trans('categorization_point3', default='Maintain supporting documentation'),
                    trans('categorization_point4', default='Regular reconciliation and review')
                ]
            }
        }
    }
})

# Routes
@education_bp.route('/')
@login_required
def education_home():
    """Education section home page with user type selection"""
    return render_template('education/home.html', 
                         user_types=USER_TYPES,
                         title=trans('education_title', default='Tax Education Center'))

@education_bp.route('/user-type/<user_type>')
@login_required
def user_type_modules(user_type):
    """Display modules for selected user type"""
    if user_type not in USER_TYPES:
        flash(trans('invalid_user_type', default='Invalid user type selected'), 'error')
        return redirect(url_for('education_bp.education_home'))
    
    user_config = USER_TYPES[user_type]
    modules = []
    
    for module_id in user_config['modules']:
        if module_id in EDUCATION_MODULES:
            module = EDUCATION_MODULES[module_id].copy()
            module['id'] = module_id
            modules.append(module)
    
    return render_template('education/user_type.html',
                         user_type=user_type,
                         user_config=user_config,
                         modules=modules,
                         title=f"{trans('education_for', default='Tax Education for')} {user_config['name']}")

@education_bp.route('/module/<module_id>')
@login_required
def view_module(module_id):
    """Display specific education module"""
    if module_id not in EDUCATION_MODULES:
        flash(trans('module_not_found', default='Module not found'), 'error')
        return redirect(url_for('education_bp.education_home'))
    
    module = EDUCATION_MODULES[module_id]
    
    # Track module view
    try:
        db = get_mongo_db()
        db.education_progress.update_one(
            {'user_id': current_user.id, 'module_id': module_id},
            {
                '$set': {
                    'last_viewed': datetime.now(timezone.utc),
                    'view_count': 1
                },
                '$inc': {'total_views': 1}
            },
            upsert=True
        )
    except Exception as e:
        logger.error(f"Error tracking module view for user {current_user.id}: {str(e)}")
    
    return render_template('education/module.html',
                         module_id=module_id,
                         module=module,
                         title=module['title'])

@education_bp.route('/glossary')
@login_required
def glossary():
    """Display tax glossary"""
    # Tax glossary terms
    TAX_GLOSSARY = {
        'assessable_income': {
            'term': trans('glossary_assessable_income', default='Assessable Income'),
            'definition': trans('glossary_assessable_income_def', default='Total income from all sources before deductions and reliefs')
        },
        'taxable_profit': {
            'term': trans('glossary_taxable_profit', default='Taxable Profit'),
            'definition': trans('glossary_taxable_profit_def', default='Business profit after deducting allowable expenses and reliefs')
        },
        'allowable_expenses': {
            'term': trans('glossary_allowable_expenses', default='Allowable Expenses'),
            'definition': trans('glossary_allowable_expenses_def', default='Business expenses that can be deducted from income for tax purposes')
        },
        'presumptive_tax': {
            'term': trans('glossary_presumptive_tax', default='Presumptive Tax'),
            'definition': trans('glossary_presumptive_tax_def', default='Simplified tax system based on estimated income rather than actual records')
        },
        'tin': {
            'term': trans('glossary_tin', default='Tax Identification Number (TIN)'),
            'definition': trans('glossary_tin_def', default='Unique number assigned to taxpayers for identification and tracking')
        },
        'paye': {
            'term': trans('glossary_paye', default='Pay-As-You-Earn (PAYE)'),
            'definition': trans('glossary_paye_def', default='Tax deducted from employee salaries by employers')
        },
        'pit': {
            'term': trans('glossary_pit', default='Personal Income Tax (PIT)'),
            'definition': trans('glossary_pit_def', default='Tax on income earned by individuals and sole proprietors')
        },
        'cit': {
            'term': trans('glossary_cit', default='Companies Income Tax (CIT)'),
            'definition': trans('glossary_cit_def', default='Tax on profits earned by registered companies')
        },
        'development_levy': {
            'term': trans('glossary_development_levy', default='Development Levy'),
            'definition': trans('glossary_development_levy_def', default='4% levy on companies above ₦50 million turnover under NTA 2025')
        },
        'nta_2025': {
            'term': trans('glossary_nta', default='Nigeria Tax Act (NTA) 2025'),
            'definition': trans('glossary_nta_def', default='Governs CIT, PIT, and Development Levy with ₦50 million small company threshold')
        },
        'ntaa_2025': {
            'term': trans('glossary_ntaa', default='Nigeria Tax Administration Act (NTAA) 2025'),
            'definition': trans('glossary_ntaa_def', default='Governs VAT and tax administration with ₦100 million small business threshold')
        },
        'wholly_exclusively': {
            'term': trans('glossary_wholly_exclusively', default='Wholly and Exclusively Test'),
            'definition': trans('glossary_wholly_exclusively_def', default='NTA 2025 standard for deductible expenses - removes "reasonable" and "necessary" tests')
        }
    }
    
    return render_template('education/glossary.html',
                         glossary=TAX_GLOSSARY,
                         title=trans('tax_glossary', default='Tax Glossary'))

@education_bp.route('/progress')
@login_required
def user_progress():
    """Display user's learning progress"""
    try:
        db = get_mongo_db()
        progress_records = list(db.education_progress.find({'user_id': current_user.id}))
        
        # Calculate progress statistics
        total_modules = len(EDUCATION_MODULES)
        viewed_modules = len(progress_records)
        progress_percentage = (viewed_modules / total_modules * 100) if total_modules > 0 else 0
        
        return render_template('education/progress.html',
                             progress_records=progress_records,
                             total_modules=total_modules,
                             viewed_modules=viewed_modules,
                             progress_percentage=progress_percentage,
                             title=trans('learning_progress', default='Learning Progress'))
    
    except Exception as e:
        logger.error(f"Error fetching progress for user {current_user.id}: {str(e)}")
        flash(trans('error_loading_progress', default='Error loading progress'), 'error')
        return redirect(url_for('education_bp.education_home'))

@education_bp.route('/search')
@login_required
def search():
    """Search education content"""
    query = request.args.get('q', '').strip()
    
    if not query:
        return render_template('education/search.html',
                             query='',
                             results=[],
                             title=trans('search_education', default='Search Education'))
    
    # Simple search through module content
    results = []
    query_lower = query.lower()
    
    for module_id, module in EDUCATION_MODULES.items():
        # Search in title and description
        if (query_lower in module['title'].lower() or 
            query_lower in module['description'].lower()):
            results.append({
                'type': 'module',
                'id': module_id,
                'title': module['title'],
                'description': module['description'],
                'url': url_for('education_bp.view_module', module_id=module_id)
            })
    
    return render_template('education/search.html',
                         query=query,
                         results=results,
                         title=f"{trans('search_results_for', default='Search Results for')} '{query}'")

@education_bp.route('/api/track-completion', methods=['POST'])
@login_required
def track_completion():
    """Track module completion"""
    try:
        data = request.get_json()
        module_id = data.get('module_id')
        
        if module_id not in EDUCATION_MODULES:
            return jsonify({'success': False, 'error': 'Invalid module ID'}), 400
        
        db = get_mongo_db()
        result = db.education_progress.update_one(
            {'user_id': current_user.id, 'module_id': module_id},
            {
                '$set': {
                    'completed': True,
                    'completed_at': datetime.now(timezone.utc)
                }
            },
            upsert=True
        )
        
        return jsonify({'success': True, 'message': 'Progress tracked successfully'})
    
    except Exception as e:
        logger.error(f"Error tracking completion for user {current_user.id}: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500