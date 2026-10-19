"use client";

import { useEffect, useRef, useState, type ComponentPropsWithRef, type HTMLAttributes, type ReactNode } from "react";

export function Button({ variant = "secondary", className = "", ...props }: ComponentPropsWithRef<"button"> & { variant?: "primary" | "secondary" | "ghost" }) {
  return <button className={`ui-button ${variant} ${className}`} {...props} />;
}
export function Card(props: HTMLAttributes<HTMLElement>) { return <section {...props} className={`ui-card ${props.className || ""}`} />; }
export function Badge({ children }: { children: ReactNode }) { return <span className="ui-badge">{children}</span>; }
export function Progress({ value, label }: { value: number; label: string }) {
  return <div className="ui-progress" role="progressbar" aria-label={label} aria-valuenow={value} aria-valuemin={0} aria-valuemax={100}><span style={{ width: `${value}%` }} /></div>;
}
export function Toast({ children, onClose }: { children: ReactNode; onClose: () => void }) {
  useEffect(() => { const timer = setTimeout(onClose, 4000); return () => clearTimeout(timer); }, [children, onClose]);
  return <div className="ui-toast" role="status"><span>{children}</span><Button variant="ghost" aria-label="Đóng thông báo" onClick={onClose}>×</Button></div>;
}
export function Select({ value, options, onChange, label }: { value: string; options: { value: string; label: string }[]; onChange: (value: string) => void; label: string }) {
  const [open, setOpen] = useState(false);
  const root = useRef<HTMLDivElement>(null);
  const trigger = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    if (!open) return;
    const close = (e: PointerEvent) => { if (!root.current?.contains(e.target as Node)) setOpen(false); };
    document.addEventListener("pointerdown", close);
    root.current?.querySelector<HTMLButtonElement>('[aria-selected="true"]')?.focus();
    return () => document.removeEventListener("pointerdown", close);
  }, [open]);
  return <div className="ui-select" ref={root} onBlur={e => { if (!e.currentTarget.contains(e.relatedTarget)) setOpen(false); }} onKeyDown={e => {
    if (e.key === "Escape") { setOpen(false); trigger.current?.focus(); }
    if (["ArrowDown", "ArrowUp", "Home", "End"].includes(e.key)) {
      e.preventDefault(); if (!open) { setOpen(true); return; }
      const items = Array.from(root.current?.querySelectorAll<HTMLButtonElement>('[role="option"]') || []);
      const index = items.indexOf(document.activeElement as HTMLButtonElement);
      const next = e.key === "Home" ? 0 : e.key === "End" ? items.length - 1 : (index + (e.key === "ArrowDown" ? 1 : -1) + items.length) % items.length;
      items[next]?.focus();
    }
  }}>
    <Button ref={trigger} aria-label={label} aria-haspopup="listbox" aria-expanded={open} onClick={() => setOpen(!open)}>{options.find(o => o.value === value)?.label || "Chọn môn học"}<span aria-hidden="true">⌄</span></Button>
    {open && <div className="ui-options" role="listbox" aria-label={label}>{options.map(o => <button key={o.value} role="option" aria-selected={value === o.value} onClick={() => { onChange(o.value); setOpen(false); trigger.current?.focus(); }}>{o.label}</button>)}</div>}
  </div>;
}
export function Skeleton() { return <div className="ui-skeleton" role="status" aria-label="Đang tải dữ liệu"><span /><span /><span /></div>; }

// Native dialog supplies focus containment, Escape handling and focus restoration.
export function useConfirmation() {
  const dialog = useRef<HTMLDialogElement>(null);
  const resolver = useRef<((answer: boolean) => void) | null>(null);
  const [message, setMessage] = useState("");
  useEffect(() => () => { resolver.current?.(false); }, []);
  function confirmAction(text: string) {
    setMessage(text);
    dialog.current?.showModal();
    return new Promise<boolean>(resolve => { resolver.current = resolve; });
  }
  function finish(answer: boolean) {
    dialog.current?.close(); resolver.current?.(answer); resolver.current = null;
  }
  const modal = <dialog className="ui-modal" ref={dialog} aria-label="Xác nhận thao tác" onCancel={e => { e.preventDefault(); finish(false); }}><h2>Xác nhận thao tác</h2><p>{message}</p><div><Button autoFocus onClick={() => finish(false)}>Hủy</Button><Button variant="primary" onClick={() => finish(true)}>Xác nhận</Button></div></dialog>;
  return { confirmAction, modal };
}
