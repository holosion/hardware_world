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
        connection.commit()
