import { ImageResponse } from "next/og";

export const ogSize = { width: 1200, height: 630 };

/** Shared branded Open Graph card rendered at build time. */
export function renderOgImage({ eyebrow, title }: { eyebrow: string; title: string }) {
  return new ImageResponse(
    <div
      style={{
        width: "100%",
        height: "100%",
        display: "flex",
        flexDirection: "column",
        justifyContent: "space-between",
        background: "#faf6ee",
        padding: "72px 80px",
        position: "relative",
      }}
    >
      <div
        style={{
          position: "absolute",
          right: -120,
          bottom: -160,
          width: 560,
          height: 560,
          borderRadius: 9999,
          background: "#dcc28a",
          opacity: 0.55,
        }}
      />
      <div
        style={{
          position: "absolute",
          right: 0,
          bottom: 0,
          width: 1200,
          height: 150,
          background: "#6f8761",
        }}
      />
      <div style={{ display: "flex", alignItems: "center", gap: 18 }}>
        <div
          style={{
            width: 56,
            height: 56,
            borderRadius: 9999,
            background: "#45593c",
            display: "flex",
          }}
        />
        <div style={{ fontSize: 30, color: "#24221f", letterSpacing: -0.5 }}>
          Think Positive Always
        </div>
      </div>
      <div style={{ display: "flex", flexDirection: "column", maxWidth: 900, marginBottom: 120 }}>
        <div
          style={{
            fontSize: 24,
            color: "#45593c",
            textTransform: "uppercase",
            letterSpacing: 4,
            marginBottom: 20,
          }}
        >
          {eyebrow}
        </div>
        <div style={{ fontSize: 66, lineHeight: 1.1, color: "#24221f", letterSpacing: -1.5 }}>
          {title}
        </div>
      </div>
    </div>,
    ogSize,
  );
}
