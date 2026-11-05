# 2-APP-TIER  ->  App-tier EC2 (private subnets)

Yahan poora Flask application hai (backend + HTML templates). AWS par ye **private subnet** ke EC2 servers par chalta hai.

| File / folder | Kaam |
|---|---|
| `app.py` | Poora application (login, internships, jobs, tests, courses, portfolio, admin panels) |
| `templates/` | HTML pages |
| `static/` | CSS, JavaScript, logo (Nginx bhi iski copy serve karta hai) |
| `requirements.txt` | Python libraries |
| `manage.py` | Helper: `python manage.py check` (database check) |
| `app.env.example` | Settings ka sample. Copy karke `app.env` banao, bharo, S3 `deploy/` me upload karo |
| `setup-app-tier.sh` | Launch Template ke **User data** me paste hone wali script (server khud install kar leta hai) |
| `connect-app.service` | systemd service (gunicorn chalata hai, port 8000) |
| `uploads/` | Sirf laptop par testing ke liye. AWS par uploads S3 me jaate hain |

## Laptop par test karna (AWS ke bina)
```
python -m venv venv
venv\Scripts\activate
python -m pip install -r requirements.txt
python app.py
```
Browser: http://127.0.0.1:5000   (database SQLite, files local folder - kuch set karna nahi padta)
Demo login: owner `admin@premtech.com` / `Admin@123`, company `hr@technova.com` / `Company@123`
