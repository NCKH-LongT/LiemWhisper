import type { ReactNode } from "react";
export const metadata = {title: "LiemWhisper — Data Collection", description: "Research recording platform (prototype)"};
export default function RootLayout({children}: {children: ReactNode}) {
  return <html lang="vi"><body style={{fontFamily: "Arial, sans-serif", margin: 0, background: "#f8fafc", color: "#172033"}}>{children}</body></html>;
}
