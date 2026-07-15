import os
import re
import sys
import time
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

def get_sim_processes():
    procs = []
    raw_list = [] # list of (pid, command_line)
    if os.name == 'nt':
        try:
            cmd = 'wmic process where "name=\'python.exe\' or name=\'pythonw.exe\'" get ProcessId,CommandLine'
            out = subprocess.check_output(cmd, shell=True).decode(errors='ignore')
            lines = out.strip().split('\n')
            for line in lines[1:]:
                line = line.strip()
                if not line: continue
                parts = line.split()
                if len(parts) >= 2:
                    pid_str = parts[-1]
                    command_line = " ".join(parts[:-1])
                    if pid_str.isdigit() and "script_tool_simulator_device_" in command_line:
                        raw_list.append((int(pid_str), command_line))
        except Exception as e:
            print("Error getting simulator PIDs on Windows:", e)
    else:
        try:
            # Dùng ps -ef để quét tiến trình trên Linux/Ubuntu
            out = subprocess.check_output('ps -ef', shell=True).decode(errors='ignore')
            lines = out.strip().split('\n')
            for line in lines:
                if "script_tool_simulator_device_" in line and "grep" not in line:
                    parts = line.split()
                    if len(parts) >= 2:
                        pid_str = parts[1] # Cột thứ 2 của ps -ef là PID
                        if pid_str.isdigit():
                            raw_list.append((int(pid_str), line))
        except Exception as e:
            print("Error getting simulator PIDs on Linux:", e)

    # Đọc cấu hình từ từng file script đang chạy
    for pid, cmdline in raw_list:
        match = re.search(r'(script_tool_simulator_device_\d+\.py)', cmdline)
        if match:
            script_name = match.group(1)
            script_path = os.path.join("folder_script", script_name)
            
            num_dev = 0
            start_index = 0
            code_prefix = ""
            id_prefix = ""
            broker_host = ""
            
            if os.path.exists(script_path):
                try:
                    with open(script_path, "r", encoding="utf-8") as f:
                        content = f.read()
                        m_num = re.search(r'NUM_DEV\s*=\s*(\d+)', content)
                        m_start = re.search(r'START_INDEX\s*=\s*(\d+)', content)
                        m_code = re.search(r'DEVICE_CODE_PREFIX\s*=\s*["\'](.*?)["\']', content)
                        m_id = re.search(r'DEVICE_ID_PREFIX\s*=\s*["\'](.*?)["\']', content)
                        m_host = re.search(r'BROKER_HOST\s*=\s*["\'](.*?)["\']', content)
                        
                        if m_num: num_dev = int(m_num.group(1))
                        if m_start: start_index = int(m_start.group(1))
                        if m_code: code_prefix = m_code.group(1)
                        if m_id: id_prefix = m_id.group(1)
                        if m_host: broker_host = m_host.group(1)
                except:
                    pass
            
            procs.append({
                "pid": pid,
                "script_name": script_name,
                "num_dev": num_dev,
                "start_index": start_index,
                "device_code_prefix": code_prefix,
                "device_id_prefix": id_prefix,
                "broker_host": broker_host
            })
    return procs

def parse_device_sim_logs(active_scripts):
    total_stats = {
        "connected": 0,
        "disconnected": 0,
        "sent": 0,
        "received": 0,
        "rpc_sent": 0,
        "success_rate": 0.0
    }
    
    for script in active_scripts:
        match = re.search(r'script_tool_simulator_device_(.*?)\.py', script)
        if not match: continue
        suffix = match.group(1)
        log_path = os.path.abspath(f"logs/device_sim_{suffix}.log")
        if not os.path.exists(log_path): continue
        
        try:
            with open(log_path, "r", encoding="utf-8", errors="ignore") as f:
                f.seek(0, os.SEEK_END)
                size = f.tell()
                # Đọc 2000 ký tự cuối của từng log file
                f.seek(max(0, size - 2000))
                content = f.read()
                matches = re.findall(
                    r"Connected:\s*(\d+),\s*Disconnected:\s*(\d+),\s*Sent:\s*(\d+),\s*Received:\s*(\d+),\s*RPC Sent:\s*(\d+)",
                    content
                )
                if matches:
                    last = matches[-1]
                    total_stats["connected"] += int(last[0])
                    total_stats["disconnected"] += int(last[1])
                    total_stats["sent"] += int(last[2])
                    total_stats["received"] += int(last[3])
                    total_stats["rpc_sent"] += int(last[4])
        except:
            pass
            
    if total_stats["sent"] > 0:
        total_stats["success_rate"] = (total_stats["received"] / total_stats["sent"]) * 100
        
    return total_stats

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

class StopRequest(BaseModel):
    pid: int = None

@app.post("/api/start")
async def start_sim():
    try:
        # Đọc cấu hình hiện tại
        config = DEFAULT_CONFIG.copy()
        if os.path.exists(CONFIG_PATH):
            try:
                with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                    config.update(json.load(f))
            except:
                pass

        # Tính toán ID thiết bị đầu tiên và cuối cùng để đặt tên hậu tố theo chuẩn cấu hình
        max_val = config['START_INDEX'] + config['NUM_DEV']
        padding_len = max(3, len(str(max_val)))
        
        first_num = config['START_INDEX'] + 1
        first_dev = f"{config['DEVICE_CODE_PREFIX']}{first_num:0{padding_len}d}"
        
        last_num = config['START_INDEX'] + config['NUM_DEV']
        last_dev = f"{config['DEVICE_CODE_PREFIX']}{last_num:0{padding_len}d}"
        
        broker_safe = config['BROKER_HOST'].replace('.', '_').replace(':', '_')
        suffix = f"{first_dev}_{last_dev}__{broker_safe}"
        
        script_name = f"script_tool_simulator_device_{suffix}.py"
        script_path = os.path.abspath(os.path.join("folder_script", script_name))
        log_path = os.path.abspath(os.path.join("logs", f"device_sim_{suffix}.log"))

        # Kiểm tra xem dải này có đang chạy sẵn hay không để tránh trùng lắp
        active_procs = get_sim_processes()
        if any(p["script_name"] == script_name for p in active_procs):
            return {"status": "error", "message": f"Dải thiết bị {first_dev} ➔ {last_dev} đã đang chạy ngầm sẵn rồi!"}

        # Tạo thư mục folder_script và logs nếu chưa có
        os.makedirs("folder_script", exist_ok=True)
        os.makedirs("logs", exist_ok=True)

        # Tạo cấu hình thay thế
        config_lines = f"""# === CONFIG_START ===
# Default parameters (Fallback)
BROKER_HOST = "{config['BROKER_HOST']}"
BROKER_PORT = {config['BROKER_PORT']}
NUM_DEV = {config['NUM_DEV']}
START_INDEX = {config['START_INDEX']}
DEVICE_CODE_PREFIX = "{config['DEVICE_CODE_PREFIX']}"
DEVICE_ID_PREFIX = "{config['DEVICE_ID_PREFIX']}"
TELEMETRY_INTERVAL = {config['TELEMETRY_INTERVAL']}
LOG_FILE_CSV = "logs/device_stats_{suffix}.csv"
LOG_INTERVAL = {config['LOG_INTERVAL']}
TELEMETRY_TOPIC = "{config['TELEMETRY_TOPIC']}"
RPC_REQUEST_TOPIC = "{config['RPC_REQUEST_TOPIC']}"
TELEMETRY_DATA = {repr(config['TELEMETRY_DATA'])}
RESPONSE_RPC = "{config['RESPONSE_RPC']}"
RESPONSE_RPC_SKIP_START = {config['RESPONSE_RPC_SKIP_START']}
RESPONSE_RPC_SKIP_END = {config['RESPONSE_RPC_SKIP_END']}
# === CONFIG_END ==="""

        # Đọc simulator.py làm file mẫu
        template_path = os.path.abspath("simulator.py")
        if not os.path.exists(template_path):
            return {"status": "error", "message": "Không tìm thấy file mẫu simulator.py!"}

        with open(template_path, "r", encoding="utf-8") as f:
            code = f.read()

        # Thay thế khối kịch bản cấu hình
        pattern = r"# === CONFIG_START ===.*?# === CONFIG_END ==="
        new_code = re.sub(pattern, config_lines, code, flags=re.DOTALL)

        # Ghi file kịch bản tự chứa mới
        with open(script_path, "w", encoding="utf-8") as f:
            f.write(new_code)

        # Khởi chạy bằng python với mã hóa UTF-8 bắt buộc
        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "utf-8"
        
        log_file = open(log_path, "w", encoding="utf-8")
        if os.name == 'nt':
            subprocess.Popen([sys.executable, script_path], stdout=log_file, stderr=log_file, env=env)
        else:
            cmd = f"nohup {sys.executable} {script_path} > {log_path} 2>&1 &"
            subprocess.Popen(cmd, shell=True, env=env)
            
        return {"status": "success"}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.post("/api/stop")
async def stop_sim(req: StopRequest = None):
    pids = [req.pid] if (req and req.pid) else [p["pid"] for p in get_sim_processes()]
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
    procs = get_sim_processes()
    active_scripts = [p["script_name"] for p in procs]
    stats = parse_device_sim_logs(active_scripts)
    return {
        "is_running": len(procs) > 0,
        "processes": procs,
        "stats": stats,
        "logs": []
    }
