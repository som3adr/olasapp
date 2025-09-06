from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required, current_user
from extensions import db
from models import Tenant, GuestFeedback
from permissions import require_frontdesk_or_admin
from datetime import datetime, timedelta
from sqlalchemy import func, desc

feedback_bp = Blueprint('feedback', __name__, url_prefix='/feedback')

@feedback_bp.route('/')
@login_required
@require_frontdesk_or_admin
def index():
    """Feedback management dashboard"""
    # Get recent feedback
    recent_feedback = GuestFeedback.query.order_by(desc(GuestFeedback.created_at)).limit(10).all()
    
    # Calculate statistics
    total_feedback = GuestFeedback.query.count()
    
    # Average ratings
    avg_overall = db.session.query(func.avg(GuestFeedback.overall_rating)).scalar() or 0
    avg_cleanliness = db.session.query(func.avg(GuestFeedback.cleanliness_rating)).scalar() or 0
    avg_staff = db.session.query(func.avg(GuestFeedback.staff_rating)).scalar() or 0
    avg_location = db.session.query(func.avg(GuestFeedback.location_rating)).scalar() or 0
    avg_value = db.session.query(func.avg(GuestFeedback.value_rating)).scalar() or 0
    
    # Rating distribution
    rating_distribution = {}
    for i in range(1, 6):
        count = GuestFeedback.query.filter_by(overall_rating=i).count()
        rating_distribution[i] = count
    
    # Recent feedback by rating
    excellent_feedback = GuestFeedback.query.filter(GuestFeedback.overall_rating >= 4).count()
    poor_feedback = GuestFeedback.query.filter(GuestFeedback.overall_rating <= 2).count()
    
    # Monthly feedback trend (last 6 months)
    monthly_feedback = []
    for i in range(6):
        month_start = datetime.now().replace(day=1) - timedelta(days=30*i)
        if month_start.month == 1:
            month_end = month_start.replace(month=2, day=1) - timedelta(days=1)
        elif month_start.month == 12:
            month_end = month_start.replace(year=month_start.year+1, month=1, day=1) - timedelta(days=1)
        else:
            month_end = month_start.replace(month=month_start.month+1, day=1) - timedelta(days=1)
        
        feedback_count = GuestFeedback.query.filter(
            GuestFeedback.created_at >= month_start,
            GuestFeedback.created_at <= month_end
        ).count()
        
        avg_rating = db.session.query(func.avg(GuestFeedback.overall_rating)).filter(
            GuestFeedback.created_at >= month_start,
            GuestFeedback.created_at <= month_end
        ).scalar() or 0
        
        monthly_feedback.append({
            'month': month_start.strftime('%B %Y'),
            'count': feedback_count,
            'avg_rating': round(avg_rating, 1)
        })
    
    monthly_feedback.reverse()
    
    return render_template('feedback/index.html',
                         recent_feedback=recent_feedback,
                         total_feedback=total_feedback,
                         avg_overall=round(avg_overall, 1),
                         avg_cleanliness=round(avg_cleanliness, 1),
                         avg_staff=round(avg_staff, 1),
                         avg_location=round(avg_location, 1),
                         avg_value=round(avg_value, 1),
                         rating_distribution=rating_distribution,
                         excellent_feedback=excellent_feedback,
                         poor_feedback=poor_feedback,
                         monthly_feedback=monthly_feedback)

@feedback_bp.route('/all')
@login_required
@require_frontdesk_or_admin
def all_feedback():
    """View all feedback with filtering"""
    page = request.args.get('page', 1, type=int)
    rating_filter = request.args.get('rating', type=int)
    guest_filter = request.args.get('guest', '')
    date_from = request.args.get('date_from', '')
    date_to = request.args.get('date_to', '')
    
    query = GuestFeedback.query
    
    # Apply filters
    if rating_filter:
        query = query.filter_by(overall_rating=rating_filter)
    
    if guest_filter:
        query = query.join(Tenant).filter(Tenant.name.ilike(f'%{guest_filter}%'))
    
    if date_from:
        try:
            date_from_dt = datetime.strptime(date_from, '%Y-%m-%d')
            query = query.filter(GuestFeedback.created_at >= date_from_dt)
        except ValueError:
            pass
    
    if date_to:
        try:
            date_to_dt = datetime.strptime(date_to, '%Y-%m-%d')
            query = query.filter(GuestFeedback.created_at <= date_to_dt)
        except ValueError:
            pass
    
    feedback_list = query.order_by(desc(GuestFeedback.created_at)).paginate(
        page=page, per_page=20, error_out=False
    )
    
    return render_template('feedback/all.html',
                         feedback_list=feedback_list,
                         rating_filter=rating_filter,
                         guest_filter=guest_filter,
                         date_from=date_from,
                         date_to=date_to)

@feedback_bp.route('/view/<int:feedback_id>')
@login_required
@require_frontdesk_or_admin
def view_feedback(feedback_id):
    """View detailed feedback"""
    feedback = GuestFeedback.query.get_or_404(feedback_id)
    
    # Mark as read if not already
    if not feedback.is_read:
        feedback.is_read = True
        feedback.read_by = current_user.id
        feedback.read_at = datetime.utcnow()
        db.session.commit()
    
    return render_template('feedback/view.html', feedback=feedback)

@feedback_bp.route('/respond/<int:feedback_id>', methods=['GET', 'POST'])
@login_required
@require_frontdesk_or_admin
def respond_to_feedback(feedback_id):
    """Respond to guest feedback"""
    feedback = GuestFeedback.query.get_or_404(feedback_id)
    
    if request.method == 'POST':
        response_text = request.form.get('response_text', '').strip()
        
        if not response_text:
            flash('Response text is required.', 'error')
            return redirect(url_for('feedback.respond_to_feedback', feedback_id=feedback_id))
        
        # Update feedback with response
        feedback.response_text = response_text
        feedback.responded_by = current_user.id
        feedback.responded_at = datetime.utcnow()
        feedback.is_read = True
        
        if not feedback.read_by:
            feedback.read_by = current_user.id
            feedback.read_at = datetime.utcnow()
        
        db.session.commit()
        
        flash('Response added successfully.', 'success')
        return redirect(url_for('feedback.view_feedback', feedback_id=feedback_id))
    
    return render_template('feedback/respond.html', feedback=feedback)

# Public feedback submission routes (no login required)
@feedback_bp.route('/submit/<int:tenant_id>')
def submit_form(tenant_id):
    """Public feedback submission form"""
    tenant = Tenant.query.get_or_404(tenant_id)
    
    # Check if feedback already exists for this tenant
    existing_feedback = GuestFeedback.query.filter_by(tenant_id=tenant_id).first()
    
    return render_template('feedback/submit.html', 
                         tenant=tenant, 
                         existing_feedback=existing_feedback)

@feedback_bp.route('/submit/<int:tenant_id>', methods=['POST'])
def submit_feedback(tenant_id):
    """Process feedback submission"""
    tenant = Tenant.query.get_or_404(tenant_id)
    
    # Check if feedback already submitted
    existing_feedback = GuestFeedback.query.filter_by(tenant_id=tenant_id).first()
    if existing_feedback:
        flash('Feedback has already been submitted for this stay.', 'info')
        return redirect(url_for('feedback.thank_you'))
    
    # Get form data
    overall_rating = request.form.get('overall_rating', type=int)
    cleanliness_rating = request.form.get('cleanliness_rating', type=int)
    staff_rating = request.form.get('staff_rating', type=int)
    location_rating = request.form.get('location_rating', type=int)
    value_rating = request.form.get('value_rating', type=int)
    
    comments = request.form.get('comments', '').strip()
    would_recommend = request.form.get('would_recommend') == 'yes'
    
    # Validate ratings
    if not all([overall_rating, cleanliness_rating, staff_rating, location_rating, value_rating]):
        flash('All ratings are required.', 'error')
        return redirect(url_for('feedback.submit_form', tenant_id=tenant_id))
    
    if not all(1 <= rating <= 5 for rating in [overall_rating, cleanliness_rating, staff_rating, location_rating, value_rating]):
        flash('All ratings must be between 1 and 5.', 'error')
        return redirect(url_for('feedback.submit_form', tenant_id=tenant_id))
    
    try:
        # Create feedback record
        feedback = GuestFeedback(
            tenant_id=tenant_id,
            overall_rating=overall_rating,
            cleanliness_rating=cleanliness_rating,
            staff_rating=staff_rating,
            location_rating=location_rating,
            value_rating=value_rating,
            comments=comments,
            would_recommend=would_recommend,
            created_at=datetime.utcnow()
        )
        
        db.session.add(feedback)
        db.session.commit()
        
        flash('Thank you for your feedback!', 'success')
        return redirect(url_for('feedback.thank_you'))
        
    except Exception as e:
        db.session.rollback()
        flash('Error submitting feedback. Please try again.', 'error')
        return redirect(url_for('feedback.submit_form', tenant_id=tenant_id))

@feedback_bp.route('/thank-you')
def thank_you():
    """Thank you page after feedback submission"""
    return render_template('feedback/thank_you.html')

@feedback_bp.route('/api/stats')
@login_required
@require_frontdesk_or_admin
def api_stats():
    """API endpoint for feedback statistics"""
    # Overall statistics
    total_feedback = GuestFeedback.query.count()
    avg_overall = db.session.query(func.avg(GuestFeedback.overall_rating)).scalar() or 0
    
    # Rating breakdown
    rating_counts = {}
    for i in range(1, 6):
        rating_counts[i] = GuestFeedback.query.filter_by(overall_rating=i).count()
    
    # Recent trend (last 30 days vs previous 30 days)
    thirty_days_ago = datetime.now() - timedelta(days=30)
    sixty_days_ago = datetime.now() - timedelta(days=60)
    
    recent_count = GuestFeedback.query.filter(GuestFeedback.created_at >= thirty_days_ago).count()
    previous_count = GuestFeedback.query.filter(
        GuestFeedback.created_at >= sixty_days_ago,
        GuestFeedback.created_at < thirty_days_ago
    ).count()
    
    recent_avg = db.session.query(func.avg(GuestFeedback.overall_rating)).filter(
        GuestFeedback.created_at >= thirty_days_ago
    ).scalar() or 0
    
    previous_avg = db.session.query(func.avg(GuestFeedback.overall_rating)).filter(
        GuestFeedback.created_at >= sixty_days_ago,
        GuestFeedback.created_at < thirty_days_ago
    ).scalar() or 0
    
    return jsonify({
        'total_feedback': total_feedback,
        'avg_overall': round(avg_overall, 1),
        'rating_counts': rating_counts,
        'recent_count': recent_count,
        'previous_count': previous_count,
        'recent_avg': round(recent_avg, 1),
        'previous_avg': round(previous_avg, 1),
        'count_trend': 'up' if recent_count > previous_count else 'down' if recent_count < previous_count else 'stable',
        'rating_trend': 'up' if recent_avg > previous_avg else 'down' if recent_avg < previous_avg else 'stable'
    })

