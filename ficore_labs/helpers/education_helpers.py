"""
Education helpers for contextual prompts and integration with other app features
"""
from flask import url_for, session
from translations import trans
import random

def get_education_prompt(context_type, **kwargs):
    """
    Get contextual education prompts based on user actions
    
    Args:
        context_type: Type of context (expense_logged, receipt_added, etc.)
        **kwargs: Additional context data
    
    Returns:
        dict: Prompt data with message, link, and action text
    """
    prompts = {
        'expense_logged': {
            'message': trans('education_prompt_expense', 
                           default='Did you know some of these expenses are tax-deductible?'),
            'link': url_for('education_bp.view_module', module_id='deductions_reliefs'),
            'action_text': trans('learn_about_deductions', default='Learn About Deductions'),
            'icon': 'fas fa-percentage'
        },
        'receipt_added': {
            'message': trans('education_prompt_receipt', 
                           default='Keep digital records for tax compliance!'),
            'link': url_for('education_bp.view_module', module_id='tracking_compliance'),
            'action_text': trans('learn_record_keeping', default='Learn About Record Keeping'),
            'icon': 'fas fa-clipboard-check'
        },
        'annual_rent_updated': {
            'message': trans('education_prompt_rent', 
                           default='Rent relief can lower your tax! Learn more about available reliefs.'),
            'link': url_for('education_bp.view_module', module_id='deductions_reliefs'),
            'action_text': trans('learn_rent_relief', default='Learn About Rent Relief'),
            'icon': 'fas fa-home'
        },
        'first_time_user': {
            'message': trans('education_prompt_welcome', 
                           default='New to tax compliance? Start with understanding your tax obligations.'),
            'link': url_for('education_bp.education_home'),
            'action_text': trans('start_tax_education', default='Start Tax Education'),
            'icon': 'fas fa-graduation-cap'
        },
        'tax_season_reminder': {
            'message': trans('education_prompt_filing', 
                           default='Filing season is approaching! Make sure you understand the requirements.'),
            'link': url_for('education_bp.view_module', module_id='filing_vs_paying'),
            'action_text': trans('learn_filing_requirements', default='Learn Filing Requirements'),
            'icon': 'fas fa-calendar-alt'
        }
    }
    
    return prompts.get(context_type, None)

def get_random_education_tip():
    """Get a random education tip for display"""
    tips = [
        {
            'message': trans('tip_expense_categories', 
                           default='Properly categorizing expenses helps maximize your tax deductions'),
            'link': url_for('education_bp.view_module', module_id='deductions_reliefs'),
            'action_text': trans('learn_deductions', default='Learn About Deductions')
        },
        {
            'message': trans('tip_tin_registration', 
                           default='TIN registration is free and mandatory for all taxpayers'),
            'link': url_for('education_bp.view_module', module_id='next_steps'),
            'action_text': trans('learn_tin', default='Learn About TIN')
        },
        {
            'message': trans('tip_filing_deadline', 
                           default='Filing tax returns is required even if you owe no tax'),
            'link': url_for('education_bp.view_module', module_id='filing_vs_paying'),
            'action_text': trans('learn_filing', default='Learn About Filing')
        },
        {
            'message': trans('tip_rent_relief', 
                           default='You can claim rent relief of up to ₦500,000 annually'),
            'link': url_for('education_bp.view_module', module_id='deductions_reliefs'),
            'action_text': trans('learn_reliefs', default='Learn About Reliefs')
        }
    ]
    
    return random.choice(tips)

def should_show_education_prompt(user_id, context_type):
    """
    Determine if an education prompt should be shown based on user behavior
    
    Args:
        user_id: User ID
        context_type: Type of context
    
    Returns:
        bool: Whether to show the prompt
    """
    # Simple logic - show prompts occasionally to avoid overwhelming users
    # In a real implementation, you might track user interactions and preferences
    
    # Show prompts less frequently for experienced users
    session_key = f'education_prompt_{context_type}_shown'
    
    if session.get(session_key, False):
        return False
    
    # Show prompt with some probability
    import random
    if random.random() < 0.3:  # 30% chance
        session[session_key] = True
        return True
    
    return False

def get_user_type_recommendation(user_data):
    """
    Recommend user type based on user's business data
    
    Args:
        user_data: User data from database
    
    Returns:
        str: Recommended user type
    """
    business_details = user_data.get('business_details', {})
    
    # Simple logic to recommend user type
    if not business_details:
        return 'employee'
    
    # If they have business details but no formal registration info
    if business_details and not business_details.get('registration_type'):
        return 'entrepreneur_unregistered'
    
    # If they mention "Limited" or "Ltd" in business name
    business_name = business_details.get('name', '').lower()
    if 'limited' in business_name or 'ltd' in business_name:
        return 'company'
    
    # Default to sole proprietor if they have business details
    return 'sole_proprietor'

def get_next_recommended_module(user_id, current_module_id):
    """
    Get the next recommended module based on user's progress
    
    Args:
        user_id: User ID
        current_module_id: Current module ID
    
    Returns:
        str: Next recommended module ID
    """
    # Define learning paths for different user types
    learning_paths = {
        'employee': ['understanding_tax_types', 'paye_basics', 'deductions_reliefs', 'next_steps'],
        'entrepreneur_unregistered': ['understanding_tax_types', 'formalization_benefits', 'presumptive_tax', 'deductions_reliefs', 'tracking_compliance', 'next_steps'],
        'sole_proprietor': ['understanding_tax_types', 'pit_requirements', 'filing_vs_paying', 'deductions_reliefs', 'tracking_compliance', 'next_steps'],
        'company': ['understanding_tax_types', 'cit_requirements', 'filing_vs_paying', 'deductions_reliefs', 'tracking_compliance', 'next_steps']
    }
    
    # For now, return a general next step
    # In a real implementation, you'd check user's type and progress
    general_path = ['understanding_tax_types', 'deductions_reliefs', 'filing_vs_paying', 'next_steps']
    
    try:
        current_index = general_path.index(current_module_id)
        if current_index < len(general_path) - 1:
            return general_path[current_index + 1]
    except ValueError:
        pass
    
    return 'understanding_tax_types'  # Default starting point