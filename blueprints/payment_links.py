from flask import Blueprint, render_template, request, redirect, url_for, flash, abort
from flask_login import login_required, current_user
from extensions import db
from models import PaymentLink, Tenant, Payment
from permissions import require_frontdesk_or_admin
from datetime import datetime, timedelta
import secrets
import string

payment_links_bp = Blueprint('payment_links', __name__, url_prefix='/payment-links')


def generate_secure_token(length=32):
    """Generate a secure random token for payment links"""
    alphabet = string.ascii_letters + string.digits
    return ''.join(secrets.choice(alphabet) for _ in range(length))


@payment_links_bp.route('/')
@login_required
@require_frontdesk_or_admin
def index():
    """List all payment links"""
    page = request.args.get('page', 1, type=int)
    per_page = 20
    
    # Filter options
    status_filter = request.args.get('status', '')  # all, pending, paid, expired
    tenant_filter = request.args.get('tenant_id', '')
    
    query = PaymentLink.query
    
    # Apply filters
    if status_filter == 'pending':
        query = query.filter(
            PaymentLink.is_paid == False,
            PaymentLink.expires_at > datetime.utcnow()
        )
    elif status_filter == 'paid':
        query = query.filter(PaymentLink.is_paid == True)
    elif status_filter == 'expired':
        query = query.filter(
            PaymentLink.is_paid == False,
            PaymentLink.expires_at <= datetime.utcnow()
        )
    
    if tenant_filter:
        query = query.filter(PaymentLink.tenant_id == int(tenant_filter))
    
    # Order by most recent first
    query = query.order_by(PaymentLink.created_at.desc())
    
    # Paginate
    payment_links = query.paginate(
        page=page, per_page=per_page, error_out=False
    )
    
    # Get tenants for filter
    tenants = Tenant.query.filter_by(is_active=True).order_by(Tenant.name).all()
    
    return render_template('payment_links/index.html',
                         payment_links=payment_links,
                         tenants=tenants,
                         status_filter=status_filter,
                         tenant_filter=tenant_filter,
                         current_time=datetime.utcnow())


@payment_links_bp.route('/create/<int:tenant_id>', methods=['GET', 'POST'])
@login_required
@require_frontdesk_or_admin
def create(tenant_id):
    """Create a new payment link for a tenant"""
    tenant = Tenant.query.get_or_404(tenant_id)
    
    if request.method == 'POST':
        amount = request.form.get('amount')
        description = request.form.get('description')
        expires_in_days = request.form.get('expires_in_days', 7, type=int)
        
        if not all([amount, description]):
            flash('Amount and description are required.', 'error')
            return render_template('payment_links/create.html', tenant=tenant)
        
        try:
            amount = float(amount)
        except ValueError:
            flash('Invalid amount.', 'error')
            return render_template('payment_links/create.html', tenant=tenant)
        
        # Generate secure token
        token = generate_secure_token()
        expires_at = datetime.utcnow() + timedelta(days=expires_in_days)
        
        payment_link = PaymentLink(
            tenant_id=tenant_id,
            amount=amount,
            description=description,
            token=token,
            expires_at=expires_at,
            created_by=current_user.id
        )
        
        try:
            db.session.add(payment_link)
            db.session.commit()
            flash(f'Payment link created successfully. Link expires in {expires_in_days} days.', 'success')
            return redirect(url_for('payment_links.index'))
        except Exception as e:
            db.session.rollback()
            flash('Failed to create payment link.', 'error')
    
    return render_template('payment_links/create.html', tenant=tenant)


@payment_links_bp.route('/pay/<token>')
def pay(token):
    """Public payment page - no login required"""
    payment_link = PaymentLink.query.filter_by(token=token).first_or_404()
    
    # Check if link is expired
    if datetime.utcnow() > payment_link.expires_at:
        return render_template('payment_links/expired.html', payment_link=payment_link)
    
    # Check if already paid
    if payment_link.is_paid:
        return render_template('payment_links/already_paid.html', payment_link=payment_link)
    
    return render_template('payment_links/pay.html', payment_link=payment_link)


@payment_links_bp.route('/process/<token>', methods=['POST'])
def process_payment(token):
    """Process payment - stub implementation"""
    payment_link = PaymentLink.query.filter_by(token=token).first_or_404()
    
    # Check if link is valid
    if datetime.utcnow() > payment_link.expires_at or payment_link.is_paid:
        return redirect(url_for('payment_links.pay', token=token))
    
    # In a real implementation, this would integrate with a payment gateway
    # For now, we'll just simulate a successful payment
    
    # Create a payment record
    payment = Payment(
        tenant_id=payment_link.tenant_id,
        amount=payment_link.amount,
        payment_date=datetime.utcnow().date(),
        payment_for_month=datetime.utcnow().strftime('%Y-%m'),
        payment_type='Online Payment',
        notes=f'Paid via payment link: {payment_link.description}'
    )
    
    # Mark payment link as paid
    payment_link.is_paid = True
    payment_link.paid_at = datetime.utcnow()
    
    try:
        db.session.add(payment)
        db.session.commit()
        
        # Link the payment to the payment link
        payment_link.payment_id = payment.id
        db.session.commit()
        
        return render_template('payment_links/success.html', 
                             payment_link=payment_link, 
                             payment=payment)
    except Exception as e:
        db.session.rollback()
        flash('Payment processing failed. Please try again.', 'error')
        return redirect(url_for('payment_links.pay', token=token))


@payment_links_bp.route('/resend/<int:link_id>')
@login_required
@require_frontdesk_or_admin
def resend(link_id):
    """Resend payment link (extend expiry)"""
    payment_link = PaymentLink.query.get_or_404(link_id)
    
    if payment_link.is_paid:
        flash('Cannot resend a paid payment link.', 'error')
        return redirect(url_for('payment_links.index'))
    
    # Extend expiry by 7 days
    payment_link.expires_at = datetime.utcnow() + timedelta(days=7)
    
    try:
        db.session.commit()
        flash('Payment link expiry extended by 7 days.', 'success')
    except Exception as e:
        db.session.rollback()
        flash('Failed to extend payment link.', 'error')
    
    return redirect(url_for('payment_links.index'))


@payment_links_bp.route('/cancel/<int:link_id>')
@login_required
@require_frontdesk_or_admin
def cancel(link_id):
    """Cancel a payment link"""
    payment_link = PaymentLink.query.get_or_404(link_id)
    
    if payment_link.is_paid:
        flash('Cannot cancel a paid payment link.', 'error')
        return redirect(url_for('payment_links.index'))
    
    # Set expiry to now to effectively cancel it
    payment_link.expires_at = datetime.utcnow()
    
    try:
        db.session.commit()
        flash('Payment link cancelled.', 'success')
    except Exception as e:
        db.session.rollback()
        flash('Failed to cancel payment link.', 'error')
    
    return redirect(url_for('payment_links.index'))
