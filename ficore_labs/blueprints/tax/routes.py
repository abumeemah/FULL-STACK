from flask import render_template, request, jsonify, flash, redirect, url_for
from flask_login import login_required, current_user
from . import tax_bp
import utils
from utils import get_mongo_db, logger, get_all_expense_categories
from translations import trans
from tax_calculation_engine import (
    get_user_entity_type, ENTITY_TYPES, get_entity_type_info,
    calculate_tax_liability
)
import json
from datetime import datetime

def get_expense_categories():
    """Get expense categories with translations for tax calculator interface"""
    try:
        # Get all expense categories from utils.py
        all_categories = get_all_expense_categories()
        
        # Create translated categories for the interface
        translated_categories = {}
        
        for category_key, category_data in all_categories.items():
            # Create translation keys based on category
            name_key = f"{category_key}_cat"
            desc_key = f"{category_key}_desc"
            
            translated_categories[category_key] = {
                'name': trans(name_key, default=category_data.get('name', category_key)),
                'description': trans(desc_key, default=category_data.get('description', '')),
                'examples': category_data.get('examples', []),
                'tax_deductible': category_data.get('tax_deductible', False),
                'is_personal': category_data.get('is_personal', False),
                'is_statutory': category_data.get('is_statutory', False)
            }
        
        return translated_categories
    except Exception as e:
        logger.error(f"Error getting expense categories for tax calculator: {str(e)}")
        # Fallback to basic categories if there's an error
        return {
            'office_admin': {
                'name': 'Office & Admin',
                'description': 'Office supplies, stationery, internet/data, utility bills',
                'examples': ['Office supplies', 'Stationery', 'Internet/Data', 'Electricity'],
                'tax_deductible': True,
                'is_personal': False,
                'is_statutory': False
            }
        }

# Progressive tax bands for Nigeria Tax Act 2025
TAX_BANDS = [
    {'min': 0, 'max': 800000, 'rate': 0.0},
    {'min': 800001, 'max': 3000000, 'rate': 0.15},
    {'min': 3000001, 'max': 12000000, 'rate': 0.18},
    {'min': 12000001, 'max': 25000000, 'rate': 0.21},
    {'min': 25000001, 'max': 50000000, 'rate': 0.23},
    {'min': 50000001, 'max': float('inf'), 'rate': 0.25}
]

def calculate_progressive_tax(taxable_income):
    """Calculate tax using progressive tax bands"""
    if taxable_income <= 0:
        return 0
    
    total_tax = 0
    
    for band in TAX_BANDS:
        band_min = band['min']
        band_max = band['max']
        rate = band['rate']
        
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
    
    return total_tax

def calculate_rent_relief(annual_rent):
    """Calculate rent relief as lower of ₦500,000 or 20% of annual rent"""
    if not annual_rent or annual_rent <= 0:
        return 0
    
    twenty_percent = annual_rent * 0.20
    return min(500000, twenty_percent)

@tax_bp.route('/calculator')
@login_required
def tax_calculator():
    """Render the tax calculator page with enhanced four-step calculation support"""
    try:
        db = get_mongo_db()
        
        # Get user's entity type
        user_entity_type = get_user_entity_type(current_user.id, db)
        entity_info = get_entity_type_info(user_entity_type)
        
        # Get all available entity types for selection
        available_entity_types = ENTITY_TYPES
        
        # Get expense categories with full metadata
        expense_categories = get_expense_categories()
        
        # Add calculation breakdown context for template
        calculation_context = {
            'four_step_process': {
                'step1': 'Net Business Profit Calculation',
                'step2': 'Statutory & Legal Contributions Deduction', 
                'step3': 'Rent Relief Application',
                'step4': 'Progressive Tax Band Application'
            },
            'deductible_categories': [key for key, data in expense_categories.items() 
                                    if data.get('tax_deductible', False) and not data.get('is_statutory', False)],
            'statutory_categories': [key for key, data in expense_categories.items() 
                                   if data.get('is_statutory', False)],
            'non_deductible_categories': [key for key, data in expense_categories.items() 
                                        if not data.get('tax_deductible', False)]
        }
        
        return render_template('tax/tax_calculator.html', 
                             expense_categories=expense_categories,
                             user_annual_rent=current_user.annual_rent or 0,
                             user_entity_type=user_entity_type,
                             entity_info=entity_info,
                             available_entity_types=available_entity_types,
                             calculation_context=calculation_context)
                             
    except Exception as e:
        logger.error(f"Error in tax_calculator route: {str(e)}")
        flash('Error loading tax calculator. Please try again.', 'error')
        return redirect(url_for('dashboard_bp.dashboard'))

@tax_bp.route('/calculate', methods=['POST'])
@login_required
def calculate_tax():
    """Enhanced API endpoint for tax calculation with detailed breakdown response"""
    try:
        db = get_mongo_db()
        data = request.get_json()
        
        # Validate input data
        if not data:
            return jsonify({
                'success': False,
                'error': 'No data provided',
                'message': 'Please provide income and expense data for calculation.'
            }), 400
        
        # Use enhanced validation
        is_valid, validation_errors = utils.validate_tax_calculation_input(data)
        if not is_valid:
            error_messages = utils.format_validation_errors_for_flash(validation_errors)
            return jsonify({
                'success': False,
                'error': 'Validation failed',
                'message': 'Please correct the following errors: ' + '; '.join(error_messages),
                'validation_errors': validation_errors
            }), 400
        
        # Get user's entity type
        user_entity_type = get_user_entity_type(current_user.id, db)
        entity_info = get_entity_type_info(user_entity_type)
        
        # Extract validated data
        total_income = float(data.get('total_income', 0))
        annual_rent = float(data.get('annual_rent', current_user.annual_rent or 0))
        
        # Clean expense data
        expenses = data.get('expenses', {})
        cleaned_expenses = {}
        for category, amount in expenses.items():
            amount_float = float(amount) if amount else 0
            cleaned_expenses[category] = amount_float
        
        current_year = datetime.now().year
        
        try:
            # Perform calculation based on entity type with enhanced error handling
            if user_entity_type == 'limited_liability':
                # Use CIT calculation logic
                result = simulate_cit_calculation(total_income, cleaned_expenses, entity_info)
            else:
                # Use PIT four-step calculation logic
                result = simulate_pit_four_step_calculation(total_income, cleaned_expenses, annual_rent, entity_info)
            
            # Validate calculation result
            if not result or not isinstance(result, dict):
                raise ValueError("Invalid calculation result")
            
            # Ensure required fields are present
            required_fields = ['calculation_type']
            missing_fields = [field for field in required_fields if field not in result]
            if missing_fields:
                logger.warning(f"Calculation result missing fields: {missing_fields}")
                # Continue with available data but log the issue
            
            # Add metadata to response
            result['calculation_metadata'] = {
                'user_id': current_user.id,
                'calculation_timestamp': datetime.now().isoformat(),
                'tax_year': current_year,
                'calculation_version': '2.0',
                'entity_type': user_entity_type,
                'input_validation_passed': True
            }
            
            logger.info(f"Tax calculation completed successfully for user {current_user.id}")
            
            return jsonify({
                'success': True,
                'breakdown': result,
                'message': 'Tax calculation completed successfully'
            })
            
        except ValueError as calc_error:
            logger.error(f"Calculation error for user {current_user.id}: {str(calc_error)}")
            return jsonify({
                'success': False,
                'error': 'Calculation error',
                'message': 'Unable to complete tax calculation. Please check your input data.',
                'details': str(calc_error)
            }), 400
            
        except Exception as calc_error:
            logger.error(f"Unexpected calculation error for user {current_user.id}: {str(calc_error)}", exc_info=True)
            return jsonify({
                'success': False,
                'error': 'Calculation failure',
                'message': 'An error occurred during tax calculation. Please try again.',
                'user_message': 'We encountered an issue while calculating your tax. Please verify your data and try again.'
            }), 500
        
    except ValueError as e:
        logger.error(f"Validation error in tax calculation for user {current_user.id}: {str(e)}")
        return jsonify({
            'success': False,
            'error': 'Validation error',
            'message': str(e),
            'user_message': 'Please check your input data and try again.'
        }), 400
    except Exception as e:
        logger.error(f"Unexpected error in tax calculation for user {current_user.id}: {str(e)}", exc_info=True)
        return jsonify({
            'success': False,
            'error': 'Internal server error',
            'message': 'An unexpected error occurred during tax calculation. Please try again.',
            'user_message': 'We are experiencing technical difficulties. Please try again later.'
        }), 500

def simulate_cit_calculation(total_income, expenses, entity_info):
    """Simulate CIT calculation with comprehensive breakdown for API response"""
    try:
        # Validate and sanitize inputs
        validated_income, validated_expenses, _, warnings = validate_calculation_inputs(
            total_income, expenses, 0.0
        )
        
        if warnings:
            logger.warning(f"CIT calculation warnings: {warnings}")
        
        cit_revenue_threshold = 50000000.0  # ₦50 Million
        
        # Calculate total expenses from all business categories
        total_expenses = sum(validated_expenses.values())
        
        # Categorize expenses for detailed breakdown
        expense_categories = get_expense_categories()
        categorized_expenses = {}
        for category, amount in validated_expenses.items():
            if category in expense_categories:
                categorized_expenses[category] = {
                    'amount': amount,
                    'category_name': expense_categories[category]['name'],
                    'tax_deductible': expense_categories[category]['tax_deductible']
                }
        
        if validated_income <= cit_revenue_threshold:
            # Small company exemption
            result = {
                'calculation_type': 'CIT',
                'entity_type': 'limited_liability',
                'entity_info': entity_info,
                'total_revenue': validated_income,
                'revenue_threshold': cit_revenue_threshold,
                'total_expenses': total_expenses,
                'exemption_applied': True,
                'tax_rate': 0.0,
                'taxable_income': 0.0,
                'tax_liability': 0.0,
                'effective_tax_rate': 0.0,
                'exemption_reason': f'Small company exemption (revenue ≤₦{cit_revenue_threshold:,.0f})',
                'calculation_note': 'No tax liability due to small company exemption under CIT regulations',
                'expense_breakdown': categorized_expenses,
                'calculation_steps': [
                    {
                        'step': 1,
                        'description': 'Revenue Assessment',
                        'calculation': f'Total Revenue: ₦{validated_income:,.2f}',
                        'result': validated_income
                    },
                    {
                        'step': 2,
                        'description': 'Threshold Check',
                        'calculation': f'₦{validated_income:,.2f} ≤ ₦{cit_revenue_threshold:,.2f}',
                        'result': 'Exemption Applied'
                    },
                    {
                        'step': 3,
                        'description': 'Final Tax Liability',
                        'calculation': 'Small Company Exemption = 0% tax rate',
                        'result': 0.0
                    }
                ]
            }
            
            # Add warnings if any
            if warnings:
                result['calculation_warnings'] = warnings
            
            return result
        else:
            # Large company: 30% tax on taxable income
            taxable_income = max(0, validated_income - total_expenses)
            tax_liability = taxable_income * 0.30
            effective_tax_rate = (tax_liability / validated_income * 100) if validated_income > 0 else 0
            
            result = {
                'calculation_type': 'CIT',
                'entity_type': 'limited_liability',
                'entity_info': entity_info,
                'total_revenue': validated_income,
                'revenue_threshold': cit_revenue_threshold,
                'total_expenses': total_expenses,
                'taxable_income': taxable_income,
                'exemption_applied': False,
                'tax_rate': 0.30,
                'tax_liability': tax_liability,
                'effective_tax_rate': effective_tax_rate,
                'expense_breakdown': categorized_expenses,
                'calculation_formula': f'Taxable Income × 30% = ₦{taxable_income:,.2f} × 30% = ₦{tax_liability:,.2f}',
                'calculation_steps': [
                    {
                        'step': 1,
                        'description': 'Revenue Assessment',
                        'calculation': f'Total Revenue: ₦{validated_income:,.2f}',
                        'result': validated_income
                    },
                    {
                        'step': 2,
                        'description': 'Expense Deduction',
                        'calculation': f'₦{validated_income:,.2f} - ₦{total_expenses:,.2f}',
                        'result': taxable_income
                    },
                    {
                        'step': 3,
                        'description': 'Tax Calculation',
                        'calculation': f'₦{taxable_income:,.2f} × 30%',
                        'result': tax_liability
                    }
                ]
            }
            
            # Add warnings if any
            if warnings:
                result['calculation_warnings'] = warnings
            
            return result
    except Exception as e:
        logger.error(f"Error in CIT calculation simulation: {str(e)}")
        raise

def handle_incomplete_data_scenario(user_id, data_type, fallback_value=0.0):
    """
    Handle scenarios where tax year data is incomplete or missing.
    
    Args:
        user_id: User ID for logging
        data_type: Type of missing data
        fallback_value: Default value to use
        
    Returns:
        Fallback value with logging
    """
    logger.warning(f"Incomplete {data_type} data for user {user_id}, using fallback value: {fallback_value}")
    return fallback_value

def validate_calculation_inputs(total_income, expenses, annual_rent):
    """
    Validate and sanitize calculation inputs with fallback logic.
    
    Args:
        total_income: Total income value
        expenses: Dictionary of expenses
        annual_rent: Annual rent value
        
    Returns:
        Tuple of (validated_income, validated_expenses, validated_rent, warnings)
    """
    warnings = []
    
    # Validate income
    try:
        validated_income = float(total_income) if total_income is not None else 0.0
        if validated_income < 0:
            warnings.append("Income was negative, adjusted to zero")
            validated_income = 0.0
    except (ValueError, TypeError):
        warnings.append("Invalid income value, using zero")
        validated_income = 0.0
    
    # Validate expenses
    validated_expenses = {}
    if isinstance(expenses, dict):
        for category, amount in expenses.items():
            try:
                validated_amount = float(amount) if amount is not None else 0.0
                if validated_amount < 0:
                    warnings.append(f"Negative expense for {category}, adjusted to zero")
                    validated_amount = 0.0
                validated_expenses[category] = validated_amount
            except (ValueError, TypeError):
                warnings.append(f"Invalid expense amount for {category}, using zero")
                validated_expenses[category] = 0.0
    else:
        warnings.append("Invalid expenses data, using empty expenses")
        validated_expenses = {}
    
    # Validate rent
    try:
        validated_rent = float(annual_rent) if annual_rent is not None else 0.0
        if validated_rent < 0:
            warnings.append("Annual rent was negative, adjusted to zero")
            validated_rent = 0.0
    except (ValueError, TypeError):
        warnings.append("Invalid annual rent value, using zero")
        validated_rent = 0.0
    
    return validated_income, validated_expenses, validated_rent, warnings

def simulate_pit_four_step_calculation(total_income, expenses, annual_rent, entity_info):
    """Simulate comprehensive PIT four-step calculation with detailed API breakdown"""
    try:
        # Validate and sanitize inputs
        validated_income, validated_expenses, validated_rent, warnings = validate_calculation_inputs(
            total_income, expenses, annual_rent
        )
        
        if warnings:
            logger.warning(f"PIT calculation warnings: {warnings}")
        
        expense_categories = get_expense_categories()
        
        # Step 1: Net Business Profit (6 deductible categories, excluding statutory)
        deductible_categories = ['office_admin', 'staff_wages', 'business_travel', 
                               'rent_utilities', 'marketing_sales', 'cogs']
        
        deductible_expenses = {}
        for category in deductible_categories:
            amount = validated_expenses.get(category, 0)
            if amount > 0:
                deductible_expenses[category] = {
                    'amount': amount,
                    'category_name': expense_categories.get(category, {}).get('name', category),
                    'tax_deductible': True
                }
        
        total_deductible_expenses = sum(exp['amount'] for exp in deductible_expenses.values())
        net_business_profit = validated_income - total_deductible_expenses
        
        step1_breakdown = {
            'step': 1,
            'step_name': 'Net Business Profit Calculation',
            'description': 'Calculate profit using only the 6 main deductible business expense categories',
            'total_income': validated_income,
            'deductible_categories': deductible_categories,
            'deductible_expenses': deductible_expenses,
            'total_deductible_expenses': total_deductible_expenses,
            'net_business_profit': net_business_profit,
            'formula': f'₦{validated_income:,.2f} - ₦{total_deductible_expenses:,.2f} = ₦{net_business_profit:,.2f}',
            'calculation_note': 'Personal Expenses and Statutory & Legal Contributions are excluded from this step'
        }
        
        # Step 2: Statutory & Legal Contributions deduction
        statutory_expenses = validated_expenses.get('statutory_legal', 0)
        adjusted_profit_after_statutory = net_business_profit - statutory_expenses
        
        step2_breakdown = {
            'step': 2,
            'step_name': 'Statutory & Legal Contributions Deduction',
            'description': 'Apply statutory and legal expenses as a separate deduction step',
            'net_business_profit_input': net_business_profit,
            'statutory_expenses': statutory_expenses,
            'adjusted_profit_after_statutory': adjusted_profit_after_statutory,
            'formula': f'₦{net_business_profit:,.2f} - ₦{statutory_expenses:,.2f} = ₦{adjusted_profit_after_statutory:,.2f}',
            'calculation_note': 'Statutory & Legal Contributions are treated separately per NTA 2025'
        }
        
        # Step 3: Rent Relief application
        rent_relief = calculate_rent_relief(validated_rent)
        twenty_percent_rent = validated_rent * 0.20 if validated_rent > 0 else 0
        max_rent_relief = 500000.0
        taxable_income_after_rent_relief = adjusted_profit_after_statutory - rent_relief
        
        step3_breakdown = {
            'step': 3,
            'step_name': 'Rent Relief Application',
            'description': 'Apply rent relief as the lesser of 20% of annual rent or ₦500,000',
            'adjusted_profit_input': adjusted_profit_after_statutory,
            'annual_rent': validated_rent,
            'twenty_percent_of_rent': twenty_percent_rent,
            'max_rent_relief_cap': max_rent_relief,
            'calculated_rent_relief': rent_relief,
            'taxable_income_after_rent_relief': taxable_income_after_rent_relief,
            'formula': f'₦{adjusted_profit_after_statutory:,.2f} - min(₦{twenty_percent_rent:,.2f}, ₦{max_rent_relief:,.2f}) = ₦{taxable_income_after_rent_relief:,.2f}',
            'calculation_note': f'Rent relief = min(20% × ₦{validated_rent:,.2f}, ₦500,000) = ₦{rent_relief:,.2f}'
        }
        
        # Step 4: Progressive tax bands
        final_taxable_income = max(0, taxable_income_after_rent_relief)
        tax_liability = calculate_progressive_tax(final_taxable_income)
        tax_band_breakdown = get_tax_band_breakdown(final_taxable_income)
        effective_tax_rate = (tax_liability / validated_income * 100) if validated_income > 0 else 0
        
        step4_breakdown = {
            'step': 4,
            'step_name': 'Progressive Tax Band Application',
            'description': 'Apply NTA 2025 progressive tax bands to final taxable income',
            'taxable_income': final_taxable_income,
            'tax_liability': tax_liability,
            'effective_tax_rate': effective_tax_rate,
            'tax_band_breakdown': tax_band_breakdown,
            'formula': f'Progressive bands applied to ₦{final_taxable_income:,.2f} = ₦{tax_liability:,.2f}',
            'calculation_note': 'Tax calculated using NTA 2025 progressive tax bands'
        }
        
        # Include non-deductible expenses for reference
        personal_expenses = validated_expenses.get('personal_expenses', 0)
        
        return {
            'calculation_type': 'PIT',
            'entity_type': 'sole_proprietor',
            'entity_info': entity_info,
            'four_step_breakdown': {
                'step1': step1_breakdown,
                'step2': step2_breakdown,
                'step3': step3_breakdown,
                'step4': step4_breakdown
            },
            'summary': {
                'total_income': validated_income,
                'total_deductible_expenses': total_deductible_expenses,
                'statutory_expenses': statutory_expenses,
                'personal_expenses': personal_expenses,
                'rent_relief': rent_relief,
                'final_taxable_income': final_taxable_income,
                'tax_liability': tax_liability,
                'effective_tax_rate': effective_tax_rate
            },
            'expense_breakdown': {
                'deductible': deductible_expenses,
                'statutory': {
                    'statutory_legal': {
                        'amount': statutory_expenses,
                        'category_name': 'Statutory & Legal Contributions',
                        'tax_deductible': True,
                        'special_treatment': 'Applied in Step 2'
                    }
                } if statutory_expenses > 0 else {},
                'non_deductible': {
                    'personal_expenses': {
                        'amount': personal_expenses,
                        'category_name': 'Personal Expenses',
                        'tax_deductible': False,
                        'note': 'Not included in tax calculations'
                    }
                } if personal_expenses > 0 else {}
            },
            'calculation_methodology': 'Four-step PIT calculation per NTA 2025 regulations'
        }
        
        # Add warnings if any
        if warnings:
            result['calculation_warnings'] = warnings
        
        return result
    except Exception as e:
        logger.error(f"Error in PIT four-step calculation simulation: {str(e)}")
        raise

def get_tax_band_breakdown(taxable_income):
    """Get detailed tax band breakdown for progressive tax calculation"""
    if taxable_income <= 0:
        return []
    
    tax_bands = [
        {'min': 0, 'max': 800000, 'rate': 0.0, 'description': 'First ₦800,000 (Tax-free)'},
        {'min': 800001, 'max': 3000000, 'rate': 0.15, 'description': 'Next ₦2,200,000 (15%)'},
        {'min': 3000001, 'max': 12000000, 'rate': 0.18, 'description': 'Next ₦9,000,000 (18%)'},
        {'min': 12000001, 'max': 25000000, 'rate': 0.21, 'description': 'Next ₦13,000,000 (21%)'},
        {'min': 25000001, 'max': 50000000, 'rate': 0.23, 'description': 'Next ₦25,000,000 (23%)'},
        {'min': 50000001, 'max': float('inf'), 'rate': 0.25, 'description': 'Above ₦50,000,000 (25%)'}
    ]
    
    breakdown = []
    
    for band in tax_bands:
        if taxable_income < band['min']:
            continue
            
        taxable_in_band = min(taxable_income, band['max']) - band['min'] + 1
        if taxable_in_band <= 0:
            continue
            
        tax_in_band = taxable_in_band * band['rate']
        
        breakdown.append({
            'description': band['description'],
            'taxable_amount': taxable_in_band,
            'rate': band['rate'],
            'tax_amount': tax_in_band,
            'formula': f'₦{taxable_in_band:,.2f} × {band["rate"]:.1%} = ₦{tax_in_band:,.2f}'
        })
    
    return breakdown

@tax_bp.route('/update-rent', methods=['POST'])
@login_required
def update_annual_rent():
    """Update user's annual rent in database"""
    try:
        data = request.get_json()
        annual_rent = float(data.get('annual_rent', 0))
        
        # Update user's annual rent in MongoDB
        db = get_mongo_db()
        result = db.users.update_one(
            {'_id': current_user.id},
            {'$set': {'annual_rent': annual_rent}}
        )
        
        if result.modified_count > 0:
            logger.info(f"Updated annual rent for user {current_user.id}: {annual_rent}")
        
        return jsonify({
            'success': True,
            'message': 'Annual rent updated successfully'
        })
        
    except Exception as e:
        logger.error(f"Error updating annual rent for user {current_user.id}: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 400

@tax_bp.route('/update-entity-type', methods=['POST'])
@login_required
def update_entity_type():
    """Update user's business entity type"""
    try:
        from tax_calculation_engine import update_user_entity_type, validate_entity_type
        
        data = request.get_json()
        entity_type = data.get('entity_type')
        
        # Validate entity type
        if not validate_entity_type(entity_type):
            return jsonify({
                'success': False,
                'error': 'Invalid entity type'
            }), 400
        
        # Update entity type in database
        db = get_mongo_db()
        success = update_user_entity_type(current_user.id, entity_type, db)
        
        if success:
            logger.info(f"Updated entity type for user {current_user.id}: {entity_type}")
            entity_info = get_entity_type_info(entity_type)
            
            return jsonify({
                'success': True,
                'message': 'Entity type updated successfully',
                'entity_type': entity_type,
                'entity_info': entity_info
            })
        else:
            return jsonify({
                'success': False,
                'error': 'Failed to update entity type'
            }), 500
        
    except Exception as e:
        logger.error(f"Error updating entity type for user {current_user.id}: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 400