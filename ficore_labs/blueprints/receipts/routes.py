from flask import Blueprint, render_template, redirect, url_for, flash, request, Response, jsonify, session
from flask_login import login_required, current_user
from flask_wtf import FlaskForm
from flask_wtf.csrf import CSRFError
from translations import trans
import utils
from bson import ObjectId
from datetime import datetime, timezone, date
from zoneinfo import ZoneInfo
from wtforms import StringField, DateField, FloatField, SelectField, SubmitField
from wtforms.validators import DataRequired, Optional, Length, NumberRange
import logging
import io
import re
import tempfile
import os
import requests
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from reportlab.lib.units import inch

logger = logging.getLogger(__name__)

class ReceiptForm(FlaskForm):
    party_name = StringField(trans('receipts_party_name', default='Customer Name'), validators=[DataRequired(), Length(max=100)])
    date = DateField(trans('general_date', default='Date'), validators=[DataRequired()])
    amount = FloatField(trans('general_amount', default='Sale Amount'), validators=[DataRequired(), NumberRange(min=0.01)])
    method = SelectField(trans('general_payment_method', default='Payment Method'), choices=[
        ('cash', trans('general_cash', default='Cash')),
        ('card', trans('general_card', default='Card')),
        ('bank', trans('general_bank_transfer', default='Bank Transfer'))
    ], validators=[Optional()])
    category = StringField(trans('general_category', default='Category'), validators=[Optional(), Length(max=50)])
    contact = StringField(trans('general_contact', default='Contact'), validators=[Optional(), Length(max=100)])
    description = StringField(trans('general_description', default='Description'), validators=[Optional(), Length(max=1000)])
    submit = SubmitField(trans('receipts_add_receipt', default='Record Sale'))

receipts_bp = Blueprint('receipts', __name__, url_prefix='/receipts')

@receipts_bp.route('/')
@login_required
@utils.requires_role(['trader', 'startup', 'admin'])
def index():
    """List all sales income cashflows for the current user."""
    try:
        db = utils.get_mongo_db()
        query = {'user_id': str(current_user.id), 'type': 'receipt'}
        receipts = list(db.cashflows.find(query).sort('created_at', -1))
        
        # Convert naive datetimes to timezone-aware
        for receipt in receipts:
            if receipt.get('created_at') and receipt['created_at'].tzinfo is None:
                receipt['created_at'] = receipt['created_at'].replace(tzinfo=ZoneInfo("UTC"))
        
        logger.info(
            f"Fetched receipts for user {current_user.id}",
            extra={'session_id': session.get('sid', 'no-session-id'), 'user_id': current_user.id}
        )
        return render_template(
            'receipts/index.html',
            receipts=receipts,
            format_currency=utils.format_currency,
            format_date=utils.format_date,
            title=trans('receipts_title', default='Money In', lang=session.get('lang', 'en')),
            can_interact=utils.can_user_interact(current_user)
        )
    except Exception as e:
        logger.error(
            f"Error fetching receipts for user {current_user.id}: {str(e)}",
            extra={'session_id': session.get('sid', 'no-session-id'), 'user_id': current_user.id}
        )
        flash(trans('receipts_fetch_error', default='An error occurred'), 'danger')
        return redirect(url_for('dashboard.index'))

@receipts_bp.route('/manage')
@login_required
@utils.requires_role(['trader', 'startup', 'admin'])
def manage():
    """Manage all receipt cashflows for the current user (edit/delete)."""
    try:
        db = utils.get_mongo_db()
        query = {'user_id': str(current_user.id), 'type': 'receipt'}
        receipts = list(db.cashflows.find(query).sort('created_at', -1))
        
        # Convert naive datetimes to timezone-aware
        for receipt in receipts:
            if receipt.get('created_at') and receipt['created_at'].tzinfo is None:
                receipt['created_at'] = receipt['created_at'].replace(tzinfo=ZoneInfo("UTC"))
        
        logger.info(
            f"Fetched receipts for manage page for user {current_user.id}",
            extra={'session_id': session.get('sid', 'no-session-id'), 'user_id': current_user.id}
        )
        return render_template(
            'receipts/manage.html',
            receipts=receipts,
            format_currency=utils.format_currency,
            format_date=utils.format_date,
            title=trans('receipts_manage', default='Manage Receipts', lang=session.get('lang', 'en')),
            can_interact=utils.can_user_interact(current_user)
        )
    except Exception as e:
        logger.error(
            f"Error fetching receipts for manage page for user {current_user.id}: {str(e)}",
            extra={'session_id': session.get('sid', 'no-session-id'), 'user_id': current_user.id}
        )
        flash(trans('receipts_fetch_error', default='An error occurred'), 'danger')
        return redirect(url_for('receipts.index'))

@receipts_bp.route('/view/<id>')
@login_required
@utils.requires_role(['trader', 'startup', 'admin'])
def view(id):
    """View formatted receipt preview page."""
    try:
        db = utils.get_mongo_db()
        query = {'_id': ObjectId(id), 'user_id': str(current_user.id), 'type': 'receipt'}
        receipt = db.cashflows.find_one(query)
        if not receipt:
            logger.warning(
                f"Receipt {id} not found for user {current_user.id}",
                extra={'session_id': session.get('sid', 'no-session-id'), 'user_id': current_user.id}
            )
            flash(trans('receipts_record_not_found', default='Record not found'), 'danger')
            return redirect(url_for('receipts.index'))
        
        # Convert naive datetimes to timezone-aware
        if receipt.get('created_at') and receipt['created_at'].tzinfo is None:
            receipt['created_at'] = receipt['created_at'].replace(tzinfo=ZoneInfo("UTC"))
        
        logger.info(
            f"Viewing receipt {id} for user {current_user.id}",
            extra={'session_id': session.get('sid', 'no-session-id'), 'user_id': current_user.id}
        )
        
        return render_template(
            'receipts/view.html',
            receipt=receipt,
            format_currency=utils.format_currency,
            format_date=utils.format_date,
            title=trans('receipts_view_title', default='Receipt Details', lang=session.get('lang', 'en'))
        )
    except ValueError:
        logger.error(
            f"Invalid receipt ID {id} for user {current_user.id}",
            extra={'session_id': session.get('sid', 'no-session-id'), 'user_id': current_user.id}
        )
        flash(trans('receipts_invalid_id', default='Invalid receipt ID'), 'danger')
        return redirect(url_for('receipts.index'))
    except Exception as e:
        logger.error(
            f"Error fetching receipt {id} for user {current_user.id}: {str(e)}",
            extra={'session_id': session.get('sid', 'no-session-id'), 'user_id': current_user.id}
        )
        flash(trans('receipts_fetch_error', default='An error occurred'), 'danger')
        return redirect(url_for('receipts.index'))

@receipts_bp.route('/api/view/<id>')
@login_required
@utils.requires_role(['trader', 'startup', 'admin'])
def api_view(id):
    """API endpoint for receipt data (JSON format)."""
    try:
        db = utils.get_mongo_db()
        query = {'_id': ObjectId(id), 'user_id': str(current_user.id), 'type': 'receipt'}
        receipt = db.cashflows.find_one(query)
        if not receipt:
            logger.warning(
                f"Receipt {id} not found for user {current_user.id}",
                extra={'session_id': session.get('sid', 'no-session-id'), 'user_id': current_user.id}
            )
            return jsonify({'error': trans('receipts_record_not_found', default='Record not found')}), 404
        
        # Convert naive datetimes to timezone-aware
        if receipt.get('created_at') and receipt['created_at'].tzinfo is None:
            receipt['created_at'] = receipt['created_at'].replace(tzinfo=ZoneInfo("UTC"))
        
        receipt['_id'] = str(receipt['_id'])
        receipt['created_at'] = receipt['created_at'].isoformat() if receipt.get('created_at') else None
        logger.info(
            f"Fetched receipt API data {id} for user {current_user.id}",
            extra={'session_id': session.get('sid', 'no-session-id'), 'user_id': current_user.id}
        )
        return jsonify(receipt)
    except ValueError:
        logger.error(
            f"Invalid receipt ID {id} for user {current_user.id}",
            extra={'session_id': session.get('sid', 'no-session-id'), 'user_id': current_user.id}
        )
        return jsonify({'error': trans('receipts_invalid_id', default='Invalid receipt ID')}), 404
    except Exception as e:
        logger.error(
            f"Error fetching receipt {id} for user {current_user.id}: {str(e)}",
            extra={'session_id': session.get('sid', 'no-session-id'), 'user_id': current_user.id}
        )
        return jsonify({'error': trans('receipts_fetch_error', default='An error occurred')}), 500

@receipts_bp.route('/generate_pdf/<id>')
@login_required
@utils.requires_role(['trader', 'startup', 'admin'])
def generate_pdf(id):
    """Generate PDF receipt for a receipt transaction."""
    try:
        if not utils.can_user_interact(current_user):
            flash(trans('receipts_subscription_required', default='Your trial has expired or you do not have an active subscription. Please subscribe to generate a PDF receipt.'), 'warning')
            return redirect(url_for('subscribe_bp.subscribe'))
        
        db = utils.get_mongo_db()
        query = {'_id': ObjectId(id), 'user_id': str(current_user.id), 'type': 'receipt'}
        receipt = db.cashflows.find_one(query)
        if not receipt:
            logger.warning(
                f"Receipt {id} not found for user {current_user.id}",
                extra={'session_id': session.get('sid', 'no-session-id'), 'user_id': current_user.id}
            )
            flash(trans('receipts_record_not_found', default='Record not found'), 'danger')
            return redirect(url_for('receipts.index'))
        
        # Convert naive datetimes to timezone-aware
        if receipt.get('created_at') and receipt['created_at'].tzinfo is None:
            receipt['created_at'] = receipt['created_at'].replace(tzinfo=ZoneInfo("UTC"))
        
        # Sanitize inputs for PDF generation
        receipt['party_name'] = utils.sanitize_input(receipt['party_name'], max_length=100)
        receipt['category'] = utils.sanitize_input(receipt.get('category', 'No category provided'), max_length=50)
        receipt['contact'] = utils.sanitize_input(receipt.get('contact', ''), max_length=100) if receipt.get('contact') else ''
        receipt['description'] = utils.sanitize_input(receipt.get('description', ''), max_length=1000) if receipt.get('description') else ''
        
        buffer = io.BytesIO()
        p = canvas.Canvas(buffer, pagesize=letter)
        width, height = letter
        p.setFont("Helvetica-Bold", 24)
        p.drawString(inch, height - inch, trans('receipts_pdf_title', default='FiCore Records - Money In Receipt'))
        p.setFont("Helvetica", 12)
        y_position = height - inch - 0.5 * inch
        p.drawString(inch, y_position, f"{trans('receipts_party_name', default='Payer')}: {receipt['party_name']}")
        y_position -= 0.3 * inch
        p.drawString(inch, y_position, f"{trans('general_amount', default='Amount Received')}: {utils.format_currency(receipt['amount'])}")
        y_position -= 0.3 * inch
        p.drawString(inch, y_position, f"{trans('general_payment_method', default='Payment Method')}: {receipt.get('method', 'N/A')}")
        y_position -= 0.3 * inch
        p.drawString(inch, y_position, f"{trans('general_category', default='Category')}: {receipt['category']}")
        y_position -= 0.3 * inch
        p.drawString(inch, y_position, f"{trans('general_date', default='Date')}: {utils.format_date(receipt['created_at'])}")
        y_position -= 0.3 * inch
        p.drawString(inch, y_position, f"{trans('receipts_id', default='Receipt ID')}: {str(receipt['_id'])}")
        y_position -= 0.3 * inch
        if receipt['contact']:
            p.drawString(inch, y_position, f"{trans('general_contact', default='Contact')}: {receipt['contact']}")
            y_position -= 0.3 * inch
        if receipt['description']:
            p.drawString(inch, y_position, f"{trans('general_description', default='Description')}: {receipt['description']}")
        p.setFont("Helvetica-Oblique", 10)
        p.drawString(inch, inch, trans('receipts_pdf_footer', default='This document serves as an official receipt generated by FiCore Records.'))
        p.showPage()
        p.save()
        buffer.seek(0)
        logger.info(
            f"Generated PDF for receipt {id} for user {current_user.id}",
            extra={'session_id': session.get('sid', 'no-session-id'), 'user_id': current_user.id}
        )
        return Response(
            buffer.getvalue(),
            mimetype='application/pdf',
            headers={
                'Content-Disposition': f'attachment; filename=receipt_{utils.sanitize_input(receipt["party_name"], max_length=50)}_{str(receipt["_id"])}.pdf'
            }
        )
    except ValueError:
        logger.error(
            f"Invalid receipt ID {id} for user {current_user.id}",
            extra={'session_id': session.get('sid', 'no-session-id'), 'user_id': current_user.id}
        )
        flash(trans('receipts_invalid_id', default='Invalid receipt ID'), 'danger')
        return redirect(url_for('receipts.index'))
    except Exception as e:
        logger.error(
            f"Error generating PDF for receipt {id} for user {current_user.id}: {str(e)}",
            extra={'session_id': session.get('sid', 'no-session-id'), 'user_id': current_user.id}
        )
        flash(trans('receipts_pdf_generation_error', default='An error occurred'), 'danger')
        return redirect(url_for('receipts.index'))

@receipts_bp.route('/add', methods=['GET', 'POST'])
@login_required
@utils.requires_role(['trader', 'startup', 'admin'])
@utils.limiter.limit('10 per minute')
def add():
    """Add a new receipt cashflow."""
    try:
        if not utils.can_user_interact(current_user):
            flash(trans('receipts_subscription_required', default='Your trial has expired or you do not have an active subscription. Please subscribe to add a receipt.'), 'warning')
            return redirect(url_for('subscribe_bp.subscribe'))
        
        form = ReceiptForm()
        if form.validate_on_submit():
            try:
                db = utils.get_mongo_db()
                # Convert date to datetime with UTC timezone
                receipt_date = datetime.combine(form.date.data, datetime.min.time(), tzinfo=ZoneInfo("UTC"))
                cashflow = {
                    'user_id': str(current_user.id),
                    'type': 'receipt',
                    'party_name': utils.sanitize_input(form.party_name.data, max_length=100),
                    'amount': form.amount.data,
                    'method': form.method.data,
                    'category': utils.sanitize_input(form.category.data, max_length=50) if form.category.data else None,
                    'contact': utils.sanitize_input(form.contact.data, max_length=100) if form.contact.data else None,
                    'description': utils.sanitize_input(form.description.data, max_length=1000) if form.description.data else None,
                    'created_at': receipt_date,
                    'updated_at': datetime.now(timezone.utc)
                }
                db.cashflows.insert_one(cashflow)
                logger.info(
                    f"Receipt added for user {current_user.id}",
                    extra={'session_id': session.get('sid', 'no-session-id'), 'user_id': current_user.id}
                )
                flash(trans('receipts_add_success', default='Receipt added successfully'), 'success')
                return redirect(url_for('receipts.index'))
            except Exception as e:
                logger.error(
                    f"Error adding receipt for user {current_user.id}: {str(e)}",
                    extra={'session_id': session.get('sid', 'no-session-id'), 'user_id': current_user.id}
                )
                flash(trans('receipts_add_error', default='An error occurred'), 'danger')
        return render_template(
            'receipts/add.html',
            form=form,
            title=trans('receipts_add_title', default='Add Money In', lang=session.get('lang', 'en')),
            can_interact=utils.can_user_interact(current_user)
        )
    except CSRFError as e:
        logger.error(
            f"CSRF error in adding receipt for user {current_user.id}: {str(e)}",
            extra={'session_id': session.get('sid', 'no-session-id'), 'user_id': current_user.id}
        )
        flash(trans('receipts_csrf_error', default='Invalid CSRF token. Please try again.'), 'danger')
        return render_template(
            'receipts/add.html',
            form=form,
            title=trans('receipts_add_title', default='Add Money In', lang=session.get('lang', 'en')),
            can_interact=utils.can_user_interact(current_user)
        ), 400

@receipts_bp.route('/edit/<id>', methods=['GET', 'POST'])
@login_required
@utils.requires_role(['trader', 'startup', 'admin'])
@utils.limiter.limit('10 per minute')
def edit(id):
    """Edit an existing receipt cashflow."""
    try:
        if not utils.can_user_interact(current_user):
            flash(trans('receipts_subscription_required', default='Your trial has expired or you do not have an active subscription. Please subscribe to edit receipts.'), 'warning')
            return redirect(url_for('subscribe_bp.subscribe'))
        
        db = utils.get_mongo_db()
        query = {'_id': ObjectId(id), 'user_id': str(current_user.id), 'type': 'receipt'}
        receipt = db.cashflows.find_one(query)
        if not receipt:
            logger.warning(
                f"Receipt {id} not found for user {current_user.id}",
                extra={'session_id': session.get('sid', 'no-session-id'), 'user_id': current_user.id}
            )
            flash(trans('receipts_record_not_found', default='Cashflow not found'), 'danger')
            return redirect(url_for('receipts.index'))
        
        # Convert naive datetimes to timezone-aware
        if receipt.get('created_at') and receipt['created_at'].tzinfo is None:
            receipt['created_at'] = receipt['created_at'].replace(tzinfo=ZoneInfo("UTC"))
        
        form = ReceiptForm(data={
            'party_name': receipt['party_name'],
            'date': receipt['created_at'].date(),  # Extract date part for form
            'amount': receipt['amount'],
            'method': receipt.get('method'),
            'category': receipt.get('category'),
            'contact': receipt.get('contact'),
            'description': receipt.get('description')
        })
        if form.validate_on_submit():
            try:
                # Convert date to datetime with UTC timezone
                receipt_date = datetime.combine(form.date.data, datetime.min.time(), tzinfo=ZoneInfo("UTC"))
                updated_cashflow = {
                    'party_name': utils.sanitize_input(form.party_name.data, max_length=100),
                    'amount': form.amount.data,
                    'method': form.method.data,
                    'category': utils.sanitize_input(form.category.data, max_length=50) if form.category.data else None,
                    'contact': utils.sanitize_input(form.contact.data, max_length=100) if form.contact.data else None,
                    'description': utils.sanitize_input(form.description.data, max_length=1000) if form.description.data else None,
                    'created_at': receipt_date,
                    'updated_at': datetime.now(timezone.utc)
                }
                db.cashflows.update_one({'_id': ObjectId(id)}, {'$set': updated_cashflow})
                logger.info(
                    f"Receipt {id} updated for user {current_user.id}",
                    extra={'session_id': session.get('sid', 'no-session-id'), 'user_id': current_user.id}
                )
                flash(trans('receipts_edit_success', default='Receipt updated successfully'), 'success')
                return redirect(url_for('receipts.index'))
            except Exception as e:
                logger.error(
                    f"Error updating receipt {id} for user {current_user.id}: {str(e)}",
                    extra={'session_id': session.get('sid', 'no-session-id'), 'user_id': current_user.id}
                )
                flash(trans('receipts_edit_error', default='An error occurred'), 'danger')
        return render_template(
            'receipts/edit.html',
            form=form,
            receipt=receipt,
            title=trans('receipts_edit_title', default='Edit Receipt', lang=session.get('lang', 'en')),
            can_interact=utils.can_user_interact(current_user)
        )
    except ValueError:
        logger.error(
            f"Invalid receipt ID {id} for user {current_user.id}",
            extra={'session_id': session.get('sid', 'no-session-id'), 'user_id': current_user.id}
        )
        flash(trans('receipts_invalid_id', default='Invalid receipt ID'), 'danger')
        return redirect(url_for('receipts.index'))
    except CSRFError as e:
        logger.error(
            f"CSRF error in editing receipt {id} for user {current_user.id}: {str(e)}",
            extra={'session_id': session.get('sid', 'no-session-id'), 'user_id': current_user.id}
        )
        flash(trans('receipts_csrf_error', default='Invalid CSRF token. Please try again.'), 'danger')
        return render_template(
            'receipts/edit.html',
            form=form,
            receipt=receipt,
            title=trans('receipts_edit_title', default='Edit Receipt', lang=session.get('lang', 'en')),
            can_interact=utils.can_user_interact(current_user)
        ), 400
    except Exception as e:
        logger.error(
            f"Error fetching receipt {id} for user {current_user.id}: {str(e)}",
            extra={'session_id': session.get('sid', 'no-session-id'), 'user_id': current_user.id}
        )
        flash(trans('receipts_record_not_found', default='Cashflow not found'), 'danger')
        return redirect(url_for('receipts.index'))

@receipts_bp.route('/delete/<id>', methods=['POST'])
@login_required
@utils.requires_role(['trader', 'startup', 'admin'])
@utils.limiter.limit('10 per minute')
def delete(id):
    """Delete a receipt cashflow."""
    try:
        if not utils.can_user_interact(current_user):
            flash(trans('receipts_subscription_required', default='Your trial has expired or you do not have an active subscription. Please subscribe to delete receipts.'), 'warning')
            return redirect(url_for('subscribe_bp.subscribe'))
        
        db = utils.get_mongo_db()
        query = {'_id': ObjectId(id), 'user_id': str(current_user.id), 'type': 'receipt'}
        result = db.cashflows.delete_one(query)
        if result.deleted_count:
            logger.info(
                f"Receipt {id} deleted for user {current_user.id}",
                extra={'session_id': session.get('sid', 'no-session-id'), 'user_id': current_user.id}
            )
            flash(trans('receipts_delete_success', default='Receipt deleted successfully'), 'success')
        else:
            logger.warning(
                f"Receipt {id} not found for user {current_user.id}",
                extra={'session_id': session.get('sid', 'no-session-id'), 'user_id': current_user.id}
            )
            flash(trans('receipts_record_not_found', default='Cashflow not found'), 'danger')
        return redirect(url_for('receipts.index'))
    except ValueError:
        logger.error(
            f"Invalid receipt ID {id} for user {current_user.id}",
            extra={'session_id': session.get('sid', 'no-session-id'), 'user_id': current_user.id}
        )
        flash(trans('receipts_invalid_id', default='Invalid receipt ID'), 'danger')
        return redirect(url_for('receipts.index'))
    except CSRFError as e:
        logger.error(
            f"CSRF error in deleting receipt {id} for user {current_user.id}: {str(e)}",
            extra={'session_id': session.get('sid', 'no-session-id'), 'user_id': current_user.id}
        )
        flash(trans('receipts_csrf_error', default='Invalid CSRF token. Please try again.'), 'danger')
        return redirect(url_for('receipts.index'))
    except Exception as e:
        logger.error(
            f"Error deleting receipt {id} for user {current_user.id}: {str(e)}",
            extra={'session_id': session.get('sid', 'no-session-id'), 'user_id': current_user.id}
        )
        flash(trans('receipts_delete_error', default='An error occurred'), 'danger')
        return redirect(url_for('receipts.index'))

@receipts_bp.route('/process_voice_sale', methods=['POST'])
@login_required
@utils.requires_role(['trader', 'startup', 'admin'])
@utils.limiter.limit('5 per minute')
def process_voice_sale():
    """Process voice input for sales logging."""
    try:
        if not utils.can_user_interact(current_user):
            return jsonify({
                'success': False,
                'message': trans('receipts_subscription_required', default='Your trial has expired or you do not have an active subscription.')
            }), 403
        
        if 'audio' not in request.files:
            return jsonify({
                'success': False,
                'message': trans('voice_no_audio', default='No audio file provided')
            }), 400
        
        audio_file = request.files['audio']
        if audio_file.filename == '':
            return jsonify({
                'success': False,
                'message': trans('voice_empty_audio', default='Empty audio file')
            }), 400
        
        # Save audio file temporarily
        with tempfile.NamedTemporaryFile(delete=False, suffix='.wav') as temp_file:
            audio_file.save(temp_file.name)
            temp_audio_path = temp_file.name
        
        try:
            # Transcribe audio using AssemblyAI or similar service
            transcription = transcribe_audio(temp_audio_path)
            
            if not transcription:
                return jsonify({
                    'success': False,
                    'message': trans('voice_transcription_failed', default='Could not understand the audio')
                }), 400
            
            # Parse the transcription to extract sale details
            parsed_data = parse_sale_transcription(transcription)
            
            if not parsed_data:
                return jsonify({
                    'success': False,
                    'message': trans('voice_parsing_failed', default='Could not extract sale details from speech')
                }), 400
            
            # Create the sale record
            db = utils.get_mongo_db()
            cashflow = {
                'user_id': str(current_user.id),
                'type': 'receipt',
                'party_name': parsed_data.get('customer', 'Voice Customer'),
                'amount': parsed_data['amount'],
                'method': 'cash',  # Default to cash for voice sales
                'category': parsed_data.get('item', 'Voice Sale'),
                'contact': None,
                'description': f"Voice logged: {transcription}",
                'created_at': datetime.now(timezone.utc),
                'updated_at': datetime.now(timezone.utc),
                'voice_logged': True,
                'transcription': transcription
            }
            
            result = db.cashflows.insert_one(cashflow)
            
            logger.info(
                f"Voice sale added for user {current_user.id}: {transcription}",
                extra={'session_id': session.get('sid', 'no-session-id'), 'user_id': current_user.id}
            )
            
            return jsonify({
                'success': True,
                'message': trans('voice_sale_success', default='Sale recorded successfully!'),
                'sale_id': str(result.inserted_id),
                'transcription': transcription,
                'parsed_data': parsed_data
            })
            
        finally:
            # Clean up temporary file
            if os.path.exists(temp_audio_path):
                os.unlink(temp_audio_path)
                
    except Exception as e:
        logger.error(
            f"Error processing voice sale for user {current_user.id}: {str(e)}",
            extra={'session_id': session.get('sid', 'no-session-id'), 'user_id': current_user.id}
        )
        return jsonify({
            'success': False,
            'message': trans('voice_processing_error', default='Error processing voice input')
        }), 500

def transcribe_audio(audio_path):
    """Transcribe audio using AssemblyAI or similar service."""
    try:
        # For now, we'll use a simple placeholder
        # In production, you would integrate with AssemblyAI, Google STT, or Whisper
        
        # Example AssemblyAI integration:
        # import assemblyai as aai
        # aai.settings.api_key = "your-api-key"
        # transcriber = aai.Transcriber()
        # transcript = transcriber.transcribe(audio_path)
        # return transcript.text
        
        # For demo purposes, return a sample transcription
        # In real implementation, replace this with actual STT service
        return "sold 5 cartons of water for 3000 naira"
        
    except Exception as e:
        logger.error(f"Error transcribing audio: {str(e)}")
        return None

def parse_sale_transcription(transcription):
    """Parse transcription to extract sale details."""
    try:
        text = transcription.lower().strip()
        
        # Common patterns for sales
        patterns = [
            # "sold 5 cartons of water for 3000 naira"
            r'sold\s+(\d+)\s+(.+?)\s+for\s+(\d+)',
            # "5 bags of rice 2000 naira"
            r'(\d+)\s+(.+?)\s+(\d+)\s*naira',
            # "water 5 pieces 1500"
            r'(.+?)\s+(\d+)\s+(?:pieces?|items?|cartons?|bags?)\s+(\d+)',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                groups = match.groups()
                if len(groups) == 3:
                    try:
                        # Try different group arrangements
                        if groups[0].isdigit():  # quantity first
                            quantity = int(groups[0])
                            item = groups[1].strip()
                            amount = float(groups[2])
                        else:  # item first
                            item = groups[0].strip()
                            quantity = int(groups[1])
                            amount = float(groups[2])
                        
                        return {
                            'item': item,
                            'quantity': quantity,
                            'amount': amount,
                            'customer': 'Voice Customer'
                        }
                    except (ValueError, IndexError):
                        continue
        
        # Fallback: try to extract just amount
        amount_match = re.search(r'(\d+)\s*naira', text)
        if amount_match:
            return {
                'item': 'Voice Sale',
                'quantity': 1,
                'amount': float(amount_match.group(1)),
                'customer': 'Voice Customer'
            }
        
        return None
        
    except Exception as e:
        logger.error(f"Error parsing transcription: {str(e)}")
        return None

@receipts_bp.route('/share', methods=['POST'])
@login_required
@utils.requires_role(['trader', 'startup', 'admin'])
@utils.limiter.limit('10 per minute')
def share():
    """Share a receipt via SMS or WhatsApp."""
    try:
        if not utils.can_user_interact(current_user):
            return jsonify({
                'success': False,
                'message': trans('receipts_subscription_required', default='Your trial has expired or you do not have an active subscription. Please subscribe to share receipts.')
            }), 403
        
        data = request.get_json()
        receipt_id = data.get('receiptId')
        recipient = utils.sanitize_input(data.get('recipient'), max_length=100)
        message = utils.sanitize_input(data.get('message'), max_length=1000)
        share_type = data.get('type')
        
        if not all([receipt_id, recipient, message, share_type]):
            logger.error(
                f"Missing fields in share receipt request for user {current_user.id}",
                extra={'session_id': session.get('sid', 'no-session-id'), 'user_id': current_user.id}
            )
            return jsonify({
                'success': False,
                'message': trans('receipts_missing_fields', default='Missing required fields')
            }), 400
        
        valid_share_types = ['sms', 'whatsapp']
        if share_type not in valid_share_types:
            logger.error(
                f"Invalid share type {share_type} in share receipt request for user {current_user.id}",
                extra={'session_id': session.get('sid', 'no-session-id'), 'user_id': current_user.id}
            )
            return jsonify({
                'success': False,
                'message': trans('receipts_invalid_share_type', default='Invalid share type')
            }), 400
        
        db = utils.get_mongo_db()
        query = {'_id': ObjectId(receipt_id), 'user_id': str(current_user.id), 'type': 'receipt'}
        receipt = db.cashflows.find_one(query)
        if not receipt:
            logger.warning(
                f"Receipt {receipt_id} not found for user {current_user.id}",
                extra={'session_id': session.get('sid', 'no-session-id'), 'user_id': current_user.id}
            )
            return jsonify({
                'success': False,
                'message': trans('receipts_record_not_found', default='Receipt not found')
            }), 404
        
        success = utils.send_message(recipient=recipient, message=message, type=share_type)
        if success:
            logger.info(
                f"Receipt {receipt_id} shared via {share_type} for user {current_user.id}",
                extra={'session_id': session.get('sid', 'no-session-id'), 'user_id': current_user.id}
            )
            return jsonify({'success': True})
        else:
            logger.error(
                f"Failed to share receipt {receipt_id} via {share_type} for user {current_user.id}",
                extra={'session_id': session.get('sid', 'no-session-id'), 'user_id': current_user.id}
            )
            return jsonify({
                'success': False,
                'message': trans('receipts_share_failed', default='Failed to share receipt')
            }), 500
    except ValueError:
        logger.error(
            f"Invalid receipt ID {receipt_id} for user {current_user.id}",
            extra={'session_id': session.get('sid', 'no-session-id'), 'user_id': current_user.id}
        )
        return jsonify({
            'success': False,
            'message': trans('receipts_invalid_id', default='Invalid receipt ID')
        }), 404
    except CSRFError as e:
        logger.error(
            f"CSRF error in sharing receipt {receipt_id} for user {current_user.id}: {str(e)}",
            extra={'session_id': session.get('sid', 'no-session-id'), 'user_id': current_user.id}
        )
        return jsonify({
            'success': False,
            'message': trans('receipts_csrf_error', default='Invalid CSRF token. Please try again.')
        }), 400
    except Exception as e:
        logger.error(
            f"Error sharing receipt {receipt_id} for user {current_user.id}: {str(e)}",
            extra={'session_id': session.get('sid', 'no-session-id'), 'user_id': current_user.id}
        )
        return jsonify({
            'success': False,
            'message': trans('receipts_share_error', default='Error sharing receipt')
        }), 500
