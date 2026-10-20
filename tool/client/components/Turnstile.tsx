"use client";

import Script from "next/script";
import { useEffect, useRef, useState } from "react";

type TurnstileApi = {
  render: (container: HTMLElement, options: Record<string, unknown>) => string;
  remove: (id: string) => void;
};

export function Turnstile({ action, onToken }: {
  action: string;
  onToken: (token: string) => void;
}) {
  const sitekey = process.env.NEXT_PUBLIC_TURNSTILE_SITE_KEY;
  const container = useRef<HTMLDivElement>(null);
  const callback = useRef(onToken);
  callback.current = onToken;
  const [ready, setReady] = useState(false);
  const [error, setError] = useState("");
  useEffect(() => {
    const api = (window as Window & { turnstile?: TurnstileApi }).turnstile;
    if (!sitekey || !ready || !api || !container.current) return;
    const id = api.render(container.current, {
      sitekey, action, language: "vi", theme: "auto",
      callback: (token: string) => { setError(""); callback.current(token); },
      "expired-callback": () => callback.current(""),
      "error-callback": () => {
        callback.current("");
        setError("Không tải được CAPTCHA. Vui lòng kiểm tra kết nối hoặc tải lại trang.");
      },
    });
    return () => { api.remove(id); callback.current(""); };
  }, [sitekey, ready, action]);
  if (!sitekey) return null;
  return <div style={{ margin: "12px 0" }}>
    <Script src="https://challenges.cloudflare.com/turnstile/v0/api.js?render=explicit"
      onReady={() => setReady(true)}
      onError={() => setError("Không tải được CAPTCHA. Vui lòng tải lại trang.")} />
    <div ref={container} />
    {error && <p role="alert">{error}</p>}
  </div>;
}
