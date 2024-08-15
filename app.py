from flask import Flask, render_template, request, redirect, url_for, jsonify, abort
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
import secrets
import os
from werkzeug.utils import secure_filename
from functools import wraps


app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'default_secret_key')
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DATABASE_URL', 'postgresql://api:key@localhost/store')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['UPLOAD_FOLDER'] = os.getenv('UPLOAD_FOLDER', 'uploads')
ALLOWED_EXTENSIONS = {'txt', 'pdf', 'png', 'jpg', 'jpeg', 'gif'}

db = SQLAlchemy(app)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = '/new/login'

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(150), unique=True, nullable=False)
    password = db.Column(db.String(150), nullable=False)

class APIKey(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    key = db.Column(db.String(32), unique=True, nullable=False)
    description = db.Column(db.String(255), nullable=False)
    active = db.Column(db.Boolean, default=True)

class StoredFile(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    filename = db.Column(db.String(255), nullable=False)
    file_path = db.Column(db.String(255), nullable=False)

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

def require_api_key(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        api_key = request.headers.get('x-api-key')
        if not api_key:
            abort(401, description="Unauthorized access")
        key = APIKey.query.filter_by(key=api_key, active=True).first()
        if not key:
            abort(401, description="Unauthorized access")
        return f(*args, **kwargs)
    return decorated_function

@app.route('/new/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        user = User.query.filter_by(username=username).first()
        if user and check_password_hash(user.password, password):
            login_user(user)
            return redirect(url_for('/new/index'))
    return render_template('/new/login.html')

@app.route('/new/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        existing_user = User.query.filter_by(username=username).first()
        if existing_user:
            # Pass the error message to the template
            return render_template('/new/register.html', error="Username already exists. Please choose a different username.")

        hashed_password = generate_password_hash(password, method='sha256')
        user = User(username=username, password=hashed_password)
        db.session.add(user)
        db.session.commit()
        return redirect(url_for('/new/login'))
    
    return render_template('/new/register.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('/new/login'))

@app.route('/')
@login_required
def index():
    return render_template('/new/index.html')

@app.route('/generate', methods=['POST'])
@login_required
def generate():
    description = request.form['description']
    key = secrets.token_hex(16)
    new_key = APIKey(user_id=current_user.id, key=key, description=description)
    db.session.add(new_key)
    db.session.commit()
    return redirect(url_for('/new/index'))

@app.route('/keys')
@login_required
def keys():
    user_keys = APIKey.query.filter_by(user_id=current_user.id).all()
    keys_dict = {key.key: {'description': key.description, 'active': key.active} for key in user_keys}
    return jsonify(keys_dict)

@app.route('/deactivate', methods=['POST'])
@login_required
def deactivate():
    api_key = request.form['key']
    key = APIKey.query.filter_by(key=api_key, user_id=current_user.id).first()
    if key:
        key.active = False
        db.session.commit()
        return redirect(url_for('/new/index'))
    else:
        return 'API key not found or you do not have permission to deactivate this key.', 404

@app.route('/api/upload', methods=['POST'])
@require_api_key
def upload_file():
    if 'file' not in request.files:
        return 'No file part', 400
    file = request.files['file']
    if file.filename == '':
        return 'No selected file', 400
    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(file_path)
        new_file = StoredFile(user_id=current_user.id, filename=filename, file_path=file_path)
        db.session.add(new_file)
        db.session.commit()
        return 'File uploaded successfully', 200
    return 'File type not allowed', 400

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

if __name__ == '__main__':
    if not os.path.exists(app.config['UPLOAD_FOLDER']):
        os.makedirs(app.config['UPLOAD_FOLDER'])
    # db.create_all()
    app.run(debug=True)
