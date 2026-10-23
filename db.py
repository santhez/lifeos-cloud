import sqlite3
import hashlib
import secrets
import os
import json
from datetime import datetime, timedelta

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "lifeos_cloud.db")

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    cur = conn.cursor()
    
    # 1. Users table
    cur.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        salt TEXT NOT NULL,
        display_name TEXT NOT NULL,
        gemini_api_key TEXT DEFAULT '',
        role TEXT DEFAULT 'user',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """)

    # 2. Sessions table
    cur.execute("""
    CREATE TABLE IF NOT EXISTS sessions (
        token TEXT PRIMARY KEY,
        user_id INTEGER NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        expires_at TIMESTAMP NOT NULL,
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
    );
    """)

    # 3. User key-value state table (syncs Projects, Kanban, Workouts, Meditation, Psychology, Settings per user)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS user_state (
        user_id INTEGER NOT NULL,
        key TEXT NOT NULL,
        value TEXT NOT NULL,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (user_id, key),
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
    );
    """)

    # 4. User logs table (evening debrief, morning pages, notes)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS user_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        log_type TEXT NOT NULL,
        log_date TEXT NOT NULL,
        content TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
    );
    """)

    conn.commit()
    conn.close()

def hash_password(password: str, salt: str = None) -> tuple[str, str]:
    if not salt:
        salt = secrets.token_hex(16)
    hashed = hashlib.pbkdf2_hmac(
        'sha256',
        password.encode('utf-8'),
        salt.encode('utf-8'),
        100000
    ).hex()
    return hashed, salt

def verify_password(password: str, hashed: str, salt: str) -> bool:
    new_hash, _ = hash_password(password, salt)
    return secrets.compare_digest(new_hash, hashed)

def create_user(username: str, password: str, display_name: str, role: str = "user") -> dict:
    username = username.strip().lower()
    display_name = display_name.strip()
    if not username or not password or not display_name:
        raise ValueError("Заполните все обязательные поля")
    if len(password) < 4:
        raise ValueError("Пароль должен содержать минимум 4 символа")

    p_hash, salt = hash_password(password)
    conn = get_db()
    cur = conn.cursor()
    try:
        cur.execute("""
        INSERT INTO users (username, password_hash, salt, display_name, role)
        VALUES (?, ?, ?, ?, ?);
        """, (username, p_hash, salt, display_name, role))
        user_id = cur.lastrowid
        conn.commit()
        return {
            "id": user_id,
            "username": username,
            "display_name": display_name,
            "role": role,
            "gemini_api_key": ""
        }
    except sqlite3.IntegrityError:
        raise ValueError("Пользователь с таким логином уже зарегистрирован")
    finally:
        conn.close()

def authenticate_user(username: str, password: str) -> dict:
    username = username.strip().lower()
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM users WHERE username = ?;", (username,))
    row = cur.fetchone()
    conn.close()
    
    if not row:
        return None
    if not verify_password(password, row['password_hash'], row['salt']):
        return None
        
    return {
        "id": row['id'],
        "username": row['username'],
        "display_name": row['display_name'],
        "role": row['role'],
        "gemini_api_key": row['gemini_api_key'] or ""
    }

def create_session(user_id: int, days_valid: int = 60) -> str:
    token = secrets.token_hex(32)
    expires_at = datetime.utcnow() + timedelta(days=days_valid)
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
    INSERT INTO sessions (token, user_id, expires_at)
    VALUES (?, ?, ?);
    """, (token, user_id, expires_at.isoformat()))
    conn.commit()
    conn.close()
    return token

def get_user_by_token(token: str) -> dict:
    if not token:
        return None
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
    SELECT u.id, u.username, u.display_name, u.role, u.gemini_api_key, s.expires_at
    FROM sessions s
    JOIN users u ON s.user_id = u.id
    WHERE s.token = ?;
    """, (token,))
    row = cur.fetchone()
    conn.close()

    if not row:
        return None

    # Check expiration
    try:
        exp = datetime.fromisoformat(row['expires_at'])
        if datetime.utcnow() > exp:
            delete_session(token)
            return None
    except Exception:
        pass

    return {
        "id": row['id'],
        "username": row['username'],
        "display_name": row['display_name'],
        "role": row['role'],
        "gemini_api_key": row['gemini_api_key'] or ""
    }

def delete_session(token: str):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("DELETE FROM sessions WHERE token = ?;", (token,))
    conn.commit()
    conn.close()

def set_user_api_key(user_id: int, api_key: str):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("UPDATE users SET gemini_api_key = ? WHERE id = ?;", (api_key.strip(), user_id))
    conn.commit()
    conn.close()

def save_user_state_key(user_id: int, key: str, value):
    val_str = json.dumps(value, ensure_ascii=False) if not isinstance(value, str) else value
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
    INSERT INTO user_state (user_id, key, value, updated_at)
    VALUES (?, ?, ?, CURRENT_TIMESTAMP)
    ON CONFLICT(user_id, key) DO UPDATE SET
        value = excluded.value,
        updated_at = CURRENT_TIMESTAMP;
    """, (user_id, key, val_str))
    conn.commit()
    conn.close()

def get_user_state(user_id: int) -> dict:
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT key, value FROM user_state WHERE user_id = ?;", (user_id,))
    rows = cur.fetchall()
    conn.close()
    
    state = {}
    for r in rows:
        try:
            state[r['key']] = json.loads(r['value'])
        except Exception:
            state[r['key']] = r['value']
    return state

def save_user_log(user_id: int, log_type: str, log_date: str, content: str):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
    INSERT INTO user_logs (user_id, log_type, log_date, content)
    VALUES (?, ?, ?, ?);
    """, (user_id, log_type, log_date, content))
    conn.commit()
    conn.close()

def get_user_logs(user_id: int, log_type: str = None) -> list:
    conn = get_db()
    cur = conn.cursor()
    if log_type:
        cur.execute("SELECT * FROM user_logs WHERE user_id = ? AND log_type = ? ORDER BY id DESC LIMIT 50;", (user_id, log_type))
    else:
        cur.execute("SELECT * FROM user_logs WHERE user_id = ? ORDER BY id DESC LIMIT 50;", (user_id,))
    rows = cur.fetchall()
    conn.close()
    return [dict(r) for r in rows]
