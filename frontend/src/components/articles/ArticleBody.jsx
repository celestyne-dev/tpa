import { ArrowRight, CircleCheck, Info, Lightbulb, Play, TriangleAlert } from "lucide-react";
import { createContext, useContext, useMemo, useState } from "react";
import { Link } from "react-router";
import { ContentImage, IMAGE_SIZES } from "@/components/ui/ContentImage";
import { routes } from "@/config/navigation";
import { cn, slugify } from "@/utils/format";

const calloutStyles = {
  info: { icon: Info, className: "border-sage-200 bg-sage-50" },
  tip: { icon: Lightbulb, className: "border-gold-300 bg-gold-100/60" },
  warning: { icon: TriangleAlert, className: "border-red-200 bg-red-50" },
  success: { icon: CircleCheck, className: "border-sage-300 bg-sage-100/70" },
};

const isInternal = (href) => href?.startsWith("/");

/** Internal links use the router; external ones open normally with safe rel. */
// Paid links listed on a sponsored article's sponsorship (rel="sponsored"); others are organic.
const SponsoredLinksContext = createContext(null);

function SmartLink({ href, className, children }) {
  const sponsored = useContext(SponsoredLinksContext)?.has(href);
  if (isInternal(href) && !sponsored)
    return (
      <Link to={href} className={className}>
        {children}
      </Link>
    );
  return (
    <a
      href={href}
      className={className}
      rel={sponsored ? "sponsored noopener noreferrer" : "noopener noreferrer"}
    >
      {children}
    </a>
  );
}

const alignClass = {
  center: "",
  wide: "lg:-mx-16",
  full: "lg:-mx-32 xl:-mx-48",
  left: "sm:float-left sm:mr-6 sm:mb-3 sm:w-1/2",
  right: "sm:float-right sm:ml-6 sm:mb-3 sm:w-1/2",
};

function Figure({ image, caption, align = "center" }) {
  const credit = image.credit;
  const sizes =
    align === "full"
      ? IMAGE_SIZES.full
      : align === "wide"
        ? IMAGE_SIZES.wide
        : align === "left" || align === "right"
          ? "(min-width: 640px) 360px, 100vw"
          : IMAGE_SIZES.body;
  const text = caption || image.caption;
  return (
    <figure className={cn("not-prose", alignClass[align])}>
      <ContentImage image={image} sizes={sizes} className="w-full rounded-2xl" />
      {(text || credit) && (
        <figcaption className="mt-2 text-sm text-muted">
          {text}
          {credit && <span className="ml-1 text-xs">({credit})</span>}
        </figcaption>
      )}
    </figure>
  );
}

/** Privacy-friendly video: nothing loads from the provider until the reader asks for it. */
function VideoEmbed({ provider, videoId, title, caption }) {
  const [active, setActive] = useState(false);
  const src =
    provider === "youtube"
      ? `https://www.youtube-nocookie.com/embed/${videoId}?autoplay=1&rel=0`
      : `https://player.vimeo.com/video/${videoId}?autoplay=1&dnt=1`;
  return (
    <figure className="not-prose">
      <div className="relative aspect-video overflow-hidden rounded-2xl bg-charcoal">
        {active ? (
          <iframe
            src={src}
            title={title}
            className="absolute inset-0 h-full w-full"
            allow="autoplay; encrypted-media; picture-in-picture; fullscreen"
            referrerPolicy="strict-origin-when-cross-origin"
            loading="lazy"
          />
        ) : (
          <button
            type="button"
            onClick={() => setActive(true)}
            className="absolute inset-0 flex flex-col items-center justify-center gap-3 text-ivory"
          >
            <span className="grid size-16 place-items-center rounded-full bg-ivory/15 ring-2 ring-ivory/60">
              <Play aria-hidden className="size-7" />
            </span>
            <span className="px-6 text-center text-base font-medium">Play video: {title}</span>
            <span className="text-xs text-ivory/70">
              Loads from {provider === "youtube" ? "YouTube" : "Vimeo"}
            </span>
          </button>
        )}
      </div>
      {caption && <figcaption className="mt-2 text-sm text-muted">{caption}</figcaption>}
    </figure>
  );
}

/** Renders structured article blocks as semantic HTML (text only, no raw HTML injection). */
export function ArticleBody({ blocks, sponsoredLinks }) {
  const paid = useMemo(() => new Set(sponsoredLinks ?? []), [sponsoredLinks]);
  return (
    <SponsoredLinksContext.Provider value={paid}>
      <ArticleBlocks blocks={blocks} />
    </SponsoredLinksContext.Provider>
  );
}

function ArticleBlocks({ blocks }) {
  return (
    <div className="prose-tpa flow-root">
      {blocks.map((block, index) => {
        switch (block.type) {
          case "paragraph":
            return <p key={index}>{block.text}</p>;
          case "heading": {
            const Heading = block.level === 3 ? "h3" : "h2";
            return (
              <Heading key={index} id={block.id ?? slugify(block.text)}>
                {block.text}
              </Heading>
            );
          }
          case "list": {
            const List = block.ordered ? "ol" : "ul";
            return (
              <List key={index}>
                {block.items.map((item, i) => (
                  <li key={i}>{item}</li>
                ))}
              </List>
            );
          }
          case "quote":
            return (
              <blockquote key={index}>
                <p>{block.text}</p>
                {block.cite && (
                  <footer className="mt-3 font-sans text-base text-muted not-italic">
                    — {block.cite}
                  </footer>
                )}
              </blockquote>
            );
          case "pullquote":
            return (
              <figure
                key={index}
                className="not-prose my-10 border-y-2 border-gold-300 py-8 text-center"
              >
                <blockquote className="font-serif text-3xl leading-snug text-charcoal italic">
                  “{block.text}”
                </blockquote>
                {block.cite && (
                  <figcaption className="mt-4 text-sm font-semibold tracking-wide text-sage-700 uppercase">
                    {block.cite}
                  </figcaption>
                )}
              </figure>
            );
          case "callout": {
            const style = calloutStyles[block.tone] ?? calloutStyles.info;
            const Icon = style.icon;
            return (
              <aside
                key={index}
                className={cn("flex gap-4 rounded-2xl border p-5 text-base", style.className)}
              >
                <Icon aria-hidden className="mt-1 size-5 shrink-0 text-charcoal" />
                <div>
                  {block.title && <p className="font-semibold text-charcoal">{block.title}</p>}
                  <p className={block.title ? "mt-1" : undefined}>{block.text}</p>
                </div>
              </aside>
            );
          }
          case "divider":
            return <hr key={index} className="mx-auto w-24 border-t-2 border-gold-300" />;
          case "image":
            return block.image ? (
              <Figure key={index} image={block.image} caption={block.caption} align={block.align} />
            ) : null;
          case "gallery":
            return (
              <figure key={index} className="not-prose">
                <ul
                  className={cn(
                    "grid grid-cols-2 gap-3",
                    block.columns === 3 && "sm:grid-cols-3",
                    block.columns === 4 && "sm:grid-cols-4",
                  )}
                >
                  {(block.items ?? []).map((item, i) => (
                    <li key={i}>
                      <ContentImage
                        image={item.image}
                        sizes={IMAGE_SIZES.gallery}
                        className="aspect-square w-full rounded-xl object-cover"
                      />
                      {item.caption && <p className="mt-1 text-xs text-muted">{item.caption}</p>}
                    </li>
                  ))}
                </ul>
                {block.caption && (
                  <figcaption className="mt-2 text-sm text-muted">{block.caption}</figcaption>
                )}
              </figure>
            );
          case "video":
            return (
              <VideoEmbed
                key={index}
                provider={block.provider}
                videoId={block.video_id}
                title={block.title}
                caption={block.caption}
              />
            );
          case "button":
            return (
              <p key={index} className={cn("not-prose", block.align === "center" && "text-center")}>
                <SmartLink
                  href={block.href}
                  className={cn(
                    "inline-flex items-center gap-2 rounded-full px-6 py-3 text-base font-semibold no-underline",
                    block.style === "secondary"
                      ? "border border-charcoal/20 text-charcoal hover:border-sage-600"
                      : "bg-sage-700 text-ivory hover:bg-sage-800",
                  )}
                >
                  {block.label}
                  <ArrowRight aria-hidden className="size-4" />
                </SmartLink>
              </p>
            );
          case "cta":
            return (
              <aside
                key={index}
                className="not-prose rounded-[var(--radius-card)] bg-sage-800 p-8 text-ivory"
              >
                <p className="font-serif text-2xl">{block.title}</p>
                {block.text && <p className="mt-2 text-ivory/80">{block.text}</p>}
                <SmartLink
                  href={block.button_href}
                  className="mt-5 inline-flex items-center gap-2 rounded-full bg-gold-300 px-6 py-3 font-semibold text-charcoal no-underline hover:bg-gold-400"
                >
                  {block.button_label}
                  <ArrowRight aria-hidden className="size-4" />
                </SmartLink>
              </aside>
            );
          case "related":
            return (
              <aside key={index} className="not-prose rounded-2xl border border-charcoal/10 p-6">
                <p className="text-sm font-semibold tracking-[0.14em] text-sage-700 uppercase">
                  {block.title || "Related reading"}
                </p>
                <ul className="mt-4 space-y-3">
                  {(block.articles ?? []).map((a) => (
                    <li key={a.slug} className="flex items-center gap-4">
                      <span className="relative block size-16 shrink-0 overflow-hidden rounded-lg bg-beige">
                        <ContentImage
                          image={a.image}
                          fill
                          sizes={IMAGE_SIZES.thumb}
                          className="object-cover"
                        />
                      </span>
                      <Link
                        to={routes.article(a.slug)}
                        className="font-serif text-lg leading-snug text-charcoal no-underline hover:text-sage-700"
                      >
                        {a.title}
                      </Link>
                    </li>
                  ))}
                </ul>
              </aside>
            );
          case "resource":
            return (
              <aside
                key={index}
                className="not-prose flex flex-col gap-4 rounded-2xl border border-gold-300 bg-cream p-6 sm:flex-row sm:items-center"
              >
                {block.image && (
                  <span className="relative block aspect-[4/3] w-full shrink-0 overflow-hidden rounded-xl sm:w-32">
                    <ContentImage image={block.image} fill sizes="128px" className="object-cover" />
                  </span>
                )}
                <div className="flex-1">
                  <p className="font-serif text-xl text-charcoal">{block.title}</p>
                  {block.description && (
                    <p className="mt-1 text-base text-muted">{block.description}</p>
                  )}
                </div>
                <SmartLink
                  href={block.href}
                  className="inline-flex items-center gap-2 font-semibold text-sage-700 no-underline hover:underline"
                >
                  {block.label || "Learn more"}
                  <ArrowRight aria-hidden className="size-4" />
                </SmartLink>
              </aside>
            );
          case "table": {
            const [head, ...rows] = block.header_row ? block.rows : [null, ...block.rows];
            return (
              <div key={index} className="not-prose overflow-x-auto">
                <table className="w-full border-collapse text-left text-base">
                  {block.caption && (
                    <caption className="mb-2 text-left text-sm text-muted">{block.caption}</caption>
                  )}
                  {head && (
                    <thead>
                      <tr>
                        {head.map((cell, i) => (
                          <th
                            key={i}
                            scope="col"
                            className="border-b-2 border-sage-200 px-3 py-2 font-semibold"
                          >
                            {cell}
                          </th>
                        ))}
                      </tr>
                    </thead>
                  )}
                  <tbody>
                    {rows.map((row, r) => (
                      <tr key={r} className="border-b border-charcoal/10">
                        {row.map((cell, c) => (
                          <td key={c} className="px-3 py-2 align-top">
                            {cell}
                          </td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            );
          }
          default:
            return null;
        }
      })}
    </div>
  );
}
