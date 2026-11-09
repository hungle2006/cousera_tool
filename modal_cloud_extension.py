"""Coursera Control Center: interactive cloud Chromium + existing MV3 extension.

Deploys a separate Modal app. Uses noVNC behind nginx Basic Auth for manual login.
Cloudflare token is injected into extension storage, never into HTML or logs.
Does NOT log in automatically, complete lessons, or submit assessments.

PowerShell:
  modal deploy modal_cloud_extension.py --env main
  modal run --detach --env main modal_cloud_extension.py::start --minutes 45
  modal run --env main modal_cloud_extension.py::status
  modal run --env main modal_cloud_extension.py::stop
"""
from __future__ import annotations

import json
import hmac
import os
import re
import secrets
import shutil
import subprocess
import tempfile
import time
import uuid
from datetime import datetime, timezone, timedelta
from pathlib import Path
from urllib.parse import urlparse

import modal
from fastapi import Request, HTTPException

APP = "coursera-cloud-extension-v1"
VOLUME_NAME = "coursera-cloud-extension-profile-v1"
DICT_NAME = "coursera-cloud-extension-control-v1"
SECRET_NAME = "coursera-cloud-extension-v1"
DATA = Path("/data")
STATE = DATA / "cloud-status.json"
PROFILE = DATA / "chrome-profile"
LOCAL_PROFILE = Path("/tmp/cloud-chrome-profile")
EXT = Path("/app/extension")
VNC_PORT = 6080
SCREEN = "1365x850x24"
WORKER_DEFAULT = "https://coursera-ai-control-v5.hungle06-01-01.workers.dev"
COURSE_DEFAULT = "https://www.coursera.org/"

app = modal.App(APP)
volume = modal.Volume.from_name(VOLUME_NAME, create_if_missing=True)
control = modal.Dict.from_name(DICT_NAME, create_if_missing=True)

browser_image = (
    modal.Image.debian_slim(python_version="3.11")
    .apt_install(
        "xvfb", "x11vnc", "fluxbox", "novnc", "websockify", "nginx",
        "apache2-utils", "fonts-liberation", "fonts-noto-core", "procps", "ca-certificates",
    )
    .pip_install("playwright==1.56.0", "httpx==0.28.1", "fastapi[standard]")
    .run_commands("python -m playwright install --with-deps chromium")
    .add_local_dir("./extension", "/app/extension", copy=True)
)
status_image = modal.Image.debian_slim(python_version="3.11").pip_install("fastapi[standard]", "httpx==0.28.1")


def iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def validate_config(worker_url: str, extension_token: str, password: str) -> str:
    parsed = urlparse(worker_url)
    if parsed.scheme != "https" or not parsed.hostname or parsed.port or parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.path not in ("", "/"):
        raise ValueError("CLOUDFLARE_WORKER_URL phải là HTTPS origin, không có đường dẫn/tham số")
    if not re.fullmatch(r"ccc_[a-f0-9]{64}", extension_token):
        raise ValueError("EXTENSION_TOKEN không đúng định dạng. Đổi token trong dashboard rồi nhập vào Modal Secret.")
    if len(password) < 20 or len(password) > 256 or "\n" in password or "\r" in password:
        raise ValueError("REMOTE_ACCESS_PASSWORD tối thiểu 20 ký tự, không có xuống dòng")
    return worker_url.rstrip("/")


def write_state(update: dict, *, commit: bool = True):
    control["snapshot"] = update.copy()
    STATE.parent.mkdir(parents=True, exist_ok=True)
    tmp = STATE.with_suffix(".tmp")
    tmp.write_text(json.dumps(update, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(STATE)
    if commit:
        volume.commit()


def start_process(args: list[str], *, env=None, output=None):
    """Subprocesses stay in the cloud container; stdout goes to /tmp logs."""
    stream = open(output, "ab", buffering=0) if output else subprocess.DEVNULL
    proc = subprocess.Popen(args, env=env, stdout=stream, stderr=subprocess.STDOUT, start_new_session=True)
    return proc


def prepare_proxy(password: str):
    # Authenticates both noVNC HTML and its WebSocket transport. VNC is loopback-only.
    from grp import getgrnam
    pwfile = "/tmp/cloud-viewer.htpasswd"
    subprocess.run(["htpasswd", "-iB", "-c", pwfile, "admin"], input=password+"\n", text=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, check=True)
    os.chown(pwfile, 0, getgrnam("www-data").gr_gid)
    os.chmod(pwfile, 0o640)
    conf = r"""
    pid /tmp/nginx-cloud.pid;
    events { worker_connections 128; }
    http {
      access_log off;
      include /etc/nginx/mime.types;
      server {
        listen 6080;
        server_name _;
        client_max_body_size 1m;
        auth_basic "Private Modal Cloud Browser";
        auth_basic_user_file /tmp/cloud-viewer.htpasswd;
        add_header Cache-Control "no-store" always;
        add_header X-Frame-Options "DENY" always;
        add_header X-Content-Type-Options "nosniff" always;
        location / {
          proxy_pass http://127.0.0.1:6081;
          proxy_http_version 1.1;
          proxy_set_header Host $host;
          proxy_set_header Upgrade $http_upgrade;
          proxy_set_header Connection "upgrade";
          proxy_read_timeout 3600s;
          proxy_send_timeout 3600s;
          proxy_buffering off;
        }
      }
    }
    """
    path = "/tmp/nginx-cloud.conf"
    Path(path).write_text(conf, encoding="utf-8")
    subprocess.run(["nginx", "-t", "-c", path], capture_output=True, check=True)
    return path


def launch_screen(password: str) -> list[subprocess.Popen]:
    env = {**os.environ, "DISPLAY": ":99"}
    procs = [start_process(["Xvfb", ":99", "-screen", "0", SCREEN, "-nolisten", "tcp"], env=env, output="/tmp/xvfb.log")]
    time.sleep(1.5)
    procs.append(start_process(["fluxbox"], env=env, output="/tmp/fluxbox.log"))
    procs.append(start_process(["x11vnc", "-display", ":99", "-localhost", "-nopw", "-rfbport", "5900", "-shared", "-forever", "-noxdamage"], env=env, output="/tmp/x11vnc.log"))
    procs.append(start_process(["websockify", "--web", "/usr/share/novnc", "127.0.0.1:6081", "127.0.0.1:5900"], env=env, output="/tmp/websockify.log"))
    nginx_conf = prepare_proxy(password)
    procs.append(start_process(["nginx", "-c", nginx_conf, "-g", "daemon off;"], env=env, output="/tmp/nginx.log"))
    time.sleep(1.0)
    for p in procs:
        if p.poll() is not None:
            raise RuntimeError("noVNC/display failed; inspect Modal logs, Xvfb, nginx and websockify startup")
    return procs


def unpack_profile():
    # Never share one Chromium profile across concurrent cloud sessions.
    if LOCAL_PROFILE.exists():
        shutil.rmtree(LOCAL_PROFILE)
    if PROFILE.exists():
        shutil.copytree(PROFILE, LOCAL_PROFILE, ignore=shutil.ignore_patterns("Singleton*", "DevToolsActivePort", "*.lock", "Cache", "Code Cache", "GPUCache"))
    else:
        LOCAL_PROFILE.mkdir(parents=True)


def store_profile():
    """Copy only after Chromium closes, avoiding a partial SQLite database snapshot."""
    if not LOCAL_PROFILE.exists():
        return
    tmp = DATA / "chrome-profile-staging"
    if tmp.exists():
        shutil.rmtree(tmp)
    shutil.copytree(LOCAL_PROFILE, tmp, ignore=shutil.ignore_patterns("Singleton*", "DevToolsActivePort", "*.lock", "Cache", "Code Cache", "GPUCache"))
    old = DATA / "chrome-profile-previous"
    if old.exists():
        shutil.rmtree(old)
    if PROFILE.exists():
        PROFILE.rename(old)
    tmp.rename(PROFILE)
    volume.commit()
    if old.exists():
        shutil.rmtree(old)
        volume.commit()


def set_extension_config(service_worker, worker_url: str, extension_token: str):
    # token goes straight from Modal Secret to chrome.storage.local inside the cloud browser.
    # Never returned to the UI, logs, or D1 status.
    return service_worker.evaluate(
        """async ({origin, token}) => {
          await chrome.storage.local.set({
            aiAssistantConfig: {worker: origin, token, mode: 'auto'},
            autoVideoMonitorConfig: {enabled: true, autoStart: false}
          });
          const p = await chrome.permissions.contains({origins:[origin+'/*']});
          return {hasWorkerPermission:p, configured:true};
        }""",
        {"origin": worker_url, "token": extension_token}
    )


@app.function(image=browser_image, secrets=[modal.Secret.from_name(SECRET_NAME)], volumes={"/data": volume}, timeout=10800, cpu=2, memory=4096, max_containers=1)
def cloud_session(run_id: str, minutes: int, account_id: str):
    """A visible, manually authenticated browser session, no automatic learning actions."""
    if not re.fullmatch(r"[0-9a-f]{32}", run_id) or not 5 <= minutes <= 170:
        raise ValueError("run_id/minutes không hợp lệ")
    if (control.get("snapshot") or {}).get("run_id") != run_id:
        return
    import httpx
    from playwright.sync_api import sync_playwright
    worker = validate_config(os.environ.get("CLOUDFLARE_WORKER_URL", WORKER_DEFAULT), os.environ.get("EXTENSION_TOKEN", ""), os.environ.get("REMOTE_ACCESS_PASSWORD", ""))
    password = os.environ["REMOTE_ACCESS_PASSWORD"]
    snapshot = {"account_id":account_id,"expires_at":(datetime.now(timezone.utc)+timedelta(minutes=minutes)).isoformat(),"profile_saved":False,"run_id":run_id,"state":"starting","started_at":iso(),"last_heartbeat_at":None,"heartbeats":0,
                "cloud_browser_alive":False,"extension_loaded":False,"extension_cloudflare_configured":False,
                "coursera_login":"not_verified","cloudflare_connected":False,"url":None,"note":"Browser cloud có giao diện thủ công; không đánh dấu hoàn thành Coursera"}
    write_state(snapshot)
    pids=[]
    ctx=None
    start=time.monotonic()
    try:
        pids=launch_screen(password)
        volume.reload()
        unpack_profile()
        browser_env={**os.environ,"DISPLAY":":99"}
        os.environ["DISPLAY"] = ":99"
        with sync_playwright() as p:
            ctx = p.chromium.launch_persistent_context(
                str(LOCAL_PROFILE), channel="chromium", headless=False,
                viewport={"width":1330,"height":755},
                args=["--no-sandbox", "--disable-dev-shm-usage", f"--disable-extensions-except={EXT}", f"--load-extension={EXT}", "--window-size=1365,850"],
            )
            workers=ctx.service_workers
            sw=workers[0] if workers else ctx.wait_for_event("serviceworker", timeout=60000)
            snapshot["extension_loaded"] = sw.url.startswith("chrome-extension://")
            setting=set_extension_config(sw,worker,os.environ["EXTENSION_TOKEN"])
            snapshot["extension_cloudflare_configured"] = bool(setting.get("configured") and setting.get("hasWorkerPermission"))
            # Manual login only, no extraction or transfer of local browser cookies.
            page=ctx.pages[0] if ctx.pages else ctx.new_page()
            page.goto(COURSE_DEFAULT,wait_until="domcontentloaded",timeout=45000)
            with modal.forward(VNC_PORT) as tunnel:
                snapshot["url"]=tunnel.url+"/vnc.html?autoconnect=1&resize=remote"
                snapshot["state"]="running"
                snapshot["cloud_browser_alive"]=True
                until=start + minutes*60
                while time.monotonic() < until:
                    if control.get("stop_run_id") == run_id:
                        snapshot["state"]="stopping"
                        break
                    try:
                        active=bool(ctx.pages)
                        # MV3 workers can sleep and restart; resolve the current live worker.
                        workers = ctx.service_workers
                        if workers:
                            sw = workers[0]
                        snapshot["cloud_browser_alive"]=active
                        snapshot["extension_loaded"] = bool(sw.url.startswith("chrome-extension://"))
                        if snapshot["heartbeats"] % 3 == 0:
                            try:
                                # Token authenticated check, cannot fake login status.
                                resp=httpx.get(worker+"/client/identity",headers={"Authorization":"Bearer "+os.environ["EXTENSION_TOKEN"]},timeout=12)
                                snapshot["cloudflare_connected"]=(resp.status_code==200 and resp.json().get("ok") is True)
                            except Exception:
                                snapshot["cloudflare_connected"]=False
                        snapshot["last_heartbeat_at"]=iso()
                        snapshot["heartbeats"]+=1
                        write_state(snapshot)
                        if not active:
                            snapshot["state"]="error"
                            snapshot["error"]="Cloud Chromium hoặc tab chính đã đóng"
                            break
                    except Exception as exc:
                        snapshot["state"]="error"
                        snapshot["error"]=str(exc)[:180]
                        break
                    time.sleep(10)
            ctx.close()
            ctx=None
        store_profile()
        snapshot["profile_saved"]=True
        if snapshot["state"] in ("running","stopping"):
            snapshot["state"]="completed" if snapshot["state"]=="running" else "stopped"
    except Exception as exc:
        snapshot["state"]="error"
        snapshot["error"]=str(exc)[:180]
        raise
    finally:
        if ctx is not None:
            try:
                ctx.close()
                store_profile()
                snapshot["profile_saved"]=True
            except Exception:
                snapshot["profile_save_error"]="Không thể lưu hồ sơ trình duyệt sau lỗi"
        for proc in reversed(pids):
            try:
                proc.terminate()
            except Exception:
                pass
        snapshot["cloud_browser_alive"]=False
        snapshot["finished_at"]=iso()
        write_state(snapshot)
        if control.get("stop_run_id")==run_id:
            control.pop("stop_run_id",None)


@app.function(image=status_image, volumes={"/data":volume}, timeout=30)
def read_status() -> dict:
    import datetime
    snapshot=control.get("snapshot")
    if not snapshot:
        return {"state":"not_started","message":"Chưa chạy Cloud Extension Runner"}
    snapshot=snapshot.copy()
    dt=datetime.datetime.fromisoformat(snapshot.get("last_heartbeat_at") or snapshot.get("started_at"))
    delay=(datetime.datetime.now(datetime.timezone.utc)-dt).total_seconds()
    snapshot["seconds_since_last_report"]=round(delay)
    snapshot["heartbeat_fresh"]=bool(delay < 45 and snapshot.get("state") in ("running","starting"))
    if snapshot.get("state") in ("running","starting","stopping") and delay>90:
        snapshot["state"]="stale_unconfirmed"
    return snapshot


def session_busy(snapshot: dict) -> bool:
    if snapshot.get("state") not in ("running", "starting", "stopping", "stale_unconfirmed"):
        return False
    expiry = snapshot.get("expires_at")
    return not expiry or datetime.now(timezone.utc) < datetime.fromisoformat(expiry) + timedelta(minutes=5)


@app.function(image=status_image, secrets=[modal.Secret.from_name(SECRET_NAME)], timeout=40, max_containers=1)
def lifecycle(action: str, account_id: str = "", minutes: int = 45) -> dict:
    """Serialized controller used by HTTP and CLI. Status lives in Dict, not stale Volume mounts."""
    import httpx
    if action not in ("start", "status", "stop"):
        return {"ok":False,"error":"Thao tác không hợp lệ"}
    snapshot=read_status.remote()
    if action=="status":
        return {"ok":True,"session":snapshot}
    if action=="stop":
        if snapshot.get("account_id") and account_id != snapshot["account_id"]:
            return {"ok":False,"error":"Phiên cloud thuộc tài khoản khác"}
        if session_busy(snapshot):
            control["stop_run_id"]=snapshot["run_id"]
            snapshot["state"]="stopping"
            control["snapshot"]=snapshot
        return {"ok":True,"session":snapshot}
    if type(minutes) is not int or not 5 <= minutes <= 170:
        return {"ok":False,"error":"Thời lượng phải từ 5 đến 170 phút"}
    if session_busy(snapshot):
        return {"ok":False,"error":"Phiên cloud đang chạy hoặc đang lưu profile. Hãy dừng phiên hiện tại trước.","code":"session_busy"}
    worker=validate_config(os.environ.get("CLOUDFLARE_WORKER_URL",WORKER_DEFAULT),os.environ.get("EXTENSION_TOKEN",""),os.environ.get("REMOTE_ACCESS_PASSWORD",""))
    try:
        r=httpx.get(worker+"/client/identity",headers={"Authorization":"Bearer "+os.environ["EXTENSION_TOKEN"]},timeout=12)
        identity=r.json()
        if r.status_code!=200 or not identity.get("ok"):
            return {"ok":False,"error":"EXTENSION_TOKEN không được Worker chấp nhận"}
        actual=identity["account_id"]
        if account_id and account_id != actual:
            return {"ok":False,"error":"Tài khoản đã chọn khác token trong Modal Secret. Chọn đúng tài khoản cloud.","code":"account_mismatch"}
    except Exception:
        return {"ok":False,"error":"Không xác minh được tài khoản cloud với Worker"}
    run_id=uuid.uuid4().hex
    snapshot={"state":"starting","run_id":run_id,"account_id":actual,"started_at":iso(),"expires_at":(datetime.now(timezone.utc)+timedelta(minutes=minutes+5)).isoformat(),"heartbeats":0,"profile_saved":False}
    control["stop_run_id"]=""
    control["snapshot"]=snapshot
    try:
        cloud_session.spawn(run_id,minutes,actual)
    except Exception:
        snapshot["state"]="error"
        snapshot["error"]="Không khởi tạo được tác vụ Modal"
        control["snapshot"]=snapshot
        return {"ok":False,"error":snapshot["error"]}
    return {"ok":True,"session":snapshot}


@app.function(image=status_image, secrets=[modal.Secret.from_name(SECRET_NAME)], timeout=55)
@modal.fastapi_endpoint(method="POST", docs=False)
def cloud_api(request: Request, body: dict):
    expected=os.environ.get("CLOUD_MODAL_TOKEN", "")
    if len(expected)<32 or not hmac.compare_digest(request.headers.get("authorization", ""), "Bearer "+expected):
        raise HTTPException(status_code=401,detail="Unauthorized")
    action=body.get("action")
    if action not in ("start","status","stop"):
        raise HTTPException(status_code=400,detail="Invalid action")
    result=lifecycle.remote(action,str(body.get("account_id", "")),body.get("minutes",45))
    if not result.get("ok"):
        from fastapi.responses import JSONResponse
        return JSONResponse(result,status_code=409 if result.get("code")=="session_busy" else 400)
    return result


@app.local_entrypoint()
def start(minutes: int = 45):
    print(json.dumps(lifecycle.remote("start","",minutes),ensure_ascii=False,indent=2))


@app.local_entrypoint()
def status():
    print(json.dumps(read_status.remote(),ensure_ascii=False,indent=2))


@app.local_entrypoint()
def stop():
    s=read_status.remote()
    print(json.dumps(lifecycle.remote("stop",s.get("account_id", "")),ensure_ascii=False,indent=2))
