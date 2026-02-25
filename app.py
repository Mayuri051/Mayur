from flask import Flask, render_template, request, redirect, url_for, session, flash
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
from datetime import datetime, timezone, timedelta
import os
import secrets
import hashlib
import logging
from logging.handlers import RotatingFileHandler
import json
import csv
import io
from flask import send_file

# Import models - CORRECT WAY
from models import db, User, TestAssignment, TestPaper, TestQuestion, Question, TestResult, StudentQuery, ActivityLog

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.config['SECRET_KEY'] = secrets.token_hex(32)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///secure_test_system.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(hours=2)

# Initialize db with app - CORRECT WAY
db.init_app(app)

# Remove all model definitions from app.py - they should only be in models.py

# Database Models

# Helper function for clean redirection logic
def get_dashboard_redirect(role):
    if role == 'admin':
        return 'admin_dashboard'
    elif role == 'teacher':
        return 'teacher_dashboard'
    elif role == 'student':
        return 'student_dashboard'
    else:
        return 'login'

# Login required decorator
def login_required(role=None):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if 'user_id' not in session:
                flash('Please log in to access this page.', 'warning')
                return redirect(url_for('login'))
            
            user = db.session.get(User, session['user_id'])
            if not user or not user.is_active:
                session.clear()
                flash('Your account is not active or has been deleted.', 'danger')
                return redirect(url_for('login'))
            
            if role and session.get('role') != role:
                flash('You do not have permission to access this page.', 'danger')
                return redirect(url_for('dashboard'))
            
            return f(*args, **kwargs)
        return decorated_function
    return decorator

def log_activity(user_id, activity_type, description, request=None):
    """Log user activity"""
    try:
        log = ActivityLog(
            user_id=user_id,
            activity_type=activity_type,
            description=description,
            ip_address=request.remote_addr if request else None,
            user_agent=request.headers.get('User-Agent') if request else None
        )
        db.session.add(log)
        db.session.commit()
    except Exception as e:
        logger.error(f"Activity logging error: {str(e)}")

import json
import csv
import io
from flask import send_file

def calculate_rankings(results):
    """Calculate rankings based on marks and time"""
    ranked_results = []
    for result in results:
        # Score is primarily based on percentage, then time taken
        # Lower time taken gives better ranking for same percentage
        score = result.percentage * 100 - (result.time_taken / result.total_time_available * 10)
        ranked_results.append((result, score))
    
    # Sort by score descending
    ranked_results.sort(key=lambda x: x[1], reverse=True)
    return [result[0] for result in ranked_results]

# Routes
@app.route('/')
def index():
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    # If already logged in, redirect immediately
    if 'user_id' in session:
        role = session.get('role')
        return redirect(url_for(get_dashboard_redirect(role)))

    # Generate CSRF token
    if 'csrf_token' not in session:
        session['csrf_token'] = secrets.token_hex(16)

    if request.method == 'POST':
        # Verify CSRF token
        if request.form.get('csrf_token') != session.get('csrf_token'):
            flash('Invalid session token. Please try again.', 'danger')
            return redirect(url_for('login'))

        username = request.form['username']
        password = request.form['password']

        user = User.query.filter_by(username=username, is_active=True).first()

        if user and check_password_hash(user.password_hash, password):
            # Set session variables
            session['user_id'] = user.id
            session['username'] = user.username
            session['role'] = user.role
            session['name'] = user.name

            # Update last login
            user.last_login = datetime.now(timezone.utc)
            db.session.commit()

            flash(f'Welcome back, {user.name}!', 'success')
            logger.info(f"User {username} logged in successfully as {user.role}")

            # Redirect based on role
            return redirect(url_for(get_dashboard_redirect(user.role)))
        else:
            flash('Invalid username or password!', 'danger')
            logger.warning(f"Failed login attempt for username: {username}")

    return render_template('login.html', csrf_token=session['csrf_token'])



@app.route('/teacher/assign_test/<int:test_id>', methods=['GET', 'POST'])
@login_required('teacher')
def assign_test_to_students(test_id):
    try:
        test = TestPaper.query.filter_by(id=test_id, created_by=session['user_id']).first_or_404()
        
        if request.method == 'POST':
            student_ids = request.form.get('student_ids', '').split(',')
            student_ids = [sid for sid in student_ids if sid]  # Remove empty strings
            test_date = datetime.strptime(request.form['test_date'], '%Y-%m-%d').date()
            
            assigned_count = 0
            for student_id in student_ids:
                # Check if assignment already exists
                existing_assignment = TestAssignment.query.filter_by(
                    student_id=student_id,
                    test_paper_id=test_id,
                    test_date=test_date
                ).first()
                
                if not existing_assignment:
                    assignment = TestAssignment(
                        student_id=student_id,
                        test_paper_id=test_id,
                        test_date=test_date,
                        assigned_by=session['user_id']
                    )
                    db.session.add(assignment)
                    assigned_count += 1
            
            if assigned_count > 0:
                db.session.commit()
                flash(f'Test assigned to {assigned_count} students successfully!', 'success')
            else:
                flash('No new assignments were made. Students may already have this test assigned.', 'info')
            
            return redirect(url_for('manage_tests'))
        
        # GET request - show assignment form
        students = User.query.filter_by(role='student', is_active=True).all()
        
        # Get already assigned students for this test
        assigned_students = TestAssignment.query.filter_by(test_paper_id=test_id).all()
        assigned_student_ids = [assignment.student_id for assignment in assigned_students]
        
        # Get today's date for the date picker
        today = datetime.now().date().isoformat()
        
        return render_template('assign_to_students.html', 
                             test=test, 
                             students=students,
                             assigned_student_ids=assigned_student_ids,
                             today=today)
        
    except Exception as e:
        logger.error(f"Test assignment error: {str(e)}")
        flash('Error assigning test.', 'danger')
        return redirect(url_for('manage_tests'))

@app.route('/logout')
def logout():
    session.clear()
    flash('You have been logged out successfully.', 'success')
    return redirect(url_for('login'))

@app.route('/dashboard')
@login_required()
def dashboard():
    role = session.get('role')
    return redirect(url_for(get_dashboard_redirect(role)))

# Admin Routes
# Admin Routes - Enhanced
@app.route('/admin/dashboard')
@login_required('admin')
def admin_dashboard():
    try:
        # Basic counts
        total_users = User.query.count()
        total_teachers = User.query.filter_by(role='teacher').count()
        total_students = User.query.filter_by(role='student').count()
        total_tests = TestResult.query.count()
        total_assignments = TestAssignment.query.count()
        
        # Recent activity
        recent_activity = ActivityLog.query.order_by(ActivityLog.created_at.desc()).limit(10).all()
        
        # Top performers
        top_students = db.session.query(
            User.name, 
            db.func.avg(TestResult.percentage).label('avg_score'),
            db.func.count(TestResult.id).label('tests_taken')
        ).join(TestResult, User.id == TestResult.student_id
        ).filter(User.role == 'student'
        ).group_by(User.id
        ).order_by(db.desc('avg_score')
        ).limit(5).all()
        
        return render_template('admin_dashboard.html', 
                             total_users=total_users,
                             total_teachers=total_teachers,
                             total_students=total_students,
                             total_tests=total_tests,
                             total_assignments=total_assignments,
                             recent_activity=recent_activity,
                             top_students=top_students)
    except Exception as e:
        logger.error(f"Admin dashboard error: {str(e)}")
        flash('Error loading dashboard.', 'danger')
        return redirect(url_for('dashboard'))

@app.route('/admin/users')
@login_required('admin')
def manage_users():
    users = User.query.all()
    return render_template('manage_users.html', users=users)

@app.route('/admin/create_user', methods=['GET', 'POST'])
@login_required('admin')
def create_user():
    if request.method == 'POST':
        try:
            username = request.form['username']
            password = request.form['password']
            name = request.form['name']
            role = request.form['role']
            email = request.form.get('email', '')
            
            if User.query.filter_by(username=username).first():
                flash('Username already exists!', 'danger')
                return redirect(url_for('manage_users'))
            
            user = User(
                username=username,
                password_hash=generate_password_hash(password),
                name=name,
                role=role,
                email=email
            )
            
            db.session.add(user)
            db.session.commit()
            
            log_activity(session['user_id'], 'user_creation', f'Created user: {username} ({role})', request)
            flash(f'User {name} created successfully!', 'success')
        except Exception as e:
            logger.error(f"User creation error: {str(e)}")
            flash('Error creating user.', 'danger')
        
        return redirect(url_for('manage_users'))
    
    return render_template('create_user.html')

@app.route('/admin/edit_user/<int:user_id>', methods=['GET', 'POST'])
@login_required('admin')
def edit_user(user_id):
    user = User.query.get_or_404(user_id)
    
    if request.method == 'POST':
        try:
            user.name = request.form['name']
            user.email = request.form['email']
            user.role = request.form['role']
            user.is_active = 'is_active' in request.form
            
            # Update password if provided
            new_password = request.form.get('new_password')
            if new_password:
                user.password_hash = generate_password_hash(new_password)
            
            db.session.commit()
            
            log_activity(session['user_id'], 'user_update', f'Updated user: {user.username}', request)
            flash('User updated successfully!', 'success')
            return redirect(url_for('manage_users'))
        except Exception as e:
            logger.error(f"User update error: {str(e)}")
            flash('Error updating user.', 'danger')
    
    return render_template('edit_user.html', user=user)

@app.route('/admin/toggle_user/<int:user_id>')
@login_required('admin')
def toggle_user(user_id):
    try:
        user = db.session.get(User, user_id)
        if not user:
            flash('User not found!', 'danger')
            return redirect(url_for('manage_users'))
            
        user.is_active = not user.is_active
        db.session.commit()
        
        status = "activated" if user.is_active else "deactivated"
        log_activity(session['user_id'], 'user_toggle', f'{status} user: {user.username}', request)
        flash(f'User {status} successfully!', 'success')
    except Exception as e:
        logger.error(f"User toggle error: {str(e)}")
        flash('Error updating user status.', 'danger')
    
    return redirect(url_for('manage_users'))

@app.route('/admin/delete_user/<int:user_id>')
@login_required('admin')
def delete_user(user_id):
    try:
        user = User.query.get_or_404(user_id)
        
        # Prevent admin from deleting themselves
        if user.id == session['user_id']:
            flash('You cannot delete your own account!', 'danger')
            return redirect(url_for('manage_users'))
        
        db.session.delete(user)
        db.session.commit()
        
        log_activity(session['user_id'], 'user_deletion', f'Deleted user: {user.username}', request)
        flash('User deleted successfully!', 'success')
    except Exception as e:
        logger.error(f"User deletion error: {str(e)}")
        flash('Error deleting user.', 'danger')
    
    return redirect(url_for('manage_users'))

@app.route('/admin/assign_test', methods=['GET', 'POST'])
@login_required('admin')
def assign_test():
    if request.method == 'POST':
        try:
            student_id = request.form['student_id']
            test_folder = request.form['test_folder']
            test_name = request.form['test_name']
            test_date = datetime.strptime(request.form['test_date'], '%Y-%m-%d').date()
            test_duration = int(request.form.get('test_duration', 60))
            
            assignment = TestAssignment(
                student_id=student_id,
                test_folder=test_folder,
                test_name=test_name,
                test_date=test_date,
                test_duration=test_duration,
                assigned_by=session['user_id']
            )
            
            db.session.add(assignment)
            db.session.commit()
            
            log_activity(session['user_id'], 'test_assignment', f'Assigned test "{test_name}" to student ID {student_id}', request)
            flash('Test assigned successfully!', 'success')
        except Exception as e:
            logger.error(f"Test assignment error: {str(e)}")
            flash('Error assigning test.', 'danger')
        
        return redirect(url_for('assign_test'))
    
    students = User.query.filter_by(role='student', is_active=True).all()
    teachers = User.query.filter_by(role='teacher', is_active=True).all()
    assignments = TestAssignment.query.filter_by(is_active=True).all()
    return render_template('assign_test.html', students=students, teachers=teachers, assignments=assignments)

@app.route('/admin/test_results')
@login_required('admin')
def admin_test_results():
    try:
        # Get all test results with student information
        results = TestResult.query.join(User).order_by(TestResult.submitted_at.desc()).all()
        
        # Statistics
        total_tests = len(results)
        avg_score = sum(r.percentage for r in results) / total_tests if total_tests > 0 else 0
        best_score = max(r.percentage for r in results) if results else 0
        
        return render_template('admin_test_results.html',
                             results=results,
                             total_tests=total_tests,
                             avg_score=avg_score,
                             best_score=best_score)
    except Exception as e:
        logger.error(f"Test results error: {str(e)}")
        flash('Error loading test results.', 'danger')
        return redirect(url_for('admin_dashboard'))

@app.route('/admin/download_results')
@login_required('admin')
def download_results():
    try:
        output = io.StringIO()
        writer = csv.writer(output)
        
        # Write header
        writer.writerow(['Student ID', 'Student Name', 'Test Name', 'Test Date', 
                        'Total Questions', 'Correct Answers', 'Percentage', 
                        'Time Taken (seconds)', 'Submitted At'])
        
        # Get all results
        results = TestResult.query.join(User).all()
        
        for result in results:
            writer.writerow([
                result.student.id,
                result.student.name,
                result.test_name,
                result.test_date.strftime('%Y-%m-%d'),
                result.total_questions,
                result.correct_answers,
                f"{result.percentage:.2f}%",
                result.time_taken,
                result.submitted_at.strftime('%Y-%m-%d %H:%M:%S')
            ])
        
        output.seek(0)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        return send_file(
            io.BytesIO(output.getvalue().encode('utf-8')),
            mimetype='text/csv',
            as_attachment=True,
            download_name=f'student_results_{timestamp}.csv'
        )
    except Exception as e:
        logger.error(f"Results download error: {str(e)}")
        flash('Error downloading results.', 'danger')
        return redirect(url_for('admin_test_results'))

@app.route('/admin/leaderboard')
@login_required('admin')
def leaderboard():
    try:
        # Top students by average score
        top_students = db.session.query(
            User.id,
            User.name,
            User.username,
            db.func.avg(TestResult.percentage).label('avg_score'),
            db.func.count(TestResult.id).label('tests_taken'),
            db.func.max(TestResult.percentage).label('best_score')
        ).join(TestResult, User.id == TestResult.student_id
        ).filter(User.role == 'student'
        ).group_by(User.id
        ).having(db.func.count(TestResult.id) >= 1
        ).order_by(db.desc('avg_score')
        ).limit(10).all()
        
        # Teacher performance (based on their students' results)
        teacher_performance = db.session.query(
            User.name.label('teacher_name'),
            db.func.avg(TestResult.percentage).label('avg_class_score'),
            db.func.count(TestResult.id).label('total_tests_taken')
        ).join(Question, User.id == Question.uploaded_by
        ).join(TestAssignment, Question.subject == TestAssignment.test_folder
        ).join(TestResult, (TestAssignment.student_id == TestResult.student_id) & 
                          (TestAssignment.test_name == TestResult.test_name)
        ).filter(User.role == 'teacher'
        ).group_by(User.id
        ).order_by(db.desc('avg_class_score')
        ).all()
        
        # Test performance
        test_performance = db.session.query(
            TestResult.test_name,
            db.func.avg(TestResult.percentage).label('avg_score'),
            db.func.count(TestResult.id).label('attempts')
        ).group_by(TestResult.test_name
        ).order_by(db.desc('avg_score')
        ).all()
        
        return render_template('leaderboard.html',
                             top_students=top_students,
                             teacher_performance=teacher_performance,
                             test_performance=test_performance)
    except Exception as e:
        logger.error(f"Leaderboard error: {str(e)}")
        flash('Error loading leaderboard.', 'danger')
        return redirect(url_for('admin_dashboard'))

@app.route('/admin/student_details/<int:student_id>')
@login_required('admin')
def student_details(student_id):
    try:
        student = User.query.get_or_404(student_id)
        if student.role != 'student':
            flash('User is not a student!', 'danger')
            return redirect(url_for('manage_users'))
        
        # Get student's test results
        results = TestResult.query.filter_by(student_id=student_id).order_by(TestResult.submitted_at.desc()).all()
        
        # Get student's assignments
        assignments = TestAssignment.query.filter_by(student_id=student_id).all()
        
        # Calculate statistics
        total_tests = len(results)
        avg_score = sum(r.percentage for r in results) / total_tests if total_tests > 0 else 0
        best_score = max(r.percentage for r in results) if results else 0
        
        return render_template('student_details.html',
                             student=student,
                             results=results,
                             assignments=assignments,
                             total_tests=total_tests,
                             avg_score=avg_score,
                             best_score=best_score)
    except Exception as e:
        logger.error(f"Student details error: {str(e)}")
        flash('Error loading student details.', 'danger')
        return redirect(url_for('manage_users'))


# Teacher Routes
@app.route('/teacher/dashboard')
@login_required('teacher')
def teacher_dashboard():
    try:
        user_id = session['user_id']
        
        # Basic counts
        questions_count = Question.query.filter_by(uploaded_by=user_id).count()
        active_questions = Question.query.filter_by(uploaded_by=user_id, is_active=True).count()
        tests_count = TestPaper.query.filter_by(created_by=user_id).count()
        active_tests = TestPaper.query.filter_by(created_by=user_id, is_active=True).count()
        pending_queries = StudentQuery.query.join(TestPaper).filter(
            TestPaper.created_by == user_id,
            StudentQuery.status == 'pending'
        ).count()
        
        # Recent test results
        recent_results = TestResult.query.join(TestPaper).filter(
            TestPaper.created_by == user_id
        ).order_by(TestResult.submitted_at.desc()).limit(5).all()
        
        return render_template('teacher_dashboard.html', 
                             questions_count=questions_count,
                             active_questions=active_questions,
                             tests_count=tests_count,
                             active_tests=active_tests,
                             pending_queries=pending_queries,
                             recent_results=recent_results)
    except Exception as e:
        logger.error(f"Teacher dashboard error: {str(e)}")
        flash('Error loading dashboard.', 'danger')
        return redirect(url_for('dashboard'))

@app.route('/teacher/questions')
@login_required('teacher')
def manage_questions():
    questions = Question.query.filter_by(uploaded_by=session['user_id']).all()
    return render_template('manage_questions.html', questions=questions)

# Teacher Test Management Routes
@app.route('/teacher/create_test', methods=['GET', 'POST'])
@login_required('teacher')
def create_test():
    if request.method == 'POST':
        try:
            name = request.form['test_name']
            description = request.form.get('description', '')
            subject = request.form['subject']
            duration = int(request.form['duration'])
            question_count = int(request.form['question_count'])
            
            # Create test paper
            test_paper = TestPaper(
                name=name,
                description=description,
                subject=subject,
                total_questions=question_count,
                duration=duration,
                created_by=session['user_id']
            )
            db.session.add(test_paper)
            db.session.flush()  # Get the ID
            
            # Get available questions for this subject
            available_questions = Question.query.filter_by(
                subject=subject, 
                uploaded_by=session['user_id'],
                is_active=True
            ).all()
            
            if len(available_questions) < question_count:
                flash(f'Not enough questions available. You have {len(available_questions)} questions but need {question_count}.', 'danger')
                db.session.rollback()
                return redirect(url_for('create_test'))
            
            # Select random questions
            import random
            selected_questions = random.sample(available_questions, question_count)
            
            # Add questions to test paper
            for i, question in enumerate(selected_questions, 1):
                test_question = TestQuestion(
                    test_paper_id=test_paper.id,
                    question_id=question.id,
                    question_number=i
                )
                db.session.add(test_question)
            
            db.session.commit()
            log_activity(session['user_id'], 'test_creation', f'Created test: {name}', request)
            flash('Test created successfully!', 'success')
            return redirect(url_for('manage_tests'))
            
        except Exception as e:
            db.session.rollback()
            logger.error(f"Test creation error: {str(e)}")
            flash('Error creating test.', 'danger')
    
    # Get unique subjects from teacher's questions
    subjects = db.session.query(Question.subject).filter_by(
        uploaded_by=session['user_id']
    ).distinct().all()
    subjects = [s[0] for s in subjects]
    
    return render_template('create_test.html', subjects=subjects)

@app.route('/teacher/tests')
@login_required('teacher')
def manage_tests():
    tests = TestPaper.query.filter_by(created_by=session['user_id']).order_by(TestPaper.created_at.desc()).all()
    return render_template('manage_tests.html', tests=tests)

@app.route('/teacher/view_test/<int:test_id>')
@login_required('teacher')
def view_test(test_id):
    try:
        test = TestPaper.query.filter_by(id=test_id, created_by=session['user_id']).first_or_404()
        test_questions = TestQuestion.query.filter_by(test_paper_id=test_id).order_by(TestQuestion.question_number).all()
        
        # Get test statistics
        total_attempts = TestResult.query.filter_by(test_paper_id=test_id).count()
        
        # Calculate average score safely
        avg_score_result = db.session.query(db.func.avg(TestResult.percentage)).filter_by(test_paper_id=test_id).scalar()
        avg_score = avg_score_result if avg_score_result is not None else 0
        
        return render_template('view_test.html', 
                             test=test, 
                             test_questions=test_questions,
                             total_attempts=total_attempts,
                             avg_score=avg_score)
    except Exception as e:
        logger.error(f"View test error: {str(e)}")
        flash('Error loading test details.', 'danger')
        return redirect(url_for('manage_tests'))

@app.route('/teacher/test_results/<int:test_id>')
@login_required('teacher')
def test_results(test_id):
    try:
        test = TestPaper.query.filter_by(id=test_id, created_by=session['user_id']).first_or_404()
        results = TestResult.query.filter_by(test_paper_id=test_id).all()
        
        # Calculate rankings
        ranked_results = calculate_rankings(results)
        
        return render_template('test_results.html', test=test, results=ranked_results)
    except Exception as e:
        logger.error(f"Test results error: {str(e)}")
        flash('Error loading test results.', 'danger')
        return redirect(url_for('manage_tests'))

@app.route('/teacher/test_leaderboard/<int:test_id>')
@login_required('teacher')
def test_leaderboard(test_id):
    test = TestPaper.query.filter_by(id=test_id, created_by=session['user_id']).first_or_404()
    results = TestResult.query.filter_by(test_paper_id=test_id).all()
    
    # Calculate rankings based on both score and time
    ranked_results = calculate_rankings(results)
    
    return render_template('test_leaderboard.html', test=test, results=ranked_results)

@app.route('/teacher/student_performance')
@login_required('teacher')
def student_performance():
    try:
        # Get all students who have taken tests created by this teacher
        student_performance = db.session.query(
            User.id,
            User.name,
            User.username,
            db.func.count(TestResult.id).label('tests_taken'),
            db.func.avg(TestResult.percentage).label('avg_score'),
            db.func.avg(TestResult.time_taken).label('avg_time_taken')
        ).join(TestResult, User.id == TestResult.student_id
        ).join(TestPaper, TestResult.test_paper_id == TestPaper.id
        ).filter(TestPaper.created_by == session['user_id']
        ).group_by(User.id
        ).all()
        
        return render_template('student_performance.html', students=student_performance)
    except Exception as e:
        logger.error(f"Student performance error: {str(e)}")
        flash('Error loading student performance data.', 'danger')
        return redirect(url_for('teacher_dashboard'))

@app.route('/teacher/download_performance')
@login_required('teacher')
def download_performance():
    try:
        output = io.StringIO()
        writer = csv.writer(output)
        
        # Write header
        writer.writerow(['Student ID', 'Student Name', 'Tests Taken', 'Average Score', 'Average Time Taken (seconds)'])
        
        # Get performance data
        student_performance = db.session.query(
            User.id,
            User.name,
            db.func.count(TestResult.id).label('tests_taken'),
            db.func.avg(TestResult.percentage).label('avg_score'),
            db.func.avg(TestResult.time_taken).label('avg_time_taken')
        ).join(TestResult, User.id == TestResult.student_id
        ).join(TestPaper, TestResult.test_paper_id == TestPaper.id
        ).filter(TestPaper.created_by == session['user_id']
        ).group_by(User.id
        ).all()
        
        for student in student_performance:
            writer.writerow([
                student.id,
                student.name,
                student.tests_taken,
                f"{student.avg_score:.2f}%",
                f"{student.avg_time_taken:.2f}"
            ])
        
        output.seek(0)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        return send_file(
            io.BytesIO(output.getvalue().encode('utf-8')),
            mimetype='text/csv',
            as_attachment=True,
            download_name=f'student_performance_{timestamp}.csv'
        )
    except Exception as e:
        logger.error(f"Performance download error: {str(e)}")
        flash('Error downloading performance data.', 'danger')
        return redirect(url_for('student_performance'))

@app.route('/teacher/student_queries')
@login_required('teacher')
def student_queries():
    try:
        teacher_id = session['user_id']
        print(f"DEBUG: Loading queries for teacher ID: {teacher_id}")
        
        # Use eager loading to prevent N+1 queries
        queries = StudentQuery.query\
            .join(TestPaper)\
            .join(User, StudentQuery.student_id == User.id)\
            .options(
                db.joinedload(StudentQuery.student),
                db.joinedload(StudentQuery.test_paper),
                db.joinedload(StudentQuery.question),
                db.joinedload(StudentQuery.resolving_teacher)
            )\
            .filter(TestPaper.created_by == teacher_id)\
            .order_by(StudentQuery.created_at.desc())\
            .all()
        
        print(f"DEBUG: Found {len(queries)} queries")
        
        # Debug print each query
        for i, query in enumerate(queries):
            print(f"DEBUG Query {i}: ID={query.id}, Student={query.student.name if query.student else 'None'}, QuestionID={query.question_id}")
        
        return render_template('student_queries.html', queries=queries)
        
    except Exception as e:
        logger.error(f"Student queries error: {str(e)}")
        import traceback
        print(f"ERROR: {traceback.format_exc()}")
        flash('Error loading student queries.', 'danger')
        return redirect(url_for('teacher_dashboard'))

@app.route('/create_test_query')
@login_required('teacher')
def create_test_query():
    """Create a test student query for debugging"""
    try:
        teacher_id = session['user_id']
        
        # Get or create test data
        student = User.query.filter_by(role='student').first()
        test_paper = TestPaper.query.filter_by(created_by=teacher_id).first()
        question = Question.query.filter_by(uploaded_by=teacher_id).first()
        
        if not test_paper:
            # Create a test paper if none exists
            test_paper = TestPaper(
                name="Sample Test",
                subject="Mathematics",
                total_questions=10,
                duration=60,
                created_by=teacher_id
            )
            db.session.add(test_paper)
            db.session.flush()
        
        if not question:
            # Create a sample question
            question = Question(
                subject="Mathematics",
                question_text="What is 2+2?",
                option_a="3",
                option_b="4", 
                option_c="5",
                option_d="6",
                correct_answer="B",
                uploaded_by=teacher_id
            )
            db.session.add(question)
            db.session.flush()
        
        if student and test_paper and question:
            query = StudentQuery(
                student_id=student.id,
                test_paper_id=test_paper.id,
                question_id=question.id,
                query_text="This is a test query for debugging purposes. The question seems unclear.",
                status='pending'
            )
            db.session.add(query)
            db.session.commit()
            flash('Test query created successfully!', 'success')
        else:
            flash('Could not create test query - missing required data', 'warning')
            
        return redirect(url_for('student_queries'))
    except Exception as e:
        flash(f'Error creating test query: {str(e)}', 'danger')
        return redirect(url_for('student_queries'))

@app.route('/teacher/resolve_query/<int:query_id>', methods=['POST'])
@login_required('teacher')
def resolve_query(query_id):
    try:
        query = StudentQuery.query.get_or_404(query_id)
        
        # Verify the teacher owns this test
        if query.test_paper.created_by != session['user_id']:
            flash('You do not have permission to resolve this query.', 'danger')
            return redirect(url_for('student_queries'))
        
        response = request.form['response']
        action = request.form.get('action')
        
        query.response = response
        query.resolved_by = session['user_id']
        query.resolved_at = datetime.now(timezone.utc)
        
        if action == 'update_question':
            # Update the question if needed
            question = Question.query.get(query.question_id)
            if question and question.uploaded_by == session['user_id']:
                # Here you can update the question based on the query
                flash('Question updated based on student query.', 'info')
        
        query.status = 'resolved'
        db.session.commit()
        
        flash('Query resolved successfully!', 'success')
    except Exception as e:
        logger.error(f"Query resolution error: {str(e)}")
        flash('Error resolving query.', 'danger')
        db.session.rollback()
    
    return redirect(url_for('student_queries'))

@app.route('/debug/queries')
@login_required('teacher')
def debug_queries():
    from sqlalchemy import text
    # Check database connection
    try:
        result = db.session.execute(text("SELECT 1"))
        print("Database connection: OK")
    except Exception as e:
        print(f"Database connection error: {e}")
    
    # Check queries
    queries = StudentQuery.query.all()
    print(f"Total queries in DB: {len(queries)}")
    
    for q in queries:
        print(f"Query {q.id}: Student={q.student_id}, Test={q.test_paper_id}, Status={q.status}")
    
    return f"Debug: {len(queries)} queries found"

@app.route('/student/dashboard')
@login_required('student')
def student_dashboard():
    try:
        today = datetime.now().date()
        student_id = session['user_id']
        
        # Get current assignments for today
        current_assignments = TestAssignment.query.filter_by(
            student_id=student_id, 
            test_date=today,
            is_active=True
        ).all()
        
        # Check which tests have been taken
        taken_tests = []
        for assignment in current_assignments:
            has_taken = TestResult.query.filter_by(
                student_id=student_id,
                test_paper_id=assignment.test_paper_id,
                test_date=assignment.test_date
            ).first() is not None
            taken_tests.append({
                'assignment': assignment,
                'has_taken': has_taken
            })
        
        # Get recent results
        recent_results = TestResult.query.filter_by(
            student_id=student_id
        ).order_by(TestResult.submitted_at.desc()).limit(5).all()
        
        return render_template('student_dashboard.html', 
                             taken_tests=taken_tests,
                             recent_results=recent_results,
                             today=today)
    except Exception as e:
        logger.error(f"Student dashboard error: {str(e)}")
        flash('Error loading dashboard.', 'danger')
        return redirect(url_for('dashboard'))

# Student Routes
@app.route('/student/take_test/<int:assignment_id>')
@login_required('student')
def take_test(assignment_id):
    try:
        assignment = TestAssignment.query.filter_by(
            id=assignment_id, 
            student_id=session['user_id'],
            is_active=True
        ).first_or_404()
        
        # Check if test already taken
        existing_result = TestResult.query.filter_by(
            student_id=session['user_id'],
            test_paper_id=assignment.test_paper_id,
            test_date=assignment.test_date
        ).first()
        
        if existing_result:
            flash('You have already taken this test!', 'warning')
            return redirect(url_for('student_dashboard'))
        
        test_paper = assignment.test_paper
        questions = TestQuestion.query.filter_by(
            test_paper_id=test_paper.id
        ).order_by(TestQuestion.question_number).all()
        
        return render_template('take_test.html', 
                             assignment=assignment, 
                             test_paper=test_paper, 
                             questions=questions)
    except Exception as e:
        logger.error(f"Take test error: {str(e)}")
        flash('Error loading test.', 'danger')
        return redirect(url_for('student_dashboard'))

@app.route('/student/submit_test/<int:assignment_id>', methods=['POST'])
@login_required('student')
def submit_test(assignment_id):
    try:
        assignment = TestAssignment.query.filter_by(
            id=assignment_id, 
            student_id=session['user_id']
        ).first_or_404()
        
        answers_data = request.form.get('answers_data')
        time_taken = int(request.form.get('time_taken', 0))
        
        # Calculate score
        answers = json.loads(answers_data) if answers_data else {}
        test_paper = assignment.test_paper
        questions = TestQuestion.query.filter_by(test_paper_id=test_paper.id).all()
        
        correct_answers = 0
        for question in questions:
            student_answer = answers.get(str(question.question_id))
            if student_answer and student_answer.upper() == question.question.correct_answer:
                correct_answers += 1
        
        percentage = (correct_answers / test_paper.total_questions) * 100
        
        # Save result
        result = TestResult(
            student_id=session['user_id'],
            test_paper_id=test_paper.id,
            test_date=assignment.test_date,
            total_questions=test_paper.total_questions,
            correct_answers=correct_answers,
            percentage=percentage,
            time_taken=time_taken,
            total_time_available=test_paper.duration * 60,
            answers_data=answers_data
        )
        
        db.session.add(result)
        db.session.commit()
        
        flash('Test submitted successfully!', 'success')
        return redirect(url_for('student_dashboard'))
        
    except Exception as e:
        logger.error(f"Test submission error: {str(e)}")
        flash('Error submitting test.', 'danger')
        return redirect(url_for('student_dashboard'))

# Error handlers
@app.errorhandler(404)
def not_found_error(error):
    return render_template('404.html'), 404

# Add these routes to your Flask app



@app.route('/student/query_question', methods=['POST'])
@login_required('student')
def query_question():
    try:
        question_id = request.form['question_id']
        test_paper_id = request.form['test_paper_id']
        query_text = request.form['query_text']
        
        query = StudentQuery(
            student_id=session['user_id'],
            test_paper_id=test_paper_id,
            question_id=question_id,
            query_text=query_text
        )
        
        db.session.add(query)
        db.session.commit()
        
        flash('Your query has been submitted to the teacher.', 'success')
    except Exception as e:
        logger.error(f"Query submission error: {str(e)}")
        flash('Error submitting query.', 'danger')
    
    return redirect(url_for('student_dashboard'))

@app.route('/teacher/leaderboard')
@login_required('teacher')
def teacher_leaderboard():
    try:
        # Top students in teacher's tests
        top_students = db.session.query(
            User.id,
            User.name,
            User.username,
            db.func.avg(TestResult.percentage).label('avg_score'),
            db.func.avg(TestResult.time_taken).label('avg_time'),
            db.func.count(TestResult.id).label('tests_taken')
        ).join(TestResult, User.id == TestResult.student_id
        ).join(TestPaper, TestResult.test_paper_id == TestPaper.id
        ).filter(TestPaper.created_by == session['user_id']
        ).group_by(User.id
        ).order_by(db.desc('avg_score')
        ).limit(10).all()
        
        # Test-wise performance
        test_performance = db.session.query(
            TestPaper.name,
            db.func.avg(TestResult.percentage).label('avg_score'),
            db.func.count(TestResult.id).label('attempts')
        ).join(TestResult, TestPaper.id == TestResult.test_paper_id
        ).filter(TestPaper.created_by == session['user_id']
        ).group_by(TestPaper.id
        ).order_by(db.desc('avg_score')
        ).all()
        
        return render_template('teacher_leaderboard.html',
                             top_students=top_students,
                             test_performance=test_performance)
    except Exception as e:
        logger.error(f"Leaderboard error: {str(e)}")
        flash('Error loading leaderboard.', 'danger')
        return redirect(url_for('teacher_dashboard'))



@app.route('/teacher/view_results')
@login_required('teacher')
def view_results():
    try:
        # Get results for tests created by this teacher
        results = TestResult.query.join(TestPaper).filter(
            TestPaper.created_by == session['user_id']
        ).order_by(TestResult.submitted_at.desc()).all()
        
        # Calculate statistics
        total_tests = len(results)
        
        if total_tests > 0:
            average_percentage = sum(r.percentage for r in results) / total_tests
            best_score = max(r.percentage for r in results)
            
            # Get unique students
            student_ids = set(r.student_id for r in results)
            total_students = len(student_ids)
            
            # Prepare scores for chart
            scores = [r.percentage for r in results]
            scores_json = json.dumps(scores)
        else:
            average_percentage = 0
            best_score = 0
            total_students = 0
            scores_json = json.dumps([])
        
        return render_template('teacher_results.html', 
                             results=results,
                             total_tests=total_tests,
                             average_percentage=average_percentage,
                             best_score=best_score,
                             total_students=total_students,
                             scores_json=scores_json)
    except Exception as e:
        logger.error(f"Results view error: {str(e)}")
        flash('Error loading results.', 'danger')
        return redirect(url_for('teacher_dashboard'))

@app.route('/teacher/upload_question', methods=['POST'])
@login_required('teacher')
def upload_question():
    try:
        subject = request.form['subject']
        question_text = request.form['question_text']
        option_a = request.form['option_a']
        option_b = request.form['option_b']
        option_c = request.form['option_c']
        option_d = request.form['option_d']
        correct_answer = request.form['correct_answer']
        explanation = request.form.get('explanation', '')
        difficulty = request.form.get('difficulty', 'medium')
        
        if not all([subject, question_text, option_a, option_b, option_c, option_d, correct_answer]):
            flash('All fields except explanation are required!', 'danger')
            return redirect(url_for('manage_questions'))
        
        if correct_answer.upper() not in ['A', 'B', 'C', 'D']:
            flash('Correct answer must be A, B, C, or D!', 'danger')
            return redirect(url_for('manage_questions'))
        
        question = Question(
            subject=subject,
            question_text=question_text,  # Remove encryption for now
            option_a=option_a,
            option_b=option_b,
            option_c=option_c,
            option_d=option_d,
            correct_answer=correct_answer.upper(),
            explanation=explanation,
            difficulty=difficulty,
            uploaded_by=session['user_id']
        )
        
        db.session.add(question)
        db.session.commit()
        
        flash('Question uploaded successfully!', 'success')
    except Exception as e:
        logger.error(f"Question upload error: {str(e)}")
        flash('Error uploading question. Please try again.', 'danger')
        db.session.rollback()
    
    return redirect(url_for('manage_questions'))

@app.route('/teacher/toggle_question/<int:question_id>')
@login_required('teacher')
def toggle_question(question_id):
    try:
        question = Question.query.filter_by(id=question_id, uploaded_by=session['user_id']).first_or_404()
        question.is_active = not question.is_active
        db.session.commit()
        
        status = "activated" if question.is_active else "deactivated"
        flash(f'Question {status} successfully!', 'success')
    except Exception as e:
        logger.error(f"Question toggle error: {str(e)}")
        flash('Error updating question status.', 'danger')
    
    return redirect(url_for('manage_questions'))

# Initialize database
def init_db():
    with app.app_context():
        db.create_all()
        
        if not User.query.filter_by(role='admin').first():
            admin = User(
                username='admin',
                password_hash=generate_password_hash('Admin123!'),
                name='System Administrator',
                role='admin',
                email='admin@testsystem.com'
            )
            teacher = User(
                username='teacher1',
                password_hash=generate_password_hash('Teacher123!'),
                name='Sample Teacher',
                role='teacher',
                email='teacher@testsystem.com'
            )
            student = User(
                username='student1',
                password_hash=generate_password_hash('Student123!'),
                name='Sample Student',
                role='student',
                email='student@testsystem.com'
            )
            db.session.add_all([admin, teacher, student])
            db.session.commit()
            print("=" * 50)
            print("DEFAULT USERS CREATED:")
            print("Admin: username='admin', password='Admin123!'")
            print("Teacher: username='teacher1', password='Teacher123!'")
            print("Student: username='student1', password='Student123!'")
            print("=" * 50)

if __name__ == '__main__':
    # Create directories if they don't exist
    os.makedirs('templates', exist_ok=True)
    os.makedirs('static', exist_ok=True)
    os.makedirs('logs', exist_ok=True)
    
    # Initialize database
    init_db()
    
    print("\n>>> Secure Online Test Management System Started!")
    print(">>> Access the application at: http://localhost:5000")
    print(">>> Default users have been created (see above for credentials)")
    print(">>> Remember to change default passwords in production!\n")
    
    app.run(debug=True, host='0.0.0.0', port=5000)