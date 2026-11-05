-- OPTIONAL hardening (see DEPLOY-GUIDE.md, "Extra: separate database user").
-- Creates a database user that can only work inside connect_db (cannot drop the database or touch other databases).
-- Easier way without a MySQL client:  python manage.py create-db-user --env /etc/connect.env   (run on an app-tier server)

CREATE DATABASE IF NOT EXISTS connect_db CHARACTER SET utf8mb4;
CREATE USER IF NOT EXISTS 'connect_app'@'%' IDENTIFIED BY 'CHANGE_THIS_PASSWORD';
GRANT SELECT, INSERT, UPDATE, DELETE, CREATE, INDEX, ALTER ON connect_db.* TO 'connect_app'@'%';
FLUSH PRIVILEGES;
