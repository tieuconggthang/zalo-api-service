#!/usr/bin/env python3
"""
Zalo API Service - Public API for Zalo messaging
"""

import os
import sys
import json
import asyncio
import subprocess
import time
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any

from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.responses import FileResponse, JSONResponse, HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

# Setup paths
BASE_DIR = Path(__file__).parent
PLUGIN_DIR = BASE_DIR / "zalo_plugin"
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)

SESSION_FILE = DATA_DIR / "zalo_session.json"
QR_FILE = DATA_DIR / "qr_code.png"

# Set env for plugin
os.environ["ZALO_SESSION"] = str(SESSION_FILE)
os.environ["HERMES_HOME"] = str(DATA_DIR)

app = FastAPI(title="Zalo API Service", version="2.0.0")

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global state
zalo_state = {
    "is_logged_in": False,
    "login_time": None,
    "user_info": None,
    "qr_generating": False,
    "login_process": None,
    "qr_created_at": None
}

# ============================================================================
# Pydantic Models
# ============================================================================

class SendMessageRequest(BaseModel):
    phone: str = Field(..., description="Phone number or user ID")
    message: str = Field(..., description="Message content", max_length=5000)
    image_url: Optional[str] = Field(None, description="Optional image URL")

class SendGroupRequest(BaseModel):
    group_name: str = Field(..., description="Group name")
    message: str = Field(..., description="Message content", max_length=5000)
    image_url: Optional[str] = Field(None, description="Optional image URL")

class ApiResponse(BaseModel):
    success: bool
    message: str
    data: Optional[Dict] = None
    timestamp: str = Field(default_factory=lambda: datetime.now().isoformat())

# ============================================================================
# Zalo Bridge Functions
# ============================================================================

def run_bridge(method: str, args=None, timeout: int = 30):
    """Run Node.js bridge to call zca-js methods"""
    bridge_script = PLUGIN_DIR / "zalo-api-bridge.js"
    
    cmd = ["node", str(bridge_script), method]
    if args is not None:
        cmd.append(json.dumps(args, ensure_ascii=False))
    
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout,
            cwd=str(PLUGIN_DIR),
            env={**os.environ, "NODE_NO_WARNINGS": "1"}
        )
        
        if result.returncode != 0:
            err = result.stderr.strip().split('\n')[-1] if result.stderr else "unknown error"
            return {"success": False, "error": err}
        
        for line in reversed(result.stdout.strip().split('\n')):
            if not line.strip():
                continue
            try:
                data = json.loads(line)
                return {"success": True, "data": data}
            except json.JSONDecodeError:
                continue
        
        return {"success": False, "error": "No JSON in output"}
        
    except subprocess.TimeoutExpired:
        return {"success": False, "error": f"Timeout after {timeout}s"}
    except Exception as e:
        return {"success": False, "error": str(e)}

# ============================================================================
# OpenZCA CLI Functions
# ============================================================================

def run_openzca_cmd(args: list, timeout: int = 30) -> Dict:
    """Run openzca CLI command"""
    cmd = ["openzca"] + args
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout,
            cwd=str(DATA_DIR)
        )
        if result.returncode != 0:
            return {"success": False, "error": result.stderr.strip() or result.stdout.strip()}
        try:
            data = json.loads(result.stdout.strip())
            return {"success": True, "data": data}
        except json.JSONDecodeError:
            # Nếu không phải JSON, trả về raw output
            return {"success": True, "data": result.stdout.strip()}
    except subprocess.TimeoutExpired:
        return {"success": False, "error": f"Timeout after {timeout}s"}
    except Exception as e:
        return {"success": False, "error": str(e)}

def check_session():
    """Check if valid session exists using openzca"""
    result = run_openzca_cmd(["me", "id"], timeout=10)
    
    if result.get("success") and result.get("data"):
        zalo_state["is_logged_in"] = True
        # Get profile info
        profile_result = run_openzca_cmd(["me", "info", "-j"], timeout=10)
        if profile_result.get("success"):
            profile = profile_result.get("data", {})
            zalo_state["user_info"] = {
                "uid": profile.get("id"),
                "name": profile.get("name"),
                "phone": profile.get("phone")
            }
        return True
    
    zalo_state["is_logged_in"] = False
    return False

def find_user_by_phone(phone: str) -> Optional[Dict]:
    """Find user by phone number using openzca CLI"""
    # Remove + prefix if present for comparison
    phone_clean = phone.replace("+", "")
    
    # List all friends using JSON format
    result = run_openzca_cmd(["friend", "list", "-j"], timeout=15)
    if result.get("success") and result.get("data"):
        friends = result.get("data", [])
        # Handle both list and dict formats
        if isinstance(friends, dict):
            # If returned as dict with userId as keys
            for uid, friend in friends.items():
                friend_phone = str(friend.get("phoneNumber", "")).replace("+", "")
                if friend_phone == phone_clean or friend_phone.endswith(phone_clean):
                    return {
                        "id": uid or friend.get("id") or friend.get("uid") or friend.get("userId"),
                        "name": friend.get("name", "Unknown")
                    }
        elif isinstance(friends, list):
            # If returned as list
            for friend in friends:
                friend_phone = str(friend.get("phoneNumber") or friend.get("phone") or "").replace("+", "")
                if friend_phone == phone_clean or friend_phone.endswith(phone_clean):
                    return {
                        "id": friend.get("id") or friend.get("uid") or friend.get("userId"),
                        "name": friend.get("name", "Unknown")
                    }
    return None

def find_group_by_name(name: str) -> Optional[Dict]:
    """Find group by name using openzca CLI"""
    result = run_openzca_cmd(["group", "list", "-j"], timeout=15)
    if result.get("success") and result.get("data"):
        groups = result.get("data", [])
        name_lower = name.lower()
        for group in groups:
            if name_lower in group.get("name", "").lower():
                return {
                    "id": group.get("groupId") or group.get("id"),
                    "name": group.get("name")
                }
    return None

def send_message_to_user(user_id: str, message: str, image_url: Optional[str] = None) -> Dict:
    """Send message to user using openzca CLI"""
    if image_url:
        result = run_openzca_cmd([
            "msg", "image", str(user_id),
            "-u", image_url,
            "-m", message
        ], timeout=20)
    else:
        result = run_openzca_cmd(["msg", "send", str(user_id), message], timeout=15)
    return result

def send_message_to_group(group_id: str, message: str, image_url: Optional[str] = None) -> Dict:
    """Send message to group using openzca CLI"""
    if image_url:
        result = run_openzca_cmd([
            "msg", "image", str(group_id),
            "-u", image_url,
            "-m", message,
            "-g"
        ], timeout=20)
    else:
        result = run_openzca_cmd(["msg", "send", str(group_id), message, "-g"], timeout=15)
    return result

# Helper function to run openzca CLI
def run_openzca_cmd(args: list, timeout: int = 30) -> Dict:
    """Run openzca CLI command"""
    import subprocess
    cmd = ["openzca"] + args
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout,
            cwd=str(DATA_DIR)
        )
        if result.returncode != 0:
            return {"success": False, "error": result.stderr.strip() or result.stdout.strip()}
        try:
            data = json.loads(result.stdout.strip())
            return {"success": True, "data": data}
        except json.JSONDecodeError:
            return {"success": True, "data": result.stdout.strip()}
    except Exception as e:
        return {"success": False, "error": str(e)}

# ============================================================================
# API Endpoints
# ============================================================================

@app.on_event("startup")
async def startup():
    """Check existing session on startup"""
    check_session()
    print(f"🚀 Zalo API Service v2.0 started")
    print(f"   Port: 10000")
    print(f"   Session: {SESSION_FILE}")
    print(f"   Logged in: {zalo_state['is_logged_in']}")

@app.get("/")
async def root():
    """Root endpoint - API info"""
    return {
        "service": "Zalo API Service",
        "version": "2.0.0",
        "status": "running",
        "logged_in": zalo_state["is_logged_in"],
        "user_info": zalo_state.get("user_info") if zalo_state["is_logged_in"] else None
    }

@app.get("/health")
async def health():
    """Health check endpoint"""
    is_valid = check_session()
    return {
        "status": "healthy" if is_valid else "not_logged_in",
        "logged_in": is_valid,
        "user_info": zalo_state.get("user_info") if is_valid else None
    }

# ============================================================================
# Authentication Endpoints
# ============================================================================

@app.get("/login/qr/web", response_class=HTMLResponse)
async def get_qr_web():
    """Show QR code on web page"""
    html_content = """
<!DOCTYPE html>
<html>
<head>
    <title>Zalo QR Login</title>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <style>
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            min-height: 100vh;
            margin: 0;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
        }
        .container {
            text-align: center;
            padding: 40px;
            background: rgba(255,255,255,0.1);
            border-radius: 20px;
            backdrop-filter: blur(10px);
        }
        h1 { margin-bottom: 10px; }
        .qr-container {
            background: white;
            padding: 20px;
            border-radius: 15px;
            margin: 20px 0;
        }
        .qr-container img { width: 300px; height: 300px; }
        .instructions { margin-top: 30px; text-align: left; max-width: 400px; }
        .instructions ol { line-height: 1.8; }
        button {
            margin-top: 20px;
            padding: 12px 30px;
            background: #00b894;
            color: white;
            border: none;
            border-radius: 25px;
            cursor: pointer;
            font-size: 16px;
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>📱 Zalo QR Login</h1>
        <p>Quét mã QR để đăng nhập</p>
        
        <div class="qr-container">
            <img id="qrImage" src="/qr-code.png" alt="QR Code">
        </div>
        
        <div class="instructions">
            <h3>📝 Hướng dẫn:</h3>
            <ol>
                <li>Mở <strong>Zalo</strong> trên điện thoại</li>
                <li>Chạm vào <strong>Quét mã QR</strong></li>
                <li>Quét mã bên trên</li>
                <li>Bấm <strong>"CÓ"</strong> để đăng nhập</li>
            </ol>
        </div>
        
        <button onclick="location.reload()">🔄 Tải lại trang</button>
        <br><br>
        <button onclick="refreshQR()" style="background: #e74c3c;">🔄 Tạo QR mới</button>
        <p id="status" style="margin-top: 20px; font-weight: bold;"></p>
    </div>
    
    <script>
        // Auto generate QR on page load
        window.onload = function() {
            refreshQR();
        };
        
        function refreshQR() {
            document.getElementById('status').innerHTML = '🔄 Đang tạo QR mới...';
            document.getElementById('qrImage').style.display = 'none';
            
            // Gọi API tạo QR mới
            fetch('/login/qr/refresh', {method: 'POST'})
                .then(r => r.json())
                .then(data => {
                    console.log(data);
                    // Đợi 3 giây rồi lấy QR
                    setTimeout(() => {
                        loadQRImage();
                    }, 3000);
                })
                .catch(err => {
                    document.getElementById('status').innerHTML = '❌ Lỗi: ' + err.message;
                });
        }
        
        function loadQRImage() {
            // Thử lấy QR từ /app/qr.png (openzca) hoặc /app/data/qr_code.png
            fetch('/qr-image')
                .then(r => r.json())
                .then(data => {
                    if (data.success && data.image_base64) {
                        document.getElementById('qrImage').src = data.image_base64;
                        document.getElementById('qrImage').style.display = 'block';
                        document.getElementById('status').innerHTML = '✅ QR đã sẵn sàng! Quét ngay (có hiệu lực 2 phút)';
                    } else {
                        // Thử fallback về /qr-code.png
                        document.getElementById('qrImage').src = '/qr-code.png?' + Date.now();
                        document.getElementById('qrImage').style.display = 'block';
                        document.getElementById('status').innerHTML = '⚠️ QR có thể hết hạn, bấm "Tạo QR mới" nếu cần';
                    }
                })
                .catch(() => {
                    // Fallback
                    document.getElementById('qrImage').src = '/qr-code.png?' + Date.now();
                    document.getElementById('qrImage').style.display = 'block';
                });
        }
        
        // Check login status mỗi 5 giây
        setInterval(() => {
            fetch('/login/status')
                .then(r => r.json())
                .then(data => {
                    if (data.logged_in) {
                        document.getElementById('status').innerHTML = '✅ Đã đăng nhập thành công! Tên: ' + (data.user_info?.name || 'Unknown');
                        document.getElementById('qrImage').style.display = 'none';
                    }
                })
                .catch(() => {});
        }, 5000);
    </script>
</body>
</html>
"""
    return HTMLResponse(content=html_content)

@app.get("/login/qr")
async def get_qr_login():
    """Get QR code for Zalo login"""
    global zalo_state
    
    # Check if already logged in
    if check_session():
        return JSONResponse({
            "status": "already_logged_in",
            "message": "Already logged in",
            "user_info": zalo_state.get("user_info")
        })
    
    # Check if QR generation in progress
    if zalo_state["qr_generating"]:
        # Wait for QR to be ready
        for _ in range(10):
            await asyncio.sleep(1)
            if QR_FILE.exists():
                return FileResponse(QR_FILE, media_type="image/png")
        return JSONResponse({
            "status": "generating",
            "message": "QR generation in progress, please wait"
        })
    
    # Remove old QR and generate new
    if QR_FILE.exists():
        QR_FILE.unlink()
    
    zalo_state["qr_generating"] = True
    zalo_state["qr_created_at"] = time.time()
    
    async def generate_qr():
        """Generate QR using openzca and copy to web location"""
        try:
            # Xóa QR cũ
            if QR_FILE.exists():
                QR_FILE.unlink()
            
            # Chạy openzca login (tạo qr.png)
            proc = await asyncio.create_subprocess_exec(
                "openzca", "auth", "login",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
                cwd="/app"  # openzca lưu qr.png tại /app
            )
            
            zalo_state["login_process"] = proc
            stdout, stderr = await proc.communicate()
            output = (stdout or b'').decode()
            
            print(f"[openzca] {output}")
            
            # Copy qr.png sang vị trí web đọc
            import shutil
            source_qr = Path("/app/qr.png")
            if source_qr.exists():
                shutil.copy(str(source_qr), str(QR_FILE))
                print(f"📷 QR copied to {QR_FILE}")
            
            if proc.returncode == 0:
                zalo_state["is_logged_in"] = True
                zalo_state["login_time"] = datetime.now().isoformat()
                check_session()
                print(f"✅ Login successful")
            else:
                print(f"❌ Login ended with code {proc.returncode}")
                
        except Exception as e:
            print(f"❌ Error: {e}")
            import traceback
            traceback.print_exc()
        finally:
            zalo_state["qr_generating"] = False
            zalo_state["login_process"] = None
    
    asyncio.create_task(generate_qr())
    await asyncio.sleep(3)
    
    if QR_FILE.exists():
        return FileResponse(QR_FILE, media_type="image/png")
    
    await asyncio.sleep(3)
    
    if QR_FILE.exists():
        return FileResponse(QR_FILE, media_type="image/png")
    
    return JSONResponse({
        "status": "generating",
        "message": "QR code is being generated"
    })

@app.post("/login/qr/refresh")
async def refresh_qr():
    """Force refresh QR code"""
    global zalo_state
    
    # Kill old process
    if zalo_state["login_process"]:
        try:
            zalo_state["login_process"].kill()
        except:
            pass
        zalo_state["login_process"] = None
    
    # Reset state và xóa QR cũ
    zalo_state["qr_generating"] = False
    zalo_state["qr_created_at"] = None
    
    if QR_FILE.exists():
        QR_FILE.unlink()
    
    # Xóa cả qr.png của openzca
    import os
    if os.path.exists("/app/qr.png"):
        os.remove("/app/qr.png")
    
    # Tạo QR mới ngay
    if not zalo_state["qr_generating"]:
        zalo_state["qr_generating"] = True
        zalo_state["qr_created_at"] = time.time()
        
        async def generate_new_qr():
            try:
                proc = await asyncio.create_subprocess_exec(
                    "openzca", "auth", "login",
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.STDOUT,
                    cwd="/app"
                )
                
                zalo_state["login_process"] = proc
                stdout, _ = await proc.communicate()
                print(f"[openzca] {stdout.decode()}")
                
                # Copy QR file
                import shutil
                if os.path.exists("/app/qr.png"):
                    shutil.copy("/app/qr.png", str(QR_FILE))
                    print(f"📷 QR saved to {QR_FILE}")
                
                if proc.returncode == 0:
                    zalo_state["is_logged_in"] = True
                    check_session()
                    
            except Exception as e:
                print(f"❌ Error: {e}")
            finally:
                zalo_state["qr_generating"] = False
                zalo_state["login_process"] = None
        
        asyncio.create_task(generate_new_qr())
    
    return {"success": True, "message": "QR generation started. Wait 3-5 seconds and refresh page"}

@app.get("/qr-image")
async def get_qr_base64():
    """Get QR as base64 for immediate display"""
    import base64
    
    # Ưu tiên lấy từ /app/qr.png (openzca tạo ra)
    source_paths = ["/app/qr.png", str(QR_FILE)]
    
    for path in source_paths:
        if os.path.exists(path):
            try:
                with open(path, "rb") as f:
                    img_data = f.read()
                    base64_str = base64.b64encode(img_data).decode()
                    return {
                        "success": True,
                        "image_base64": f"data:image/png;base64,{base64_str}",
                        "created_at": os.path.getmtime(path)
                    }
            except Exception as e:
                continue
    
    return {"success": False, "error": "No QR available. Click 'Tạo QR mới' first"}

@app.get("/qr-code.png")
async def get_qr_image():
    """Get the current QR code image - ưu tiên /app/qr.png (openzca)"""
    # Ưu tiên lấy từ /app/qr.png (openzca tạo)
    if os.path.exists("/app/qr.png"):
        return FileResponse("/app/qr.png", media_type="image/png")
    
    # Fallback về /app/data/qr_code.png
    if QR_FILE.exists():
        return FileResponse(QR_FILE, media_type="image/png")
    
    raise HTTPException(404, "No QR code available. Click 'Tạo QR mới'")

@app.get("/login/status")
async def login_status():
    """Check login status"""
    is_valid = check_session()
    return {
        "logged_in": is_valid,
        "user_info": zalo_state.get("user_info") if is_valid else None,
        "login_time": zalo_state.get("login_time"),
        "qr_generating": zalo_state["qr_generating"]
    }

@app.post("/logout")
async def logout():
    """Logout and clear session"""
    global zalo_state
    
    if SESSION_FILE.exists():
        SESSION_FILE.unlink()
    
    if QR_FILE.exists():
        QR_FILE.unlink()
    
    zalo_state["is_logged_in"] = False
    zalo_state["user_info"] = None
    zalo_state["login_time"] = None
    
    return {"success": True, "message": "Logged out successfully"}

# ============================================================================
# Friends & Groups Endpoints
# ============================================================================

@app.get("/friends")
async def list_friends():
    """List all Zalo friends with phone numbers and IDs"""
    if not check_session():
        raise HTTPException(401, "Not logged in")
    
    result = run_openzca_cmd(["friend", "list", "-j"], timeout=15)
    if result.get("success"):
        return {
            "success": True,
            "count": len(result.get("data", [])),
            "friends": result.get("data", [])
        }
    else:
        return {
            "success": False,
            "error": result.get("error", "Failed to fetch friends")
        }

@app.get("/groups")
async def list_groups():
    """List all Zalo groups"""
    if not check_session():
        raise HTTPException(401, "Not logged in")
    
    result = run_openzca_cmd(["group", "list", "-j"], timeout=15)
    if result.get("success"):
        return {
            "success": True,
            "count": len(result.get("data", [])),
            "groups": result.get("data", [])
        }
    else:
        return {
            "success": False,
            "error": result.get("error", "Failed to fetch groups")
        }

# ============================================================================
# Messaging Endpoints
# ============================================================================

@app.post("/send", response_model=ApiResponse)
async def send_message(request: SendMessageRequest):
    """Send a message to a user by phone number"""
    
    if not check_session():
        raise HTTPException(401, "Not logged in. Please login via /login/qr first")
    
    user = find_user_by_phone(request.phone)
    if not user:
        return ApiResponse(
            success=False,
            message=f"User not found with phone: {request.phone}"
        )
    
    result = send_message_to_user(user["id"], request.message, request.image_url)
    
    if result.get("success"):
        return ApiResponse(
            success=True,
            message=f"Message sent to {user.get('name', request.phone)}",
            data={"user_id": user["id"], "user_name": user.get("name")}
        )
    else:
        return ApiResponse(
            success=False,
            message="Failed to send message",
            data={"error": result.get("error")}
        )

@app.post("/send-group", response_model=ApiResponse)
async def send_group_message(request: SendGroupRequest):
    """Send a message to a group by name"""
    
    if not check_session():
        raise HTTPException(401, "Not logged in")
    
    group = find_group_by_name(request.group_name)
    if not group:
        return ApiResponse(
            success=False,
            message=f"Group not found: {request.group_name}"
        )
    
    result = send_message_to_group(group["id"], request.message, request.image_url)
    
    if result.get("success"):
        return ApiResponse(
            success=True,
            message=f"Message sent to group {group['name']}",
            data={"group_id": group["id"], "group_name": group["name"]}
        )
    else:
        return ApiResponse(
            success=False,
            message="Failed to send message",
            data={"error": result.get("error")}
        )

# ============================================================================
# Direct Messaging Endpoints (for Java Service)
# ============================================================================

class SendToUserRequest(BaseModel):
    user_id: str = Field(..., description="Zalo user ID (not phone)")
    message: str = Field(..., description="Message content")

class SendImageToUserRequest(BaseModel):
    user_id: str = Field(..., description="Zalo user ID")
    image_url: str = Field(..., description="Image URL to send")
    caption: str = Field("", description="Caption text")

@app.post("/send-to-user", response_model=ApiResponse)
async def send_to_user_direct(request: SendToUserRequest):
    """Send text message directly to user_id (no phone lookup)"""
    if not check_session():
        raise HTTPException(401, "Not logged in")
    
    result = run_openzca_cmd(["msg", "send", request.user_id, request.message], timeout=15)
    
    if result.get("success"):
        return ApiResponse(
            success=True,
            message=f"Message sent to user {request.user_id}",
            data={"user_id": request.user_id}
        )
    else:
        return ApiResponse(
            success=False,
            message="Failed to send message",
            data={"error": result.get("error")}
        )

@app.post("/send-image", response_model=ApiResponse)
async def send_image_by_phone(
    phone: str,
    image_url: str,
    caption: str = ""
):
    """Send image to user by phone number (query params for easy testing)"""
    if not check_session():
        raise HTTPException(401, "Not logged in")
    
    user = find_user_by_phone(phone)
    if not user:
        return ApiResponse(
            success=False,
            message=f"User not found with phone: {phone}"
        )
    
    result = run_openzca_cmd([
        "msg", "image", user["id"],
        "-u", image_url,
        "-m", caption
    ], timeout=20)
    
    if result.get("success"):
        return ApiResponse(
            success=True,
            message=f"Image sent to {user.get('name', phone)}",
            data={"user_id": user["id"], "user_name": user.get("name")}
        )
    else:
        return ApiResponse(
            success=False,
            message="Failed to send image",
            data={"error": result.get("error")}
        )

@app.post("/send-image-to-user", response_model=ApiResponse)
async def send_image_to_user_direct(request: SendImageToUserRequest):
    """Send image directly to user_id (recommended for Java service)"""
    if not check_session():
        raise HTTPException(401, "Not logged in")
    
    result = run_openzca_cmd([
        "msg", "image", request.user_id,
        "-u", request.image_url,
        "-m", request.caption
    ], timeout=20)
    
    if result.get("success"):
        return ApiResponse(
            success=True,
            message=f"Image sent to user {request.user_id}",
            data={"user_id": request.user_id}
        )
    else:
        return ApiResponse(
            success=False,
            message="Failed to send image",
            data={"error": result.get("error")}
        )

# ============================================================================
# Data Endpoints
# ============================================================================

@app.get("/friends")
async def get_friends():
    """Get all friends list"""
    if not check_session():
        raise HTTPException(401, "Not logged in")
    
    result = run_bridge("getAllFriends", timeout=15)
    if result.get("success"):
        return {"success": True, "count": len(result["data"]), "friends": result["data"]}
    else:
        raise HTTPException(500, result.get("error", "Failed to get friends"))

@app.get("/groups")
async def get_groups():
    """Get all groups list"""
    if not check_session():
        raise HTTPException(401, "Not logged in")
    
    result = run_bridge("getAllGroups", timeout=15)
    if result.get("success"):
        return {"success": True, "count": len(result["data"]), "groups": result["data"]}
    else:
        raise HTTPException(500, result.get("error", "Failed to get groups"))

@app.get("/account")
async def get_account_info():
    """Get current account info"""
    if not check_session():
        raise HTTPException(401, "Not logged in")
    
    result = run_bridge("fetchAccountInfo", timeout=10)
    if result.get("success"):
        return {"success": True, "account": result["data"]}
    else:
        raise HTTPException(500, result.get("error", "Failed to get account info"))

# ============================================================================
# Main
# ============================================================================

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", "10000"))
    host = os.getenv("HOST", "0.0.0.0")
    uvicorn.run(app, host=host, port=port)
