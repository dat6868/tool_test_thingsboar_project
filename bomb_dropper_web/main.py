import asyncio
import aiohttp
import time
import re
import requests
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
    curl: str
    rate: int
    step: int

class StartRequest(BaseModel):
    token: Optional[str] = None
    login_url: Optional[str] = None
    username: Optional[str] = None
    password: Optional[str] = None
    apis: List[ApiConfig]

# Global State
class EngineState:
    def __init__(self):
        self.is_running = False
        self.stats = {"success": 0, "fail": 0}
        self.logs = []
        self.threshold_alerts = []
        self.tasks = []
        
        self.is_basic_running = False
        self.basic_stats = {"success": 0, "fail": 0}
        self.basic_logs = []
        self.basic_tasks = []
        
        self.login_config = {}
        self.current_token = None
        self.token_lock = asyncio.Lock()
        
        self.is_locked = False
        self.lock_password = None

state = EngineState()

def push_log(msg: str):
    ts = time.strftime('%H:%M:%S')
    state.logs.append(f"[{ts}] {msg}")
    if len(state.logs) > 100:
        state.logs.pop(0)

def push_basic_log(msg: str):
    ts = time.strftime('%H:%M:%S')
    state.basic_logs.append(f"[{ts}] {msg}")
    if len(state.basic_logs) > 100:
        state.basic_logs.pop(0)

class BasicApiConfig(BaseModel):
    curl: str
    interval: int

class StartBasicRequest(BaseModel):
    token: Optional[str] = None
    login_url: Optional[str] = None
    username: Optional[str] = None
    password: Optional[str] = None
    apis: List[BasicApiConfig]

class LockRequest(BaseModel):
    password: str

@app.get("/")
async def root(request: Request):
    return templates.TemplateResponse(request=request, name="index.html")

@app.post("/api/lock")
async def lock_session(req: LockRequest):
    if not req.password:
        return {"status": "error", "message": "Mật khẩu không được để trống!"}
    state.is_locked = True
    state.lock_password = req.password
    return {"status": "success"}

@app.post("/api/unlock")
async def unlock_session(req: LockRequest):
    if not state.is_locked:
        return {"status": "success"}
    if req.password != state.lock_password:
        return {"status": "error", "message": "Sai mật khẩu mở khóa!"}
    state.is_locked = False
    state.lock_password = None
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

@app.post("/api/start")
async def start_bombing(req: StartRequest):
    if state.is_locked:
        return {"status": "error", "message": "Hệ thống đang bị khóa!"}
    if state.is_running:
        return {"status": "error", "message": "Chiến dịch thả bom đã đang chạy!"}
    
    parsed_apis = []
    for cfg in req.apis:
        req_data = CurlParser.parse(cfg.curl)
        if not req_data["url"]: continue
        
        if req.token and "X-Authorization" not in req_data["headers"]:
            req_data["headers"]["X-Authorization"] = f"Bearer {req.token}"
            
        req_data["rate"] = cfg.rate
        req_data["step"] = cfg.step
        parsed_apis.append(req_data)
        
    if not parsed_apis:
        return {"status": "error", "message": "Không có API hợp lệ nào để test."}
        
    state.is_running = True
    state.stats = {"success": 0, "fail": 0}
    state.logs = []
    state.threshold_alerts = []
    state.login_config = {
        "url": req.login_url,
        "username": req.username,
        "password": req.password
    }
    state.current_token = req.token
    
    push_log(f"Đã nạp {len(parsed_apis)} API. Bắt đầu tổng tấn công...")
    
    asyncio.create_task(bomb_manager(parsed_apis))
    return {"status": "success"}

@app.post("/api/stop")
async def stop_bombing():
    if state.is_locked:
        return {"status": "error", "message": "Hệ thống đang bị khóa!"}
    state.is_running = False
    push_log("Đã nhận lệnh DỪNG thả bom.")
    return {"status": "success"}

@app.get("/api/status")
async def get_status():
    logs = state.logs.copy()
    state.logs.clear() # Trả về rồi xóa đi để đỡ tốn băng thông
    return {
        "is_locked": state.is_locked,
        "is_running": state.is_running,
        "stats": state.stats,
        "logs": logs,
        "thresholds": state.threshold_alerts
    }

@app.post("/api/start_basic")
async def start_basic(req: StartBasicRequest):
    if state.is_locked:
        return {"status": "error", "message": "Hệ thống đang bị khóa!"}
    if state.is_basic_running:
        return {"status": "error", "message": "Kiểm tra cơ bản đang chạy!"}
    
    parsed_apis = []
    for cfg in req.apis:
        req_data = CurlParser.parse(cfg.curl)
        if not req_data["url"]: continue
        
        if req.token and "X-Authorization" not in req_data["headers"]:
            req_data["headers"]["X-Authorization"] = f"Bearer {req.token}"
            
        req_data["interval"] = cfg.interval
        parsed_apis.append(req_data)
        
    if not parsed_apis:
        return {"status": "error", "message": "Không có API hợp lệ nào để test."}
        
    state.is_basic_running = True
    state.basic_stats = {"success": 0, "fail": 0}
    state.basic_logs = []
    state.login_config = {
        "url": req.login_url,
        "username": req.username,
        "password": req.password
    }
    state.current_token = req.token
    
    push_basic_log(f"Đã nạp {len(parsed_apis)} API. Bắt đầu kiểm tra cơ bản...")
    
    asyncio.create_task(basic_test_manager(parsed_apis))
    return {"status": "success"}

@app.post("/api/stop_basic")
async def stop_basic():
    if state.is_locked:
        return {"status": "error", "message": "Hệ thống đang bị khóa!"}
    state.is_basic_running = False
    push_basic_log("Đã nhận lệnh DỪNG kiểm tra cơ bản.")
    return {"status": "success"}

@app.get("/api/status_basic")
async def get_status_basic():
    logs = state.basic_logs.copy()
    state.basic_logs.clear()
    return {
        "is_locked": state.is_locked,
        "is_running": state.is_basic_running,
        "stats": state.basic_stats,
        "logs": logs
    }

async def bomb_manager(parsed_apis):
    connector = aiohttp.TCPConnector(limit=0)
    async with aiohttp.ClientSession(connector=connector) as session:
        for api in parsed_apis:
            task = asyncio.create_task(fire_api(session, api))
            state.tasks.append(task)
            
        await asyncio.gather(*state.tasks, return_exceptions=True)
        
    state.is_running = False
    state.tasks.clear()
    push_log("Chiến dịch thả bom đã kết thúc.")

async def fire_api(session, api):
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
        if not state.is_running or has_failed: return
        
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
                    state.stats["success"] += 1
                    await res.read()
                elif res.status == 401 and state.login_config.get("url"):
                    async with state.token_lock:
                        current_auth = api["headers"].get("X-Authorization")
                        if current_auth != f"Bearer {state.current_token}":
                            # Another task refreshed it
                            api["headers"]["X-Authorization"] = f"Bearer {state.current_token}"
                            return await do_request() # Retry
                        else:
                            login_url = f"{state.login_config['url'].rstrip('/')}/api/auth/login"
                            login_data = {"username": state.login_config['username'], "password": state.login_config['password']}
                            async with session.post(login_url, json=login_data) as login_res:
                                if login_res.status == 200:
                                    data = await login_res.json()
                                    state.current_token = data.get("token")
                                    api["headers"]["X-Authorization"] = f"Bearer {state.current_token}"
                                    push_log("🔄 Token hết hạn. Đã tự động gia hạn Token mới thành công!")
                                    return await do_request() # Retry
                                else:
                                    state.stats["fail"] += 1
                                    push_log(f"❌ Gia hạn Token thất bại! HTTP {login_res.status}")
                else:
                    state.stats["fail"] += 1
                    err_txt = await res.text()
                    if state.is_running and not has_failed:
                        has_failed = True
                        push_log(f"💣 LỖI CHÍ MẠNG: Server gục ngã ở ngưỡng {current_rate} req/s. HTTP {res.status}: {err_txt[:100]}")
                        state.threshold_alerts.append(f"Ngưỡng chết: {current_rate} req/s (HTTP {res.status})")
                        state.is_running = False
        except Exception as e:
            state.stats["fail"] += 1
            if state.is_running and not has_failed:
                has_failed = True
                push_log(f"💣 LỖI NGOẠI LỆ: Server sập ở mức {current_rate} req/s. Lỗi: {str(e)}")
                state.threshold_alerts.append(f"Ngưỡng chết: {current_rate} req/s (Network Error)")
                state.is_running = False
        finally:
            active_tasks -= 1

    while state.is_running and not has_failed:
        if active_tasks > 100:
            has_failed = True
            state.is_running = False
            push_log(f"⚠️ MẠCH BẢO VỆ: Server bị treo đơ ở ngưỡng {current_rate} req/s (100 reqs pending).")
            state.threshold_alerts.append(f"Treo đơ ở: {current_rate} req/s")
            break

        start_time = time.time()
        
        if start_time - last_step_time >= 5.0:
            current_rate += step
            last_step_time = start_time
            push_log(f"[TĂNG TỐC] Tăng tốc độ bắn lên {current_rate} req/s")
            
        sleep_time = 1.0 / current_rate if current_rate > 0 else 0.01
        
        asyncio.create_task(do_request())
            
        elapsed = time.time() - start_time
        if elapsed < sleep_time:
            await asyncio.sleep(sleep_time - elapsed)

async def basic_test_manager(parsed_apis):
    connector = aiohttp.TCPConnector(limit=0)
    async with aiohttp.ClientSession(connector=connector) as session:
        for api in parsed_apis:
            task = asyncio.create_task(fire_basic_api(session, api))
            state.basic_tasks.append(task)
            
        await asyncio.gather(*state.basic_tasks, return_exceptions=True)
        
    state.is_basic_running = False
    state.basic_tasks.clear()
    push_basic_log("Chiến dịch kiểm tra cơ bản đã kết thúc.")

async def fire_basic_api(session, api):
    interval = api["interval"]
    url = api["url"]
    method = api["method"]
    headers = api["headers"]
    data = api["data"]
    
    while state.is_basic_running:
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
                    state.basic_stats["success"] += 1
                    push_basic_log(f"✅ Gửi thành công tới {url} (HTTP {res.status})")
                    await res.read()
                elif res.status == 401 and state.login_config.get("url"):
                    async with state.token_lock:
                        current_auth = api["headers"].get("X-Authorization")
                        if current_auth != f"Bearer {state.current_token}":
                            # Another task refreshed it
                            api["headers"]["X-Authorization"] = f"Bearer {state.current_token}"
                        else:
                            login_url = f"{state.login_config['url'].rstrip('/')}/api/auth/login"
                            login_data = {"username": state.login_config['username'], "password": state.login_config['password']}
                            async with session.post(login_url, json=login_data) as login_res:
                                if login_res.status == 200:
                                    data = await login_res.json()
                                    state.current_token = data.get("token")
                                    api["headers"]["X-Authorization"] = f"Bearer {state.current_token}"
                                    push_basic_log("🔄 Token hết hạn. Đã tự động gia hạn Token mới thành công!")
                                else:
                                    state.basic_stats["fail"] += 1
                                    push_basic_log(f"❌ Gia hạn Token thất bại! HTTP {login_res.status}")
                else:
                    state.basic_stats["fail"] += 1
                    err_txt = await res.text()
                    # Cắt chuỗi lỗi ở 200 ký tự để tránh tràn UI nhưng vẫn đủ chi tiết
                    push_basic_log(f"❌ Lỗi HTTP {res.status} tại {url}: {err_txt[:200]}")
        except Exception as e:
            state.basic_stats["fail"] += 1
            push_basic_log(f"❌ Lỗi Mạng tại {url}: {str(e)}")
            
        elapsed = time.time() - start_time
        if elapsed < interval:
            await asyncio.sleep(interval - elapsed)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=5000, reload=True)
