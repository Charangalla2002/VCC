"""
run_all.py -- Unified launcher script for VCC application components.

Runs:
1. Backend API (FastAPI, Port 8000)
2. Detection Layer (GStreamer + YOLO, Port 8001)
3. Frontend Dev Server (Vite React UI, Port 5173)

Monitors all processes and handles graceful shutdown (Ctrl+C).
"""

import sys
import os
import subprocess
import threading
import time
import shutil
import socket

def log_reader(pipe, prefix, color_code):
    """Reads lines from a subprocess pipe and logs them with a prefix in color."""
    reset = "\033[0m"
    try:
        for line in iter(pipe.readline, ''):
            if not line:
                break
            print(f"{color_code}{prefix}{reset} {line.strip()}")
    except Exception:
        pass

def get_npm_cmd():
    """Locate npm executable across Windows, Linux, and WSL environments."""
    if os.name == "nt":
        return shutil.which("npm.cmd") or "npm.cmd"
    return shutil.which("npm") or "npm"

def get_wsl_ip():
    """Detect if running inside WSL and return the primary eth0 IP address."""
    try:
        if os.path.exists("/proc/version"):
            with open("/proc/version", "r") as f:
                if "microsoft" in f.read().lower():
                    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                    s.connect(("8.8.8.8", 80))
                    ip = s.getsockname()[0]
                    s.close()
                    return ip
    except Exception:
        pass
    return None

def check_port_in_use(port: int) -> bool:
    """Check if a local TCP port is already open/bound."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(0.5)
            return s.connect_ex(('127.0.0.1', port)) == 0
    except Exception:
        return False

def main():
    # Locate virtualenv python
    venv_python = (
        os.path.join("backend", "venv", "Scripts", "python.exe")
        if os.name == "nt"
        else os.path.join("backend", "venv", "bin", "python")
    )
    if not os.path.isfile(venv_python):
        venv_python = sys.executable
    else:
        venv_python = os.path.abspath(venv_python)

    # Check for GStreamer disable option in backend/.env
    disable_gst = False
    env_path = os.path.join("backend", ".env")
    if os.path.isfile(env_path):
        try:
            with open(env_path, "r") as f:
                for line in f:
                    if line.strip().startswith("VCC_DISABLE_GST"):
                        parts = line.strip().split("=")
                        if len(parts) >= 2:
                            disable_gst = parts[1].strip().lower() == "true"
        except Exception:
            pass

    # Setup GStreamer path configuration for detection subprocess
    gst_root = r"C:\Users\Charan Galla\AppData\Local\Programs\gstreamer\1.0\msvc_x86_64"
    gst_bin = os.path.join(gst_root, "bin")
    gst_typelibs = os.path.join(gst_root, "lib", "girepository-1.0")
    local_bin = os.path.abspath(os.path.join("detection", "bin"))

    # Copy current environment and update paths for child processes
    env = os.environ.copy()
    env["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = "rtsp_transport;tcp|buffer_size;10240000|max_delay;500000"
    if not disable_gst and os.path.isdir(gst_bin):
        env["PATH"] = gst_bin + os.pathsep + local_bin + os.pathsep + env.get("PATH", "")
        env["GI_TYPELIB_PATH"] = gst_typelibs

    processes = []

    # -- Color codes --
    cyan = "\033[36m"
    green = "\033[32m"
    yellow = "\033[33m"
    magenta = "\033[35m"
    red = "\033[31m"
    reset = "\033[0m"

    print("=" * 70)
    print(f"{cyan}VCC UNIFIED SERVICE LAUNCHER{reset}")
    print("=" * 70)

    wsl_ip = get_wsl_ip()
    if wsl_ip:
        print(f"{yellow}[SYSTEM INFO] WSL Environment Detected! WSL IP: {wsl_ip}{reset}")
        print(f"{yellow}[SYSTEM INFO] Frontend will bind to 0.0.0.0 (Accessible via http://{wsl_ip}:5173 or http://localhost:5173){reset}\n")

    # Check node_modules in frontend
    node_modules = os.path.join("frontend", "node_modules")
    npm_cmd = get_npm_cmd()
    if not os.path.exists(node_modules):
        print(f"{yellow}[SYSTEM] 'frontend/node_modules' missing. Running 'npm install'...{reset}")
        try:
            subprocess.run([npm_cmd, "install"], cwd="frontend", check=True, shell=(os.name != "nt"))
        except Exception as e:
            print(f"{red}[SYSTEM ERROR] Failed to run 'npm install': {e}{reset}")

    try:
        # 1. Start Backend API
        print(f"{green}[SYSTEM] Starting Backend API (Port 8000)...{reset}")
        backend_proc = subprocess.Popen(
            [venv_python, "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"],
            cwd="backend",
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
            env=env
        )
        processes.append(("BACKEND", backend_proc))
        
        threading.Thread(target=log_reader, args=(backend_proc.stdout, "[BACKEND]", green), daemon=True).start()
        threading.Thread(target=log_reader, args=(backend_proc.stderr, "[BACKEND]", green), daemon=True).start()

        # 1b. Start Training Dedicated Server
        print(f"{magenta}[SYSTEM] Starting Training Dedicated Server (Port 8002)...{reset}")
        training_proc = subprocess.Popen(
            [venv_python, "-m", "uvicorn", "training_app:app", "--host", "0.0.0.0", "--port", "8002"],
            cwd="backend",
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
            env=env
        )
        processes.append(("TRAINING", training_proc))
        
        threading.Thread(target=log_reader, args=(training_proc.stdout, "[TRAINING]", magenta), daemon=True).start()
        threading.Thread(target=log_reader, args=(training_proc.stderr, "[TRAINING]", magenta), daemon=True).start()

        time.sleep(2)

        # 2. Start Detection Layer
        print(f"{yellow}[SYSTEM] Starting Detection Layer (GStreamer + YOLO, Port 8001)...{reset}")
        detection_proc = subprocess.Popen(
            [venv_python, "start_detection.py"],
            cwd=".",
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
            env=env
        )
        processes.append(("DETECTION", detection_proc))

        threading.Thread(target=log_reader, args=(detection_proc.stdout, "[DETECTION]", yellow), daemon=True).start()
        threading.Thread(target=log_reader, args=(detection_proc.stderr, "[DETECTION]", yellow), daemon=True).start()

        # 3. Start Frontend Dev Server
        print(f"{cyan}[SYSTEM] Starting Frontend Dev Server (Vite, Port 5173)...{reset}")
        use_shell = (os.name != "nt")
        frontend_proc = subprocess.Popen(
            [npm_cmd, "run", "dev"] if not use_shell else f"{npm_cmd} run dev",
            cwd="frontend",
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
            env=env,
            shell=use_shell
        )
        processes.append(("FRONTEND", frontend_proc))

        threading.Thread(target=log_reader, args=(frontend_proc.stdout, "[FRONTEND]", cyan), daemon=True).start()
        threading.Thread(target=log_reader, args=(frontend_proc.stderr, "[FRONTEND]", cyan), daemon=True).start()

        # 4. Start Isolated Training Studio UI
        print(f"{magenta}[SYSTEM] Starting Isolated Training Studio UI (Vite, Port 5174)...{reset}")
        training_frontend_proc = subprocess.Popen(
            [npm_cmd, "run", "dev:training"] if not use_shell else f"{npm_cmd} run dev:training",
            cwd="frontend",
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
            env=env,
            shell=use_shell
        )
        processes.append(("TRAINING-UI", training_frontend_proc))

        threading.Thread(target=log_reader, args=(training_frontend_proc.stdout, "[TRAINING-UI]", magenta), daemon=True).start()
        threading.Thread(target=log_reader, args=(training_frontend_proc.stderr, "[TRAINING-UI]", magenta), daemon=True).start()

        print(f"\n{green}[SYSTEM] All 5 microservices running! Press Ctrl+C to terminate all services.{reset}\n")

        if wsl_ip:
            print(f"{cyan}➜ Dashboard (WSL):    http://{wsl_ip}:5173/{reset}")
            print(f"{cyan}➜ Dashboard (Local):  http://localhost:5173/{reset}")
            print(f"{magenta}➜ Training UI (WSL):  http://{wsl_ip}:5174/{reset}")
            print(f"{magenta}➜ Training UI (Local):http://localhost:5174/{reset}\n")

        # Monitor loop
        while True:
            for name, proc in processes:
                code = proc.poll()
                if code is not None:
                    print(f"{red}[SYSTEM] {name} process exited unexpectedly with code {code}.{reset}")
                    raise KeyboardInterrupt
            time.sleep(1)

    except KeyboardInterrupt:
        print(f"\n{red}[SYSTEM] Terminating all services...{reset}")
        for name, proc in processes:
            print(f"  Stopping {name}...")
            if os.name == "nt":
                subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            else:
                proc.terminate()
                
        for _, proc in processes:
            try:
                proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                proc.kill()
        print(f"{green}[SYSTEM] All services cleanly terminated.{reset}")

if __name__ == "__main__":
    main()
