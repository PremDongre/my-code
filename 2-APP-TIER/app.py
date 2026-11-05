"""Connect - Internship & Jobs platform by PremTech (Flask + HTML + CSS + JavaScript)
Roles: owner (PremTech) | company (company admin) | student
Database: SQLite for local testing, MySQL (AWS RDS) when DB_HOST is set.  Uploads: local folder, or S3 when S3_BUCKET is set."""
import os, re, json, secrets, sqlite3, smtplib, socket, ipaddress, html as htmlmod
import mimetypes, hashlib
import urllib.request, urllib.parse, urllib.error
from concurrent.futures import ThreadPoolExecutor
import time
from datetime import datetime, timedelta
from email.message import EmailMessage
from functools import wraps
from flask import (Flask, g, render_template, request, redirect, url_for,
                   session, flash, abort, send_from_directory, Response, jsonify)
from werkzeug.middleware.proxy_fix import ProxyFix
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

BASE = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.environ.get("DATA_DIR", BASE)          # local data folder (SQLite file + secret key)
DB_PATH = os.path.join(DATA_DIR, "internsphere.db")
UPLOAD_DIR = os.path.join(DATA_DIR, "uploads")
DEMO = os.environ.get("SEED_DEMO", "1") != "0"        # set SEED_DEMO=0 in production
STATUSES = ["Pending", "Under Review", "Shortlisted", "Accepted", "Rejected"]
STAFF = ("owner", "company")
MIN_PW = 8
USE_MYSQL = bool(os.environ.get("DB_HOST"))           # AWS: RDS MySQL.  Local: SQLite
S3_BUCKET = os.environ.get("S3_BUCKET")               # AWS: uploads go to S3.  Local: uploads folder
os.makedirs(DATA_DIR, exist_ok=True)
if not S3_BUCKET:
    os.makedirs(UPLOAD_DIR, exist_ok=True)
if USE_MYSQL:
    import pymysql, pymysql.cursors
if S3_BUCKET:
    import boto3
    from botocore.exceptions import ClientError
    s3 = boto3.client("s3", region_name=os.environ.get("AWS_REGION") or os.environ.get("AWS_DEFAULT_REGION"))

def load_secret():
    k = os.environ.get("SECRET_KEY")
    if k:
        return k
    if USE_MYSQL:
        raise RuntimeError("Set SECRET_KEY (same value on every app server) in /etc/connect.env")
    p = os.path.join(DATA_DIR, ".secret_key")
    if os.path.exists(p):
        return open(p).read().strip()
    k = secrets.token_hex(32)
    open(p, "w").write(k)
    return k

app = Flask(__name__)
app.secret_key = load_secret()
app.config.update(MAX_CONTENT_LENGTH=5 * 1024 * 1024, SESSION_COOKIE_HTTPONLY=True,
                  SESSION_COOKIE_SAMESITE="Lax", SESSION_COOKIE_SECURE=os.environ.get("COOKIE_SECURE") == "1",
                  PERMANENT_SESSION_LIFETIME=timedelta(days=7))
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=int(os.environ.get("PROXY_HOPS", "1")), x_proto=1, x_host=1)   # AWS 3-tier: PROXY_HOPS=3

# ---------------------------------------------------------------- database (SQLite locally, MySQL on AWS)
def _sql(sql):
    """Our queries are written SQLite style; translate for MySQL."""
    if not USE_MYSQL:
        return sql
    sql = sql.replace("%", "%%").replace("?", "%s")
    sql = sql.replace("INSERT OR IGNORE", "INSERT IGNORE").replace("INSERT OR REPLACE INTO", "REPLACE INTO")
    return re.sub(r"(?<![\w`])key(?=\s*=)", "`key`", sql)

class Conn:
    def __init__(self, raw):
        self.raw = raw
    def execute(self, sql, args=()):
        if USE_MYSQL:
            cur = self.raw.cursor(); cur.execute(_sql(sql), tuple(args)); return cur
        return self.raw.execute(sql, args)
    def script(self, text):
        if USE_MYSQL:
            cur = self.raw.cursor()
            for stmt in [x.strip() for x in text.split(";") if x.strip()]:
                cur.execute(stmt)
        else:
            self.raw.executescript(text)
    def commit(self):
        self.raw.commit()
    def close(self):
        self.raw.close()

def connect():
    if USE_MYSQL:
        kw = {}
        if os.environ.get("DB_SSL_CA"):
            kw["ssl"] = {"ca": os.environ["DB_SSL_CA"]}
        raw = pymysql.connect(host=os.environ["DB_HOST"], port=int(os.environ.get("DB_PORT", 3306)), user=os.environ["DB_USER"],
                              password=os.environ["DB_PASSWORD"], database=os.environ.get("DB_NAME", "connect_db"), charset="utf8mb4",
                              cursorclass=pymysql.cursors.DictCursor, autocommit=True, connect_timeout=8, **kw)
    else:
        raw = sqlite3.connect(DB_PATH, timeout=15)
        raw.row_factory = sqlite3.Row
    return Conn(raw)

def db():
    if "db" not in g:
        g.db = connect()
    return g.db

@app.teardown_appcontext
def close_db(_):
    d = g.pop("db", None)
    if d:
        d.close()

def q(sql, args=(), one=False):
    rows = db().execute(sql, args).fetchall()
    return (rows[0] if rows else None) if one else rows

def n(sql, args=()):
    row = db().execute(sql, args).fetchone()
    return next(iter(row.values())) if USE_MYSQL else row[0]

def run(sql, args=()):
    cur = db().execute(sql, args); db().commit()
    return cur.lastrowid

def now():
    return datetime.now().strftime("%Y-%m-%d %H:%M")

def ts():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

SCHEMA = """
CREATE TABLE IF NOT EXISTS companies(id INTEGER PRIMARY KEY, name TEXT, website TEXT, description TEXT,
 status TEXT DEFAULT 'pending', created TEXT);
CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY, name TEXT, email TEXT UNIQUE, password TEXT,
 role TEXT DEFAULT 'student', phone TEXT, college TEXT, course TEXT, skills TEXT, about TEXT, resume TEXT,
 email_updates INTEGER DEFAULT 1, created TEXT, alias TEXT, photo TEXT, company_id INTEGER,
 headline TEXT, linkedin TEXT, github TEXT, website TEXT, portfolio_public INTEGER DEFAULT 0);
CREATE TABLE IF NOT EXISTS internships(id INTEGER PRIMARY KEY, title TEXT, company TEXT, location TEXT,
 category TEXT, type TEXT, stipend TEXT, duration TEXT, deadline TEXT, description TEXT, requirements TEXT,
 created TEXT, apply_url TEXT, company_id INTEGER, kind TEXT DEFAULT 'internship');
CREATE TABLE IF NOT EXISTS saved(user_id INTEGER, internship_id INTEGER, UNIQUE(user_id, internship_id));
CREATE TABLE IF NOT EXISTS applications(id INTEGER PRIMARY KEY, user_id INTEGER, internship_id INTEGER, cover TEXT,
 status TEXT DEFAULT 'Pending', applied_at TEXT, UNIQUE(user_id, internship_id));
CREATE TABLE IF NOT EXISTS notifications(id INTEGER PRIMARY KEY, user_id INTEGER, message TEXT, is_read INTEGER DEFAULT 0, created TEXT);
CREATE TABLE IF NOT EXISTS messages(id INTEGER PRIMARY KEY, name TEXT, email TEXT, message TEXT, created TEXT);
CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE IF NOT EXISTS tests(id INTEGER PRIMARY KEY, internship_id INTEGER, title TEXT, instructions TEXT,
 duration_min INTEGER DEFAULT 10, pass_percent INTEGER DEFAULT 50, created TEXT, strict INTEGER DEFAULT 1, max_violations INTEGER DEFAULT 3);
CREATE TABLE IF NOT EXISTS questions(id INTEGER PRIMARY KEY, test_id INTEGER, text TEXT, qtype TEXT DEFAULT 'mcq',
 a TEXT, b TEXT, c TEXT, d TEXT, answer TEXT, marks INTEGER DEFAULT 1);
CREATE TABLE IF NOT EXISTS attempts(id INTEGER PRIMARY KEY, test_id INTEGER, user_id INTEGER, started_at TEXT,
 submitted_at TEXT, score REAL, total REAL, percent REAL, passed INTEGER, violations INTEGER DEFAULT 0, blocked INTEGER DEFAULT 0, loads INTEGER DEFAULT 0,
 violation_log TEXT, draft TEXT, forced INTEGER DEFAULT 0, UNIQUE(test_id, user_id));
CREATE TABLE IF NOT EXISTS courses(id INTEGER PRIMARY KEY, title TEXT, provider TEXT, category TEXT, level TEXT, language TEXT,
 url TEXT, description TEXT, certificate TEXT DEFAULT 'free', note TEXT, company_id INTEGER, added_by INTEGER,
 active INTEGER DEFAULT 1, clicks INTEGER DEFAULT 0, created TEXT);
CREATE TABLE IF NOT EXISTS certificates(id INTEGER PRIMARY KEY, user_id INTEGER, title TEXT, issuer TEXT, issue_date TEXT, url TEXT, file TEXT, created TEXT);
CREATE TABLE IF NOT EXISTS projects(id INTEGER PRIMARY KEY, user_id INTEGER, title TEXT, description TEXT, tech TEXT, repo_url TEXT, live_url TEXT, created TEXT);
CREATE TABLE IF NOT EXISTS answers(id INTEGER PRIMARY KEY, attempt_id INTEGER, question_id INTEGER, response TEXT, correct INTEGER);
"""

COURSE_CATEGORIES = ["Programming", "Web Development", "Computer Science", "Data & AI", "Cloud Computing", "Cybersecurity", "Networking",
                     "Digital Marketing", "Business", "Design", "Languages & Communication", "General Skills"]
COURSE_LEVELS = ["Beginner", "Intermediate", "Advanced", "All levels"]
COURSE_LANGS = ["English", "Hindi", "Marathi", "Tamil", "Telugu", "Other"]
CERTS = {"free": "Free certificate", "badge": "Free badge / credential", "paid": "Free to learn · certificate paid", "none": "No certificate"}

# Curated free courses (we only link to the original websites - we do not host any course)
CURATED = [
 ("Python Programming (Scientific Computing with Python)", "freeCodeCamp", "Programming", "Beginner", "English", "https://www.freecodecamp.org/learn", "Learn Python by building projects. Finish the certification projects to earn a free certificate.", "free", "Free certification by completing projects"),
 ("Web Development: HTML, CSS & JavaScript Certifications", "freeCodeCamp", "Web Development", "Beginner", "English", "https://www.freecodecamp.org/learn", "Responsive Web Design and JavaScript certifications with hands-on projects.", "free", "Free certification by completing projects"),
 ("CS50x: Introduction to Computer Science", "Harvard University (CS50)", "Computer Science", "Beginner", "English", "https://cs50.harvard.edu/x/", "Harvard's famous intro course: C, Python, SQL, web programming and problem solving.", "free", "Free CS50 certificate after problem sets and final project"),
 ("Skills Certification: Python, Java, SQL, JavaScript, C# & more", "HackerRank", "Programming", "All levels", "English", "https://www.hackerrank.com/skills-verification", "Take free skill tests in popular programming languages and get a shareable certificate.", "free", "Free skills certificate on passing the test"),
 ("Python (Kaggle Learn)", "Kaggle", "Programming", "Beginner", "English", "https://www.kaggle.com/learn/python", "Short, practical Python lessons with coding exercises.", "free", "Free certificate of completion"),
 ("Intro to Machine Learning (Kaggle Learn)", "Kaggle", "Data & AI", "Beginner", "English", "https://www.kaggle.com/learn/intro-to-machine-learning", "Build your first machine learning models with hands-on exercises.", "free", "Free certificate of completion"),
 ("Elements of AI", "University of Helsinki & MinnaLearn", "Data & AI", "Beginner", "English", "https://www.elementsofai.com/", "A friendly, non-technical introduction to artificial intelligence. No coding needed.", "free", "Free certificate of completion"),
 ("AI, Cybersecurity & Professional Skills", "IBM SkillsBuild", "Data & AI", "Beginner", "English", "https://skillsbuild.org/", "Free IBM courses in AI, cybersecurity, data and workplace skills.", "badge", "Free digital credentials"),
 ("Networking Basics & Introduction to Cybersecurity", "Cisco Skills for All", "Networking", "Beginner", "English", "https://skillsforall.com/", "Self-paced Cisco courses on networking, cybersecurity, Python and more.", "badge", "Free digital badge on completion"),
 ("Fortinet Certified Fundamentals (Cybersecurity)", "Fortinet Training Institute", "Cybersecurity", "Beginner", "English", "https://training.fortinet.com/", "Free cybersecurity fundamentals training with an official Fortinet credential.", "free", "Free fundamentals-level certification"),
 ("Azure Fundamentals - Free Learning Paths", "Microsoft Learn", "Cloud Computing", "Beginner", "English", "https://learn.microsoft.com/training/", "Free interactive learning paths for Azure, Power Platform, security and more.", "paid", "Learning is free; the official exam has a fee"),
 ("Cloud Practitioner Essentials", "AWS Skill Builder", "Cloud Computing", "Beginner", "English", "https://skillbuilder.aws/", "Free digital courses on AWS cloud concepts, services, security and pricing.", "badge", "Free knowledge badges; certification exam is paid"),
 ("Google Cloud Skills Boost: Skill Badges", "Google Cloud", "Cloud Computing", "Intermediate", "English", "https://www.cloudskillsboost.google/", "Hands-on Google Cloud labs and learning paths that earn skill badges.", "badge", "Free skill badges (some labs may use credits)"),
 ("Trailhead: Salesforce Admin & Developer Paths", "Salesforce Trailhead", "Cloud Computing", "Beginner", "English", "https://trailhead.salesforce.com/", "Gamified free learning for Salesforce admin, developer and CRM skills.", "badge", "Free badges and ranks"),
 ("Free Courses in AI, Data Science, Java, Python & Cloud", "Great Learning Academy", "Data & AI", "Beginner", "English / Hindi", "https://www.mygreatlearning.com/academy", "600+ short free courses on programming languages, AI, data science and cloud.", "free", "Free certificate on course completion"),
 ("Business, Management & Analytics Courses", "Great Learning Academy", "Business", "Beginner", "English / Hindi", "https://www.mygreatlearning.com/academy", "Free short courses on business analytics, management and finance basics.", "free", "Free certificate on course completion"),
 ("SkillUp: Free Courses in Programming, Cloud & Marketing", "Simplilearn SkillUp", "General Skills", "Beginner", "English", "https://www.simplilearn.com/skillup", "Free self-paced courses across tech, digital marketing and project management.", "free", "Free completion certificate"),
 ("Fundamentals of Digital Marketing", "Google Digital Garage", "Digital Marketing", "Beginner", "English", "https://learndigital.withgoogle.com/digitalgarage", "Google's popular beginner course on SEO, social media, email and analytics.", "free", "Free certificate after passing the final exam"),
 ("Google Ads & Analytics Certifications", "Google Skillshop", "Digital Marketing", "Intermediate", "English", "https://skillshop.withgoogle.com/", "Free training and certifications for Google Ads, Analytics and Marketing Platform.", "free", "Free certificate after passing the assessment"),
 ("Inbound Marketing, SEO & Content Marketing Certifications", "HubSpot Academy", "Digital Marketing", "Beginner", "English", "https://academy.hubspot.com/", "Free marketing, sales and service courses, each ending with a HubSpot certification.", "free", "Free HubSpot certification"),
 ("IIT & IISc Courses: Engineering, Data, Management", "NPTEL", "Computer Science", "All levels", "English", "https://nptel.ac.in/courses", "Free video courses from IITs and IISc by India's national programme.", "paid", "Learning is free; certificate needs a paid proctored exam"),
 ("Government of India Online Courses", "SWAYAM", "General Skills", "All levels", "English / Hindi", "https://swayam.gov.in/", "Free courses from school level to university level on India's national platform.", "paid", "Learning is free; certificate needs a paid exam"),
 ("Free Skill Courses by NSDC", "Skill India Digital Hub", "General Skills", "Beginner", "Hindi / English", "https://www.skillindiadigital.gov.in/", "Government of India's digital skilling platform with free job-oriented courses.", "free", "Free government certificate (varies by course)"),
 ("Free Technology & Soft Skills Courses", "Infosys Springboard", "Programming", "All levels", "English", "https://infyspringboard.onwingspan.com/", "Free courses on programming languages, data, cloud and communication skills.", "free", "Free certificate on completion (varies by course)"),
 ("Free Courses: Graphic Design & UI Basics", "Alison", "Design", "Beginner", "English", "https://alison.com/", "Free design and creative courses with a free learner record.", "paid", "Learning is free; printed or digital certificate may cost"),
 ("English Language & Communication Skills", "Alison", "Languages & Communication", "Beginner", "English", "https://alison.com/", "Free spoken and written English, business communication and soft-skills courses.", "paid", "Learning is free; certificate may cost"),
 ("Languages, Study Skills & Career Courses", "OpenLearn (The Open University)", "Languages & Communication", "All levels", "English", "https://www.open.edu/openlearn/", "Free university-quality courses including languages, with free badges.", "badge", "Free badges and statement of participation"),
 ("Free Courses: Tech, Business & Creative Skills", "Udemy", "General Skills", "All levels", "English / Hindi", "https://www.udemy.com/courses/free/", "Thousands of free Udemy courses; many include a certificate of completion.", "free", "Free certificate of completion on eligible courses"),
]


SCHEMA_MYSQL = """
CREATE TABLE IF NOT EXISTS companies(id INT AUTO_INCREMENT PRIMARY KEY, name TEXT, website TEXT, description TEXT, status VARCHAR(20) DEFAULT 'pending', created VARCHAR(20)) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
CREATE TABLE IF NOT EXISTS users(id INT AUTO_INCREMENT PRIMARY KEY, name TEXT, email VARCHAR(190) UNIQUE, password VARCHAR(255), role VARCHAR(20) DEFAULT 'student',
 phone TEXT, college TEXT, course TEXT, skills TEXT, about TEXT, resume VARCHAR(255), email_updates TINYINT DEFAULT 1, created VARCHAR(20), alias VARCHAR(40) UNIQUE,
 photo VARCHAR(255), company_id INT, headline TEXT, linkedin TEXT, github TEXT, website TEXT, portfolio_public TINYINT DEFAULT 0, KEY idx_users_company(company_id)) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
CREATE TABLE IF NOT EXISTS internships(id INT AUTO_INCREMENT PRIMARY KEY, title TEXT, company TEXT, location TEXT, category TEXT, type TEXT, stipend TEXT, duration TEXT, deadline TEXT,
 description TEXT, requirements TEXT, created VARCHAR(20), apply_url TEXT, company_id INT, kind VARCHAR(20) DEFAULT 'internship', KEY idx_int_company(company_id), KEY idx_int_kind(kind)) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
CREATE TABLE IF NOT EXISTS saved(user_id INT, internship_id INT, UNIQUE KEY uq_saved(user_id, internship_id)) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
CREATE TABLE IF NOT EXISTS applications(id INT AUTO_INCREMENT PRIMARY KEY, user_id INT, internship_id INT, cover TEXT, status VARCHAR(30) DEFAULT 'Pending', applied_at VARCHAR(20),
 UNIQUE KEY uq_app(user_id, internship_id), KEY idx_app_int(internship_id)) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
CREATE TABLE IF NOT EXISTS notifications(id INT AUTO_INCREMENT PRIMARY KEY, user_id INT, message TEXT, is_read TINYINT DEFAULT 0, created VARCHAR(20), KEY idx_notif_user(user_id)) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
CREATE TABLE IF NOT EXISTS messages(id INT AUTO_INCREMENT PRIMARY KEY, name TEXT, email TEXT, message TEXT, created VARCHAR(20)) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
CREATE TABLE IF NOT EXISTS settings(`key` VARCHAR(64) PRIMARY KEY, value TEXT) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
CREATE TABLE IF NOT EXISTS tests(id INT AUTO_INCREMENT PRIMARY KEY, internship_id INT, title TEXT, instructions TEXT, duration_min INT DEFAULT 10, pass_percent INT DEFAULT 50, created VARCHAR(20), strict TINYINT DEFAULT 1, max_violations INT DEFAULT 3, KEY idx_tests_int(internship_id)) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
CREATE TABLE IF NOT EXISTS questions(id INT AUTO_INCREMENT PRIMARY KEY, test_id INT, text TEXT, qtype VARCHAR(10) DEFAULT 'mcq', a TEXT, b TEXT, c TEXT, d TEXT, answer TEXT, marks INT DEFAULT 1, KEY idx_q_test(test_id)) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
CREATE TABLE IF NOT EXISTS attempts(id INT AUTO_INCREMENT PRIMARY KEY, test_id INT, user_id INT, started_at VARCHAR(20), submitted_at VARCHAR(20), score DOUBLE, total DOUBLE, percent DOUBLE, passed TINYINT, violations INT DEFAULT 0, blocked INT DEFAULT 0, loads INT DEFAULT 0,
 violation_log TEXT, draft TEXT, forced TINYINT DEFAULT 0, UNIQUE KEY uq_attempt(test_id, user_id)) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
CREATE TABLE IF NOT EXISTS answers(id INT AUTO_INCREMENT PRIMARY KEY, attempt_id INT, question_id INT, response TEXT, correct TINYINT, KEY idx_ans_att(attempt_id)) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
CREATE TABLE IF NOT EXISTS courses(id INT AUTO_INCREMENT PRIMARY KEY, title TEXT, provider TEXT, category TEXT, level TEXT, language TEXT, url TEXT, description TEXT, certificate VARCHAR(10) DEFAULT 'free',
 note TEXT, company_id INT, added_by INT, active TINYINT DEFAULT 1, clicks INT DEFAULT 0, created VARCHAR(20)) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
CREATE TABLE IF NOT EXISTS certificates(id INT AUTO_INCREMENT PRIMARY KEY, user_id INT, title TEXT, issuer TEXT, issue_date TEXT, url TEXT, file VARCHAR(255), created VARCHAR(20), KEY idx_cert_user(user_id)) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
CREATE TABLE IF NOT EXISTS projects(id INT AUTO_INCREMENT PRIMARY KEY, user_id INT, title TEXT, description TEXT, tech TEXT, repo_url TEXT, live_url TEXT, created VARCHAR(20), KEY idx_proj_user(user_id)) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
"""

def init_db():
    con = connect()
    try:
        if USE_MYSQL:
            con.execute("SELECT GET_LOCK('connect_init', 60)").fetchone()      # several servers may start together: run init one at a time
        _init_db(con)
    finally:
        if USE_MYSQL:
            con.execute("SELECT RELEASE_LOCK('connect_init')").fetchone()
        con.commit(); con.close()

# columns added after the first release - added automatically to databases that already exist (SQLite and RDS MySQL)
NEW_COLUMNS = [
    ("tests", "strict", "INTEGER DEFAULT 1", "TINYINT DEFAULT 1"),
    ("tests", "max_violations", "INTEGER DEFAULT 3", "INT DEFAULT 3"),
    ("attempts", "violations", "INTEGER DEFAULT 0", "INT DEFAULT 0"),
    ("attempts", "blocked", "INTEGER DEFAULT 0", "INT DEFAULT 0"),
    ("attempts", "loads", "INTEGER DEFAULT 0", "INT DEFAULT 0"),
    ("attempts", "violation_log", "TEXT", "TEXT"),
    ("attempts", "draft", "TEXT", "TEXT"),
    ("attempts", "forced", "INTEGER DEFAULT 0", "TINYINT DEFAULT 0"),
]

def _add_missing_columns(con):
    for table, col, ddl_sqlite, ddl_mysql in NEW_COLUMNS:
        if USE_MYSQL:
            exists = con.execute("SELECT COUNT(*) c FROM information_schema.columns WHERE table_schema=DATABASE() AND table_name=? AND column_name=?",
                                 (table, col)).fetchone()["c"]
        else:
            exists = col in [r[1] for r in con.execute(f"PRAGMA table_info({table})")]
        if not exists:
            con.execute(f"ALTER TABLE {table} ADD COLUMN {col} {ddl_mysql if USE_MYSQL else ddl_sqlite}")

def _init_db(con):
    if USE_MYSQL:
        con.script(SCHEMA_MYSQL)
    else:
        con.raw.execute("PRAGMA journal_mode=WAL")
        con.script(SCHEMA)
        _upgrade_sqlite(con)
    _add_missing_columns(con)
    _seed(con)

def _upgrade_sqlite(con):
    for table, col in [("users", "alias"), ("users", "photo"), ("users", "company_id"),
                       ("internships", "apply_url"), ("internships", "company_id"), ("internships", "kind"),
                       ("users", "headline"), ("users", "linkedin"), ("users", "github"), ("users", "website")]:   # upgrade old databases
        if col not in [r[1] for r in con.execute(f"PRAGMA table_info({table})")]:
            con.execute(f"ALTER TABLE {table} ADD COLUMN {col} TEXT")
    if "portfolio_public" not in [r[1] for r in con.execute("PRAGMA table_info(users)")]:
        con.execute("ALTER TABLE users ADD COLUMN portfolio_public INTEGER DEFAULT 0")
    con.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_alias ON users(alias)")

def _seed(con):
    con.execute("UPDATE internships SET kind='internship' WHERE kind IS NULL")
    con.execute("UPDATE users SET role='owner' WHERE role='admin'")
    for k, v in [("portal_name", "Connect"), ("contact_email", "support@premtech.com"), ("applications_open", "yes")]:
        con.execute("INSERT OR IGNORE INTO settings VALUES(?,?)", (k, v))
    con.execute("UPDATE settings SET value='Connect' WHERE key='portal_name' AND value IN ('PremTech','InternSphere')")
    if not con.execute("SELECT 1 FROM users WHERE role='owner'").fetchone():
        email = os.environ.get("OWNER_EMAIL", "admin@premtech.com").lower()
        pw = os.environ.get("OWNER_PASSWORD", "Admin@123")
        if pw == "Admin@123":
            print("WARNING: default owner password in use - set OWNER_PASSWORD before going live!")
        try:
            con.execute("INSERT INTO users(name,email,password,role,created,alias) VALUES(?,?,?,?,?,?)",
                        ("PremTech Owner", email, generate_password_hash(pw), "owner", now(), "premtech"))
        except Exception:          # another server created it first
            pass
    if DEMO and not con.execute("SELECT 1 FROM internships").fetchone():
        samples = [
            ("Python Developer Intern", "TechNova", "Pune", "Technology", "Hybrid", "10000/month", "3 months", "2027-12-31", "Work on backend services using Python and Flask.", "Python basics, SQL, Git", "https://internshala.com/internships/python-internship"),
            ("UI/UX Design Intern", "PixelCraft", "Remote", "Design", "Remote", "8000/month", "2 months", "2027-12-15", "Design screens and prototypes for web apps.", "Figma, creativity", "https://internshala.com/internships/graphic-design-internship"),
            ("Digital Marketing Intern", "GrowFast", "Mumbai", "Marketing", "On-site", "6000/month", "3 months", "2027-11-30", "Run social media campaigns and analyse results.", "Communication, basic analytics", "https://internshala.com/internships/digital-marketing-internship"),
            ("Data Analyst Intern", "DataWiz", "Bengaluru", "Data", "Remote", "12000/month", "6 months", "2027-12-20", "Clean data and build dashboards.", "Excel, SQL, Python", "https://internshala.com/internships/data-science-internship")]
        for s in samples:
            con.execute("INSERT INTO internships(title,company,location,category,type,stipend,duration,deadline,description,requirements,apply_url,created) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)", s + (now(),))
    if DEMO and not con.execute("SELECT 1 FROM internships WHERE kind='job'").fetchone():
        for j in [("Junior Python Developer", "TechNova", "Pune", "Technology", "Hybrid", "4-6 LPA", "Full-time · 0-2 yrs", "2027-12-31", "Build and maintain backend APIs in Python.", "Python, Flask, SQL", "https://www.linkedin.com/jobs/"),
                  ("Graphic Designer", "PixelCraft", "Remote", "Design", "Remote", "3-5 LPA", "Full-time · 1-3 yrs", "2027-12-20", "Create brand and social media designs.", "Photoshop, Illustrator, Figma", "https://www.naukri.com/"),
                  ("Sales Executive", "GrowFast", "Mumbai", "Sales", "On-site", "3-4 LPA + incentives", "Full-time · 0-2 yrs", "2027-11-30", "Handle leads and close sales for our services.", "Communication, negotiation", "https://www.indeed.com/")]:
            con.execute("INSERT INTO internships(title,company,location,category,type,stipend,duration,deadline,description,requirements,apply_url,kind,created) VALUES(?,?,?,?,?,?,?,?,?,?,?,'job',?)", j + (now(),))
    for r in con.execute("SELECT DISTINCT company FROM internships WHERE company_id IS NULL AND company IS NOT NULL").fetchall():
        ex = con.execute("SELECT id FROM companies WHERE name=?", (r["company"],)).fetchone()
        cid = ex["id"] if ex else con.execute("INSERT INTO companies(name,status,created) VALUES(?,?,?)", (r["company"], "approved", now())).lastrowid
        con.execute("UPDATE internships SET company_id=? WHERE company=? AND company_id IS NULL", (cid, r["company"]))
    if DEMO and not con.execute("SELECT 1 FROM users WHERE role='company'").fetchone():
        co = con.execute("SELECT id FROM companies WHERE name='TechNova'").fetchone()
        if co:
            con.execute("INSERT OR IGNORE INTO users(name,email,password,role,company_id,created,alias) VALUES(?,?,?,?,?,?,?)",
                        ("TechNova HR", "hr@technova.com", generate_password_hash("Company@123"), "company", co["id"], now(), "technova"))
    if DEMO and not con.execute("SELECT 1 FROM tests").fetchone():
        it = con.execute("SELECT id FROM internships WHERE title='Python Developer Intern'").fetchone()
        if it:
            t = con.execute("INSERT INTO tests(internship_id,title,instructions,duration_min,pass_percent,created) VALUES(?,?,?,?,?,?)",
                            (it["id"], "Python Basics Aptitude", "Answer all questions. You get one attempt.", 10, 60, now())).lastrowid
            for qq in [("What is the output of len([1,2,3])?", "mcq", "2", "3", "4", "Error", "B"),
                       ("Which keyword defines a function in Python?", "mcq", "func", "def", "function", "lambda", "B"),
                       ("Which HTTP method is normally used to submit a form?", "text", "", "", "", "", "post")]:
                con.execute("INSERT INTO questions(test_id,text,qtype,a,b,c,d,answer) VALUES(?,?,?,?,?,?,?,?)", (t,) + qq)
    if not con.execute("SELECT 1 FROM courses").fetchone():
        for c in CURATED:
            con.execute("INSERT INTO courses(title,provider,category,level,language,url,description,certificate,note,created) VALUES(?,?,?,?,?,?,?,?,?,?)", c + (now(),))

# ---------------------------------------------------------------- helpers / security
def setting(key, default=""):
    r = q("SELECT value FROM settings WHERE key=?", (key,), one=True)
    return r["value"] if r else default

def current_user():
    if "_user" not in g:
        u = q("SELECT * FROM users WHERE id=?", (session["uid"],), one=True) if "uid" in session else None
        if u and u["role"] == "company":
            c = q("SELECT status FROM companies WHERE id=?", (u["company_id"],), one=True)
            if not c or c["status"] != "approved":
                session.clear(); u = None
        g._user = u
    return g._user

def cid():
    u = current_user()
    return u["company_id"] if u and u["role"] == "company" else None

def scope(alias="i"):
    c = cid()
    return (f" AND {alias}.company_id=?", [c]) if c else ("", [])

@app.context_processor
def inject():
    u = current_user(); unread = 0; mine = {}
    if u and u["role"] == "student":
        unread = n("SELECT COUNT(*) FROM notifications WHERE user_id=? AND is_read=0", (u["id"],))
        mine = {r["internship_id"]: r["status"] for r in q("SELECT internship_id,status FROM applications WHERE user_id=?", (u["id"],))}
    comp = q("SELECT * FROM companies WHERE id=?", (u["company_id"],), one=True) if u and u["role"] == "company" else None
    return dict(me=u, unread=unread, asset=asset, my_apps=mine, my_company=comp, demo=DEMO,
                course_categories=COURSE_CATEGORIES, course_levels=COURSE_LEVELS, course_langs=COURSE_LANGS, certs=CERTS,
                support=setting("contact_email"), portal_name=setting("portal_name", "Connect"), statuses=STATUSES)

def login_required(*roles):
    def deco(f):
        @wraps(f)
        def wrapper(*a, **kw):
            u = current_user()
            if not u:
                flash("Please login first.", "error")
                return redirect(url_for("login"))
            if roles and u["role"] not in roles:
                abort(403)
            return f(*a, **kw)
        return wrapper
    return deco

def ensure_alias(u):
    """Every user gets a short login alias on first login (so alias + password works from then on)."""
    if u["alias"]:
        return u["alias"]
    base = re.sub(r"[^a-z0-9_.]", "", ((u["name"] or u["email"].split("@")[0]).lower().replace(" ", "_")))[:14]
    if len(base) < 3:
        base = (base + "user")[:14]
    alias = base
    while q("SELECT 1 FROM users WHERE alias=?", (alias,), one=True):
        alias = f"{base}{secrets.randbelow(900) + 100}"
    run("UPDATE users SET alias=? WHERE id=?", (alias, u["id"]))
    return alias

def _asset_version():
    """Changes whenever css/js/logo change, so browsers (and Nginx's 7-day cache) fetch the new files."""
    h = hashlib.md5()
    for name in ("style.css", "app.js", "proctor.js", "logo.png"):
        p = os.path.join(BASE, "static", name)
        if os.path.exists(p):
            h.update(open(p, "rb").read())
    return h.hexdigest()[:8]

ASSET_V = _asset_version()

def asset(name):
    return url_for("static", filename=name, v=ASSET_V)

def csrf_token():
    if "_csrf" not in session:
        session["_csrf"] = secrets.token_hex(16)
    return session["_csrf"]

@app.before_request
def csrf_protect():
    if request.method == "POST":
        tok = session.get("_csrf", "")
        if not tok or not secrets.compare_digest(tok, request.form.get("_csrf", "")):
            abort(400)

@app.after_request
def inject_csrf(resp):
    if resp.mimetype == "text/html" and not resp.direct_passthrough:
        html = resp.get_data(as_text=True)
        html = re.sub(r'(<form\b[^>]*\bmethod=["\']post["\'][^>]*>)',
                      r'\1<input type="hidden" name="_csrf" value="%s">' % csrf_token(), html, flags=re.I)
        resp.set_data(html)
    resp.headers.setdefault("X-Content-Type-Options", "nosniff")
    resp.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
    return resp

def back(default):
    r = request.referrer
    return r if r and urllib.parse.urlparse(r).netloc == request.host else url_for(default)

FAILS = {}
def too_many(key):
    FAILS[key] = [t for t in FAILS.get(key, []) if t > time.time() - 600]
    return len(FAILS[key]) >= 8

def send_email(to, subject, body):
    """Real email if SMTP_* env vars are set, otherwise printed to console."""
    host = os.environ.get("SMTP_HOST")
    if not host:
        print(f"[EMAIL - console mode] To: {to} | {subject}\n{body}\n"); return
    try:
        msg = EmailMessage(); msg["From"] = os.environ.get("SMTP_USER"); msg["To"] = to; msg["Subject"] = subject
        msg.set_content(body)
        port = int(os.environ.get("SMTP_PORT", 587))
        with (smtplib.SMTP_SSL(host, port) if port == 465 else smtplib.SMTP(host, port)) as s:
            if port != 465:
                s.starttls()
            s.login(os.environ["SMTP_USER"], os.environ["SMTP_PASS"]); s.send_message(msg)
    except Exception as e:
        print("Email failed:", e)

def notify(user_id, message, subject="Update"):
    run("INSERT INTO notifications(user_id,message,created) VALUES(?,?,?)", (user_id, message, now()))
    u = q("SELECT email,email_updates FROM users WHERE id=?", (user_id,), one=True)
    if u and u["email_updates"]:
        send_email(u["email"], f"{setting('portal_name')} - {subject}", message)

def store_file(fs, name):
    """Save an uploaded file: S3 on AWS, local folder when testing."""
    if S3_BUCKET:
        s3.upload_fileobj(fs.stream, S3_BUCKET, "uploads/" + name,
                          ExtraArgs={"ContentType": mimetypes.guess_type(name)[0] or "application/octet-stream", "ServerSideEncryption": "AES256"})
    else:
        fs.save(os.path.join(UPLOAD_DIR, name))

def delete_file(name):
    if not name:
        return
    if S3_BUCKET:
        try:
            s3.delete_object(Bucket=S3_BUCKET, Key="uploads/" + name)
        except Exception:
            pass
    elif os.path.exists(os.path.join(UPLOAD_DIR, name)):
        os.remove(os.path.join(UPLOAD_DIR, name))

def serve_file(name):
    if S3_BUCKET:
        try:
            obj = s3.get_object(Bucket=S3_BUCKET, Key="uploads/" + name)
        except ClientError:
            abort(404)
        return Response(obj["Body"].iter_chunks(65536), mimetype=mimetypes.guess_type(name)[0] or "application/octet-stream",
                        headers={"Content-Length": str(obj["ContentLength"]), "Cache-Control": "private, max-age=300"})
    return send_from_directory(UPLOAD_DIR, name)

ALLOWED_IMG = (".png", ".jpg", ".jpeg", ".webp", ".gif")

def clean_url(u):
    u = (u or "").strip()
    return "" if not u else (u if re.match(r"^https?://", u, re.I) else "https://" + u)

def update_identity(uid, form, files):
    """Saves alias (short username) + profile photo. Returns an error text or None."""
    alias = form.get("alias", "").strip().lstrip("@").lower()
    if alias:
        if not re.fullmatch(r"[a-z0-9_.]{3,20}", alias):
            return "Alias must be 3-20 characters: letters, numbers, _ or . only."
        if q("SELECT 1 FROM users WHERE alias=? AND id<>?", (alias, uid), one=True):
            return "This alias is already taken. Try another."
    run("UPDATE users SET alias=? WHERE id=?", (alias or None, uid))
    old = q("SELECT photo FROM users WHERE id=?", (uid,), one=True)["photo"]
    def drop_old():
        delete_file(old)
    f = files.get("photo")
    if f and f.filename:
        ext = os.path.splitext(f.filename)[1].lower()
        if ext not in ALLOWED_IMG:
            return "Photo must be PNG, JPG, WEBP or GIF."
        name = f"avatar_{uid}_{secrets.token_hex(4)}{ext}"
        store_file(f, name)
        run("UPDATE users SET photo=? WHERE id=?", (name, uid)); drop_old()
    elif form.get("remove_photo"):
        run("UPDATE users SET photo=NULL WHERE id=?", (uid,)); drop_old()
    return None

@app.route("/health")
def health():
    return "ok"                                   # load balancer check for the app tier

@app.route("/health/db")
def health_db():
    try:
        n("SELECT 1")
        return "ok"
    except Exception:
        return "database not reachable", 500

@app.route("/avatar/<int:uid>")
def avatar(uid):
    r = q("SELECT photo FROM users WHERE id=?", (uid,), one=True)
    if not r or not r["photo"]:
        abort(404)
    return serve_file(r["photo"])

def applied_to_company(student_id, company_id):
    return bool(q("SELECT 1 FROM applications a JOIN internships i ON i.id=a.internship_id WHERE a.user_id=? AND i.company_id=?",
                  (student_id, company_id), one=True))

def own_internship(iid):
    it = q("SELECT * FROM internships WHERE id=?", (iid,), one=True) or abort(404)
    if cid() and it["company_id"] != cid():
        abort(403)
    return it

def own_test(tid):
    t = q("SELECT t.*, i.company_id, i.title ititle FROM tests t JOIN internships i ON i.id=t.internship_id WHERE t.id=?", (tid,), one=True) or abort(404)
    if cid() and t["company_id"] != cid():
        abort(403)
    return t

def delete_test(tid):
    run("DELETE FROM answers WHERE attempt_id IN (SELECT id FROM attempts WHERE test_id=?)", (tid,))
    for t in ("attempts", "questions"):
        run(f"DELETE FROM {t} WHERE test_id=?", (tid,))
    run("DELETE FROM tests WHERE id=?", (tid,))

# ---------------------------------------------------------------- public pages
@app.route("/")
def index():
    base = "SELECT i.* FROM internships i JOIN companies c ON c.id=i.company_id WHERE c.status='approved' AND i.kind=? ORDER BY i.id DESC LIMIT 3"
    stats = {"internships": n("SELECT COUNT(*) FROM internships WHERE kind='internship'"), "jobs": n("SELECT COUNT(*) FROM internships WHERE kind='job'"),
             "companies": n("SELECT COUNT(*) FROM companies WHERE status='approved'"), "students": n("SELECT COUNT(*) FROM users WHERE role='student'")}
    cats = [r["category"] for r in q("SELECT DISTINCT category FROM internships")]
    return render_template("index.html", latest_i=q(base, ("internship",)), latest_j=q(base, ("job",)), stats=stats, cats=cats)

def listing(kind):
    f = request.args
    sql = "SELECT i.* FROM internships i JOIN companies c ON c.id=i.company_id WHERE c.status='approved' AND i.kind=?"
    args = [kind]
    if f.get("q", "").strip():
        sql += " AND (i.title LIKE ? OR i.company LIKE ? OR i.description LIKE ?)"; args += [f"%{f['q'].strip()}%"] * 3
    if f.get("category"): sql += " AND i.category=?"; args.append(f["category"])
    if f.get("type"): sql += " AND i.type=?"; args.append(f["type"])
    if f.get("company"): sql += " AND i.company_id=?"; args.append(f["company"])
    if f.get("location", "").strip(): sql += " AND i.location LIKE ?"; args.append(f"%{f['location'].strip()}%")
    rows = q(sql + " ORDER BY i.id DESC", args)
    cats = [r["category"] for r in q("SELECT DISTINCT category FROM internships WHERE kind=?", (kind,))]
    comps = q("SELECT id,name FROM companies WHERE status='approved' ORDER BY name")
    return render_template("internships.html", rows=rows, cats=cats, comps=comps, f=f, kind=kind)

@app.route("/internships")
def internships():
    return listing("internship")

@app.route("/jobs")
def jobs():
    return listing("job")

@app.route("/internship/<int:iid>")
def internship_detail(iid):
    it = q("SELECT * FROM internships WHERE id=?", (iid,), one=True) or abort(404)
    want = "job_detail" if it["kind"] == "job" else "internship_detail"
    if request.endpoint != want:
        return redirect(url_for(want, iid=iid))
    comp = q("SELECT * FROM companies WHERE id=?", (it["company_id"],), one=True)
    u = current_user(); saved = False; tests = []
    if u and u["role"] == "student":
        saved = bool(q("SELECT 1 FROM saved WHERE user_id=? AND internship_id=?", (u["id"], iid), one=True))
        if iid in {r["internship_id"] for r in q("SELECT internship_id FROM applications WHERE user_id=?", (u["id"],))}:
            tests = q("SELECT id,title FROM tests WHERE internship_id=?", (iid,))
    return render_template("internship_detail.html", it=it, comp=comp, saved=saved, tests=tests,
                           open_=setting("applications_open") == "yes")

@app.route("/about")
def about():
    return render_template("about.html")

@app.route("/contact", methods=["GET", "POST"])
def contact():
    if request.method == "POST":
        run("INSERT INTO messages(name,email,message,created) VALUES(?,?,?,?)",
            (request.form["name"][:100], request.form["email"][:120], request.form["message"][:2000], now()))
        flash("Message sent. Our team will contact you soon.", "success")
        return redirect(url_for("contact"))
    return render_template("contact.html")

# ---------------------------------------------------------------- auth
@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        f = request.form
        if len(f["password"]) < MIN_PW:
            flash(f"Password must be at least {MIN_PW} characters.", "error")
        elif q("SELECT 1 FROM users WHERE email=?", (f["email"].strip().lower(),), one=True):
            flash("Email already registered.", "error")
        else:
            run("INSERT INTO users(name,email,password,role,college,course,created) VALUES(?,?,?,?,?,?,?)",
                (f["name"].strip(), f["email"].strip().lower(), generate_password_hash(f["password"]), "student",
                 f.get("college"), f.get("course"), now()))
            flash("Registration successful! Please login.", "success")
            return redirect(url_for("login"))
    return render_template("register.html")

@app.route("/company/register", methods=["GET", "POST"])
def company_register():
    if request.method == "POST":
        f = request.form; email = f["email"].strip().lower()
        if len(f["password"]) < MIN_PW:
            flash(f"Password must be at least {MIN_PW} characters.", "error")
        elif q("SELECT 1 FROM users WHERE email=?", (email,), one=True):
            flash("Email already registered.", "error")
        else:
            c = run("INSERT INTO companies(name,website,description,status,created) VALUES(?,?,?,?,?)",
                    (f["company_name"].strip(), clean_url(f.get("website")), f.get("description", ""), "pending", now()))
            run("INSERT INTO users(name,email,password,role,company_id,created) VALUES(?,?,?,?,?,?)",
                (f["name"].strip(), email, generate_password_hash(f["password"]), "company", c, now()))
            flash("Company registered! You can login once PremTech approves your account.", "success")
            return redirect(url_for("login"))
    return render_template("company_register.html")

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        ident = request.form["email"].strip().lower().lstrip("@")
        key = f"{request.remote_addr}|{ident}"
        if too_many(key):
            flash("Too many failed attempts. Try again in 10 minutes.", "error")
            return render_template("login.html")
        u = q("SELECT * FROM users WHERE email=? OR alias=?", (ident, ident), one=True)
        if u and check_password_hash(u["password"], request.form["password"]):
            if u["role"] == "company":
                c = q("SELECT status FROM companies WHERE id=?", (u["company_id"],), one=True)
                if not c or c["status"] != "approved":
                    flash("Your company account is " + ("awaiting PremTech approval." if c and c["status"] == "pending" else "not active."), "error")
                    return render_template("login.html")
            session.clear(); session["uid"] = u["id"]; session.permanent = bool(request.form.get("remember"))
            alias = ensure_alias(u)
            if not u["alias"]:
                flash(f"Your login alias is @{alias}. From now on you can login with your email OR @{alias} + password. (Change it anytime in your profile.)", "success")
            return redirect(url_for("dashboard" if u["role"] == "student" else "admin_dashboard"))
        FAILS.setdefault(key, []).append(time.time())
        flash("Invalid email/alias or password.", "error")
    return render_template("login.html")

@app.route("/logout")
def logout():
    session.clear()
    flash("Logged out.", "success")
    return redirect(url_for("index"))

# ---------------------------------------------------------------- student portal
@app.route("/dashboard")
@login_required("student")
def dashboard():
    u = current_user(); uid = u["id"]
    stats = {"applied": n("SELECT COUNT(*) FROM applications WHERE user_id=?", (uid,)),
             "saved": n("SELECT COUNT(*) FROM saved WHERE user_id=?", (uid,)),
             "shortlisted": n("SELECT COUNT(*) FROM applications WHERE user_id=? AND status IN ('Shortlisted','Accepted')", (uid,)),
             "tasks": n("SELECT COUNT(*) FROM tests t JOIN applications a ON a.internship_id=t.internship_id WHERE a.user_id=? AND t.id NOT IN (SELECT test_id FROM attempts WHERE user_id=? AND submitted_at IS NOT NULL)", (uid, uid))}
    recent = q("SELECT a.*, i.title, i.company, i.kind FROM applications a JOIN internships i ON i.id=a.internship_id WHERE a.user_id=? ORDER BY a.id DESC LIMIT 5", (uid,))
    parts = [u["phone"], u["college"], u["course"], u["skills"], u["about"], u["resume"], u["photo"]]
    complete = int(100 * sum(1 for p in parts if p) / len(parts))
    return render_template("student/dashboard.html", stats=stats, recent=recent, complete=complete)

@app.route("/profile", methods=["GET", "POST"])
@login_required("student")
def profile():
    uid = session["uid"]
    if request.method == "POST":
        f = request.form
        run("UPDATE users SET name=?,phone=?,college=?,course=?,skills=?,about=? WHERE id=?",
            (f["name"], f["phone"], f["college"], f["course"], f["skills"], f["about"], uid))
        file = request.files.get("resume")
        if file and file.filename:
            if not file.filename.lower().endswith((".pdf", ".doc", ".docx")):
                flash("Resume must be PDF/DOC/DOCX.", "error"); return redirect(url_for("profile"))
            name = f"resume_{uid}_{secrets.token_hex(3)}_{secure_filename(file.filename)}"
            store_file(file, name)
            run("UPDATE users SET resume=? WHERE id=?", (name, uid))
        err = update_identity(uid, f, request.files)
        flash(err or "Profile updated.", "error" if err else "success")
        return redirect(url_for("profile"))
    return render_template("student/profile.html")

@app.route("/resume/<int:uid>")
@login_required()
def resume(uid):
    u = current_user()
    if u["role"] == "student" and u["id"] != uid:
        abort(403)
    r = q("SELECT resume, portfolio_public FROM users WHERE id=?", (uid,), one=True)
    if u["role"] == "company" and not (applied_to_company(uid, u["company_id"]) or (r and r["portfolio_public"])):
        abort(403)
    if not r or not r["resume"]:
        abort(404)
    return serve_file(r["resume"])

@app.route("/save/<int:iid>", methods=["POST"])
@login_required("student")
def save(iid):
    uid = session["uid"]
    if q("SELECT 1 FROM saved WHERE user_id=? AND internship_id=?", (uid, iid), one=True):
        run("DELETE FROM saved WHERE user_id=? AND internship_id=?", (uid, iid)); flash("Removed from saved.", "success")
    else:
        run("INSERT INTO saved VALUES(?,?)", (uid, iid)); flash("Internship saved.", "success")
    return redirect(back("saved_list"))

@app.route("/saved")
@login_required("student")
def saved_list():
    rows = q("SELECT i.* FROM internships i JOIN saved s ON s.internship_id=i.id WHERE s.user_id=?", (session["uid"],))
    return render_template("student/saved.html", rows=rows)

@app.route("/apply/<int:iid>", methods=["POST"])
@login_required("student")
def apply(iid):
    u = current_user(); it = q("SELECT title FROM internships WHERE id=?", (iid,), one=True) or abort(404)
    if setting("applications_open") != "yes":
        flash("Applications are currently closed.", "error")
    elif not u["resume"]:
        flash("Please upload your resume in your profile before applying.", "error")
        return redirect(url_for("profile"))
    elif q("SELECT 1 FROM applications WHERE user_id=? AND internship_id=?", (u["id"], iid), one=True):
        flash("You have already applied for this internship.", "error")
    else:
        run("INSERT INTO applications(user_id,internship_id,cover,applied_at) VALUES(?,?,?,?)",
            (u["id"], iid, request.form.get("cover", "")[:2000], now()))
        has_tests = n("SELECT COUNT(*) FROM tests WHERE internship_id=?", (iid,))
        notify(u["id"], f"Your application for '{it['title']}' was submitted." + (" Please complete the task in your Tasks section." if has_tests else ""), "Application submitted")
        flash("Application submitted!" + (" A task is waiting for you in the Tasks section." if has_tests else ""), "success")
    return redirect(url_for("internship_detail", iid=iid))

@app.route("/applications")
@login_required("student")
def my_applications():
    rows = q("SELECT a.*, i.title, i.company, i.kind FROM applications a JOIN internships i ON i.id=a.internship_id WHERE a.user_id=? ORDER BY a.id DESC", (session["uid"],))
    return render_template("student/applications.html", rows=rows)

@app.route("/notifications")
@login_required("student")
def notifications():
    rows = q("SELECT * FROM notifications WHERE user_id=? ORDER BY id DESC", (session["uid"],))
    run("UPDATE notifications SET is_read=1 WHERE user_id=?", (session["uid"],))
    return render_template("student/notifications.html", rows=rows)

@app.route("/settings", methods=["GET", "POST"])
@login_required()
def user_settings():
    u = current_user()
    if request.method == "POST":
        f = request.form
        if f.get("action") == "password":
            if not check_password_hash(u["password"], f["old"]):
                flash("Current password is wrong.", "error")
            elif len(f["new"]) < MIN_PW or f["new"] != f["confirm"]:
                flash(f"New passwords must match and be {MIN_PW}+ characters.", "error")
            else:
                run("UPDATE users SET password=? WHERE id=?", (generate_password_hash(f["new"]), u["id"]))
                flash("Password changed.", "success")
        else:
            run("UPDATE users SET email_updates=? WHERE id=?", (1 if f.get("email_updates") else 0, u["id"]))
            flash("Settings saved.", "success")
        return redirect(url_for("user_settings"))
    return render_template("settings.html")

# ---------------------------------------------------------------- student tasks (aptitude tests)
def norm(s):
    return re.sub(r"\s+", " ", (s or "").strip().lower())

def is_correct(qu, resp):
    if qu["qtype"] == "text":
        return norm(resp) in {norm(x) for x in (qu["answer"] or "").split("|") if x.strip()}
    return (resp or "").strip().upper() == (qu["answer"] or "").strip().upper()

def grade(test, attempt_id, uid, form, forced=False):
    score = total = 0
    for qu in q("SELECT * FROM questions WHERE test_id=?", (test["id"],)):
        resp = (form.get(f"q{qu['id']}", "") if form else "").strip()
        ok = is_correct(qu, resp); marks = qu["marks"] or 1
        total += marks; score += marks if ok else 0
        run("INSERT INTO answers(attempt_id,question_id,response,correct) VALUES(?,?,?,?)", (attempt_id, qu["id"], resp, 1 if ok else 0))
    pct = round(score * 100 / total, 1) if total else 0
    passed = 1 if pct >= (test["pass_percent"] or 0) else 0
    run("UPDATE attempts SET score=?,total=?,percent=?,passed=?,submitted_at=?,forced=? WHERE id=?", (score, total, pct, passed, ts(), 1 if forced else 0, attempt_id))
    notify(uid, f"You scored {pct}% ({int(score)}/{int(total)}) in '{test['title']}' - {'Passed' if passed else 'Not passed'}." +
           (" The test was submitted automatically because of too many warnings." if forced else ""), "Task result")

def student_test(tid):
    u = current_user()
    return q("SELECT t.*, i.title ititle, i.company FROM tests t JOIN internships i ON i.id=t.internship_id "
             "JOIN applications a ON a.internship_id=i.id AND a.user_id=? WHERE t.id=?", (u["id"], tid), one=True) or abort(404)

@app.route("/tasks")
@login_required("student")
def tasks():
    uid = session["uid"]
    rows = q("SELECT t.*, i.title ititle, i.company, (SELECT COUNT(*) FROM questions WHERE test_id=t.id) nq, "
             "at.id aid, at.percent, at.score, at.total, at.passed, at.submitted_at FROM tests t JOIN internships i ON i.id=t.internship_id "
             "JOIN applications a ON a.internship_id=i.id AND a.user_id=? LEFT JOIN attempts at ON at.test_id=t.id AND at.user_id=? ORDER BY t.id DESC", (uid, uid))
    return render_template("student/tasks.html", rows=rows)

# ---- anti-cheat helpers ----------------------------------------------------------------------------
COUNTED = {"tab_hidden", "window_blur", "fullscreen_exit", "reload"}      # each one = 1 warning
BLOCKED = {"blocked_copy", "blocked_cut", "blocked_paste", "blocked_contextmenu", "blocked_shortcut", "blocked_back"}   # only logged

def attempt_of(tid, uid):
    return q("SELECT * FROM attempts WHERE test_id=? AND user_id=?", (tid, uid), one=True)

def seconds_left(t, at):
    elapsed = (datetime.now() - datetime.strptime(at["started_at"], "%Y-%m-%d %H:%M:%S")).total_seconds()
    return int(t["duration_min"] * 60 - elapsed)

def max_warnings(t):
    return int(t["max_violations"] if t["max_violations"] is not None else 3)

def is_strict(t):
    return t["strict"] is None or bool(t["strict"])

def draft_form(at):
    try:
        d = json.loads(at["draft"] or "{}")
        return d if isinstance(d, dict) else {}
    except ValueError:
        return {}

def finish_from_draft(t, at, uid, forced):
    """Grades what the student had answered so far (used for time over / too many warnings)."""
    fresh = attempt_of(t["id"], uid)
    if fresh and not fresh["submitted_at"]:
        grade(t, at["id"], uid, draft_form(fresh), forced=forced)

def add_log(at_id, line, counted):
    cur = q("SELECT violations, blocked, violation_log FROM attempts WHERE id=?", (at_id,), one=True)
    log = ((cur["violation_log"] or "") + f"{datetime.now().strftime('%H:%M:%S')} {line}\n")[-4000:]
    if counted:
        run("UPDATE attempts SET violations=?, violation_log=? WHERE id=?", ((cur["violations"] or 0) + 1, log, at_id))
        return (cur["violations"] or 0) + 1
    run("UPDATE attempts SET blocked=?, violation_log=? WHERE id=?", ((cur["blocked"] or 0) + 1, log, at_id))
    return cur["violations"] or 0

@app.route("/tasks/<int:tid>")
@login_required("student")
def task_start(tid):
    """Rules page. The timer does NOT start here - only after the student presses Start."""
    t = student_test(tid); uid = session["uid"]
    at = attempt_of(tid, uid)
    if at and at["submitted_at"]:
        return redirect(url_for("task_result", tid=tid))
    if at:
        return redirect(url_for("task_take", tid=tid))
    return render_template("student/task_intro.html", t=t, nq=n("SELECT COUNT(*) FROM questions WHERE test_id=?", (tid,)),
                           strict=is_strict(t), max_w=max_warnings(t))

@app.route("/tasks/<int:tid>/begin", methods=["POST"])
@login_required("student")
def task_begin(tid):
    t = student_test(tid); uid = session["uid"]
    if is_strict(t) and not request.form.get("agree"):
        flash("Please tick the box to confirm that you have read the rules.", "error")
        return redirect(url_for("task_start", tid=tid))
    if not attempt_of(tid, uid):
        try:
            run("INSERT INTO attempts(test_id,user_id,started_at) VALUES(?,?,?)", (tid, uid, ts()))
        except Exception:                      # double click / two tabs: the attempt already exists
            pass
    return redirect(url_for("task_take", tid=tid))

@app.route("/tasks/<int:tid>/take")
@login_required("student")
def task_take(tid):
    t = student_test(tid); uid = session["uid"]
    at = attempt_of(tid, uid)
    if not at:
        return redirect(url_for("task_start", tid=tid))
    if at["submitted_at"]:
        return redirect(url_for("task_result", tid=tid))
    if seconds_left(t, at) <= 0:                         # time over -> grade the saved answers
        finish_from_draft(t, at, uid, forced=False)
        return redirect(url_for("task_result", tid=tid))
    loads = (at["loads"] or 0) + 1
    run("UPDATE attempts SET loads=? WHERE id=?", (loads, at["id"]))
    warnings = at["violations"] or 0
    if is_strict(t) and loads > 1:                       # page was refreshed / reopened = 1 warning
        warnings = add_log(at["id"], "reload (page refreshed or reopened)", True)
        if warnings >= max_warnings(t):
            finish_from_draft(t, at, uid, forced=True)
            return redirect(url_for("task_result", tid=tid))
    qs = q("SELECT id,text,qtype,a,b,c,d FROM questions WHERE test_id=? ORDER BY id", (tid,))   # answers never sent
    return render_template("student/task_take.html", t=t, qs=qs, remaining=seconds_left(t, at), strict=is_strict(t),
                           max_w=max_warnings(t), warnings=warnings, draft=draft_form(at))

@app.route("/tasks/<int:tid>", methods=["POST"])
@login_required("student")
def task_submit(tid):
    t = student_test(tid); uid = session["uid"]
    at = attempt_of(tid, uid)
    if not at:
        return redirect(url_for("task_start", tid=tid))
    if at["submitted_at"]:
        return redirect(url_for("task_result", tid=tid))
    if seconds_left(t, at) < -20:                        # submitted long after the time limit: only the answers saved in time count
        finish_from_draft(t, at, uid, forced=False)
    else:
        grade(t, at["id"], uid, request.form)
    return redirect(url_for("task_result", tid=tid))

@app.route("/tasks/<int:tid>/event", methods=["POST"])
@login_required("student")
def task_event(tid):
    """Receives the autosave + the 'student left the page' signals from the test page."""
    t = student_test(tid); uid = session["uid"]
    at = attempt_of(tid, uid)
    done = jsonify(ended=True, url=url_for("task_result", tid=tid))
    if not at or at["submitted_at"]:
        return done
    raw = request.form.get("draft", "")
    if raw and len(raw) < 20000:
        try:
            d = json.loads(raw)
            if isinstance(d, dict):
                run("UPDATE attempts SET draft=? WHERE id=?", (json.dumps({k: str(v)[:500] for k, v in d.items() if str(k).startswith("q")}), at["id"]))
        except ValueError:
            pass
    if seconds_left(t, at) <= 0:
        finish_from_draft(t, at, uid, forced=False)
        return done
    kind = request.form.get("type", "")[:30]
    warnings = at["violations"] or 0
    if is_strict(t) and kind in COUNTED:
        warnings = add_log(at["id"], kind, True)
        if warnings >= max_warnings(t):
            finish_from_draft(t, at, uid, forced=True)
            return done
    elif is_strict(t) and kind in BLOCKED:
        add_log(at["id"], kind, False)
    return jsonify(ended=False, warnings=warnings, max=max_warnings(t))

@app.route("/tasks/<int:tid>/result")
@login_required("student")
def task_result(tid):
    t = student_test(tid)
    at = q("SELECT * FROM attempts WHERE test_id=? AND user_id=? AND submitted_at IS NOT NULL", (tid, session["uid"]), one=True)
    if not at:
        return redirect(url_for("task_start", tid=tid))
    return render_template("student/task_result.html", t=t, at=at)

# ---------------------------------------------------------------- staff panel (owner + company admins)
@app.route("/admin")
@login_required(*STAFF)
def admin_dashboard():
    sc, sa = scope(); u = current_user()
    apps_ = n(f"SELECT COUNT(*) FROM applications a JOIN internships i ON i.id=a.internship_id WHERE 1=1{sc}", sa)
    pending = n(f"SELECT COUNT(*) FROM applications a JOIN internships i ON i.id=a.internship_id WHERE a.status='Pending'{sc}", sa)
    tests_ = n(f"SELECT COUNT(*) FROM tests t JOIN internships i ON i.id=t.internship_id WHERE 1=1{sc}", sa)
    ints = n(f"SELECT COUNT(*) FROM internships i WHERE i.kind='internship'{sc}", sa)
    jobs_ = n(f"SELECT COUNT(*) FROM internships i WHERE i.kind='job'{sc}", sa)
    courses_ = n("SELECT COUNT(*) FROM courses WHERE company_id=?", (cid(),)) if cid() else n("SELECT COUNT(*) FROM courses")
    if u["role"] == "owner":
        cards = [("Companies", n("SELECT COUNT(*) FROM companies WHERE status='approved'"), "briefcase"),
                 ("Awaiting approval", n("SELECT COUNT(*) FROM companies WHERE status='pending'"), "clock"),
                 ("Students", n("SELECT COUNT(*) FROM users WHERE role='student'"), "users"),
                 ("Internships", ints, "grid"), ("Jobs", jobs_, "briefcase"), ("Courses", courses_, "bookmark"), ("Applications", apps_, "file"), ("Tests", tests_, "check")]
    else:
        studs = n(f"SELECT COUNT(DISTINCT a.user_id) FROM applications a JOIN internships i ON i.id=a.internship_id WHERE 1=1{sc}", sa)
        cards = [("Internships", ints, "grid"), ("Jobs", jobs_, "briefcase"), ("Courses", courses_, "bookmark"), ("Applicants", studs, "users"), ("Applications", apps_, "file"),
                 ("Pending", pending, "clock"), ("Tests", tests_, "check")]
    by_status = {s: n(f"SELECT COUNT(*) FROM applications a JOIN internships i ON i.id=a.internship_id WHERE a.status=?{sc}", [s] + sa) for s in STATUSES}
    recent = q(f"SELECT a.*, u.name, i.title, i.company FROM applications a JOIN users u ON u.id=a.user_id JOIN internships i ON i.id=a.internship_id WHERE 1=1{sc} ORDER BY a.id DESC LIMIT 6", sa)
    return render_template("admin/dashboard.html", cards=cards, recent=recent, by_status=by_status, top=max(by_status.values()) or 1)

def admin_list(kind):
    sc, sa = scope()
    rows = q("SELECT i.*, (SELECT COUNT(*) FROM applications WHERE internship_id=i.id) napps, (SELECT COUNT(*) FROM tests WHERE internship_id=i.id) ntests "
             f"FROM internships i WHERE i.kind=?{sc} ORDER BY i.id DESC", [kind] + sa)
    return render_template("admin/internships.html", rows=rows, kind=kind)

@app.route("/admin/internships")
@login_required(*STAFF)
def admin_internships():
    return admin_list("internship")

@app.route("/admin/jobs")
@login_required(*STAFF)
def admin_jobs():
    return admin_list("job")

FIELDS = ["title", "location", "category", "type", "stipend", "duration", "deadline", "description", "requirements", "apply_url"]

@app.route("/admin/internships/new", methods=["GET", "POST"])
@app.route("/admin/internships/<int:iid>/edit", methods=["GET", "POST"])
@login_required(*STAFF)
def admin_internship_form(iid=None):
    return listing_form(iid, "internship")

@app.route("/admin/jobs/new", methods=["GET", "POST"])
@app.route("/admin/jobs/<int:iid>/edit", methods=["GET", "POST"])
@login_required(*STAFF)
def admin_job_form(iid=None):
    return listing_form(iid, "job")

def listing_form(iid, kind):
    it = own_internship(iid) if iid else None
    if it:
        kind = it["kind"] or "internship"
    back_ep = "admin_jobs" if kind == "job" else "admin_internships"
    comps = q("SELECT id,name FROM companies WHERE status='approved' ORDER BY name")
    if request.method == "POST":
        vals = [request.form.get(k, "").strip() for k in FIELDS]
        vals[FIELDS.index("apply_url")] = clean_url(vals[FIELDS.index("apply_url")])
        company_id = cid() or int(request.form.get("company_id") or 0)
        co = q("SELECT * FROM companies WHERE id=?", (company_id,), one=True)
        if not co:
            flash("Please select a company.", "error"); return redirect(request.url)
        if it:
            run("UPDATE internships SET " + ",".join(f"{k}=?" for k in FIELDS) + ",company=?,company_id=? WHERE id=?", vals + [co["name"], co["id"], iid])
            flash("Updated successfully.", "success")
        else:
            run("INSERT INTO internships(" + ",".join(FIELDS) + ",company,company_id,kind,created) VALUES(" + ",".join("?" * (len(FIELDS) + 4)) + ")",
                vals + [co["name"], co["id"], kind, now()])
            flash("Job posted." if kind == "job" else "Internship created.", "success")
        return redirect(url_for(back_ep))
    return render_template("admin/internship_form.html", it=it, comps=comps, kind=kind)

@app.route("/admin/internships/<int:iid>/delete", methods=["POST"])
@login_required(*STAFF)
def admin_internship_delete(iid):
    it = own_internship(iid)
    for t in q("SELECT id FROM tests WHERE internship_id=?", (iid,)):
        delete_test(t["id"])
    for t in ("applications", "saved"):
        run(f"DELETE FROM {t} WHERE internship_id=?", (iid,))
    run("DELETE FROM internships WHERE id=?", (iid,))
    flash("Deleted.", "success")
    return redirect(url_for("admin_jobs" if it["kind"] == "job" else "admin_internships"))

def applied_filter():
    c = cid()
    return (" AND EXISTS(SELECT 1 FROM applications a JOIN internships i ON i.id=a.internship_id WHERE a.user_id=u.id AND i.company_id=?)", [c]) if c else ("", [])

@app.route("/admin/students")
@login_required(*STAFF)
def admin_students():
    sc, sa = scope(); af, aa = applied_filter()
    rows = q("SELECT u.*, (SELECT GROUP_CONCAT(DISTINCT i.company) FROM applications a JOIN internships i ON i.id=a.internship_id "
             f"WHERE a.user_id=u.id{sc}) applied_to FROM users u WHERE u.role='student'{af} ORDER BY u.id DESC", sa + aa)
    return render_template("admin/students.html", rows=rows)

@app.route("/admin/students/<int:uid>")
@login_required(*STAFF)
def admin_student_detail(uid):
    s = q("SELECT * FROM users WHERE id=? AND role='student'", (uid,), one=True) or abort(404)
    if cid() and not applied_to_company(uid, cid()):
        abort(403)
    sc, sa = scope()
    apps_ = q("SELECT a.*, i.title, i.company, (SELECT MAX(at.percent) FROM attempts at JOIN tests t ON t.id=at.test_id WHERE at.user_id=a.user_id "
              f"AND t.internship_id=a.internship_id AND at.submitted_at IS NOT NULL) score FROM applications a JOIN internships i ON i.id=a.internship_id WHERE a.user_id=?{sc}", [uid] + sa)
    return render_template("admin/student_detail.html", s=s, apps=apps_)

@app.route("/admin/students/<int:uid>/delete", methods=["POST"])
@login_required("owner")
def admin_student_delete(uid):
    run("DELETE FROM answers WHERE attempt_id IN (SELECT id FROM attempts WHERE user_id=?)", (uid,))
    for t in ("attempts", "applications", "saved", "notifications", "certificates", "projects"):
        run(f"DELETE FROM {t} WHERE user_id=?", (uid,))
    run("DELETE FROM users WHERE id=? AND role='student'", (uid,))
    flash("Student removed.", "success")
    return redirect(url_for("admin_students"))

@app.route("/admin/applications")
@login_required(*STAFF)
def admin_applications():
    sc, sa = scope(); st = request.args.get("status", ""); co = request.args.get("company", "")
    sql = ("SELECT a.*, u.name, u.email, u.alias, u.photo, i.title, i.company, (SELECT MAX(at.percent) FROM attempts at JOIN tests t ON t.id=at.test_id "
           "WHERE at.user_id=a.user_id AND t.internship_id=a.internship_id AND at.submitted_at IS NOT NULL) score "
           "FROM applications a JOIN users u ON u.id=a.user_id JOIN internships i ON i.id=a.internship_id WHERE 1=1" + sc)
    args = list(sa)
    if st: sql += " AND a.status=?"; args.append(st)
    if co and not cid(): sql += " AND i.company_id=?"; args.append(co)
    comps = q("SELECT id,name FROM companies ORDER BY name") if not cid() else []
    return render_template("admin/applications.html", rows=q(sql + " ORDER BY a.id DESC", args), st=st, co=co, comps=comps)

@app.route("/admin/applications/<int:aid>/status", methods=["POST"])
@login_required(*STAFF)
def admin_update_status(aid):
    a = q("SELECT a.*, i.title, i.company_id FROM applications a JOIN internships i ON i.id=a.internship_id WHERE a.id=?", (aid,), one=True) or abort(404)
    if cid() and a["company_id"] != cid():
        abort(403)
    status = request.form["status"]
    if status in STATUSES:
        run("UPDATE applications SET status=? WHERE id=?", (status, aid))
        notify(a["user_id"], f"Your application for '{a['title']}' is now: {status}.", f"Application {status}")
        flash("Status updated and student notified.", "success")
    return redirect(back("admin_applications"))

# ---- tests / tasks
@app.route("/admin/tests")
@login_required(*STAFF)
def admin_tests():
    sc, sa = scope()
    rows = q("SELECT t.*, i.title ititle, i.company, (SELECT COUNT(*) FROM questions WHERE test_id=t.id) nq, "
             "(SELECT COUNT(*) FROM attempts WHERE test_id=t.id AND submitted_at IS NOT NULL) natt, "
             f"(SELECT ROUND(AVG(percent),1) FROM attempts WHERE test_id=t.id AND submitted_at IS NOT NULL) avg FROM tests t JOIN internships i ON i.id=t.internship_id WHERE 1=1{sc} ORDER BY t.id DESC", sa)
    return render_template("admin/tests.html", rows=rows)

@app.route("/admin/tests/new", methods=["GET", "POST"])
@app.route("/admin/tests/<int:tid>/edit", methods=["GET", "POST"])
@login_required(*STAFF)
def admin_test_form(tid=None):
    t = own_test(tid) if tid else None
    sc, sa = scope()
    ints = q(f"SELECT i.id,i.title,i.company,i.kind FROM internships i WHERE 1=1{sc} ORDER BY i.id DESC", sa)
    has_attempts = bool(t and n("SELECT COUNT(*) FROM attempts WHERE test_id=?", (tid,)))
    if request.method == "POST":
        f = request.form
        try:
            iid = int(f["internship_id"]); dur = max(1, int(f.get("duration_min") or 10)); pas = min(100, max(0, int(f.get("pass_percent") or 50)))
            strict = 1 if f.get("strict") else 0; maxv = min(10, max(1, int(f.get("max_violations") or 3)))
        except ValueError:
            flash("Please fill the numbers correctly.", "error"); return redirect(request.url)
        own_internship(iid)
        texts, types = f.getlist("qtext"), f.getlist("qtype")
        A, B, C, D = (f.getlist(k) for k in ("oa", "ob", "oc", "od")); mc, tx = f.getlist("qmc"), f.getlist("qtxt")
        qs = []
        for k, text in enumerate(texts):
            if not text.strip():
                continue
            if types[k] == "text":
                if not tx[k].strip():
                    flash(f"Question {k+1}: add the accepted answer.", "error"); return redirect(request.url)
                qs.append((text.strip(), "text", "", "", "", "", tx[k].strip()))
            else:
                opts = [A[k].strip(), B[k].strip(), C[k].strip(), D[k].strip()]
                if sum(1 for o in opts if o) < 2 or not opts["ABCD".index(mc[k])]:
                    flash(f"Question {k+1}: add at least 2 options and pick a non-empty correct option.", "error"); return redirect(request.url)
                qs.append((text.strip(), "mcq", *opts, mc[k]))
        if not t and not qs:
            flash("Add at least one question.", "error"); return redirect(request.url)
        if t:
            run("UPDATE tests SET internship_id=?,title=?,instructions=?,duration_min=?,pass_percent=?,strict=?,max_violations=? WHERE id=?", (iid, f["title"].strip(), f.get("instructions", ""), dur, pas, strict, maxv, tid))
            if has_attempts:
                flash("Test details updated. Questions are locked because students already attempted it.", "success")
            else:
                run("DELETE FROM questions WHERE test_id=?", (tid,))
        else:
            tid = run("INSERT INTO tests(internship_id,title,instructions,duration_min,pass_percent,created,strict,max_violations) VALUES(?,?,?,?,?,?,?,?)",
                      (iid, f["title"].strip(), f.get("instructions", ""), dur, pas, now(), strict, maxv))
            for s in q("SELECT user_id FROM applications WHERE internship_id=?", (iid,)):
                notify(s["user_id"], f"New task assigned: '{f['title'].strip()}'. Open the Tasks section to attempt it.", "New task")
        if not has_attempts:
            for qq in qs:
                run("INSERT INTO questions(test_id,text,qtype,a,b,c,d,answer) VALUES(?,?,?,?,?,?,?,?)", (tid,) + qq)
            flash("Test saved.", "success")
        return redirect(url_for("admin_tests"))
    qs = q("SELECT * FROM questions WHERE test_id=? ORDER BY id", (tid,)) if t else []
    return render_template("admin/test_form.html", t=t, ints=ints, qs=qs, locked=has_attempts)

@app.route("/admin/tests/<int:tid>/delete", methods=["POST"])
@login_required(*STAFF)
def admin_test_delete(tid):
    own_test(tid); delete_test(tid)
    flash("Test deleted.", "success")
    return redirect(url_for("admin_tests"))

@app.route("/admin/tests/<int:tid>/results")
@login_required(*STAFF)
def admin_test_results(tid):
    t = own_test(tid)
    rows = q("SELECT at.*, u.name, u.email, u.alias, u.photo, u.id uid FROM attempts at JOIN users u ON u.id=at.user_id WHERE at.test_id=? ORDER BY at.percent DESC", (tid,))
    return render_template("admin/test_results.html", t=t, rows=rows)

@app.route("/admin/attempts/<int:aid>")
@login_required(*STAFF)
def admin_test_attempt(aid):
    at = q("SELECT at.*, u.name, u.email FROM attempts at JOIN users u ON u.id=at.user_id WHERE at.id=?", (aid,), one=True) or abort(404)
    t = own_test(at["test_id"])
    rows = q("SELECT an.*, qu.text, qu.qtype, qu.answer, qu.a, qu.b, qu.c, qu.d FROM answers an JOIN questions qu ON qu.id=an.question_id WHERE an.attempt_id=? ORDER BY qu.id", (aid,))
    return render_template("admin/attempt.html", at=at, t=t, rows=rows)

# ---- notifications / profile
@app.route("/admin/notify", methods=["GET", "POST"])
@login_required(*STAFF)
def admin_notify():
    u = current_user()
    if request.method == "POST":
        msg = request.form["message"].strip()
        if msg:
            if u["role"] == "owner":
                ids = [r["id"] for r in q("SELECT id FROM users WHERE role='student'")]
            else:
                ids = [r["user_id"] for r in q("SELECT DISTINCT a.user_id FROM applications a JOIN internships i ON i.id=a.internship_id WHERE i.company_id=?", (u["company_id"],))]
            for sid in ids:
                notify(sid, (f"[{my_company_name()}] " if u["role"] == "company" else "") + msg, "Announcement")
            flash(f"Notification sent to {len(ids)} student(s).", "success")
        return redirect(url_for("admin_notify"))
    msgs = q("SELECT * FROM messages ORDER BY id DESC LIMIT 20") if u["role"] == "owner" else []
    return render_template("admin/notify.html", msgs=msgs)

def my_company_name():
    c = q("SELECT name FROM companies WHERE id=?", (cid(),), one=True)
    return c["name"] if c else ""

@app.route("/admin/profile", methods=["GET", "POST"])
@login_required(*STAFF)
def admin_profile():
    if request.method == "POST":
        email = request.form["email"].strip().lower()
        if q("SELECT 1 FROM users WHERE email=? AND id<>?", (email, session["uid"]), one=True):
            flash("That email is already used by another account.", "error")
            return redirect(url_for("admin_profile"))
        run("UPDATE users SET name=?, email=? WHERE id=?", (request.form["name"], email, session["uid"]))
        err = update_identity(session["uid"], request.form, request.files)
        flash(err or "Profile updated.", "error" if err else "success")
        return redirect(url_for("admin_profile"))
    return render_template("admin/profile.html")

@app.route("/admin/company", methods=["GET", "POST"])
@login_required("company")
def admin_company_profile():
    c = q("SELECT * FROM companies WHERE id=?", (cid(),), one=True)
    if request.method == "POST":
        name = request.form["name"].strip()
        run("UPDATE companies SET name=?, website=?, description=? WHERE id=?", (name, clean_url(request.form.get("website")), request.form.get("description", ""), c["id"]))
        run("UPDATE internships SET company=? WHERE company_id=?", (name, c["id"]))
        flash("Company profile updated.", "success")
        return redirect(url_for("admin_company_profile"))
    return render_template("admin/company_profile.html", c=c)

# ---------------------------------------------------------------- PremTech owner only
@app.route("/admin/companies")
@login_required("owner")
def admin_companies():
    rows = q("SELECT c.*, (SELECT COUNT(*) FROM internships WHERE company_id=c.id) ni, "
             "(SELECT COUNT(*) FROM applications a JOIN internships i ON i.id=a.internship_id WHERE i.company_id=c.id) na, "
             "(SELECT COUNT(DISTINCT a.user_id) FROM applications a JOIN internships i ON i.id=a.internship_id WHERE i.company_id=c.id) ns, "
             "(SELECT email FROM users WHERE company_id=c.id AND role='company' LIMIT 1) admin_email FROM companies c ORDER BY c.id DESC")
    return render_template("admin/companies.html", rows=rows)

@app.route("/admin/companies/new", methods=["GET", "POST"])
@login_required("owner")
def admin_company_form():
    if request.method == "POST":
        f = request.form; email = f["email"].strip().lower()
        if len(f["password"]) < MIN_PW:
            flash(f"Password must be at least {MIN_PW} characters.", "error")
        elif q("SELECT 1 FROM users WHERE email=?", (email,), one=True):
            flash("That admin email is already registered.", "error")
        else:
            c = run("INSERT INTO companies(name,website,description,status,created) VALUES(?,?,?,?,?)",
                    (f["company_name"].strip(), clean_url(f.get("website")), f.get("description", ""), "approved", now()))
            run("INSERT INTO users(name,email,password,role,company_id,created) VALUES(?,?,?,?,?,?)",
                (f["name"].strip(), email, generate_password_hash(f["password"]), "company", c, now()))
            send_email(email, f"{setting('portal_name')} - company account created", f"Your company admin account is ready. Login with {email}.")
            flash("Company and admin account created.", "success")
            return redirect(url_for("admin_companies"))
    return render_template("admin/company_form.html")

@app.route("/admin/companies/<int:cid_>/status", methods=["POST"])
@login_required("owner")
def admin_company_status(cid_):
    st = request.form["status"]
    c = q("SELECT * FROM companies WHERE id=?", (cid_,), one=True) or abort(404)
    if st in ("approved", "pending", "suspended"):
        run("UPDATE companies SET status=? WHERE id=?", (st, cid_))
        for u in q("SELECT email FROM users WHERE company_id=? AND role='company'", (cid_,)):
            send_email(u["email"], f"{setting('portal_name')} - account {st}", f"Your company '{c['name']}' is now: {st}.")
        flash(f"{c['name']} is now {st}.", "success")
    return redirect(url_for("admin_companies"))

@app.route("/admin/portal", methods=["GET", "POST"])
@login_required("owner")
def admin_portal_settings():
    if request.method == "POST":
        for k in ("portal_name", "contact_email"):
            run("INSERT OR REPLACE INTO settings VALUES(?,?)", (k, request.form[k]))
        run("INSERT OR REPLACE INTO settings VALUES('applications_open',?)", ("yes" if request.form.get("applications_open") else "no",))
        flash("Platform settings saved.", "success")
        return redirect(url_for("admin_portal_settings"))
    return render_template("admin/portal.html", s={k: setting(k) for k in ("portal_name", "contact_email", "applications_open")})

# ---------------------------------------------------------------- Student portfolio
CERT_EXT = (".pdf", ".png", ".jpg", ".jpeg", ".webp")

def social(v, domain, prefix):
    """Accepts a full link or just a username. Returns a clean link, "" if empty, None if it is not on the right website."""
    v = (v or "").strip()
    if not v:
        return ""
    if "/" not in v and "." not in v:
        name = v.lstrip("@")
        return prefix + name if re.fullmatch(r"[A-Za-z0-9_-]{1,60}", name) else None
    v = clean_url(v)
    host = (urllib.parse.urlparse(v).hostname or "").lower()
    return v if host == domain or host.endswith("." + domain) else None

def can_view_portfolio(st):
    u = current_user()
    if u["role"] == "owner" or u["id"] == st["id"]:
        return True
    if u["role"] == "company":
        return bool(st["portfolio_public"]) or applied_to_company(st["id"], u["company_id"])
    return False

@app.route("/portfolio")
@login_required("student")
def portfolio_edit():
    uid = session["uid"]
    return render_template("student/portfolio.html", certs_=q("SELECT * FROM certificates WHERE user_id=? ORDER BY id DESC", (uid,)),
                           projs=q("SELECT * FROM projects WHERE user_id=? ORDER BY id DESC", (uid,)))

@app.route("/portfolio/links", methods=["POST"])
@login_required("student")
def portfolio_links():
    f = request.form
    li = social(f.get("linkedin"), "linkedin.com", "https://www.linkedin.com/in/")
    gh = social(f.get("github"), "github.com", "https://github.com/")
    web = clean_url(f.get("website"))
    if li is None:
        flash("LinkedIn must be a linkedin.com link (or just your username).", "error")
    elif gh is None:
        flash("GitHub must be a github.com link (or just your username).", "error")
    elif web and not valid_url(web):
        flash("Website link is not valid.", "error")
    else:
        run("UPDATE users SET headline=?, linkedin=?, github=?, website=?, portfolio_public=? WHERE id=?",
            (f.get("headline", "").strip()[:100], li, gh, web, 1 if f.get("portfolio_public") else 0, session["uid"]))
        flash("Portfolio details saved.", "success")
    return redirect(url_for("portfolio_edit"))

@app.route("/portfolio/certificate", methods=["POST"])
@login_required("student")
def portfolio_cert_add():
    f = request.form; uid = session["uid"]; title = f.get("title", "").strip()
    url = clean_url(f.get("url")); file = request.files.get("file"); name = None
    if not title:
        flash("Please enter the certificate name.", "error"); return redirect(url_for("portfolio_edit"))
    if url and not valid_url(url):
        flash("Certificate link is not valid.", "error"); return redirect(url_for("portfolio_edit"))
    if file and file.filename:
        ext = os.path.splitext(file.filename)[1].lower()
        if ext not in CERT_EXT:
            flash("Certificate file must be PDF, PNG, JPG or WEBP.", "error"); return redirect(url_for("portfolio_edit"))
        name = f"cert_{uid}_{secrets.token_hex(4)}{ext}"
        store_file(file, name)
    if not url and not name:
        flash("Upload the certificate file or paste its link.", "error"); return redirect(url_for("portfolio_edit"))
    run("INSERT INTO certificates(user_id,title,issuer,issue_date,url,file,created) VALUES(?,?,?,?,?,?,?)",
        (uid, title[:120], f.get("issuer", "").strip()[:80], f.get("issue_date", "").strip()[:20], url, name, now()))
    flash("Certificate added.", "success")
    return redirect(url_for("portfolio_edit"))

@app.route("/portfolio/certificate/<int:cert_id>/delete", methods=["POST"])
@login_required("student")
def portfolio_cert_delete(cert_id):
    c = q("SELECT * FROM certificates WHERE id=? AND user_id=?", (cert_id, session["uid"]), one=True) or abort(404)
    delete_file(c["file"])
    run("DELETE FROM certificates WHERE id=?", (cert_id,))
    flash("Certificate removed.", "success")
    return redirect(url_for("portfolio_edit"))

@app.route("/cert/<int:cert_id>")
@login_required()
def cert_file(cert_id):
    c = q("SELECT * FROM certificates WHERE id=?", (cert_id,), one=True) or abort(404)
    st = q("SELECT * FROM users WHERE id=?", (c["user_id"],), one=True)
    if not st or not can_view_portfolio(st) or not c["file"]:
        abort(403 if st else 404)
    return serve_file(c["file"])

@app.route("/portfolio/project", methods=["POST"])
@login_required("student")
def portfolio_project_add():
    f = request.form; title = f.get("title", "").strip()
    repo, live = clean_url(f.get("repo_url")), clean_url(f.get("live_url"))
    if not title:
        flash("Please enter the project name.", "error")
    elif (repo and not valid_url(repo)) or (live and not valid_url(live)):
        flash("Project link is not valid.", "error")
    else:
        run("INSERT INTO projects(user_id,title,description,tech,repo_url,live_url,created) VALUES(?,?,?,?,?,?,?)",
            (session["uid"], title[:120], f.get("description", "").strip()[:800], f.get("tech", "").strip()[:150], repo, live, now()))
        flash("Project added.", "success")
    return redirect(url_for("portfolio_edit"))

@app.route("/portfolio/project/<int:pid>/delete", methods=["POST"])
@login_required("student")
def portfolio_project_delete(pid):
    q("SELECT 1 FROM projects WHERE id=? AND user_id=?", (pid, session["uid"]), one=True) or abort(404)
    run("DELETE FROM projects WHERE id=?", (pid,))
    flash("Project removed.", "success")
    return redirect(url_for("portfolio_edit"))

@app.route("/portfolio/<int:uid>")
@login_required()
def portfolio_view(uid):
    st = q("SELECT * FROM users WHERE id=? AND role='student'", (uid,), one=True) or abort(404)
    if not can_view_portfolio(st):
        abort(403)
    return render_template("portfolio_view.html", st=st, certs_=q("SELECT * FROM certificates WHERE user_id=? ORDER BY id DESC", (uid,)),
                           projs=q("SELECT * FROM projects WHERE user_id=? ORDER BY id DESC", (uid,)))

@app.route("/admin/talent")
@login_required(*STAFF)
def admin_talent():
    kw = request.args.get("q", "").strip()
    sql = ("SELECT u.*, (SELECT COUNT(*) FROM projects WHERE user_id=u.id) np, (SELECT COUNT(*) FROM certificates WHERE user_id=u.id) nc "
           "FROM users u WHERE u.role='student' AND u.portfolio_public=1")
    args = []
    if kw:
        sql += " AND (u.name LIKE ? OR u.skills LIKE ? OR u.college LIKE ? OR u.headline LIKE ? OR u.course LIKE ?)"; args = [f"%{kw}%"] * 5
    return render_template("admin/talent.html", rows=q(sql + " ORDER BY u.id DESC", args), kw=kw)

# ---------------------------------------------------------------- Study Here (free courses - links to original websites)
def _safe_host(host):
    try:
        for info in socket.getaddrinfo(host, None):
            ip = ipaddress.ip_address(info[4][0])
            if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast or ip.is_unspecified:
                return False
        return True
    except Exception:
        return False

class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k):
        return None

def fetch_title(url):
    """Reads the <title> of a web page. Blocks private/internal addresses (SSRF safe) and checks every redirect."""
    opener = urllib.request.build_opener(_NoRedirect)
    for _ in range(4):
        pr = urllib.parse.urlparse(url)
        if pr.scheme not in ("http", "https") or not pr.hostname or pr.port not in (None, 80, 443) or not _safe_host(pr.hostname):
            return None
        try:
            r = opener.open(urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (PremTech course fetcher)"}), timeout=6)
        except urllib.error.HTTPError as e:
            if e.code in (301, 302, 303, 307, 308) and e.headers.get("Location"):
                url = urllib.parse.urljoin(url, e.headers["Location"]); continue
            return None
        except Exception:
            return None
        data = r.read(200000).decode("utf-8", "ignore")
        m = re.search(r"<title[^>]*>(.*?)</title>", data, re.I | re.S)
        return htmlmod.unescape(re.sub(r"\s+", " ", m.group(1))).strip()[:150] if m else None
    return None

def valid_url(u):
    pr = urllib.parse.urlparse(u)
    return pr.scheme in ("http", "https") and "." in (pr.hostname or "")

@app.route("/study")
def study():
    f = request.args; u = current_user()
    sql = "SELECT c.*, co.name company_name FROM courses c LEFT JOIN companies co ON co.id=c.company_id WHERE c.active=1"
    args = []
    if f.get("q", "").strip():
        sql += " AND (c.title LIKE ? OR c.provider LIKE ? OR c.description LIKE ?)"; args += [f"%{f['q'].strip()}%"] * 3
    if f.get("category"): sql += " AND c.category=?"; args.append(f["category"])
    if f.get("level"): sql += " AND c.level=?"; args.append(f["level"])
    if f.get("language"): sql += " AND c.language LIKE ?"; args.append(f"%{f['language']}%")
    if f.get("cert") == "free": sql += " AND c.certificate='free'"
    if f.get("source") == "premtech": sql += " AND c.company_id IS NULL"
    if f.get("source") == "companies": sql += " AND c.company_id IS NOT NULL"
    rows = q(sql + " ORDER BY (c.company_id IS NOT NULL), c.id", args)
    tpl = "student/study.html" if u and u["role"] == "student" else "study.html"
    return render_template(tpl, rows=rows, f=f)

@app.route("/study/go/<int:cid_>")
def study_go(cid_):
    c = q("SELECT id,url FROM courses WHERE id=? AND active=1", (cid_,), one=True) or abort(404)
    run("UPDATE courses SET clicks=clicks+1 WHERE id=?", (cid_,))
    return redirect(c["url"])

def own_course(course_id):
    c = q("SELECT * FROM courses WHERE id=?", (course_id,), one=True) or abort(404)
    if cid() and c["company_id"] != cid():
        abort(403)
    return c

@app.route("/admin/courses")
@login_required(*STAFF)
def admin_courses():
    c = cid()
    rows = q("SELECT c.*, co.name company_name FROM courses c LEFT JOIN companies co ON co.id=c.company_id WHERE 1=1" + (" AND c.company_id=?" if c else "") + " ORDER BY c.id DESC", (c,) if c else ())
    return render_template("admin/courses.html", rows=rows)

@app.route("/admin/courses/new", methods=["GET", "POST"])
@app.route("/admin/courses/<int:course_id>/edit", methods=["GET", "POST"])
@login_required(*STAFF)
def admin_course_form(course_id=None):
    co = own_course(course_id) if course_id else None
    u = current_user()
    if request.method == "POST":
        f = request.form; url = clean_url(f.get("url"))
        if not valid_url(url):
            flash("Please enter a valid course link (https://...).", "error"); return redirect(request.url)
        title = f.get("title", "").strip()
        if not title and u["role"] == "owner":
            title = fetch_title(url) or ""
        if not title:
            flash("Please type the course title" + (" (could not read it from the link)." if u["role"] == "owner" else "."), "error"); return redirect(request.url)
        provider = f.get("provider", "").strip() or (my_company_name() if u["role"] == "company" else (urllib.parse.urlparse(url).hostname or "").replace("www.", ""))
        cert = f.get("certificate") if f.get("certificate") in CERTS else "free"
        vals = [title[:150], provider[:80], f.get("category") or "General Skills", f.get("level") or "All levels", f.get("language", "English")[:40], url,
                f.get("description", "")[:600], cert, f.get("note", "")[:120]]
        if co:
            run("UPDATE courses SET title=?,provider=?,category=?,level=?,language=?,url=?,description=?,certificate=?,note=? WHERE id=?", vals + [course_id])
            flash("Course updated.", "success")
        else:
            run("INSERT INTO courses(title,provider,category,level,language,url,description,certificate,note,company_id,added_by,created) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                vals + [cid(), u["id"], now()])
            flash("Course added. Students can see it in Study Here.", "success")
        return redirect(url_for("admin_courses"))
    return render_template("admin/course_form.html", co=co)

@app.route("/admin/courses/bulk", methods=["GET", "POST"])
@login_required("owner")
def admin_course_bulk():
    if request.method == "POST":
        f = request.form
        urls = []
        for line in f.get("urls", "").splitlines():
            line = clean_url(line.strip())
            if line and valid_url(line) and line not in urls:
                urls.append(line)
        urls = urls[:20]
        if not urls:
            flash("Paste at least one valid link.", "error"); return redirect(request.url)
        with ThreadPoolExecutor(max_workers=6) as ex:
            titles = list(ex.map(fetch_title, urls))
        added = skipped = 0
        cert = f.get("certificate") if f.get("certificate") in CERTS else "free"
        for url, title in zip(urls, titles):
            if q("SELECT 1 FROM courses WHERE url=? AND company_id IS NULL", (url,), one=True):
                skipped += 1; continue
            host = (urllib.parse.urlparse(url).hostname or "").replace("www.", "")
            run("INSERT INTO courses(title,provider,category,level,language,url,description,certificate,note,added_by,created) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                (title or host, host, f.get("category") or "General Skills", f.get("level") or "All levels", f.get("language", "English"), url, "", cert, "", session["uid"], now()))
            added += 1
        flash(f"{added} course(s) added" + (f", {skipped} already existed" if skipped else "") + ". You can edit titles anytime.", "success")
        return redirect(url_for("admin_courses"))
    return render_template("admin/course_bulk.html")

@app.route("/admin/courses/<int:course_id>/toggle", methods=["POST"])
@login_required(*STAFF)
def admin_course_toggle(course_id):
    c = own_course(course_id)
    run("UPDATE courses SET active=? WHERE id=?", (0 if c["active"] else 1, course_id))
    flash("Course hidden from students." if c["active"] else "Course is visible again.", "success")
    return redirect(url_for("admin_courses"))

@app.route("/admin/courses/<int:course_id>/delete", methods=["POST"])
@login_required(*STAFF)
def admin_course_delete(course_id):
    own_course(course_id)
    run("DELETE FROM courses WHERE id=?", (course_id,))
    flash("Course deleted.", "success")
    return redirect(url_for("admin_courses"))

@app.errorhandler(400)
def e400(_): return render_template("error.html", code=400, msg="Session expired or bad request. Please go back, refresh and try again."), 400
@app.errorhandler(403)
def e403(_): return render_template("error.html", code=403, msg="Access denied"), 403
@app.errorhandler(404)
def e404(_): return render_template("error.html", code=404, msg="Page not found"), 404
@app.errorhandler(413)
def e413(_): return render_template("error.html", code=413, msg="File too large (max 5 MB)"), 413

app.add_url_rule("/job/<int:iid>", endpoint="job_detail", view_func=internship_detail)

init_db()                      # safe to run on every start (creates tables / seeds only when missing)
if __name__ == "__main__":
    app.run(debug=os.environ.get("APP_ENV") != "production", port=int(os.environ.get("PORT", 5000)))
