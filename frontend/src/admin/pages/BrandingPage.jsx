import { useSelector } from "react-redux";
import { selectSite } from "@/store/slices/siteSlice";
import { cn } from "@/utils/format";
import { AdminPageHeader } from "../components/AdminPageHeader";
import { SettingsForm } from "../components/SettingsForm";

/** Live sample of the chosen presets, rendered with the same tokens as the website. */
function PresetPreview({ values }) {
  return (
    <section
      aria-label="Style preview"
      className="rounded-xl border border-charcoal/10 bg-white p-5"
    >
      <h2 className="font-sans text-base font-semibold">Preview</h2>
      <p className="text-sm text-muted">Approved presets only, so colours always stay readable.</p>
      <div
        className="mt-4 overflow-hidden rounded-xl border border-charcoal/10"
        data-palette={values["branding.palette"]}
        data-type={values["branding.typography"]}
        data-buttons={values["branding.button_shape"]}
        data-images={values["branding.image_style"]}
      >
        <div className="bg-ivory p-6">
          <p className="text-sm font-semibold tracking-[0.14em] text-sage-700 uppercase">Eyebrow</p>
          <h3 className="mt-2 text-3xl font-medium">A Better Mindset.</h3>
          <p className="mt-2 text-muted">Practical encouragement for every season of life.</p>
          <div className="mt-4 flex flex-wrap gap-2">
            <span className="tpa-button inline-flex rounded-full bg-sage-700 px-5 py-2 text-sm font-medium text-ivory">
              Primary button
            </span>
            <span className="tpa-button inline-flex rounded-full border border-charcoal/25 px-5 py-2 text-sm font-medium text-charcoal">
              Outline button
            </span>
          </div>
          <div className="mt-5 grid grid-cols-3 gap-3">
            {["bg-sage-100", "bg-gold-100", "bg-beige"].map((bg) => (
              <div key={bg} className={cn("aspect-[3/2] rounded-[var(--radius-card)]", bg)} />
            ))}
          </div>
        </div>
        <div className="bg-sage-800 px-6 py-4 text-ivory">
          Deep sage section <span className="text-gold-300">with a gold accent</span>
        </div>
      </div>
    </section>
  );
}

export function BrandingPage() {
  const favicon = useSelector(selectSite)?.data?.branding?.favicon;
  return (
    <>
      <AdminPageHeader
        title="Branding"
        description="Site name, logos, favicon, social sharing image and approved style presets."
        breadcrumbs={[{ label: "Branding" }]}
      />
      <SettingsForm groups={["Branding"]}>
        {({ values }) => (
          <>
            <PresetPreview values={values} />
            {favicon && (
              <section
                aria-label="Current favicon"
                className="flex items-center gap-4 rounded-xl border border-charcoal/10 bg-white p-5"
              >
                <img src={favicon.png192} alt="" width={48} height={48} className="rounded-lg" />
                <img src={favicon.png32} alt="" width={16} height={16} />
                <p className="text-sm text-muted">
                  favicon.ico, 32px, Apple touch and 192/512px app icons are generated
                  automatically.
                </p>
              </section>
            )}
          </>
        )}
      </SettingsForm>
    </>
  );
}
