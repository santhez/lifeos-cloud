import os
import sys
import json
import urllib.request
import urllib.error
from urllib.parse import parse_qs, urlparse
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler

if hasattr(sys.stdout, 'reconfigure'):
    try: sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception: pass
if hasattr(sys.stderr, 'reconfigure'):
    try: sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except Exception: pass

import db

PORT = int(os.environ.get("PORT", 8080))
STATIC_DIR = os.path.dirname(os.path.abspath(__file__))
SERVER_GEMINI_KEY = os.environ.get("GEMINI_API_KEY", "").strip()

# Initialize SQLite database
db.init_db()

def call_gemini_api(api_key: str, prompt: str, system_instruction: str = "") -> dict:
    """Calls Gemini API directly over HTTP with zero third-party dependencies."""
    if not api_key:
        raise ValueError("API-ключ Google Gemini не указан")
        
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={api_key}"
    payload = {
        "contents": [{"parts": [{"text": prompt}]}]
    }
    if system_instruction:
        payload["systemInstruction"] = {"parts": [{"text": system_instruction}]}
        
    data = json.dumps(payload).encode('utf-8')
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST"
    )
    
    try:
        with urllib.request.urlopen(req, timeout=40) as resp:
            res_json = json.loads(resp.read().decode('utf-8'))
            candidates = res_json.get("candidates", [])
            if candidates and "content" in candidates[0]:
                parts = candidates[0]["content"].get("parts", [])
                if parts and "text" in parts[0]:
                    return {"text": parts[0]["text"]}
            return {"text": "", "raw": res_json}
    except urllib.error.HTTPError as e:
        err_msg = e.read().decode('utf-8', errors='ignore')
        try:
            err_json = json.loads(err_msg)
            message = err_json.get("error", {}).get("message", err_msg)
        except Exception:
            message = err_msg
        raise RuntimeError(f"Ошибка Gemini API ({e.code}): {message}")
    except Exception as e:
        raise RuntimeError(f"Ошибка соединения с Gemini API: {str(e)}")

class LifeOSCloudHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=STATIC_DIR, **kwargs)

    def end_headers(self):
        # Enable CORS and disable caching
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type, Authorization')
        self.send_header('Cache-Control', 'no-store, no-cache, must-revalidate, max-age=0')
        self.send_header('Pragma', 'no-cache')
        super().end_headers()

    def do_OPTIONS(self):
        self.send_response(200)
        self.end_headers()

    def send_json(self, data, status=200):
        try:
            self.send_response(status)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.end_headers()
            self.wfile.write(json.dumps(data, ensure_ascii=False).encode('utf-8'))
        except (ConnectionResetError, BrokenPipeError, ConnectionAbortedError):
            pass

    def get_token(self):
        auth_header = self.headers.get('Authorization', '')
        if auth_header.startswith('Bearer '):
            return auth_header[7:].strip()
        if '?' in self.path:
            qs = parse_qs(urlparse(self.path).query)
            if 'token' in qs and qs['token']:
                return qs['token'][0].strip()
        return None

    def get_current_user(self):
        token = self.get_token()
        if token:
            return db.get_user_by_token(token)
        return None

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path

        if path == '/api/health':
            self.send_json({"status": "ok", "app": "LifeOS Cloud", "version": "2.0"})
            return

        # AUTH CHECK
        if path == '/api/auth/me':
            user = self.get_current_user()
            self.send_json({"user": user})
            return

        # USER STATE SYNC
        elif path == '/api/user_state':
            user = self.get_current_user()
            if not user:
                self.send_json({"error": "Требуется авторизация"}, status=401)
                return
            state = db.get_user_state(user['id'])
            self.send_json({"user": user, "state": state})
            return

        # USER LOGS
        elif path == '/api/user_logs':
            user = self.get_current_user()
            if not user:
                self.send_json({"error": "Требуется авторизация"}, status=401)
                return
            qs = parse_qs(parsed.query)
            log_type = qs.get('type', [None])[0]
            logs = db.get_user_logs(user['id'], log_type)
            self.send_json({"logs": logs})
            return

        # AI STATUS
        elif path == '/api/ai/status':
            user = self.get_current_user()
            user_key = (user.get('gemini_api_key', '') if user else '').strip()
            has_key = bool(user_key or SERVER_GEMINI_KEY)
            source = "user" if user_key else ("server" if SERVER_GEMINI_KEY else "none")
            self.send_json({"configured": has_key, "source": source})
            return

        # Static files fallback
        super().do_GET()

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path

        content_length = int(self.headers.get('Content-Length', 0))
        raw_body = self.rfile.read(content_length).decode('utf-8', errors='ignore') if content_length > 0 else ""

        # 1. REGISTER
        if path == '/api/auth/register':
            try:
                data = json.loads(raw_body)
                username = data.get('username', '')
                password = data.get('password', '')
                display_name = data.get('display_name', '')
                user = db.create_user(username, password, display_name)
                token = db.create_session(user['id'])
                self.send_json({"success": True, "token": token, "user": user})
            except ValueError as ve:
                self.send_json({"error": str(ve)}, status=400)
            except Exception as e:
                self.send_json({"error": f"Ошибка регистрации: {str(e)}"}, status=500)
            return

        # 2. LOGIN
        elif path == '/api/auth/login':
            try:
                data = json.loads(raw_body)
                username = data.get('username', '')
                password = data.get('password', '')
                user = db.authenticate_user(username, password)
                if user:
                    token = db.create_session(user['id'])
                    self.send_json({"success": True, "token": token, "user": user})
                else:
                    self.send_json({"error": "Неверный логин или пароль"}, status=401)
            except Exception as e:
                self.send_json({"error": f"Ошибка авторизации: {str(e)}"}, status=500)
            return

        # 3. LOGOUT
        elif path == '/api/auth/logout':
            token = self.get_token()
            if token:
                db.delete_session(token)
            self.send_json({"success": True})
            return

        # Protected endpoints below
        user = self.get_current_user()
        if not user:
            self.send_json({"error": "Требуется авторизация"}, status=401)
            return

        # 4. SAVE USER STATE
        if path == '/api/user_state':
            try:
                data = json.loads(raw_body)
                if isinstance(data, dict):
                    if 'key' in data and 'value' in data and len(data) <= 3:
                        db.save_user_state_key(user['id'], data['key'], data['value'])
                    else:
                        for k, v in data.items():
                            db.save_user_state_key(user['id'], k, v)
                self.send_json({"success": True})
            except Exception as e:
                self.send_json({"error": str(e)}, status=500)
            return

        # 5. SAVE GEMINI API KEY (BYOK)
        elif path == '/api/ai/save_key':
            try:
                data = json.loads(raw_body)
                api_key = data.get('api_key', '').strip()
                db.set_user_api_key(user['id'], api_key)
                self.send_json({"success": True})
            except Exception as e:
                self.send_json({"error": str(e)}, status=500)
            return

        # 6. AI DECOMPOSE IDEA
        elif path == '/api/ai/decompose_idea':
            try:
                data = json.loads(raw_body)
                idea_title = data.get('title', '')
                idea_desc = data.get('desc', '')
                idea_cat = data.get('cat', '1_Work')

                # User key has priority, then server key
                api_key = user.get('gemini_api_key', '').strip() or SERVER_GEMINI_KEY
                if not api_key:
                    self.send_json({
                        "error": "API-ключ не настроен. Добавьте ваш бесплатный ключ Google AI Studio в разделе «Настройки»."
                    }, status=400)
                    return

                system_prompt = (
                    "Ты — соматический и продуктивный архитектор платформы LifeOS. "
                    "Твоя задача: декомпозировать сырую идею в структурированный проект из 3-5 конкретных шагов. "
                    "Верни строго валидный JSON без markdown-разметки: "
                    "{\"name\": \"Название проекта\", \"cat\": \"категория\", \"deadline\": \"срок\", \"steps\": [\"шаг 1\", \"шаг 2\", \"шаг 3\"]}"
                )
                user_prompt = f"Идея: {idea_title}\nОписание: {idea_desc}\nКатегория: {idea_cat}\nДекомпозируй эту идею на практические шаги."
                
                res = call_gemini_api(api_key, user_prompt, system_prompt)
                res_text = res.get("text", "")
                
                # Clean possible codeblocks
                clean_text = res_text.strip()
                if clean_text.startswith("```"):
                    lines = clean_text.splitlines()
                    if lines[0].startswith("```"):
                        lines = lines[1:]
                    if lines and lines[-1].startswith("```"):
                        lines = lines[:-1]
                    clean_text = "\n".join(lines).strip()
                    
                parsed_plan = json.loads(clean_text)
                self.send_json({"success": True, "plan": parsed_plan})
            except Exception as e:
                self.send_json({"error": f"Ошибка ИИ: {str(e)}"}, status=500)
            return

        # 7. SAVE MORNING PAGES
        elif path == '/api/save_morning':
            try:
                today_iso = datetime.utcnow().strftime('%Y-%m-%d')
                db.save_user_log(user['id'], 'morning', today_iso, raw_body)
                self.send_json({"success": True})
            except Exception as e:
                self.send_json({"error": str(e)}, status=500)
            return

        # 8. SAVE EVENING DEBRIEF
        elif path == '/api/save_dump':
            try:
                today_iso = datetime.utcnow().strftime('%Y-%m-%d')
                db.save_user_log(user['id'], 'evening', today_iso, raw_body)
                self.send_json({"success": True})
            except Exception as e:
                self.send_json({"error": str(e)}, status=500)
            return

        else:
            self.send_json({"error": "Маршрут не найден"}, status=404)

def run():
    server_address = ('0.0.0.0', PORT)
    httpd = ThreadingHTTPServer(server_address, LifeOSCloudHandler)
    print(f"[LifeOS Cloud] Server started on http://0.0.0.0:{PORT}", flush=True)
    print(f"[LifeOS Cloud] Serving static files from: {STATIC_DIR}", flush=True)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n[LifeOS Cloud] Stopping server...", flush=True)
        httpd.server_close()

if __name__ == '__main__':
    run()
