from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
import sqlite3, os, hashlib, json
from datetime import datetime
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.secret_key = 'recruit_ai_secret_2024'
UPLOAD_FOLDER = 'uploads/resumes'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

DB = 'recruitment.db'

def get_db():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    c = conn.cursor()
    c.executescript('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            mobile TEXT NOT NULL,
            password TEXT NOT NULL,
            role TEXT DEFAULT 'user',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS profiles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER UNIQUE,
            bio TEXT,
            location TEXT,
            linkedin TEXT,
            github TEXT,
            photo TEXT,
            FOREIGN KEY(user_id) REFERENCES users(id)
        );
        CREATE TABLE IF NOT EXISTS education (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            degree TEXT,
            institution TEXT,
            year_start TEXT,
            year_end TEXT,
            grade TEXT,
            FOREIGN KEY(user_id) REFERENCES users(id)
        );
        CREATE TABLE IF NOT EXISTS experience (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            company TEXT,
            role TEXT,
            year_start TEXT,
            year_end TEXT,
            description TEXT,
            FOREIGN KEY(user_id) REFERENCES users(id)
        );
        CREATE TABLE IF NOT EXISTS skills (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            skill_name TEXT,
            level TEXT,
            FOREIGN KEY(user_id) REFERENCES users(id)
        );
        CREATE TABLE IF NOT EXISTS certificates (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            cert_name TEXT,
            issuer TEXT,
            year TEXT,
            FOREIGN KEY(user_id) REFERENCES users(id)
        );
        CREATE TABLE IF NOT EXISTS job_posts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            hr_id INTEGER,
            title TEXT,
            company TEXT,
            location TEXT,
            job_type TEXT,
            description TEXT,
            required_skills TEXT,
            required_experience TEXT,
            required_education TEXT,
            salary TEXT,
            deadline TEXT,
            status TEXT DEFAULT 'active',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(hr_id) REFERENCES users(id)
        );
        CREATE TABLE IF NOT EXISTS applications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            job_id INTEGER,
            cover_letter TEXT,
            resume_path TEXT,
            status TEXT DEFAULT 'applied',
            ai_score REAL DEFAULT 0,
            ai_feedback TEXT,
            applied_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(user_id) REFERENCES users(id),
            FOREIGN KEY(job_id) REFERENCES job_posts(id)
        );
    ''')
    # Create default HR
    pw = hashlib.sha256('hr123'.encode()).hexdigest()
    c.execute("INSERT OR IGNORE INTO users (name,email,mobile,password,role) VALUES (?,?,?,?,?)",
              ('HR Admin','hr@recruit.ai','9999999999',pw,'hr'))
    conn.commit()
    conn.close()

def hash_pw(pw): return hashlib.sha256(pw.encode()).hexdigest()

def ai_match_score(user_id, job_id):
    conn = get_db()
    job = conn.execute("SELECT * FROM job_posts WHERE id=?", (job_id,)).fetchone()
    user_skills = [r['skill_name'].lower() for r in conn.execute("SELECT skill_name FROM skills WHERE user_id=?", (user_id,)).fetchall()]
    user_edu = conn.execute("SELECT * FROM education WHERE user_id=? ORDER BY id DESC LIMIT 1", (user_id,)).fetchone()
    user_exp = conn.execute("SELECT * FROM experience WHERE user_id=?", (user_id,)).fetchall()
    conn.close()
    if not job: return 0, "Job not found"
    score = 0; feedback = []
    req_skills = [s.strip().lower() for s in (job['required_skills'] or '').split(',') if s.strip()]
    if req_skills:
        matched = [s for s in req_skills if any(s in us or us in s for us in user_skills)]
        skill_score = (len(matched)/len(req_skills))*40
        score += skill_score
        feedback.append(f"Skills match: {len(matched)}/{len(req_skills)} ({int(skill_score)}% of 40%)")
    else:
        score += 20; feedback.append("No specific skills required")
    edu_keywords = (job['required_education'] or '').lower()
    if user_edu and edu_keywords:
        deg = (user_edu['degree'] or '').lower()
        if any(k in deg for k in ['phd','doctorate']): edu_score=30
        elif any(k in deg for k in ['master','mtech','mba']): edu_score=25
        elif any(k in deg for k in ['bachelor','btech','be','bsc']): edu_score=20
        else: edu_score=10
        score += min(edu_score, 30); feedback.append(f"Education: {user_edu['degree']} ({min(edu_score,30)}% of 30%)")
    else:
        score += 15; feedback.append("Education not specified")
    exp_years = len(user_exp)*1.5
    req_exp = ''.join(filter(lambda x: x.isdigit() or x=='.', (job['required_experience'] or '0')))
    try:
        req_exp_val = float(req_exp) if req_exp else 0
        exp_score = min((exp_years / max(req_exp_val,1)) * 30, 30)
        score += exp_score; feedback.append(f"Experience: ~{exp_years:.1f} yrs vs {req_exp_val} required ({int(exp_score)}% of 30%)")
    except:
        score += 15; feedback.append("Experience partially matched")
    return round(min(score, 100), 1), ' | '.join(feedback)

# â”€â”€â”€ AUTH â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/register', methods=['GET','POST'])
def register():
    if request.method=='POST':
        name=request.form.get('name','').strip()
        email=request.form.get('email','').strip().lower()
        mobile=request.form.get('mobile','').strip()
        pw=request.form.get('password','')
        if not all([name, email, mobile, pw]):
            flash('All fields are required.','danger')
            return render_template('register.html')
        conn=get_db()
        try:
            existing = conn.execute("SELECT id FROM users WHERE email=?", (email,)).fetchone()
            if existing:
                flash('This email is already registered. Please login.','danger')
                conn.close()
                return render_template('register.html')
            conn.execute("INSERT INTO users (name,email,mobile,password) VALUES (?,?,?,?)",
                         (name,email,mobile,hash_pw(pw)))
            conn.commit()
            conn.close()
            flash('Account created successfully! Please login.','success')
            return redirect(url_for('login'))
        except Exception as e:
            conn.close()
            flash('Registration failed. Please try again.','danger')
    return render_template('register.html')

@app.route('/login', methods=['GET','POST'])
def login():
    if request.method=='POST':
        email=request.form['email']; pw=request.form['password']
        conn=get_db()
        user=conn.execute("SELECT * FROM users WHERE email=? AND password=?",(email,hash_pw(pw))).fetchone()
        conn.close()
        if user:
            session['user_id']=user['id']; session['name']=user['name']
            session['role']=user['role']; session['email']=user['email']
            return redirect(url_for('hr_dashboard') if user['role']=='hr' else url_for('user_dashboard'))
        flash('Invalid credentials.','danger')
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear(); return redirect(url_for('index'))

# â”€â”€â”€ USER â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
@app.route('/dashboard')
def user_dashboard():
    if 'user_id' not in session or session['role']!='user': return redirect(url_for('login'))
    conn=get_db()
    uid=session['user_id']
    profile=conn.execute("SELECT * FROM profiles WHERE user_id=?",(uid,)).fetchone()
    skills=conn.execute("SELECT * FROM skills WHERE user_id=?",(uid,)).fetchall()
    apps=conn.execute("""SELECT a.*,j.title,j.company,j.location FROM applications a
                         JOIN job_posts j ON a.job_id=j.id WHERE a.user_id=? ORDER BY a.applied_at DESC""",(uid,)).fetchall()
    jobs=conn.execute("SELECT * FROM job_posts WHERE status='active' ORDER BY created_at DESC LIMIT 6").fetchall()
    conn.close()
    return render_template('user_dashboard.html', profile=profile, skills=skills, apps=apps, jobs=jobs)

@app.route('/profile', methods=['GET','POST'])
def profile():
    if 'user_id' not in session or session['role']!='user': return redirect(url_for('login'))
    uid=session['user_id']; conn=get_db()
    if request.method=='POST':
        bio=request.form.get('bio',''); loc=request.form.get('location','')
        li=request.form.get('linkedin',''); gh=request.form.get('github','')
        existing=conn.execute("SELECT id FROM profiles WHERE user_id=?",(uid,)).fetchone()
        if existing: conn.execute("UPDATE profiles SET bio=?,location=?,linkedin=?,github=? WHERE user_id=?",(bio,loc,li,gh,uid))
        else: conn.execute("INSERT INTO profiles (user_id,bio,location,linkedin,github) VALUES (?,?,?,?,?)",(uid,bio,loc,li,gh))
        conn.commit(); flash('Profile updated!','success')
    p=conn.execute("SELECT * FROM profiles WHERE user_id=?",(uid,)).fetchone()
    edu=conn.execute("SELECT * FROM education WHERE user_id=?",(uid,)).fetchall()
    exp=conn.execute("SELECT * FROM experience WHERE user_id=?",(uid,)).fetchall()
    sk=conn.execute("SELECT * FROM skills WHERE user_id=?",(uid,)).fetchall()
    certs=conn.execute("SELECT * FROM certificates WHERE user_id=?",(uid,)).fetchall()
    user=conn.execute("SELECT * FROM users WHERE id=?",(uid,)).fetchone()
    conn.close()
    return render_template('profile.html', profile=p, education=edu, experience=exp, skills=sk, certificates=certs, user=user)

@app.route('/add_education', methods=['POST'])
def add_education():
    if 'user_id' not in session: return redirect(url_for('login'))
    uid=session['user_id']; conn=get_db()
    conn.execute("INSERT INTO education (user_id,degree,institution,year_start,year_end,grade) VALUES (?,?,?,?,?,?)",
                 (uid,request.form['degree'],request.form['institution'],request.form['year_start'],request.form['year_end'],request.form['grade']))
    conn.commit(); conn.close(); flash('Education added!','success')
    return redirect(url_for('profile'))

@app.route('/add_experience', methods=['POST'])
def add_experience():
    if 'user_id' not in session: return redirect(url_for('login'))
    uid=session['user_id']; conn=get_db()
    conn.execute("INSERT INTO experience (user_id,company,role,year_start,year_end,description) VALUES (?,?,?,?,?,?)",
                 (uid,request.form['company'],request.form['role'],request.form['year_start'],request.form['year_end'],request.form['description']))
    conn.commit(); conn.close(); flash('Experience added!','success')
    return redirect(url_for('profile'))

@app.route('/add_skill', methods=['POST'])
def add_skill():
    if 'user_id' not in session: return redirect(url_for('login'))
    uid=session['user_id']; conn=get_db()
    conn.execute("INSERT INTO skills (user_id,skill_name,level) VALUES (?,?,?)",(uid,request.form['skill_name'],request.form['level']))
    conn.commit(); conn.close(); flash('Skill added!','success')
    return redirect(url_for('profile'))

@app.route('/add_certificate', methods=['POST'])
def add_certificate():
    if 'user_id' not in session: return redirect(url_for('login'))
    uid=session['user_id']; conn=get_db()
    conn.execute("INSERT INTO certificates (user_id,cert_name,issuer,year) VALUES (?,?,?,?)",
                 (uid,request.form['cert_name'],request.form['issuer'],request.form['year']))
    conn.commit(); conn.close(); flash('Certificate added!','success')
    return redirect(url_for('profile'))

@app.route('/delete/<table>/<int:rid>')
def delete_item(table, rid):
    if 'user_id' not in session: return redirect(url_for('login'))
    allowed=['education','experience','skills','certificates']
    if table in allowed:
        conn=get_db(); conn.execute(f"DELETE FROM {table} WHERE id=? AND user_id=?",(rid,session['user_id']))
        conn.commit(); conn.close()
    return redirect(url_for('profile'))

@app.route('/jobs')
def jobs():
    if 'user_id' not in session: return redirect(url_for('login'))
    q=request.args.get('q',''); loc=request.args.get('loc',''); jtype=request.args.get('jtype','')
    conn=get_db()
    query="SELECT * FROM job_posts WHERE status='active'"
    params=[]
    if q: query+=" AND (title LIKE ? OR required_skills LIKE ?)"; params+=[f'%{q}%',f'%{q}%']
    if loc: query+=" AND location LIKE ?"; params.append(f'%{loc}%')
    if jtype: query+=" AND job_type=?"; params.append(jtype)
    query+=" ORDER BY created_at DESC"
    jobs=conn.execute(query,params).fetchall()
    applied=[r['job_id'] for r in conn.execute("SELECT job_id FROM applications WHERE user_id=?",(session['user_id'],)).fetchall()]
    conn.close()
    return render_template('jobs.html', jobs=jobs, applied=applied, q=q, loc=loc, jtype=jtype)

@app.route('/apply/<int:job_id>', methods=['GET','POST'])
def apply_job(job_id):
    if 'user_id' not in session or session['role']!='user': return redirect(url_for('login'))
    uid=session['user_id']; conn=get_db()
    job=conn.execute("SELECT * FROM job_posts WHERE id=?",(job_id,)).fetchone()
    if not job: flash('Job not found.','danger'); return redirect(url_for('jobs'))
    already=conn.execute("SELECT id FROM applications WHERE user_id=? AND job_id=?",(uid,job_id)).fetchone()
    if already: flash('Already applied!','warning'); conn.close(); return redirect(url_for('jobs'))
    if request.method=='POST':
        cover=request.form.get('cover_letter','')
        resume_path=''
        if 'resume' in request.files:
            f=request.files['resume']
            if f and f.filename.endswith('.pdf'):
                fn=secure_filename(f"{uid}_{job_id}_{f.filename}")
                fp=os.path.join(app.config['UPLOAD_FOLDER'],fn)
                f.save(fp); resume_path=fp
        score,feedback=ai_match_score(uid,job_id)
        conn.execute("INSERT INTO applications (user_id,job_id,cover_letter,resume_path,ai_score,ai_feedback) VALUES (?,?,?,?,?,?)",
                     (uid,job_id,cover,resume_path,score,feedback))
        conn.commit(); conn.close()
        flash(f'Application submitted! AI Match Score: {score}%','success')
        return redirect(url_for('user_dashboard'))
    conn.close()
    return render_template('apply.html', job=job)

# â”€â”€â”€ HR â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
@app.route('/hr')
def hr_dashboard():
    if 'user_id' not in session or session['role']!='hr': return redirect(url_for('login'))
    conn=get_db()
    total_jobs=conn.execute("SELECT COUNT(*) FROM job_posts WHERE hr_id=?",(session['user_id'],)).fetchone()[0]
    total_apps=conn.execute("SELECT COUNT(*) FROM applications").fetchone()[0]
    total_users=conn.execute("SELECT COUNT(*) FROM users WHERE role='user'").fetchone()[0]
    recent_apps=conn.execute("""SELECT a.*,u.name,u.email,j.title FROM applications a
        JOIN users u ON a.user_id=u.id JOIN job_posts j ON a.job_id=j.id
        ORDER BY a.applied_at DESC LIMIT 5""").fetchall()
    conn.close()
    return render_template('hr_dashboard.html', total_jobs=total_jobs, total_apps=total_apps,
                           total_users=total_users, recent_apps=recent_apps)

@app.route('/hr/post', methods=['GET','POST'])
def hr_post_job():
    if 'user_id' not in session or session['role']!='hr': return redirect(url_for('login'))
    if request.method=='POST':
        conn=get_db()
        conn.execute("""INSERT INTO job_posts (hr_id,title,company,location,job_type,description,
                        required_skills,required_experience,required_education,salary,deadline)
                        VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                     (session['user_id'],request.form['title'],request.form['company'],
                      request.form['location'],request.form['job_type'],request.form['description'],
                      request.form['required_skills'],request.form['required_experience'],
                      request.form['required_education'],request.form['salary'],request.form['deadline']))
        conn.commit(); conn.close()
        flash('Job posted successfully!','success')
        return redirect(url_for('hr_posts'))
    return render_template('hr_post_job.html')

@app.route('/hr/posts')
def hr_posts():
    if 'user_id' not in session or session['role']!='hr': return redirect(url_for('login'))
    conn=get_db()
    jobs=conn.execute("""SELECT j.*,(SELECT COUNT(*) FROM applications WHERE job_id=j.id) as app_count
                         FROM job_posts j WHERE hr_id=? ORDER BY created_at DESC""",(session['user_id'],)).fetchall()
    conn.close()
    return render_template('hr_posts.html', jobs=jobs)

@app.route('/hr/toggle_job/<int:job_id>')
def toggle_job(job_id):
    if 'user_id' not in session or session['role']!='hr': return redirect(url_for('login'))
    conn=get_db()
    job=conn.execute("SELECT status FROM job_posts WHERE id=?",(job_id,)).fetchone()
    new_status='inactive' if job['status']=='active' else 'active'
    conn.execute("UPDATE job_posts SET status=? WHERE id=?",(new_status,job_id))
    conn.commit(); conn.close()
    return redirect(url_for('hr_posts'))

@app.route('/hr/applications')
def hr_applications():
    if 'user_id' not in session or session['role']!='hr': return redirect(url_for('login'))
    job_id=request.args.get('job_id','')
    conn=get_db()
    query="""SELECT a.*,u.name,u.email,u.mobile,j.title,j.company FROM applications a
             JOIN users u ON a.user_id=u.id JOIN job_posts j ON a.job_id=j.id"""
    params=[]
    if job_id: query+=" WHERE a.job_id=?"; params.append(job_id)
    query+=" ORDER BY a.ai_score DESC"
    apps=conn.execute(query,params).fetchall()
    jobs=conn.execute("SELECT id,title FROM job_posts WHERE hr_id=?",(session['user_id'],)).fetchall()
    conn.close()
    return render_template('hr_applications.html', apps=apps, jobs=jobs, selected_job=job_id)

@app.route('/hr/candidate/<int:user_id>')
def hr_view_candidate(user_id):
    if 'user_id' not in session or session['role']!='hr': return redirect(url_for('login'))
    conn=get_db()
    user=conn.execute("SELECT * FROM users WHERE id=?",(user_id,)).fetchone()
    profile=conn.execute("SELECT * FROM profiles WHERE user_id=?",(user_id,)).fetchone()
    edu=conn.execute("SELECT * FROM education WHERE user_id=?",(user_id,)).fetchall()
    exp=conn.execute("SELECT * FROM experience WHERE user_id=?",(user_id,)).fetchall()
    sk=conn.execute("SELECT * FROM skills WHERE user_id=?",(user_id,)).fetchall()
    certs=conn.execute("SELECT * FROM certificates WHERE user_id=?",(user_id,)).fetchall()
    apps=conn.execute("""SELECT a.*,j.title FROM applications a JOIN job_posts j ON a.job_id=j.id
                         WHERE a.user_id=? ORDER BY a.ai_score DESC""",(user_id,)).fetchall()
    conn.close()
    return render_template('hr_candidate.html', candidate=user, profile=profile, education=edu,
                           experience=exp, skills=sk, certificates=certs, apps=apps)

@app.route('/hr/update_status/<int:app_id>/<status>')
def update_status(app_id, status):
    if 'user_id' not in session or session['role']!='hr': return redirect(url_for('login'))
    conn=get_db()
    conn.execute("UPDATE applications SET status=? WHERE id=?",(status,app_id))
    conn.commit(); conn.close()
    flash(f'Status updated to {status}','success')
    return redirect(request.referrer or url_for('hr_applications'))

@app.route('/hr/ranking/<int:job_id>')
def hr_ranking(job_id):
    if 'user_id' not in session or session['role']!='hr': return redirect(url_for('login'))
    conn=get_db()
    job=conn.execute("SELECT * FROM job_posts WHERE id=?",(job_id,)).fetchone()
    ranked=conn.execute("""SELECT a.*,u.name,u.email,u.mobile FROM applications a
                           JOIN users u ON a.user_id=u.id WHERE a.job_id=?
                           ORDER BY a.ai_score DESC""",(job_id,)).fetchall()
    conn.close()
    return render_template('hr_ranking.html', job=job, ranked=ranked)

@app.route('/resume/<int:user_id>')
def view_resume(user_id):
    if 'user_id' not in session: return redirect(url_for('login'))
    conn=get_db()
    user=conn.execute("SELECT * FROM users WHERE id=?",(user_id,)).fetchone()
    profile=conn.execute("SELECT * FROM profiles WHERE user_id=?",(user_id,)).fetchone()
    edu=conn.execute("SELECT * FROM education WHERE user_id=?",(user_id,)).fetchall()
    exp=conn.execute("SELECT * FROM experience WHERE user_id=?",(user_id,)).fetchall()
    sk=conn.execute("SELECT * FROM skills WHERE user_id=?",(user_id,)).fetchall()
    certs=conn.execute("SELECT * FROM certificates WHERE user_id=?",(user_id,)).fetchall()
    conn.close()
    return render_template('resume.html', user=user, profile=profile, education=edu,
                           experience=exp, skills=sk, certificates=certs)

if __name__=='__main__':
    init_db()
    app.run(debug=True)
