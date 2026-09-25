import { ImageResponse } from "next/og";
import { site } from "../lib/site";
import BrandMark from "./brand-mark";

export const dynamic = "force-static";
export const alt = `${site.name} — purchase orders, confirmed in one place`;
export const size = { width: 1200, height: 630 };
export const contentType = "image/png";

export default function OpengraphImage() {
  return new ImageResponse(
    (
      <div
        style={{
          width: "100%",
          height: "100%",
          display: "flex",
          flexDirection: "column",
          justifyContent: "space-between",
          padding: 72,
          background: "linear-gradient(140deg, #353535 0%, #284b63 100%)",
          color: "#ffffff",
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: 18 }}>
          <BrandMark size={52} color="#ffffff" />
          <div style={{ fontSize: 44, fontWeight: 700 }}>{site.name}</div>
        </div>

        <div style={{ display: "flex", flexDirection: "column", gap: 24 }}>
          <div
            style={{
              fontSize: 26,
              letterSpacing: 4,
              textTransform: "uppercase",
              color: "#d9d9d9",
            }}
          >
            For B2B suppliers and Singapore SMEs
          </div>
          <div
            style={{
              fontSize: 82,
              fontWeight: 700,
              lineHeight: 1.05,
              maxWidth: 940,
            }}
          >
            Purchase orders, confirmed in one place.
          </div>
        </div>

        <div style={{ display: "flex", gap: 20, color: "#d9d9d9", fontSize: 26 }}>
          <div>Read</div>
          <div style={{ color: "#3c6e71" }}>→</div>
          <div>Confirm</div>
          <div style={{ color: "#3c6e71" }}>→</div>
          <div>Ask</div>
        </div>
      </div>
    ),
    size,
  );
}
