import { CheckCircle2, AlertTriangle, X } from "lucide-react";
import { useCallback, useMemo, useRef, useState } from "react";
import { cn } from "@/utils/format";
import { NotifyContext } from "./notifyContext";

/** Toast notifications for success/error feedback (announced to assistive tech). */
export function NotificationProvider({ children }) {
  const [items, setItems] = useState([]);
  const nextId = useRef(1);

  const dismiss = useCallback((id) => setItems((list) => list.filter((n) => n.id !== id)), []);
  const notify = useCallback(
    (message, tone = "success") => {
      const id = nextId.current++;
      setItems((list) => [...list.slice(-3), { id, message, tone }]);
      setTimeout(() => dismiss(id), tone === "error" ? 8000 : 4000);
    },
    [dismiss],
  );
  const value = useMemo(() => notify, [notify]);

  return (
    <NotifyContext.Provider value={value}>
      {children}
      <div className="pointer-events-none fixed right-4 bottom-4 z-[70] flex w-[min(24rem,calc(100vw-2rem))] flex-col gap-2">
        {items.map((n) => (
          <div
            key={n.id}
            role={n.tone === "error" ? "alert" : "status"}
            className={cn(
              "pointer-events-auto flex items-start gap-3 rounded-xl border px-4 py-3 text-sm shadow-lift",
              n.tone === "error"
                ? "border-red-200 bg-red-50 text-red-900"
                : "border-sage-200 bg-white text-charcoal",
            )}
          >
            {n.tone === "error" ? (
              <AlertTriangle aria-hidden className="mt-0.5 size-4 shrink-0" />
            ) : (
              <CheckCircle2 aria-hidden className="mt-0.5 size-4 shrink-0 text-sage-700" />
            )}
            <p className="flex-1">{n.message}</p>
            <button
              type="button"
              onClick={() => dismiss(n.id)}
              aria-label="Dismiss notification"
              className="rounded p-0.5 text-muted hover:text-charcoal"
            >
              <X aria-hidden className="size-4" />
            </button>
          </div>
        ))}
      </div>
    </NotifyContext.Provider>
  );
}
