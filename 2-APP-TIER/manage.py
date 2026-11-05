"""Helper commands for the APP TIER.

  python manage.py check              -> connects to the database, creates the tables if missing, prints a summary
  python manage.py create-db-user     -> (run ONCE on AWS) creates the app's database + user inside RDS using the RDS admin login

Both accept  --env /etc/connect.env  to read the settings file.
create-db-user also needs DB_ADMIN_USER and DB_ADMIN_PASSWORD (type them in the terminal only - do not save them in the env file).
"""
import os, re, sys

def load_env(path):
    for line in open(path, encoding="utf-8"):
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

def create_db_user():
    import pymysql
    need = ["DB_HOST", "DB_USER", "DB_PASSWORD", "DB_ADMIN_USER", "DB_ADMIN_PASSWORD"]
    missing = [k for k in need if not os.environ.get(k)]
    if missing:
        sys.exit("Missing settings: " + ", ".join(missing))
    name, user = os.environ.get("DB_NAME", "connect_db"), os.environ["DB_USER"]
    if not re.fullmatch(r"[A-Za-z0-9_]+", name) or not re.fullmatch(r"[A-Za-z0-9_]+", user):
        sys.exit("DB_NAME and DB_USER may contain only letters, numbers and _")
    conn = pymysql.connect(host=os.environ["DB_HOST"], port=int(os.environ.get("DB_PORT", 3306)), user=os.environ["DB_ADMIN_USER"],
                           password=os.environ["DB_ADMIN_PASSWORD"], autocommit=True, connect_timeout=10)
    cur = conn.cursor()
    cur.execute(f"CREATE DATABASE IF NOT EXISTS `{name}` CHARACTER SET utf8mb4")
    cur.execute("CREATE USER IF NOT EXISTS %s@'%%' IDENTIFIED BY %s", (user, os.environ["DB_PASSWORD"]))
    cur.execute("ALTER USER %s@'%%' IDENTIFIED BY %s", (user, os.environ["DB_PASSWORD"]))
    cur.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE, CREATE, INDEX, ALTER ON `{name}`.* TO %s@'%%'", (user,))
    conn.close()
    print(f"OK: database '{name}' and user '{user}' are ready.")

def check():
    import app as A                       # importing the app creates the tables and seeds the first data
    with A.app.app_context():
        print("Database :", "MySQL @ " + os.environ["DB_HOST"] if A.USE_MYSQL else "SQLite (local file)")
        print("Uploads  :", "S3 bucket " + A.S3_BUCKET if A.S3_BUCKET else "local folder")
        print("Owner    :", [r["email"] for r in A.q("SELECT email FROM users WHERE role='owner'")])
        print("Courses  :", A.n("SELECT COUNT(*) FROM courses"), "| Companies:", A.n("SELECT COUNT(*) FROM companies"),
              "| Students:", A.n("SELECT COUNT(*) FROM users WHERE role='student'"))
    print("All good.")

if __name__ == "__main__":
    args = sys.argv[1:]
    if "--env" in args:
        load_env(args[args.index("--env") + 1])
    cmd = next((a for a in args if not a.startswith("--") and not a.startswith("/")), "check")
    create_db_user() if cmd == "create-db-user" else check()
