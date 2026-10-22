import { Monitor, Smartphone, Tablet } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { cn } from "@/utils/format";

const DEVICES = {
  desktop: { width: 1280, label: "Desktop", icon: Monitor },
  tablet: { width: 768, label: "Tablet", icon: Tablet },
  mobile: { width: 390, label: "Mobile", icon: Smartphone },
};

/**
 * Live preview of unsaved edits: the draft is posted (debounced) to a same-origin
 * iframe that renders the real public components at true device widths.
 */
export function PreviewPane({ pageId, payload, height = 720 }) {
  const [device, setDevice] = useState("desktop");
  const [ready, setReady] = useState(false);
  const [width, setWidth] = useState(640);
  const frameRef = useRef(null);
  const wrapRef = useRef(null);
  const serialized = JSON.stringify(payload);

  useEffect(() => {
    const el = wrapRef.current;
    if (!el || typeof ResizeObserver === "undefined") return undefined;
    const observer = new ResizeObserver(([entry]) => setWidth(entry.contentRect.width));
    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    const onMessage = (event) => {
      if (event.origin !== window.location.origin) return;
      if (event.data?.type === "tpa-preview-ready") setReady(true);
    };
    window.addEventListener("message", onMessage);
    return () => window.removeEventListener("message", onMessage);
  }, []);

  useEffect(() => {
    if (!ready) return undefined;
    const timer = setTimeout(() => {
      frameRef.current?.contentWindow?.postMessage(
        { type: "tpa-preview-update", payload: JSON.parse(serialized) },
        window.location.origin,
      );
    }, 500);
    return () => clearTimeout(timer);
  }, [ready, serialized]);

  const deviceWidth = DEVICES[device].width;
  const scale = Math.min(1, width / deviceWidth);
  return (
    <div className="rounded-xl border border-charcoal/10 bg-beige/40 p-3">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <p className="text-sm font-medium text-charcoal">Live preview (unsaved changes included)</p>
        <div role="group" aria-label="Preview size" className="flex gap-1">
          {Object.entries(DEVICES).map(([key, d]) => (
            <button
              key={key}
              type="button"
              aria-pressed={device === key}
              onClick={() => setDevice(key)}
              className={cn(
                "inline-flex items-center gap-1.5 rounded-full px-3 py-1 text-sm",
                device === key ? "bg-charcoal text-ivory" : "bg-white text-charcoal hover:bg-sand",
              )}
            >
              <d.icon aria-hidden className="size-4" />
              {d.label}
            </button>
          ))}
        </div>
      </div>
      <div ref={wrapRef} className="overflow-hidden rounded-lg bg-white" style={{ height }}>
        <iframe
          ref={frameRef}
          title={`Live preview (${DEVICES[device].label})`}
          src={`/admin/preview-frame/${pageId}`}
          style={{
            width: deviceWidth,
            height: height / scale,
            transform: `scale(${scale})`,
            transformOrigin: "top left",
          }}
          className="block border-0"
        />
      </div>
    </div>
  );
}
