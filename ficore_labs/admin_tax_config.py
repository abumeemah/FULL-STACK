#!/usr/bin/env python3
"""
Admin Tax Configuration Management
Adds missing tax configuration management functionality for admins
"""

from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required, current_user
from flask_wtf import FlaskForm
from wtforms import FloatField, IntegerField, StringField, SelectField, SubmitField, TextAreaField
from wtforms.validators import DataRequired, NumberRange, Length
from datetime import datetime, timezone
import logging
from utils import get_mongo_db, requires_role
from translations import trans

logger = logging.getLogger(__name__)

# Tax Configuration Forms
class TaxRateForm(FlaskForm):
    """Form for managing tax rates"""
    entity_type = SelectField(
        'Business Entity Type',
        choices=[
            ('sole_proprietor', 'Individual/Sole Proprietor'),
            ('limited_liability', 'Limited Liability Company')
        ],
        validators=[DataRequired()],
        render_kw={'class': 'form-select'}
    )
    tax_year = IntegerField(
        'Tax Year',
        validators=[DataRequired(), NumberRange(min=2020, max=2030)],
        render_kw={'class': 'form-control'}
    )
    rate_percentage = FloatField(
        'Tax Rate (%)',
        validators=[DataRequired(), NumberRange(min=0, max=100)],
        render_kw={'class': 'form-control'}
    )
    description = TextAreaField(
        'Description',
        validators=[Length(max=500)],
        render_kw={'class': 'form-control', 'rows': 3}
    )
    submit = SubmitField('Save Tax Rate', render_kw={'class': 'btn btn-primary'})

class TaxBandForm(FlaskForm):
    """Form for managing progressive tax bands"""
    tax_year = IntegerField(
        'Tax Year',
        validators=[DataRequired(), NumberRange(min=2020, max=2030)],
        render_kw={'class': 'form-control'}
    )
    band_min = FloatField(
        'Minimum Amount (₦)',
        validators=[DataRequired(), NumberRange(min=0)],
        render_kw={'class': 'form-control'}
    )
    band_max = FloatField(
        'Maximum Amount (₦)',
        validators=[NumberRange(min=0)],
        render_kw={'class': 'form-control', 'placeholder': 'Leave empty for unlimited'}
    )
    rate_percentage = FloatField(
        'Tax Rate (%)',
        validators=[DataRequired(), NumberRange(min=0, max=100)],
        render_kw={'class': 'form-control'}
    )
    description = StringField(
        'Band Description',
        validators=[DataRequired(), Length(max=200)],
        render_kw={'class': 'form-control'}
    )
    submit = SubmitField('Save Tax Band', render_kw={'class': 'btn btn-primary'})

class TaxExemptionForm(FlaskForm):
    """Form for managing tax exemptions"""
    entity_type = SelectField(
        'Business Entity Type',
        choices=[
            ('sole_proprietor', 'Individual/Sole Proprietor'),
            ('limited_liability', 'Limited Liability Company')
        ],
        validators=[DataRequired()],
        render_kw={'class': 'form-select'}
    )
    tax_year = IntegerField(
        'Tax Year',
        validators=[DataRequired(), NumberRange(min=2020, max=2030)],
        render_kw={'class': 'form-control'}
    )
    exemption_threshold = FloatField(
        'Exemption Threshold (₦)',
        validators=[DataRequired(), NumberRange(min=0)],
        render_kw={'class': 'form-control'}
    )
    exemption_type = SelectField(
        'Exemption Type',
        choices=[
            ('income_threshold', 'Income Threshold'),
            ('revenue_threshold', 'Revenue Threshold'),
            ('special_category', 'Special Category')
        ],
        validators=[DataRequired()],
        render_kw={'class': 'form-select'}
    )
    description = TextAreaField(
        'Description',
        validators=[DataRequired(), Length(max=500)],
        render_kw={'class': 'form-control', 'rows': 3}
    )
    submit = SubmitField('Save Exemption', render_kw={'class': 'btn btn-primary'})

# Tax Configuration Management Functions
def get_tax_rates(tax_year=None):
    """Get all tax rates, optionally filtered by year"""
    try:
        db = get_mongo_db()
        query = {}
        if tax_year:
            query['tax_year'] = tax_year
        
        rates = list(db.tax_rates.find(query).sort('tax_year', -1))
        return rates
    except Exception as e:
        logger.error(f"Error retrieving tax rates: {str(e)}")
        return []

def save_tax_rate(entity_type, tax_year, rate_percentage, description, admin_id):
    """Save or update a tax rate configuration"""
    try:
        db = get_mongo_db()
        
        tax_rate_data = {
            'entity_type': entity_type,
            'tax_year': tax_year,
            'rate_percentage': rate_percentage,
            'description': description,
            'updated_by': admin_id,
            'updated_at': datetime.now(timezone.utc)
        }
        
        # Update existing or create new
        result = db.tax_rates.update_one(
            {'entity_type': entity_type, 'tax_year': tax_year},
            {'$set': tax_rate_data, '$setOnInsert': {'created_at': datetime.now(timezone.utc)}},
            upsert=True
        )
        
        # Log the action
        db.audit_logs.insert_one({
            'admin_id': admin_id,
            'action': 'update_tax_rate',
            'details': tax_rate_data,
            'timestamp': datetime.now(timezone.utc)
        })
        
        return True
    except Exception as e:
        logger.error(f"Error saving tax rate: {str(e)}")
        return False

def get_tax_bands(tax_year=None):
    """Get progressive tax bands, optionally filtered by year"""
    try:
        db = get_mongo_db()
        query = {}
        if tax_year:
            query['tax_year'] = tax_year
        
        bands = list(db.tax_bands.find(query).sort([('tax_year', -1), ('band_min', 1)]))
        return bands
    except Exception as e:
        logger.error(f"Error retrieving tax bands: {str(e)}")
        return []

def save_tax_band(tax_year, band_min, band_max, rate_percentage, description, admin_id):
    """Save a progressive tax band configuration"""
    try:
        db = get_mongo_db()
        
        tax_band_data = {
            'tax_year': tax_year,
            'band_min': band_min,
            'band_max': band_max if band_max else float('inf'),
            'rate_percentage': rate_percentage,
            'description': description,
            'created_by': admin_id,
            'created_at': datetime.now(timezone.utc)
        }
        
        result = db.tax_bands.insert_one(tax_band_data)
        
        # Log the action
        db.audit_logs.insert_one({
            'admin_id': admin_id,
            'action': 'create_tax_band',
            'details': tax_band_data,
            'timestamp': datetime.now(timezone.utc)
        })
        
        return True
    except Exception as e:
        logger.error(f"Error saving tax band: {str(e)}")
        return False

def get_tax_exemptions(tax_year=None):
    """Get tax exemptions, optionally filtered by year"""
    try:
        db = get_mongo_db()
        query = {}
        if tax_year:
            query['tax_year'] = tax_year
        
        exemptions = list(db.tax_exemptions.find(query).sort('tax_year', -1))
        return exemptions
    except Exception as e:
        logger.error(f"Error retrieving tax exemptions: {str(e)}")
        return []

def save_tax_exemption(entity_type, tax_year, exemption_threshold, exemption_type, description, admin_id):
    """Save a tax exemption configuration"""
    try:
        db = get_mongo_db()
        
        exemption_data = {
            'entity_type': entity_type,
            'tax_year': tax_year,
            'exemption_threshold': exemption_threshold,
            'exemption_type': exemption_type,
            'description': description,
            'updated_by': admin_id,
            'updated_at': datetime.now(timezone.utc)
        }
        
        # Update existing or create new
        result = db.tax_exemptions.update_one(
            {'entity_type': entity_type, 'tax_year': tax_year, 'exemption_type': exemption_type},
            {'$set': exemption_data, '$setOnInsert': {'created_at': datetime.now(timezone.utc)}},
            upsert=True
        )
        
        # Log the action
        db.audit_logs.insert_one({
            'admin_id': admin_id,
            'action': 'update_tax_exemption',
            'details': exemption_data,
            'timestamp': datetime.now(timezone.utc)
        })
        
        return True
    except Exception as e:
        logger.error(f"Error saving tax exemption: {str(e)}")
        return False

def initialize_default_tax_config():
    """Initialize default tax configuration based on NTA 2025"""
    try:
        db = get_mongo_db()
        current_year = datetime.now().year
        
        # Default PIT progressive tax bands for 2024-2025
        default_bands = [
            {
                'tax_year': current_year,
                'band_min': 0,
                'band_max': 800000,
                'rate_percentage': 0.0,
                'description': 'First ₦800,000 (Tax-free)'
            },
            {
                'tax_year': current_year,
                'band_min': 800001,
                'band_max': 3000000,
                'rate_percentage': 15.0,
                'description': 'Next ₦2,200,000 (15%)'
            },
            {
                'tax_year': current_year,
                'band_min': 3000001,
                'band_max': 12000000,
                'rate_percentage': 18.0,
                'description': 'Next ₦9,000,000 (18%)'
            },
            {
                'tax_year': current_year,
                'band_min': 12000001,
                'band_max': 25000000,
                'rate_percentage': 21.0,
                'description': 'Next ₦13,000,000 (21%)'
            },
            {
                'tax_year': current_year,
                'band_min': 25000001,
                'band_max': 50000000,
                'rate_percentage': 23.0,
                'description': 'Next ₦25,000,000 (23%)'
            },
            {
                'tax_year': current_year,
                'band_min': 50000001,
                'band_max': float('inf'),
                'rate_percentage': 25.0,
                'description': 'Above ₦50,000,000 (25%)'
            }
        ]
        
        # Insert default bands if they don't exist
        for band in default_bands:
            existing = db.tax_bands.find_one({
                'tax_year': band['tax_year'],
                'band_min': band['band_min']
            })
            if not existing:
                band['created_by'] = 'system'
                band['created_at'] = datetime.now(timezone.utc)
                db.tax_bands.insert_one(band)
        
        # Default CIT rates
        default_cit_rates = [
            {
                'entity_type': 'limited_liability',
                'tax_year': current_year,
                'rate_percentage': 0.0,
                'description': '0% for companies with ≤₦50M annual revenue'
            },
            {
                'entity_type': 'limited_liability',
                'tax_year': current_year,
                'rate_percentage': 30.0,
                'description': '30% for companies with >₦50M annual revenue'
            }
        ]
        
        # Insert default CIT rates
        for rate in default_cit_rates:
            existing = db.tax_rates.find_one({
                'entity_type': rate['entity_type'],
                'tax_year': rate['tax_year'],
                'rate_percentage': rate['rate_percentage']
            })
            if not existing:
                rate['updated_by'] = 'system'
                rate['updated_at'] = datetime.now(timezone.utc)
                rate['created_at'] = datetime.now(timezone.utc)
                db.tax_rates.insert_one(rate)
        
        # Default exemptions
        default_exemptions = [
            {
                'entity_type': 'sole_proprietor',
                'tax_year': current_year,
                'exemption_threshold': 800000.0,
                'exemption_type': 'income_threshold',
                'description': 'PIT exemption for first ₦800,000 of annual income'
            },
            {
                'entity_type': 'limited_liability',
                'tax_year': current_year,
                'exemption_threshold': 50000000.0,
                'exemption_type': 'revenue_threshold',
                'description': 'CIT exemption for companies with ≤₦50M annual revenue'
            }
        ]
        
        # Insert default exemptions
        for exemption in default_exemptions:
            existing = db.tax_exemptions.find_one({
                'entity_type': exemption['entity_type'],
                'tax_year': exemption['tax_year'],
                'exemption_type': exemption['exemption_type']
            })
            if not existing:
                exemption['updated_by'] = 'system'
                exemption['updated_at'] = datetime.now(timezone.utc)
                exemption['created_at'] = datetime.now(timezone.utc)
                db.tax_exemptions.insert_one(exemption)
        
        logger.info("Default tax configuration initialized successfully")
        return True
        
    except Exception as e:
        logger.error(f"Error initializing default tax config: {str(e)}")
        return False

# Initialize default configuration on import
initialize_default_tax_config()

if __name__ == "__main__":
    print("Tax Configuration Management Module")
    print("Initializing default tax configuration...")
    
    success = initialize_default_tax_config()
    if success:
        print("✓ Default tax configuration initialized successfully")
    else:
        print("✗ Failed to initialize default tax configuration")