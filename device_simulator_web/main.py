import os
import re
import subprocess
import glob
import json
from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

app = FastAPI(title="Device Simulator Web Controller")

# Đảm bảo các thư mục static và templates tồn tại
os.makedirs("static/css", exist_ok=True)
os.makedirs("static/js", exist_ok=True)
os.makedirs("templates", exist_ok=True)

# Cấu hình static files và templates
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

# Định nghĩa đường dẫn cấu hình và log
CONFIG_PATH = os.path.abspath("device_config.json")
LOG_PATH = os.path.abspath("device_sim.log")
TOOLS_DEVICE_DIR = os.path.abspath("../ToolsDevice")

# Cấu hình mặc định của Device1.py
DEFAULT_CONFIG = {
    "BROKER_HOST": "36.50.232.86",
    "BROKER_PORT": 1883,
    "NUM_DEV": 165,
    "START_INDEX": 0,
    "DEVICE_CODE_PREFIX": "b",
    "DEVICE_ID_PREFIX": "rd_",
    "TELEMETRY_INTERVAL": 50,
    "LOG_FILE_CSV": "logs/device_stats.csv",
    "LOG_INTERVAL": 60,
    "TELEMETRY_TOPIC": "v1/devices/me/telemetry",
    "RPC_REQUEST_TOPIC": "v1/devices/me/rpc/request/{}",
    "RESPONSE_RPC": "true",
    "RESPONSE_RPC_SKIP_START": 0,
    "RESPONSE_RPC_SKIP_END": 0,
    "TELEMETRY_DATA": {
        "mode": 1,
        "relay1": False,
        "relay2": False,
        "dim": 0,
        "vercode": "0.0.13"
    }
}

class ConfigModel(BaseModel):
    BROKER_HOST: str
    BROKER_PORT: int
    NUM_DEV: int
    START_INDEX: int
    DEVICE_CODE_PREFIX: str
    DEVICE_ID_PREFIX: str
    TELEMETRY_INTERVAL: int
    LOG_FILE_CSV: str
    LOG_INTERVAL: int
    TELEMETRY_TOPIC: str
    RPC_REQUEST_TOPIC: str
    RESPONSE_RPC: str
    RESPONSE_RPC_SKIP_START: int
    RESPONSE_RPC_SKIP_END: int
    TELEMETRY_DATA: dict

def get_locust_pids():
    pids = []
    if os.name == 'nt':
        try:
            # Sử dụng wmic để quét các tiến trình chạy python/locust có chứa Device1.py
            cmd = 'wmic process where "name=\'python.exe\' or name=\'pythonw.exe\' or name=\'locust.exe\'" get ProcessId,CommandLine'
            out = subprocess.check_output(cmd, shell=True).decode(errors='ignore')
            lines = out.strip().split('\n')
            for line in lines[1:]: # bỏ qua tiêu đề
                line = line.strip()
                if not line: continue
                parts = line.split()
                if len(parts) >= 2:
                    pid_str = parts[-1]
                    command_line = " ".join(parts[:-1])
                    if pid_str.isdigit() and "Device1.py" in command_line:
                        pids.append(int(pid_str))
        except Exception as e:
            print("Error getting locust pids on Windows:", e)
    else:
        try:
            out = subprocess.check_output('pgrep -f "locust -f Device1.py"', shell=True).decode().strip()
            if out:
                pids = [int(p) for p in out.split() if p.isdigit()]
        except:
            pass
    return pids

def parse_device_sim_log():
    if not os.path.exists(LOG_PATH):
        return {"connected": 0, "disconnected": 0, "sent": 0, "received": 0, "rpc_sent": 0, "success_rate": 0}
    try:
        with open(LOG_PATH, "r", encoding="utf-8", errors="ignore") as f:
            # Đọc khoảng 4000 ký tự cuối để phân tích cho nhanh
            f.seek(0, os.SEEK_END)
            size = f.tell()
            f.seek(max(0, size - 4000))
            content = f.read()
            
            # Quét các mẫu log tổng hợp định kỳ
            # Line 1: [YYYY-MM-DD HH:MM:SS] Connected: ...
            # Line 2: RPC Resp ... Success Rate: ...
            matches = re.findall(
                r"\[([\d\-\s:]+)\]\s*Connected:\s*(\d+),\s*Disconnected:\s*(\d+),\s*Sent:\s*(\d+),\s*Received:\s*(\d+),\s*RPC Sent:\s*(\d+)\s*\n\s*RPC Resp [^\n]* Success Rate:\s*([\d\.]+)%",
                content
            )
            if matches:
                last = matches[-1]
                return {
                    "time": last[0],
                    "connected": int(last[1]),
                    "disconnected": int(last[2]),
                    "sent": int(last[3]),
                    "received": int(last[4]),
                    "rpc_sent": int(last[5]),
                    "success_rate": float(last[6])
                }
    except Exception as e:
        print("Error parsing device_sim.log:", e)
    return {"connected": 0, "disconnected": 0, "sent": 0, "received": 0, "rpc_sent": 0, "success_rate": 0}

@app.get("/")
async def root(request: Request):
    return templates.TemplateResponse(request=request, name="index.html")

@app.get("/api/config")
async def get_config():
    config = DEFAULT_CONFIG.copy()
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
                for k, v in data.items():
                    config[k] = v
        except:
            pass
    return config

@app.post("/api/config")
async def save_config(cfg: ConfigModel):
    try:
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(cfg.model_dump(), f, indent=4, ensure_ascii=False)
        return {"status": "success"}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.post("/api/start")
async def start_sim():
    pids = get_locust_pids()
    if pids:
        return {"status": "error", "message": "Tool Device Simulator đã đang chạy sẵn!"}
    
    try:
        # Xóa file log cũ trước khi khởi động mới
        if os.path.exists(LOG_PATH):
            try: os.remove(LOG_PATH)
            except: pass
            
        # Xác định file locust thực thi trong venv hoặc hệ thống
        if os.name == 'nt':
            venv_locust = os.path.join(TOOLS_DEVICE_DIR, "../venv/Scripts/locust.exe")
            locust_bin = venv_locust if os.path.exists(venv_locust) else "locust"
            # Trên Windows, chạy Popen với stdout hướng vào file log
            log_file = open(LOG_PATH, "w", encoding="utf-8")
            subprocess.Popen([locust_bin, "-f", "Device1.py", "--web-host", "0.0.0.0", "--web-port", "6366"], cwd=TOOLS_DEVICE_DIR, stdout=log_file, stderr=log_file)
        else:
            venv_locust = os.path.join(TOOLS_DEVICE_DIR, "../venv/bin/locust")
            locust_bin = venv_locust if os.path.exists(venv_locust) else "locust"
            cmd = f"nohup {locust_bin} -f Device1.py --web-host 0.0.0.0 --web-port 6366 > device_sim.log 2>&1 &"
            subprocess.Popen(cmd, shell=True, cwd=TOOLS_DEVICE_DIR)
            
        return {"status": "success"}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.post("/api/stop")
async def stop_sim():
    pids = get_locust_pids()
    if not pids:
        return {"status": "error", "message": "Không tìm thấy tiến trình nào đang chạy."}
    
    try:
        for pid in pids:
            if os.name == 'nt':
                subprocess.call(f"taskkill /F /PID {pid}", shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            else:
                subprocess.call(f"kill -9 {pid}", shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return {"status": "success"}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.get("/api/status")
async def get_status():
    pids = get_locust_pids()
    is_running = len(pids) > 0
    stats = parse_device_sim_log()
    
    logs = []
    if os.path.exists(LOG_PATH):
        try:
            with open(LOG_PATH, "r", encoding="utf-8", errors="ignore") as f:
                lines = f.readlines()
                logs = [line.rstrip() for line in lines[-100:]] # lấy 100 dòng cuối
        except:
            pass
            
    return {
        "is_running": is_running,
        "stats": stats,
        "logs": logs
    }
