"""Conservative reconciliation: preserve unknown files, trash verified duplicates."""
import hashlib
from collections import defaultdict

from app.drive_lock import serialized_drive

FOLDER = "application/vnd.google-apps.folder"


@serialized_drive
def cleanup_duplicates(db_factory, drive):
    from app.worker import participant_folder, sync_drive_manifest_csv

    with db_factory() as c:
        participants = [dict(r) for r in c.execute(
            "SELECT id, participant_code, name, email, drive_folder_id FROM participants"
        ).fetchall()]
        recordings = [dict(r) for r in c.execute(
            "SELECT id, participant_id, drive_file_id, sha256 FROM recordings WHERE drive_sync_status='synced'"
        ).fetchall()]
        all_active_ids = {r["drive_file_id"] for r in c.execute(
            "SELECT drive_file_id FROM recordings WHERE drive_file_id IS NOT NULL"
        ).fetchall()}
    root_items = drive.list_children(drive.folder_id)
    folders = [f for f in root_items if f.get("mimeType") == FOLDER]
    by_name = defaultdict(list)
    for p in participants:
        code = (p["participant_code"] or "").strip() or f"SV_{p['id'][:6]}"
        label = (p["name"] or p["email"] or "").strip()
        p["folder_name"] = f"{code} - {label}" if label else code
        by_name[p["folder_name"]].append(p["id"])
    deleted_files = deleted_folders = merged = preserved = 0
    for p in participants:
        # Same display name is not proof that two accounts are the same person.
        if len(by_name[p["folder_name"]]) != 1:
            preserved += 1
            continue
        owned = [r for r in recordings if r["participant_id"] == p["id"] and r["drive_file_id"]]
        if not owned:
            continue
        primary = participant_folder(db_factory, drive, p["id"], p["folder_name"])
        candidates = [f for f in folders if f["name"] == p["folder_name"] or f["id"] == primary]
        folder_ids = {f["id"] for f in candidates} | {primary}
        # Include misplaced recordings in the root; only exact recording IDs below qualify.
        items = [f for f in root_items if f.get("mimeType") != FOLDER]
        for folder_id in folder_ids:
            items.extend(drive.list_children(folder_id))
        item_map = {f["id"]: f for f in items}
        for r in owned:
            canonical = item_map.get(r["drive_file_id"])
            if not canonical:
                preserved += 1
                continue
            expected = r["sha256"]
            if hashlib.sha256(drive.download(canonical["id"])).hexdigest() != expected:
                preserved += 1
                continue
            if not drive.move_and_rename_file(canonical["id"], canonical["name"], primary):
                preserved += 1
                continue
            for duplicate in items:
                did = duplicate["id"]
                if did in all_active_ids or duplicate.get("mimeType") == FOLDER:
                    continue
                # Exact name includes recording ID, not just the question number.
                if duplicate["name"] != canonical["name"]:
                    continue
                if hashlib.sha256(drive.download(did)).hexdigest() != expected:
                    preserved += 1
                    continue
                # Recheck SQL: do not discard audio if re-recording happened meanwhile.
                with db_factory() as c:
                    current = c.execute("SELECT sha256, drive_file_id FROM recordings WHERE id=?", (r["id"],)).fetchone()
                    if not current or current["sha256"] != expected or current["drive_file_id"] != canonical["id"]:
                        preserved += 1
                        continue
                    drive.trash(did)
                deleted_files += 1
        for folder_id in folder_ids - {primary}:
            # Never remove a nonempty folder, even after a partially successful move.
            if drive.list_children(folder_id):
                preserved += 1
                continue
            with db_factory() as c:
                used = c.execute("SELECT id FROM participants WHERE drive_folder_id=?", (folder_id,)).fetchone()
            if used:
                preserved += 1
                continue
            drive.trash(folder_id)
            deleted_folders += 1
            merged += 1
    sync_drive_manifest_csv(db_factory, drive)
    return {
        "status": "success", "merged_folders_count": merged,
        "deleted_folders_count": deleted_folders, "deleted_files_count": deleted_files,
        "db_duplicates_removed": 0, "preserved_count": preserved,
        "message": f"Đã đưa {deleted_files} file trùng đã xác minh và {deleted_folders} thư mục rỗng vào thùng rác. Giữ lại {preserved} mục cần kiểm tra; không xóa bản thu khác nội dung.",
    }
