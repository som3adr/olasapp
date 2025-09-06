from flask import Blueprint, render_template, request, flash, redirect, url_for, jsonify
from flask_login import login_required, current_user
from models import User, db
from extensions import db as db_ext
from datetime import datetime, date, timedelta
from sqlalchemy import and_, or_

staff_tasks_bp = Blueprint('staff_tasks', __name__, url_prefix='/staff-tasks')

# Simple in-memory storage for tasks and notes (in production, use database)
# This is a simplified version - you can create proper models later
tasks = []
notes = []

@staff_tasks_bp.route('/')
@login_required
def index():
    """Staff tasks and notes dashboard"""
    # Get user's tasks
    user_tasks = [task for task in tasks if task['assigned_to'] == current_user.id or task['created_by'] == current_user.id]
    
    # Get user's notes
    user_notes = [note for note in notes if note['created_by'] == current_user.id]
    
    # Get all staff members
    staff_members = User.query.filter_by(is_active=True).all()
    
    return render_template('staff_tasks/index.html',
                         user_tasks=user_tasks,
                         user_notes=user_notes,
                         staff_members=staff_members)

@staff_tasks_bp.route('/tasks')
@login_required
def tasks_list():
    """View all tasks"""
    # Get filter parameters
    status_filter = request.args.get('status', '')
    assigned_to_filter = request.args.get('assigned_to', '')
    
    # Filter tasks
    filtered_tasks = tasks
    
    if status_filter:
        filtered_tasks = [task for task in filtered_tasks if task['status'] == status_filter]
    
    if assigned_to_filter:
        filtered_tasks = [task for task in filtered_tasks if task['assigned_to'] == int(assigned_to_filter)]
    
    # Get all staff members for filter
    staff_members = User.query.filter_by(is_active=True).all()
    
    return render_template('staff_tasks/tasks.html',
                         tasks=filtered_tasks,
                         staff_members=staff_members,
                         status_filter=status_filter,
                         assigned_to_filter=assigned_to_filter)

@staff_tasks_bp.route('/tasks/add', methods=['GET', 'POST'])
@login_required
def add_task():
    """Add new task"""
    if request.method == 'POST':
        title = request.form.get('title')
        description = request.form.get('description')
        assigned_to = request.form.get('assigned_to')
        priority = request.form.get('priority')
        due_date = request.form.get('due_date')
        
        if not all([title, assigned_to]):
            flash('Please fill in all required fields.', 'error')
            return render_template('staff_tasks/task_form.html')
        
        try:
            task = {
                'id': len(tasks) + 1,
                'title': title,
                'description': description,
                'assigned_to': int(assigned_to),
                'priority': priority,
                'due_date': datetime.strptime(due_date, '%Y-%m-%d').date() if due_date else None,
                'status': 'pending',
                'created_by': current_user.id,
                'created_at': datetime.now(),
                'completed_at': None
            }
            
            tasks.append(task)
            
            flash(f'Task "{title}" added successfully!', 'success')
            return redirect(url_for('staff_tasks.tasks_list'))
            
        except ValueError:
            flash('Please enter a valid date.', 'error')
        except Exception as e:
            flash(f'Error adding task: {str(e)}', 'error')
    
    # Get all staff members
    staff_members = User.query.filter_by(is_active=True).all()
    
    return render_template('staff_tasks/task_form.html',
                         staff_members=staff_members)

@staff_tasks_bp.route('/tasks/<int:task_id>/update-status', methods=['POST'])
@login_required
def update_task_status(task_id):
    """Update task status"""
    new_status = request.form.get('status')
    
    if not new_status:
        flash('Please select a status.', 'error')
        return redirect(url_for('staff_tasks.tasks_list'))
    
    # Find and update task
    for task in tasks:
        if task['id'] == task_id:
            task['status'] = new_status
            if new_status == 'completed':
                task['completed_at'] = datetime.now()
            break
    
    flash('Task status updated successfully!', 'success')
    return redirect(url_for('staff_tasks.tasks_list'))

@staff_tasks_bp.route('/notes')
@login_required
def notes_list():
    """View all notes"""
    # Get filter parameters
    author_filter = request.args.get('author', '')
    
    # Filter notes
    filtered_notes = notes
    
    if author_filter:
        filtered_notes = [note for note in notes if note['created_by'] == int(author_filter)]
    
    # Get all staff members for filter
    staff_members = User.query.filter_by(is_active=True).all()
    
    return render_template('staff_tasks/notes.html',
                         notes=filtered_notes,
                         staff_members=staff_members,
                         author_filter=author_filter)

@staff_tasks_bp.route('/notes/add', methods=['GET', 'POST'])
@login_required
def add_note():
    """Add new note"""
    if request.method == 'POST':
        title = request.form.get('title')
        content = request.form.get('content')
        is_public = request.form.get('is_public') == 'on'
        
        if not all([title, content]):
            flash('Please fill in all required fields.', 'error')
            return render_template('staff_tasks/note_form.html')
        
        try:
            note = {
                'id': len(notes) + 1,
                'title': title,
                'content': content,
                'is_public': is_public,
                'created_by': current_user.id,
                'created_at': datetime.now()
            }
            
            notes.append(note)
            
            flash(f'Note "{title}" added successfully!', 'success')
            return redirect(url_for('staff_tasks.notes_list'))
            
        except Exception as e:
            flash(f'Error adding note: {str(e)}', 'error')
    
    return render_template('staff_tasks/note_form.html')

@staff_tasks_bp.route('/api/quick-stats')
@login_required
def quick_stats():
    """API endpoint for quick dashboard stats"""
    try:
        # User's pending tasks
        user_pending_tasks = len([task for task in tasks if task['assigned_to'] == current_user.id and task['status'] == 'pending'])
        
        # User's completed tasks today
        today = date.today()
        user_completed_today = len([task for task in tasks if task['assigned_to'] == current_user.id and task['status'] == 'completed' and task['completed_at'] and task['completed_at'].date() == today])
        
        # Total notes
        total_notes = len(notes)
        
        return jsonify({
            'success': True,
            'stats': {
                'pending_tasks': user_pending_tasks,
                'completed_today': user_completed_today,
                'total_notes': total_notes
            }
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500
