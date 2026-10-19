#!/usr/bin/env python3
"""CLI utility to find, merge, and clean up duplicate folders and audio files in Google Drive.

Usage:
    # Preview duplicates without making any changes:
    python cleanup_drive_duplicates.py --dry-run

    # Perform cleanup and database synchronization:
    python cleanup_drive_duplicates.py
"""
import argparse
import sys
import time
from collections import defaultdict
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# Add backend directory to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
BACKEND_DIR = PROJECT_ROOT / "tool" / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.database import db, init_db
from app.drive import get_drive_client


FOLDER_MIME = "application/vnd.google-apps.folder"


def cleanup_drive(dry_run: bool = True) -> None:
    init_db()

    print("=" * 60)
    print(f"LiemWhisper - Google Drive Duplicate Cleanup Tool")
    print(f"Mode: {'[DRY RUN - CHỈ XEM, KHÔNG XÓA]' if dry_run else '[THỰC THI - TIẾN HÀNH DỌN DẸP VÀ XÓA BẢN TRÙNG]'}")
    print("=" * 60)

    try:
        drive = get_drive_client(db)
    except Exception as exc:
        print(f"[!] Không thể kết nối tới Google Drive: {exc}")
        return

    root_id = drive.folder_id
    print(f"[*] Đang quét thư mục gốc Google Drive (ID: {root_id})...")

    # 1. Quét toàn bộ thư mục con trong Root
    items_in_root = drive.list_children(root_id)
    folders = [item for item in items_in_root if item.get("mimeType") == FOLDER_MIME]
    root_files = [item for item in items_in_root if item.get("mimeType") != FOLDER_MIME]

    print(f"[*] Tìm thấy {len(folders)} thư mục người tham gia và {len(root_files)} file ngoài thư mục gốc.\n")

    # Nhóm thư mục theo tên
    folders_by_name = defaultdict(list)
    for f in folders:
        folders_by_name[f["name"]].append(f)

    duplicate_folders_count = 0
    merged_folders_count = 0
    deleted_folders_count = 0

    all_active_folders = []

    print("--- 1. XỬ LÝ TRÙNG LẶP THƯ MỤC NGƯỜI THAM GIA ---")
    for name, f_list in folders_by_name.items():
        if len(f_list) > 1:
            duplicate_folders_count += 1
            print(f"[!] Phát hiện {len(f_list)} thư mục trùng tên: '{name}'")
            for idx, f in enumerate(f_list, 1):
                created = f.get("createdTime", "N/A")
                print(f"    ({idx}) ID: {f['id']} | Tạo lúc: {created}")

            # Thư mục chính được giữ lại (ưu tiên thư mục tạo sớm nhất)
            primary_folder = sorted(f_list, key=lambda x: x.get("createdTime", ""))[0]
            redundant_folders = [f for f in f_list if f["id"] != primary_folder["id"]]

            print(f"    => Chọn thư mục chính giữ lại: ID {primary_folder['id']}")

            if not dry_run:
                # Cập nhật database participants nếu khớp
                with db() as c:
                    c.execute(
                        "UPDATE participants SET drive_folder_id = ? WHERE (name = ? OR participant_code = ? OR ? LIKE participant_code || '%')",
                        (primary_folder["id"], name, name, name)
                    )

                for dup in redundant_folders:
                    # Di chuyển các file từ folder phụ sang folder chính
                    dup_files = drive.list_children(dup["id"])
                    if dup_files:
                        print(f"    [*] Di chuyển {len(dup_files)} file từ folder phụ {dup['id']} sang {primary_folder['id']}...")
                        for df in dup_files:
                            drive.move_and_rename_file(
                                file_id=df["id"],
                                new_name=df["name"],
                                target_parent_id=primary_folder["id"],
                                old_parent_id=dup["id"]
                            )

                    # Xóa thư mục phụ rỗng
                    print(f"    [*] Xóa thư mục phụ trùng lặp: {dup['id']} ({dup['name']})")
                    drive.delete(dup["id"])
                    deleted_folders_count += 1
                merged_folders_count += 1

            all_active_folders.append(primary_folder)
        else:
            all_active_folders.append(f_list[0])

    if duplicate_folders_count == 0:
        print("[v] Không có thư mục người tham gia nào bị trùng lặp.")
    else:
        print(f"\n[Kết quả Thư mục] Phát hiện {duplicate_folders_count} nhóm thư mục trùng lặp. "
              f"{'Đã gộp và xóa ' + str(deleted_folders_count) + ' thư mục phụ.' if not dry_run else 'Sẽ gộp khi chạy không có --dry-run.'}\n")

    # 2. Xử lý trùng lặp trong cơ sở dữ liệu
    print("--- 2. XỬ LÝ TRÙNG LẶP TRONG CƠ SỞ DỮ LIỆU ---")
    db_duplicates_removed = 0
    drive_files_to_delete_from_db = set()
    with db() as c:
        dup_prompt_rows = c.execute("""
            SELECT participant_id, prompt_id, COUNT(*) as cnt
            FROM recordings
            GROUP BY participant_id, prompt_id
            HAVING COUNT(*) > 1
        """).fetchall()

        for dup in dup_prompt_rows:
            p_id, pr_id = dup["participant_id"], dup["prompt_id"]
            all_recs = c.execute("""
                SELECT id, drive_file_id, bytes, created_at
                FROM recordings
                WHERE participant_id = ? AND prompt_id = ?
                ORDER BY created_at DESC, id DESC
            """, (p_id, pr_id)).fetchall()

            primary_rec = None
            for r in all_recs:
                if r["drive_file_id"]:
                    primary_rec = r
                    break
            if not primary_rec:
                primary_rec = all_recs[0]

            for r in all_recs:
                if r["id"] != primary_rec["id"]:
                    dup_rec_id = r["id"]
                    dup_file_id = r["drive_file_id"]
                    if dup_file_id and dup_file_id != primary_rec["drive_file_id"]:
                        drive_files_to_delete_from_db.add(dup_file_id)

                    if not dry_run:
                        c.execute("DELETE FROM recording_audio WHERE recording_id = ?", (dup_rec_id,))
                        c.execute("DELETE FROM drive_sync_jobs WHERE recording_id = ?", (dup_rec_id,))
                        c.execute("DELETE FROM recordings WHERE id = ?", (dup_rec_id,))
                    db_duplicates_removed += 1

    if db_duplicates_removed == 0:
        print("[v] CSDL không có bản ghi trùng lặp (mỗi câu chỉ có đúng 1 bản thu).")
    else:
        print(f"[!] Phát hiện {db_duplicates_removed} bản ghi trùng lặp trong CSDL.")
        if not dry_run:
            print(f"    [v] Đã xóa {db_duplicates_removed} bản ghi thừa trong CSDL.")

    # 3. Quét và xử lý file audio trùng lặp trong từng thư mục
    print("\n--- 3. XỬ LÝ TRÙNG LẶP FILE AUDIO TRÊN DRIVE ---")
    import re
    duplicate_files_count = 0
    deleted_files_count = 0
    updated_db_records = 0

    active_db_drive_ids = set()
    with db() as c:
        for row in c.execute("SELECT drive_file_id FROM recordings WHERE drive_file_id IS NOT NULL AND drive_file_id != ''").fetchall():
            active_db_drive_ids.add(row["drive_file_id"])

    def extract_prompt_key(fname: str) -> str:
        m = re.match(r"^([A-Za-z0-9_-]+?(?:_Cau\d+|_SWT_\d+|_P\d+))", fname, re.IGNORECASE)
        if m:
            return m.group(1).lower()
        clean = re.sub(r"\s*\(\d+\)", "", fname)
        return clean.lower()

    folders_to_check = all_active_folders + [{"id": root_id, "name": "[Root Folder]"}]

    for folder in folders_to_check:
        fid = folder["id"]
        fname = folder["name"]
        files = [f for f in drive.list_children(fid) if f.get("mimeType") != FOLDER_MIME]

        if not files:
            continue

        audio_files = [f for f in files if not f["name"].lower().endswith(".csv")]

        files_by_key = defaultdict(list)
        for f in audio_files:
            key = extract_prompt_key(f["name"])
            files_by_key[key].append(f)

        for prompt_key, flist in files_by_key.items():
            if len(flist) > 1:
                duplicate_files_count += len(flist) - 1
                print(f"[!] Thư mục '{fname}': Phát hiện {len(flist)} bản sao của câu '{prompt_key}'")

                flist_sorted = sorted(
                    flist,
                    key=lambda x: (
                        1 if x["id"] in active_db_drive_ids else 0,
                        int(x.get("size") or 0) > 0,
                        x.get("createdTime", "")
                    ),
                    reverse=True
                )
                primary_file = flist_sorted[0]
                redundant_files = flist_sorted[1:]

                print(f"    => Giữ lại bản chính: ID {primary_file['id']} - {primary_file['name']} (size: {primary_file.get('size', 0)} bytes)")

                if not dry_run:
                    kept_id = primary_file["id"]
                    for dup in redundant_files:
                        dup_id = dup["id"]
                        if dup_id != kept_id:
                            with db() as c:
                                c.execute(
                                    "UPDATE recordings SET drive_file_id = ? WHERE drive_file_id = ?",
                                    (kept_id, dup_id)
                                )
                                c.execute(
                                    "UPDATE drive_sync_jobs SET drive_file_id = ? WHERE drive_file_id = ?",
                                    (kept_id, dup_id)
                                )
                            print(f"    [*] Đang xóa bản sao thừa: ID {dup_id} - {dup['name']}")
                            try:
                                drive.delete(dup_id)
                                deleted_files_count += 1
                            except Exception as e:
                                print(f"    [!] Lỗi khi xóa file {dup_id}: {e}")

                    updated_db_records += 1

    if duplicate_files_count == 0:
        print("[v] Không tìm thấy file audio trùng lặp nào trên Drive.")
    else:
        print(f"\n[Kết quả File Audio] Phát hiện {duplicate_files_count} file audio bị trùng.")
        if not dry_run:
            print(f"[v] Đã xóa thành công {deleted_files_count} file thừa và đồng bộ lại cơ sở dữ liệu.")
        else:
            print(f"[*] Chạy lệnh không có cờ --dry-run để tự động dọn dẹp và cập nhật database.")

    print("\n" + "=" * 60)
    print("HOÀN TẤT KIỂM TRA!")
    print("=" * 60)


def main():
    parser = argparse.ArgumentParser(description="LiemWhisper Google Drive Duplicates Cleanup Utility")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="Chỉ quét và báo cáo danh sách trùng lặp, không thực hiện thay đổi trên Drive"
    )
    args = parser.parse_args()
    cleanup_drive(dry_run=args.dry_run)


if __name__ == "__main__":
    main()
