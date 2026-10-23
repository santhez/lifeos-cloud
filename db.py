import sqlite3
import hashlib
import secrets
import os
import json
import re
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
        email TEXT UNIQUE,
        password_hash TEXT NOT NULL,
        salt TEXT NOT NULL,
        display_name TEXT NOT NULL,
        email_verified INTEGER DEFAULT 0,
        gemini_api_key TEXT DEFAULT '',
        role TEXT DEFAULT 'user',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """)

    # Safe migrations for existing users table
    try:
        cur.execute("ALTER TABLE users ADD COLUMN email TEXT;")
    except Exception:
        pass
    try:
        cur.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_users_email ON users(email);")
    except Exception:
        pass
    try:
        cur.execute("ALTER TABLE users ADD COLUMN email_verified INTEGER DEFAULT 0;")
    except Exception:
        pass

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

    # 3. User key-value state table
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

    # 4. User logs table
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

    # 5. Email Verification & Password Reset Codes (OTP)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS email_codes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        email TEXT NOT NULL,
        code TEXT NOT NULL,
        action_type TEXT NOT NULL,
        expires_at TIMESTAMP NOT NULL,
        used INTEGER DEFAULT 0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """)
    cur.execute("""
    CREATE INDEX IF NOT EXISTS idx_email_codes_lookup 
    ON email_codes(email, action_type, used);
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

def is_valid_email(email: str) -> bool:
    return bool(re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email.strip()))

def create_user_with_email(email: str, password: str, display_name: str, role: str = "user") -> dict:
    email = email.strip().lower()
    display_name = display_name.strip()
    
    if not email or not is_valid_email(email):
        raise ValueError("Укажите корректный адрес электронной почты")
    if not password or len(password) < 4:
        raise ValueError("Пароль должен содержать минимум 4 символа")
    if not display_name:
        raise ValueError("Укажите ваше имя")

    username = email.split('@')[0]
    p_hash, salt = hash_password(password)
    
    conn = get_db()
    cur = conn.cursor()
    
    # Check if email exists
    cur.execute("SELECT id FROM users WHERE email = ?;", (email,))
    if cur.fetchone():
        conn.close()
        raise ValueError("Пользователь с таким email уже зарегистрирован")

    # Generate unique fallback username if needed
    base_user = re.sub(r'[^a-zA-Z0-9_]', '', username) or 'user'
    candidate_user = base_user
    counter = 1
    while True:
        cur.execute("SELECT id FROM users WHERE username = ?;", (candidate_user,))
        if not cur.fetchone():
            break
        candidate_user = f"{base_user}_{counter}"
        counter += 1

    try:
        cur.execute("""
        INSERT INTO users (username, email, password_hash, salt, display_name, role, email_verified)
        VALUES (?, ?, ?, ?, ?, ?, 0);
        """, (candidate_user, email, p_hash, salt, display_name, role))
        user_id = cur.lastrowid
        conn.commit()
        return {
            "id": user_id,
            "username": candidate_user,
            "email": email,
            "display_name": display_name,
            "role": role,
            "email_verified": 0,
            "gemini_api_key": ""
        }
    finally:
        conn.close()

def authenticate_user(login_or_email: str, password: str) -> dict:
    identifier = login_or_email.strip().lower()
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
    SELECT * FROM users 
    WHERE LOWER(username) = ? OR LOWER(email) = ?;
    """, (identifier, identifier))
    row = cur.fetchone()
    conn.close()
    
    if not row:
        return None
    if not verify_password(password, row['password_hash'], row['salt']):
        return None
        
    return {
        "id": row['id'],
        "username": row['username'],
        "email": row['email'] or "",
        "display_name": row['display_name'],
        "role": row['role'],
        "email_verified": row['email_verified'] if 'email_verified' in row.keys() else 1,
        "gemini_api_key": row['gemini_api_key'] or ""
    }

def get_user_by_email(email: str) -> dict:
    email = email.strip().lower()
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM users WHERE LOWER(email) = ?;", (email,))
    row = cur.fetchone()
    conn.close()
    if not row:
        return None
    return {
        "id": row['id'],
        "username": row['username'],
        "email": row['email'] or "",
        "display_name": row['display_name'],
        "role": row['role'],
        "email_verified": row['email_verified'] if 'email_verified' in row.keys() else 1,
        "gemini_api_key": row['gemini_api_key'] or ""
    }

def create_otp_code(email: str, action_type: str, minutes_valid: int = 15) -> str:
    email = email.strip().lower()
    code = f"{secrets.randbelow(900000) + 100000}" # 6-digit code
    expires_at = datetime.utcnow() + timedelta(minutes=minutes_valid)
    
    conn = get_db()
    cur = conn.cursor()
    # Invalidate previous unused codes for this email and action
    cur.execute("""
    UPDATE email_codes SET used = 1 
    WHERE email = ? AND action_type = ? AND used = 0;
    """, (email, action_type))
    
    cur.execute("""
    INSERT INTO email_codes (email, code, action_type, expires_at)
    VALUES (?, ?, ?, ?);
    """, (email, code, action_type, expires_at.isoformat()))
    conn.commit()
    conn.close()
    return code

def verify_otp_code(email: str, code: str, action_type: str) -> bool:
    email = email.strip().lower()
    code = code.strip()
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
    SELECT id, expires_at FROM email_codes
    WHERE email = ? AND code = ? AND action_type = ? AND used = 0
    ORDER BY id DESC LIMIT 1;
    """, (email, code, action_type))
    row = cur.fetchone()
    
    if not row:
        conn.close()
        return False
        
    try:
        exp = datetime.fromisoformat(row['expires_at'])
        if datetime.utcnow() > exp:
            conn.close()
            return False
    except Exception:
        pass
        
    cur.execute("UPDATE email_codes SET used = 1 WHERE id = ?;", (row['id'],))
    conn.commit()
    conn.close()
    return True

def mark_email_verified(email: str):
    email = email.strip().lower()
    conn = get_db()
    cur = conn.cursor()
    cur.execute("UPDATE users SET email_verified = 1 WHERE LOWER(email) = ?;", (email,))
    conn.commit()
    conn.close()

def reset_user_password(email: str, new_password: str):
    email = email.strip().lower()
    if not new_password or len(new_password) < 4:
        raise ValueError("Пароль должен содержать минимум 4 символа")
    p_hash, salt = hash_password(new_password)
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
    UPDATE users SET password_hash = ?, salt = ? 
    WHERE LOWER(email) = ?;
    """, (p_hash, salt, email))
    conn.commit()
    conn.close()

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
    SELECT u.id, u.username, u.email, u.display_name, u.role, u.email_verified, u.gemini_api_key, s.expires_at
    FROM sessions s
    JOIN users u ON s.user_id = u.id
    WHERE s.token = ?;
    """, (token,))
    row = cur.fetchone()
    conn.close()

    if not row:
        return None

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
        "email": row['email'] or "",
        "display_name": row['display_name'],
        "role": row['role'],
        "email_verified": row['email_verified'] if 'email_verified' in row.keys() else 1,
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
