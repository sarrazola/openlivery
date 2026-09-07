"use client";

import { ReactNode, useEffect } from "react";
import { createPortal } from "react-dom";
import { X } from "lucide-react";

export function StatusBadge({ active }: { active: boolean }) {
  return <span className={`status ${active ? "status-active" : "status-inactive"}`}><i />{active ? "Activo" : "Inactivo"}</span>;
}

export function Modal({ open, title, description, onClose, children }: { open: boolean; title: string; description?: string; onClose: () => void; children: ReactNode }) {
  // Escape closes the dialog, like clicking outside it or the X.
  useEffect(() => {
    if (!open) return;
    const onKey = (event: KeyboardEvent) => { if (event.key === "Escape") { event.preventDefault(); onClose(); } };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);
  if (!open || typeof document === "undefined") return null;
  // Rendered at the body so no ancestor (a transformed or filtered wrapper,
  // a sticky bar) can clip the backdrop or stack above it.
  return createPortal(
    <div className="modal-backdrop" onMouseDown={onClose}>
      <section className="modal" role="dialog" aria-modal="true" aria-label={title} onMouseDown={(event) => event.stopPropagation()}>
        <div className="modal-head">
          <div><h2>{title}</h2>{description && <p>{description}</p>}</div>
          <button className="icon-button" onClick={onClose} aria-label="Cerrar"><X size={18} /></button>
        </div>
        {children}
      </section>
    </div>,
    document.body,
  );
}

export function PageHead({ eyebrow, title, description, action }: { eyebrow?: string; title: string; description: string; action?: ReactNode }) {
  return (
    <header className="page-head">
      <div>{eyebrow && <span className="eyebrow">{eyebrow}</span>}<h1>{title}</h1><p>{description}</p></div>
      {action}
    </header>
  );
}

export function EmptyState({ icon, title, description, action }: { icon: ReactNode; title: string; description: string; action?: ReactNode }) {
  return <div className="empty-state"><div className="empty-icon">{icon}</div><h3>{title}</h3><p>{description}</p>{action}</div>;
}

export function Alert({ type = "error", children }: { type?: "error" | "success" | "info"; children: ReactNode }) {
  return <div className={`alert alert-${type}`}>{children}</div>;
}
