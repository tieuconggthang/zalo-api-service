#!/usr/bin/env python3
"""
OpenZCA QR Login wrapper
Tạo QR code cho Zalo login sử dụng openzca CLI
"""

import subprocess
import json
import os
import sys
from pathlib import Path

DATA_DIR = Path("/app/data")
QR_FILE = DATA_DIR / "qr_code.png"

def run_login():
    """Run openzca login và tạo QR file"""
    
    # Xóa QR cũ nếu có
    if QR_FILE.exists():
        QR_FILE.unlink()
    
    try:
        # Chạy openzca login, nó sẽ tự động tạo QR và chờ scan
        proc = subprocess.Popen(
            ["openzca", "login"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            cwd=str(DATA_DIR)
        )
        
        print(f"QR_LOGIN_STARTED", flush=True)
        
        # Đọc output để biết khi nào login thành công
        stdout, stderr = proc.communicate()
        
        if proc.returncode == 0:
            print(json.dumps({"success": True, "message": "Login successful"}))
            return True
        else:
            print(json.dumps({"success": False, "error": stderr or "Unknown error"}))
            return False
            
    except Exception as e:
        print(json.dumps({"success": False, "error": str(e)}))
        return False

if __name__ == "__main__":
    run_login()
