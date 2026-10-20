"use client";

import { useCallback, useEffect, useState } from "react";

type Delivery = { participant_id: string; participant_code: string; email: string; status: string; message: string };
type Status = { sender: string | null; provider: string; permission_granted: boolean; deliveries: Delivery[] };
const labels: Record<string, string> = {
  pending: "Chờ gửi", sending: "Đang gửi", sent: "Đã gửi", failed: "Gửi thất bại", unknown: "Chưa xác định"
};

export function AdminEmailPanel({ apiBase, adminToken }: { apiBase: string; adminToken: string }) {
  const [data, setData] = useState<Status | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const refresh = useCallback(async () => {
    try {
      const response = await fetch(`${apiBase}/api/v1/admin/email/status`, { headers: { "x-admin-key": adminToken } });
      if (!response.ok) throw new Error("Không tải được trạng thái thư cảm ơn.");
      setData(await response.json());
      setError("");
    } catch { setError("Không tải được trạng thái thư cảm ơn."); }
  }, [apiBase, adminToken]);
  useEffect(() => {
    void refresh();
    const timer = setInterval(() => void refresh(), 10000);
    return () => clearInterval(timer);
  }, [refresh]);
  async function retry(id: string) {
    setBusy(true);
    try {
      const response = await fetch(`${apiBase}/api/v1/admin/email/${encodeURIComponent(id)}/retry`, {
        method: "POST", headers: { "x-admin-key": adminToken }
      });
      if (!response.ok) throw new Error();
      await refresh();
    } catch { setError("Không thể thử lại thư này. Hãy làm mới trạng thái."); }
    finally { setBusy(false); }
  }
  return <section className="card" style={{ padding: 20, marginBottom: 20 }}>
    <h3>Thư cảm ơn</h3>
    <p>Tài khoản gửi: {data?.sender || "Chưa liên kết"}</p>
    {data?.provider === "gmail_api" && !data.permission_granted &&
      <p>Bật Gmail API trong Google Cloud, sau đó bấm “Liên kết lại Google Drive” ở trên và cấp quyền gửi thư.</p>}
    <p>Hiển thị tối đa 100 thư gần nhất. Các phiên hoàn thành trước khi bật theo dõi không được tự động gửi lại.</p>
    <button onClick={() => void refresh()}>Làm mới trạng thái</button>
    {error && <p role="alert">{error}</p>}
    <div style={{ overflowX: "auto" }}>
      <table style={{ width: "100%" }}>
        <thead><tr><th>Người nhận</th><th>Trạng thái</th><th>Chi tiết</th><th>Thao tác</th></tr></thead>
        <tbody>{data?.deliveries.map(row => <tr key={row.participant_id}>
          <td>{row.participant_code}<br />{row.email}</td>
          <td>{labels[row.status] || row.status}</td><td>{row.message}</td>
          <td>{row.status === "failed" && <button disabled={busy} onClick={() => void retry(row.participant_id)}>Thử gửi lại</button>}</td>
        </tr>)}</tbody>
      </table>
    </div>
  </section>;
}
