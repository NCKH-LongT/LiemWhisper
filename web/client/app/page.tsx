export default function Home() {
  return <main style={{maxWidth: 760, margin: "64px auto", padding: 24}}>
    <p style={{color: "#366c9d", fontWeight: 700}}>LIEMWHISPER · PROTOTYPE</p>
    <h1>Thu thập dữ liệu tiếng nói Việt–Anh</h1>
    <p>Đây là bản khởi tạo giao diện. Hệ thống đăng nhập, chấp thuận tham gia, khảo sát, phân công câu nói và lưu Google Drive chưa được triển khai.</p>
    <section style={{padding: 20, border: "1px solid #d0d7e2", borderRadius: 12, background: "white"}}>
      <h2>Quy trình dự kiến</h2>
      <p>Đăng nhập → Đồng ý tham gia nghiên cứu → Khảo sát → Nhận câu từ server → Ghi âm → Nghe lại → Gửi → Kiểm duyệt.</p>
      <p style={{color: "#ad431f"}}><strong>Chưa thu âm hoặc gửi dữ liệu cá nhân trên bản prototype này.</strong></p>
    </section>
  </main>;
}
