"""MySQL connections and small SQL helpers; no ORM or migration framework."""
import os
import re
from pathlib import Path
from urllib.parse import unquote, urlsplit

import pymysql
from dotenv import load_dotenv
from flask import current_app, g

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / '.env')


def connection_settings():
    # Reuse the original MySQL credentials, but keep its database untouched.
    url = urlsplit(os.getenv('DATABASE_URL', ''))
    if url.scheme and url.scheme not in ('mysql', 'mysql+pymysql'):
        raise ValueError('This application requires MySQL.')
    return dict(
        host=url.hostname or os.getenv('DB_HOST', '127.0.0.1'),
        port=url.port or int(os.getenv('DB_PORT', '3306')),
        user=unquote(url.username) if url.username else os.getenv('DB_USER', 'root'),
        password=unquote(url.password) if url.password else os.getenv('DB_PASSWORD', ''),
        database=os.getenv('SIMPLE_DB_NAME', 'hardware_world_simple'),
        charset='utf8mb4', cursorclass=pymysql.cursors.DictCursor,
        autocommit=False,
        init_command="SET time_zone = '+03:00'",
    )


def connect(settings=None):
    return pymysql.connect(**(settings or current_app.config['MYSQL']))


def get_db():
    if 'db' not in g:
        g.db = connect()
    return g.db


def close_db(error=None):
    connection = g.pop('db', None)
    if connection is not None:
        connection.close()  # Uncommitted work is rolled back.


def query(sql, params=(), one=False):
    with get_db().cursor() as cursor:
        cursor.execute(sql, params)
        return cursor.fetchone() if one else cursor.fetchall()


def execute(sql, params=()):
    with get_db().cursor() as cursor:
        cursor.execute(sql, params)
        return cursor.lastrowid


def commit():
    """Commit all changes together, then request an automatic CSV snapshot."""
    get_db().commit()
    g.committed_change = True


def initialize(settings):
    name = settings['database']
    if not re.fullmatch(r'[A-Za-z0-9_]+', name):
        raise ValueError('Use only letters, numbers and underscores in SIMPLE_DB_NAME.')
    try:
        connect(settings).close()
    except pymysql.OperationalError as error:
        if error.args[0] != 1049:  # Unknown database; do not mask login/access errors.
            raise
        server = dict(settings)
        server.pop('database')
        with pymysql.connect(**server) as connection:
            with connection.cursor() as cursor:
                cursor.execute(f'CREATE DATABASE `{name}` CHARACTER SET utf8mb4')
    with connect(settings) as connection:
        with connection.cursor() as cursor:
            for statement in Path(__file__).with_name('schema.sql').read_text().split(';'):
                if statement.strip():
                    cursor.execute(statement)
            upgrade_roles(cursor)
            upgrade_usernames(cursor)
            from business import upgrade
            upgrade(cursor)
        connection.commit()


def upgrade_roles(cursor):
    """Upgrade existing two-role databases without deleting employees or records."""
    cursor.execute("SHOW COLUMNS FROM employees LIKE 'role'")
    column = cursor.fetchone()
    if column['Type'] == "enum('Admin','Sales','Purchasing')":
        return
    # Widen first so the old Staff value and new department roles can coexist.
    # Rerunning init-db safely resumes an interrupted upgrade.
    cursor.execute("ALTER TABLE employees MODIFY role "
                   "ENUM('Admin','Staff','Sales','Purchasing') NOT NULL DEFAULT 'Sales'")
    cursor.execute("UPDATE employees SET role='Sales' WHERE role='Staff'")
    cursor.execute("ALTER TABLE employees MODIFY role "
                   "ENUM('Admin','Sales','Purchasing') NOT NULL DEFAULT 'Sales'")


def username_from_name(name):
    """Make a readable initial username when upgrading an existing account."""
    value = re.sub(r'[^a-z0-9_.-]+', '_', name.lower()).strip('_.-')[:50]
    return value if len(value) >= 3 else 'employee'


def upgrade_usernames(cursor):
    """Preserve employee IDs, passwords, and transaction links during upgrade."""
    cursor.execute("SHOW COLUMNS FROM employees LIKE 'username'")
    column = cursor.fetchone()
    if column is None:
        cursor.execute('ALTER TABLE employees ADD username VARCHAR(50) NULL UNIQUE AFTER name')
    cursor.execute('SELECT id, name, email, role, username FROM employees ORDER BY id')
    employees = cursor.fetchall()
    used = {row['username'].lower() for row in employees if row['username']}
    for employee in employees:
        if employee['username']:
            continue
        if employee['role'] == 'Admin':
            source = os.getenv('ADMIN_USERNAME') or employee['name']
        else:
            source = (employee['email'] or employee['name']).split('@')[0]
        base = username_from_name(source)
        username, counter = base, 0
        while username in used:
            counter += 1
            suffix = f'_{employee["id"]}' + (f'_{counter}' if counter > 1 else '')
            username = base[:50-len(suffix)] + suffix
        cursor.execute('UPDATE employees SET username=%s WHERE id=%s', (username, employee['id']))
        used.add(username)
    if column is None or column['Null'] == 'YES':
        cursor.execute('ALTER TABLE employees MODIFY username VARCHAR(50) NOT NULL')
    cursor.execute("SHOW COLUMNS FROM employees LIKE 'email'")
    if cursor.fetchone()['Null'] != 'YES':
        cursor.execute('ALTER TABLE employees MODIFY email VARCHAR(150) NULL')
