import { Check, Link2, Mail } from "lucide-react";
import { useEffect, useId, useRef, useState } from "react";
import { siteConfig } from "@/config/site";
import { absoluteUrl, cn } from "@/utils/format";

const pill =
  "inline-flex min-h-10 items-center gap-2 rounded-full border border-charcoal/15 bg-white/60 px-4 text-sm font-medium text-ink transition-colors hover:border-sage-600 hover:text-sage-800 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-sage-700";

/**
 * Share links: plain links to each network's own share page (no third-party scripts,
 * trackers or buttons that load on the page), an email link, and "Copy link".
 * The shared address is the article's canonical URL.
 */
export function ShareLinks({ title, path, canonicalUrl, className }) {
  const url = canonicalUrl || absoluteUrl(path, siteConfig.url);
  const labelId = useId();
  const [copied, setCopied] = useState(false);
  const timer = useRef(null);
  useEffect(() => () => clearTimeout(timer.current), []);
  const encodedUrl = encodeURIComponent(url);
  const encodedTitle = encodeURIComponent(title);
  const networks = [
    { name: "Facebook", href: `https://www.facebook.com/sharer/sharer.php?u=${encodedUrl}` },
    { name: "X", href: `https://x.com/intent/post?url=${encodedUrl}&text=${encodedTitle}` },
    {
      name: "LinkedIn",
      href: `https://www.linkedin.com/sharing/share-offsite/?url=${encodedUrl}`,
    },
    {
      name: "Pinterest",
      href: `https://www.pinterest.com/pin/create/button/?url=${encodedUrl}&description=${encodedTitle}`,
    },
  ];

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(url);
      setCopied(true);
      clearTimeout(timer.current);
      timer.current = setTimeout(() => setCopied(false), 2500);
    } catch {
      setCopied(false);
    }
  };

  return (
    <div className={cn("flex flex-wrap items-center gap-2", className)}>
      <p id={labelId} className="mr-2 text-sm font-semibold text-charcoal">
        Share this article
      </p>
      <ul aria-labelledby={labelId} className="flex flex-wrap gap-2">
        {networks.map((network) => (
          <li key={network.name}>
            <a
              href={network.href}
              target="_blank"
              rel="noopener noreferrer"
              className={pill}
              aria-label={`Share on ${network.name} (opens in a new tab)`}
            >
              {network.name}
            </a>
          </li>
        ))}
        <li>
          <a
            href={`mailto:?subject=${encodedTitle}&body=${encodedUrl}`}
            className={pill}
            aria-label="Share by email"
          >
            <Mail aria-hidden className="size-4" />
            Email
          </a>
        </li>
        <li>
          <button type="button" onClick={copy} className={pill}>
            {copied ? (
              <Check aria-hidden className="size-4" />
            ) : (
              <Link2 aria-hidden className="size-4" />
            )}
            {copied ? "Link copied" : "Copy link"}
          </button>
        </li>
      </ul>
      <span role="status" className="sr-only">
        {copied ? "Link copied to the clipboard." : ""}
      </span>
    </div>
  );
}
