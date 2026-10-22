import { LogoMark } from "@/components/layout/Logo";
import { Seo } from "@/components/seo/Seo";

/** Centered card used by sign-in, activation and password reset screens. */
export function AuthCard({ title, subtitle, children }) {
  return (
    <div className="flex min-h-dvh items-center justify-center bg-cream px-4 py-12">
      <Seo title={`${title} · Admin`} path="/admin" noIndex />
      <div className="w-full max-w-sm rounded-2xl border border-charcoal/10 bg-ivory p-8 shadow-lift">
        <div className="mb-6 flex items-center gap-3">
          <LogoMark />
          <div>
            <h1 className="text-2xl font-medium">{title}</h1>
            <p className="text-sm text-muted">{subtitle ?? "Think Positive Always"}</p>
          </div>
        </div>
        {children}
      </div>
    </div>
  );
}
