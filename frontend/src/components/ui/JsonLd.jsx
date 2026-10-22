import { safeJson } from "@/utils/structuredData";

/** Inline JSON-LD (rendered into the prerendered HTML body). */
export function JsonLd({ data }) {
  return <script type="application/ld+json" dangerouslySetInnerHTML={{ __html: safeJson(data) }} />;
}
