import React, { useEffect, useRef, useId } from "react";
import { X } from "lucide-react";
import { label } from "./api";
export function Badge({ value }: { value: string }) {
  return (
    <span className={"badge " + value}>
      <i />
      {label(value)}
    </span>
  );
}
export function Modal({
  title,
  close,
  children,
  className,
  closeLabel = "Close dialog",
}: {
  title: string;
  close: () => void;
  children: React.ReactNode;
  className?: string;
  closeLabel?: string;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  const titleId = useId();
  useEffect(() => {
    const dialog = ref.current;
    dialog?.showModal();
    return () => dialog?.close();
  }, []);
  return (
    <dialog
      ref={ref}
      className={className}
      aria-labelledby={titleId}
      onCancel={(e) => {
        e.preventDefault();
        close();
      }}
    >
      <div className="modalHeader">
        <h2 id={titleId}>{title}</h2>
        <button aria-label={closeLabel} onClick={close}>
          <X size={18} />
        </button>
      </div>
      {children}
    </dialog>
  );
}
