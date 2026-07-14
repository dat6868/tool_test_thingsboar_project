import asyncio
import aiohttp
import time
import re
import requests
import json
import os
os.makedirs("data", exist_ok=True)
import os
from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from typing import List, Optional

app = FastAPI(title="Bomb Dropper Web API")

# Serve static files and templates
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

class CurlParser:
    @staticmethod
    def parse(curl_command):
        curl_command = curl_command.replace("\\\n", " ")
        url_match = re.search(r"curl\s+(?:-X\s+[A-Z]+\s+)?['\"]?(http[s]?://[^\s'\"]+)['\"]?", curl_command)
        if not url_match:
            url_match = re.search(r"(http[s]?://[^\s'\"]+)", curl_command)
        url = url_match.group(1) if url_match else ""
        
        method_match = re.search(r"-X\s+([A-Z]+)", curl_command)
        method = method_match.group(1) if method_match else "GET"
        
        headers = {}
        header_matches = re.findall(r"-H\s+['\"]([^'\"]+)['\"]", curl_command)
        for h in header_matches:
            if ":" in h:
                k, v = h.split(":", 1)
                headers[k.strip()] = v.strip()
                
        data_match = re.search(r"--data-raw\s+['\"](.*?)['\"]", curl_command, re.DOTALL)
        if not data_match:
            data_match = re.search(r"-d\s+['\"](.*?)['\"]", curl_command, re.DOTALL)
        data = data_match.group(1) if data_match else None
        
        return {"url": url, "method": method, "headers": headers, "data": data}

class LoginRequest(BaseModel):
    url: str
    username: str
    password: str

class ApiConfig(BaseModel):
    name: str = "Lệnh cURL"
    curl: str
    rate: int
    step: int

class StartRequest(BaseModel):
    token: Optional[str] = None
    login_url: Optional[str] = None
    username: Optional[str] = None
    password: Optional[str] = None
    apis: List[ApiConfig]

MASTER_PASSWORD = "A@88888888a.boss"

# Global State

class GlobalState:
    is_locked = False
    lock_password = None

global_state = GlobalState()

class EngineState:
    def __init__(self):
        self.is_running = False
        self.stats = {"success": 0, "fail": 0}
        self.logs = []
        self.log_counter = 0
        self.threshold_alerts = []
        self.tasks = []
        
        self.is_basic_running = False
        self.basic_stats = {"success": 0, "fail": 0}
        self.basic_api_stats = {}
        self.basic_logs = []
        self.basic_log_counter = 0
        self.basic_tasks = []
        
        self.login_config = {}
        self.current_token = None
        
        import asyncio
        self.token_lock = asyncio.Lock()
        
        self.is_locked = False
        self.lock_password = None
        
        self.log_filename = ""
        self.basic_log_filename = ""

sessions = {}

import json
import os
os.makedirs("data", exist_ok=True)
MAX_SESSIONS = 5
if os.path.exists("data/system_config.json"):
    try:
        with open("data/system_config.json", "r", encoding="utf-8") as f:
            cfg = json.load(f)
            MAX_SESSIONS = cfg.get("max_sessions", 5)
    except: pass
else:
    try:
        with open("data/system_config.json", "w", encoding="utf-8") as f:
            json.dump({"max_sessions": 5}, f, indent=4, ensure_ascii=False)
    except: pass

# Khôi phục các session từ thư mục data khi khởi động server
for entry in os.listdir("data"):
    if os.path.isdir(os.path.join("data", entry)):
        session_id = entry
        s = EngineState()
        state_file = os.path.join("data", entry, "server_state.json")
        if os.path.exists(state_file):
            try:
                with open(state_file, "r", encoding="utf-8") as f:
                    d = json.load(f)
                    s.is_locked = d.get("is_locked", False)
                    s.lock_password = d.get("lock_password")
            except: pass
        sessions[session_id] = s


def get_session_folder(session_id: str) -> str:
    sanitized = session_id.replace(" ", "_")
    folder_path = f"data/{sanitized}"
    if not os.path.exists(folder_path):
        os.makedirs(folder_path, exist_ok=True)
    return folder_path

def get_session(session_id: str) -> EngineState:
    if session_id not in sessions:
        if len(sessions) >= MAX_SESSIONS:
            raise Exception("Đã hết vị trí để thêm phiên làm việc, yêu cầu xóa bớt các phiên không dùng! Hoặc liên hệ với quản trị viên!")
        s = EngineState()
        state_file = f"{get_session_folder(session_id)}/server_state.json"
        if os.path.exists(state_file):
            try:
                with open(state_file, "r", encoding="utf-8") as f:
                    import json
                    d = json.load(f)
                    s.is_locked = d.get("is_locked", False)
                    s.lock_password = d.get("lock_password")
            except: pass
            
        # Initialize default database.json if not exists
        db_file = f"{get_session_folder(session_id)}/database.json"
        if not os.path.exists(db_file):
            try:
                import json
                default_db = {
                    "base_test_status": False,
                    "performance_test_status": False,
                    "url": "",
                    "username": "",
                    "jwtToken": "",
                    "apis": [],
                    "basicApis": []
                }
                with open(db_file, "w", encoding="utf-8") as f:
                    json.dump(default_db, f, indent=4, ensure_ascii=False)
            except: pass
        sessions[session_id] = s
    return sessions[session_id]

def save_session_state(session_id: str):
    if session_id in sessions:
        s = sessions[session_id]
        try:
            import json
            with open(f"{get_session_folder(session_id)}/server_state.json", "w", encoding="utf-8") as f:
                json.dump({"is_locked": s.is_locked, "lock_password": s.lock_password}, f)
        except: pass

def update_database_status(session_id: str, is_running: bool = None, is_basic_running: bool = None):
    db_file = f"{get_session_folder(session_id)}/database.json"
    if not os.path.exists(db_file): return
    try:
        import json
        with open(db_file, "r", encoding="utf-8") as f:
            data = json.loads(f.read())
        
        new_data = {}
        if is_basic_running is not None:
            new_data["base_test_status"] = is_basic_running
        else:
            new_data["base_test_status"] = data.get("base_test_status", False)
            
        if is_running is not None:
            new_data["performance_test_status"] = is_running
        else:
            new_data["performance_test_status"] = data.get("performance_test_status", False)
            
        for k, v in data.items():
            if k not in ["base_test_status", "performance_test_status"]:
                new_data[k] = v
            
        with open(db_file, "w", encoding="utf-8") as f:
            json.dump(new_data, f, indent=4, ensure_ascii=False)
    except: pass



class BasicApiConfig(BaseModel):
    name: str = "Lệnh cURL"
    curl: str
    interval: int

class StartBasicRequest(BaseModel):
    token: Optional[str] = None
    login_url: Optional[str] = None
    username: Optional[str] = None
    password: Optional[str] = None
    apis: List[BasicApiConfig]

class LockRequest(BaseModel):
    password: str | None = None

class CreateSessionRequest(BaseModel):
    session_id: str
    password: str | None = None

@app.get("/api/sessions")
async def get_sessions():
    return {"status": "success", "sessions": list(sessions.keys()), "max_sessions": MAX_SESSIONS}

@app.post("/api/sessions")
async def create_session(req: CreateSessionRequest):
    try:
        s = get_session(req.session_id)
        if s.is_locked:
            if not req.password or (req.password != s.lock_password and req.password != MASTER_PASSWORD):
                return {"status": "error", "message": "Sai mật khẩu phiên làm việc!"}
        if req.password and not s.is_locked:
            s.lock_password = req.password
            s.is_locked = False
            save_session_state(req.session_id)
        return {"status": "success"}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.delete("/api/sessions/{session_id}")
async def delete_session(session_id: str, password: str = None):
    if session_id in sessions:
        s = sessions[session_id]
        if s.is_locked:
            if not password or (password != s.lock_password and password != MASTER_PASSWORD):
                return {"status": "error", "message": "Sai mật khẩu!"}
        
        s.is_running = False
        s.is_basic_running = False
        
        for task in s.tasks:
            task.cancel()
        for task in s.basic_tasks:
            task.cancel()
            
        del sessions[session_id]
        
        import shutil
        folder = get_session_folder(session_id)
        if os.path.exists(folder):
            shutil.rmtree(folder, ignore_errors=True)
    return {"status": "success"}

@app.get("/")
async def root(request: Request):
    return templates.TemplateResponse(request=request, name="index.html")

@app.post("/api/lock")
async def lock_session(req: LockRequest, session_id: str):
    s = get_session(session_id)
    if s.lock_password:
        s.is_locked = True
        save_session_state(session_id)
    return {"status": "success"}

@app.post("/api/unlock")
async def unlock_session(req: LockRequest, session_id: str):
    s = get_session(session_id)
    if not s.is_locked:
        return {"status": "success"}
    if req.password != s.lock_password and req.password != MASTER_PASSWORD:
        return {"status": "error", "message": "Sai mật khẩu mở khóa!"}
    s.is_locked = False
    save_session_state(session_id)
    return {"status": "success"}



@app.get("/api/database")
async def get_database(session_id: str):
    db_file = f"{get_session_folder(session_id)}/database.json"
    if os.path.exists(db_file):
        try:
            with open(db_file, "r", encoding="utf-8") as f:
                return json.loads(f.read())
        except Exception:
            pass
    return {}

@app.post("/api/database")
async def save_database(req: Request, session_id: str, format: str = "false"):
    data = await req.json()
    db_file = f"{get_session_folder(session_id)}/database.json"
    
    new_data = {}
    
    # Đọc lại trạng thái test cũ để đưa lên đầu file
    if os.path.exists(db_file):
        try:
            with open(db_file, "r", encoding="utf-8") as f:
                old_data = json.loads(f.read())
                new_data["base_test_status"] = old_data.get("base_test_status", False)
                new_data["performance_test_status"] = old_data.get("performance_test_status", False)
        except: 
            new_data["base_test_status"] = False
            new_data["performance_test_status"] = False
    else:
        new_data["base_test_status"] = False
        new_data["performance_test_status"] = False

    for k, v in data.items():
        new_data[k] = v

    with open(db_file, "w", encoding="utf-8") as f:
        if format.lower() == "true":
            json.dump(new_data, f, indent=4, ensure_ascii=False)
        else:
            json.dump(new_data, f, ensure_ascii=False)
    return {"status": "success"}

@app.post("/api/login")
async def login(req: LoginRequest):
    try:
        login_url = f"{req.url.rstrip('/')}/api/auth/login"
        resp = requests.post(login_url, json={"username": req.username, "password": req.password}, timeout=5)
        if resp.status_code == 200:
            return {"status": "success", "token": resp.json().get("token")}
        else:
            return {"status": "error", "message": f"HTTP {resp.status_code}: {resp.text}"}
    except Exception as e:
        return {"status": "error", "message": str(e)}

def push_log(session_id: str, msg: str):
    s = get_session(session_id)
    from datetime import datetime, timezone, timedelta
    tz_vn = timezone(timedelta(hours=7))
    time_str = datetime.now(tz_vn).strftime("%H:%M:%S")
    if not msg.startswith("["):
        msg = f"[{time_str}] {msg}"
    s.log_counter += 1
    s.logs.append({"id": s.log_counter, "msg": msg})
    try:
        filename = getattr(s, "log_filename", None) or f"{get_session_folder(session_id)}/bomb_logs.json"
        with open(filename, "w", encoding="utf-8") as f:
            json.dump(s.logs, f, indent=4, ensure_ascii=False)
    except: pass

def push_basic_log(session_id: str, msg: str):
    s = get_session(session_id)
    from datetime import datetime, timezone, timedelta
    tz_vn = timezone(timedelta(hours=7))
    time_str = datetime.now(tz_vn).strftime("%H:%M:%S")
    if not msg.startswith("["):
        msg = f"[{time_str}] {msg}"
    s.basic_log_counter += 1
    s.basic_logs.append({"id": s.basic_log_counter, "msg": msg})
    try:
        filename = getattr(s, "basic_log_filename", None) or f"{get_session_folder(session_id)}/basic_logs.json"
        with open(filename, "w", encoding="utf-8") as f:
            json.dump(s.basic_logs, f, indent=4, ensure_ascii=False)
    except: pass

@app.post("/api/start")
async def start_bombing(req: StartRequest, session_id: str):
    s = get_session(session_id)
    if s.is_locked:
        return {"status": "error", "message": "Hệ thống đang bị khóa!"}
    if s.is_running:
        return {"status": "error", "message": "Chiến dịch thả bom đã đang chạy!"}
    
    s.is_running = True
    update_database_status(session_id, is_running=True)
    
    from datetime import datetime, timezone, timedelta
    tz_vn = timezone(timedelta(hours=7))
    timestamp = datetime.now(tz_vn).strftime("%d_%m_%Y-%H_%M_%S")
    s.log_filename = f"{get_session_folder(session_id)}/bomb_logs_{timestamp}.json"
    
    parsed_apis = []
    for cfg in req.apis:
        req_data = CurlParser.parse(cfg.curl)
        if not req_data["url"]: continue
        
        if req.token and "X-Authorization" not in req_data["headers"]:
            req_data["headers"]["X-Authorization"] = f"Bearer {req.token}"
            
        req_data["rate"] = cfg.rate
        req_data["step"] = cfg.step
        req_data["name"] = cfg.name
        parsed_apis.append(req_data)
        
    if not parsed_apis:
        return {"status": "error", "message": "Không có API hợp lệ nào để test."}
        
    s.is_running = True
    s.stats = {"success": 0, "fail": 0}
    s.logs = []
    s.threshold_alerts = []
    s.login_config = {
        "url": req.login_url,
        "username": req.username,
        "password": req.password
    }
    s.current_token = req.token
    
    push_log(session_id, f"Đã nạp {len(parsed_apis)} API. Bắt đầu tổng tấn công...")
    
    asyncio.create_task(bomb_manager(parsed_apis, session_id))
    return {"status": "success"}

@app.post("/api/stop")
async def stop_bombing(session_id: str):
    s = get_session(session_id)
    if s.is_locked:
        return {"status": "error", "message": "Hệ thống đang bị khóa!"}
    s.is_running = False
    update_database_status(session_id, is_running=False)
    for task in s.tasks:
        task.cancel()
    push_log(session_id, "Đã nhận lệnh DỪNG thả bom.")
    return {"status": "success"}

@app.get("/api/download_bomb_log")
async def download_bomb_log(session_id: str):
    s = get_session(session_id)
    if not getattr(s, "log_filename", None) or not os.path.exists(s.log_filename):
        return {"status": "error", "message": "Không tìm thấy file log!"}
    from fastapi.responses import FileResponse
    import os
    return FileResponse(path=s.log_filename, filename=os.path.basename(s.log_filename), media_type='application/json')

@app.get("/api/status")
async def get_status(session_id: str, last_id: int = -1):
    s = get_session(session_id)
    
    # Nếu không chạy và không phải lần tải đầu tiên -> Không cần lọc log
    if not s.is_running and last_id != -1:
        new_logs = []
    else:
        new_logs = [log for log in s.logs if log["id"] > last_id]
        
    return {
        "is_locked": s.is_locked,
        "is_running": s.is_running,
        "stats": s.stats,
        "logs": new_logs,
        "last_id": s.log_counter,
        "thresholds": s.threshold_alerts
    }

@app.post("/api/start_basic")
async def start_basic(req: StartBasicRequest, session_id: str):
    s = get_session(session_id)
    if s.is_locked:
        return {"status": "error", "message": "Hệ thống đang bị khóa!"}
    if s.is_basic_running:
        return {"status": "error", "message": "Kiểm tra cơ bản đang chạy!"}
    
    s.is_basic_running = True
    update_database_status(session_id, is_basic_running=True)

    parsed_apis = []
    for cfg in req.apis:
        req_data = CurlParser.parse(cfg.curl)
        if not req_data["url"]: continue
        
        if req.token and "X-Authorization" not in req_data["headers"]:
            req_data["headers"]["X-Authorization"] = f"Bearer {req.token}"
            
        req_data["interval"] = cfg.interval
        req_data["name"] = cfg.name
        parsed_apis.append(req_data)
        
    if not parsed_apis:
        return {"status": "error", "message": "Không có API hợp lệ nào để test."}
        
    s.is_basic_running = True
    s.basic_stats = {"success": 0, "fail": 0}
    s.basic_api_stats = {api["name"]: {"success": 0, "fail": 0, "fail_details": {}} for api in parsed_apis}
    s.basic_logs = []
    s.login_config = {
        "url": req.login_url,
        "username": req.username,
        "password": req.password
    }
    s.current_token = req.token
    
    from datetime import datetime, timezone, timedelta
    tz_vn = timezone(timedelta(hours=7))
    timestamp = datetime.now(tz_vn).strftime("%d_%m_%Y-%H_%M_%S")
    s.basic_log_filename = f"{get_session_folder(session_id)}/basic_logs_{timestamp}.json"
    
    push_basic_log(session_id, f"Đã nạp {len(parsed_apis)} API. Bắt đầu kiểm tra cơ bản...")
    
    asyncio.create_task(basic_test_manager(parsed_apis, session_id))
    return {"status": "success"}

@app.post("/api/stop_basic")
async def stop_basic(session_id: str):
    s = get_session(session_id)
    if s.is_locked:
        return {"status": "error", "message": "Hệ thống đang bị khóa!"}
    s.is_basic_running = False
    update_database_status(session_id, is_basic_running=False)
    for task in s.basic_tasks:
        task.cancel()
    push_basic_log(session_id, "Đã nhận lệnh DỪNG kiểm tra cơ bản.")
    return {"status": "success"}

@app.get("/api/download_basic_log")
async def download_basic_log(session_id: str):
    from fastapi.responses import FileResponse
    s = get_session(session_id)
    if not getattr(s, "basic_log_filename", None) or not os.path.exists(s.basic_log_filename):
        return {"status": "error", "message": "Không tìm thấy file log!"}
    return FileResponse(path=s.basic_log_filename, filename=os.path.basename(s.basic_log_filename), media_type='application/json')

@app.get("/api/status_basic")
async def get_status_basic(session_id: str, last_id: int = -1):
    s = get_session(session_id)
    
    # Nếu không chạy và không phải lần tải đầu tiên -> Không cần lọc log
    if not s.is_basic_running and last_id != -1:
        new_logs = []
    else:
        new_logs = [log for log in s.basic_logs if log["id"] > last_id]
        
    return {
        "is_locked": s.is_locked,
        "is_running": s.is_basic_running,
        "stats": s.basic_stats,
        "api_stats": s.basic_api_stats,
        "logs": new_logs,
        "last_id": s.basic_log_counter
    }

async def bomb_manager(parsed_apis, session_id):
    s = get_session(session_id)
    connector = aiohttp.TCPConnector(limit=0)
    async with aiohttp.ClientSession(connector=connector) as session:
        for api in parsed_apis:
            task = asyncio.create_task(fire_api(session, api, session_id))
            s.tasks.append(task)
            
        await asyncio.gather(*s.tasks, return_exceptions=True)
        
    s.is_running = False
    s.tasks.clear()
    push_log(session_id, "Chiến dịch thả bom đã kết thúc.")

async def fire_api(session, api, session_id):
    s = get_session(session_id)
    current_rate = api["rate"]
    step = api["step"]
    url = api["url"]
    method = api["method"]
    headers = api["headers"]
    data = api["data"]
    
    last_step_time = time.time()
    active_tasks = 0
    has_failed = False
            
    async def do_request():
        nonlocal active_tasks, has_failed
        if not s.is_running or has_failed: return
        
        active_tasks += 1
        try:
            if method == "GET":
                resp_coro = session.get(url, headers=headers)
            elif method == "POST":
                resp_coro = session.post(url, headers=headers, data=data)
            else:
                resp_coro = session.request(method, url, headers=headers, data=data)
                
            async with resp_coro as res:
                if res.status >= 200 and res.status < 300:
                    s.stats["success"] += 1
                    await res.read()
                elif res.status == 401 and s.login_config.get("url"):
                    async with s.token_lock:
                        current_auth = api["headers"].get("X-Authorization")
                        if current_auth != f"Bearer {s.current_token}":
                            # Another task refreshed it
                            api["headers"]["X-Authorization"] = f"Bearer {s.current_token}"
                            return await do_request() # Retry
                        else:
                            login_url = f"{s.login_config['url'].rstrip('/')}/api/auth/login"
                            login_data = {"username": s.login_config['username'], "password": s.login_config['password']}
                            async with session.post(login_url, json=login_data) as login_res:
                                if login_res.status == 200:
                                    data = await login_res.json()
                                    s.current_token = data.get("token")
                                    api["headers"]["X-Authorization"] = f"Bearer {s.current_token}"
                                    push_log(session_id, "🔄 Token hết hạn. Đã tự động gia hạn Token mới thành công!")
                                    return await do_request() # Retry
                                else:
                                    s.stats["fail"] += 1
                                    push_log(session_id, f"❌ Gia hạn Token thất bại! HTTP {login_res.status}")
                else:
                    s.stats["fail"] += 1
                    err_txt = await res.text()
                    if s.is_running and not has_failed:
                        has_failed = True
                        push_log(session_id, f"💣 LỖI CHÍ MẠNG: Server gục ngã ở ngưỡng {current_rate} req/s. HTTP {res.status}: {err_txt[:100]}")
                        s.threshold_alerts.append(f"Ngưỡng chết: {current_rate} req/s (HTTP {res.status})")
                        s.is_running = False
        except Exception as e:
            s.stats["fail"] += 1
            if s.is_running and not has_failed:
                has_failed = True
                push_log(session_id, f"💣 LỖI NGOẠI LỆ: Server sập ở mức {current_rate} req/s. Lỗi: {str(e)}")
                s.threshold_alerts.append(f"Ngưỡng chết: {current_rate} req/s (Network Error)")
                s.is_running = False
        finally:
            active_tasks -= 1

    while s.is_running and not has_failed:
        if active_tasks > 100:
            has_failed = True
            s.is_running = False
            push_log(session_id, f"⚠️ MẠCH BẢO VỆ: Server bị treo đơ ở ngưỡng {current_rate} req/s (100 reqs pending).")
            s.threshold_alerts.append(f"Treo đơ ở: {current_rate} req/s")
            break

        start_time = time.time()
        
        if start_time - last_step_time >= 5.0:
            current_rate += step
            last_step_time = start_time
            push_log(session_id, f"[TĂNG TỐC] Tăng tốc độ bắn lên {current_rate} req/s")
            
        sleep_time = 1.0 / current_rate if current_rate > 0 else 0.01
        
        asyncio.create_task(do_request())
            
        elapsed = time.time() - start_time
        if elapsed < sleep_time:
            await asyncio.sleep(sleep_time - elapsed)

async def basic_test_manager(parsed_apis, session_id):
    s = get_session(session_id)
    connector = aiohttp.TCPConnector(limit=0)
    async with aiohttp.ClientSession(connector=connector) as session:
        for api in parsed_apis:
            task = asyncio.create_task(fire_basic_api(session, api, session_id))
            s.basic_tasks.append(task)
            
        await asyncio.gather(*s.basic_tasks, return_exceptions=True)
        
    s.is_basic_running = False
    s.basic_tasks.clear()
    push_basic_log(session_id, "Chiến dịch kiểm tra cơ bản đã kết thúc.")

async def fire_basic_api(session, api, session_id):
    s = get_session(session_id)
    interval = api["interval"]
    url = api["url"]
    method = api["method"]
    headers = api["headers"]
    data = api["data"]
    api_name = api.get("name", "Unknown API")
    
    while s.is_basic_running:
        start_time = time.time()
        
        try:
            if method == "GET":
                resp_coro = session.get(url, headers=headers)
            elif method == "POST":
                resp_coro = session.post(url, headers=headers, data=data)
            else:
                resp_coro = session.request(method, url, headers=headers, data=data)
                
            async with resp_coro as res:
                if res.status >= 200 and res.status < 300:
                    s.basic_stats["success"] += 1
                    if api_name in s.basic_api_stats: s.basic_api_stats[api_name]["success"] += 1
                    push_basic_log(session_id, f"🟢 Gọi thành công tới {url} (HTTP {res.status})")
                    await res.read()
                elif res.status == 401 and s.login_config.get("url"):
                    async with s.token_lock:
                        current_auth = api["headers"].get("X-Authorization")
                        if current_auth != f"Bearer {s.current_token}":
                            # Another task refreshed it
                            api["headers"]["X-Authorization"] = f"Bearer {s.current_token}"
                        else:
                            login_url = f"{s.login_config['url'].rstrip('/')}/api/auth/login"
                            login_data = {"username": s.login_config['username'], "password": s.login_config['password']}
                            async with session.post(login_url, json=login_data) as login_res:
                                if login_res.status == 200:
                                    data = await login_res.json()
                                    s.current_token = data.get("token")
                                    api["headers"]["X-Authorization"] = f"Bearer {s.current_token}"
                                    push_basic_log(session_id, "🔄 Token hết hạn. Đã tự động gia hạn Token mới thành công!")
                                else:
                                    s.basic_stats["fail"] += 1
                                    if api_name in s.basic_api_stats: 
                                        s.basic_api_stats[api_name]["fail"] += 1
                                        err_code = f"HTTP {login_res.status}"
                                        s.basic_api_stats[api_name]["fail_details"][err_code] = s.basic_api_stats[api_name]["fail_details"].get(err_code, 0) + 1
                                    push_basic_log(session_id, f"❌ Gia hạn Token thất bại! HTTP {login_res.status}")
                else:
                    s.basic_stats["fail"] += 1
                    if api_name in s.basic_api_stats: 
                        s.basic_api_stats[api_name]["fail"] += 1
                        err_code = f"HTTP {res.status}"
                        s.basic_api_stats[api_name]["fail_details"][err_code] = s.basic_api_stats[api_name]["fail_details"].get(err_code, 0) + 1
                    err_txt = await res.text()
                    # Cắt chuỗi lỗi ở 200 ký tự để tránh tràn UI nhưng vẫn đủ chi tiết
                    push_basic_log(session_id, f"❌ Lỗi HTTP {res.status} tại {url}: {err_txt[:200]}")
        except Exception as e:
            s.basic_stats["fail"] += 1
            if api_name in s.basic_api_stats: 
                s.basic_api_stats[api_name]["fail"] += 1
                err_code = "Lỗi Mạng"
                s.basic_api_stats[api_name]["fail_details"][err_code] = s.basic_api_stats[api_name]["fail_details"].get(err_code, 0) + 1
            push_basic_log(session_id, f"❌ Lỗi Mạng tại {url}: {str(e)}")
            
        elapsed = time.time() - start_time
        if elapsed < interval:
            await asyncio.sleep(interval - elapsed)

@app.on_event("startup")
async def startup_event():
    import asyncio
    import os
    print("Quét trạng thái phiên làm việc để khôi phục...")
    if not os.path.exists("data"): return
    for session_id in os.listdir("data"):
        db_file = f"data/{session_id}/database.json"
        if os.path.exists(db_file):
            try:
                import json
                with open(db_file, "r", encoding="utf-8") as f:
                    data = json.loads(f.read())
                
                # Khôi phục kiểm tra hiệu năng
                if data.get("performance_test_status", False):
                    print(f"[{session_id}] Khôi phục kiểm tra hiệu năng...")
                    req = StartRequest(
                        token=data.get("jwtToken"),
                        login_url=data.get("url"),
                        username=data.get("username"),
                        password=None,
                        apis=[ApiConfig(**a) for a in data.get("apis", [])]
                    )
                    asyncio.create_task(start_bombing(req, session_id))
                    
                # Khôi phục kiểm tra cơ bản
                if data.get("base_test_status", False):
                    print(f"[{session_id}] Khôi phục kiểm tra cơ bản...")
                    req_basic = StartBasicRequest(
                        token=data.get("jwtToken"),
                        login_url=data.get("url"),
                        username=data.get("username"),
                        password=None,
                        apis=[BasicApiConfig(**a) for a in data.get("basicApis", [])]
                    )
                    asyncio.create_task(start_basic(req_basic, session_id))
            except Exception as e:
                print(f"[{session_id}] Lỗi khôi phục tiến trình: {e}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=5000, reload=True)
