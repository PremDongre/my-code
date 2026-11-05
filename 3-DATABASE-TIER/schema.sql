-- Connect database schema (MySQL 8.0 / InnoDB / utf8mb4)
-- FOR REFERENCE ONLY: the app creates all these tables by itself the first time it starts,
-- and adds any new columns to an existing database automatically when the app restarts.

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

CREATE TABLE IF NOT EXISTS projects(id INT AUTO_INCREMENT PRIMARY KEY, user_id INT, title TEXT, description TEXT, tech TEXT, repo_url TEXT, live_url TEXT, created VARCHAR(20), KEY idx_proj_user(user_id)) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
