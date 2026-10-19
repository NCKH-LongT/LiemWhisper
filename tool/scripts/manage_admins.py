#!/usr/bin/env python3
"""CLI utility to manage Administrator roles for Google/Gmail accounts in LiemWhisper.

Usage:
    python manage_admins.py list
    python manage_admins.py add user@gmail.com
    python manage_admins.py remove user@gmail.com
"""
import sys
import time
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# Add backend directory to path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
BACKEND_DIR = PROJECT_ROOT / "tool" / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.database import db, init_db
from app.auth import (
    setup_auth,
    add_admin_email,
    remove_admin_email,
    list_admin_emails,
    is_admin_email
)


def format_time(ts: int) -> str:
    if not ts:
        return "Cấu hình qua biến môi trường"
    return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(ts))


def main():
    init_db()
    setup_auth(db)

    args = sys.argv[1:]
    if not args or args[0] in ("-h", "--help", "help"):
        print("LiemWhisper - Quản lý Quản trị viên (Admin Gmail)")
        print("-" * 50)
        print("Cách dùng:")
        print("  python manage_admins.py list                 Liệt kê danh sách email admin")
        print("  python manage_admins.py add <email>          Cấp quyền admin cho Gmail")
        print("  python manage_admins.py remove <email>       Thu hồi quyền admin của Gmail")
        print("  python manage_admins.py check <email>        Kiểm tra quyền admin của Gmail")
        sys.exit(0)

    cmd = args[0].lower()

    if cmd == "list":
        admins = list_admin_emails(db)
        print(f"\nDanh sách Quản trị viên LiemWhisper ({len(admins)} tài khoản):")
        print("-" * 65)
        print(f"{'Email':<35} | {'Người cấp':<15} | {'Thời gian'}")
        print("-" * 65)
        for a in admins:
            name_info = f" ({a['name']})" if a.get("name") else ""
            print(f"{a['email'] + name_info:<35} | {a.get('created_by', 'admin'):<15} | {format_time(a.get('created_at', 0))}")
        print("-" * 65)

    elif cmd == "add":
        if len(args) < 2:
            print("Lỗi: Vui lòng nhập địa chỉ email cần cấp quyền.")
            print("Ví dụ: python manage_admins.py add researcher@gmail.com")
            sys.exit(1)
        email = args[1].strip()
        try:
            res = add_admin_email(db, email, created_by="cli")
            print(f"Thành công: Đã cấp quyền Quản trị viên (Admin) cho email: {res['email']}")
            print("Người dùng có thể đăng nhập trực tiếp bằng Google để vào Admin Dashboard.")
        except Exception as e:
            msg = getattr(e, "detail", str(e))
            print(f"Lỗi: {msg}")
            sys.exit(1)

    elif cmd == "remove":
        if len(args) < 2:
            print("Lỗi: Vui lòng nhập địa chỉ email cần thu hồi quyền.")
            print("Ví dụ: python manage_admins.py remove researcher@gmail.com")
            sys.exit(1)
        email = args[1].strip()
        try:
            success = remove_admin_email(db, email)
            if success:
                print(f"Thành công: Đã thu hồi quyền Quản trị viên của: {email}")
            else:
                print(f"Thông báo: Không tìm thấy email '{email}' trong danh sách admin database.")
        except Exception as e:
            msg = getattr(e, "detail", str(e))
            print(f"Lỗi: {msg}")
            sys.exit(1)

    elif cmd == "check":
        if len(args) < 2:
            print("Lỗi: Vui lòng nhập địa chỉ email cần kiểm tra.")
            sys.exit(1)
        email = args[1].strip()
        has_admin = is_admin_email(db, email)
        if has_admin:
            print(f"[CÓ QUYỀN ADMIN] Email '{email}' là Quản trị viên hợp lệ.")
        else:
            print(f"[KHÔNG CÓ QUYỀN] Email '{email}' không phải là Quản trị viên.")

    else:
        print(f"Lệnh không hợp lệ: '{cmd}'. Chạy 'python manage_admins.py --help' để xem hướng dẫn.")
        sys.exit(1)


if __name__ == "__main__":
    main()
