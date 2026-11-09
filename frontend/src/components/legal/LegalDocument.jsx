import { ArrowRight, ChevronDown, Info } from "lucide-react";
import { Link } from "react-router";
import { ArticleBody } from "@/components/articles/ArticleBody";
import { Breadcrumbs } from "@/components/ui/Breadcrumbs";
import { Container } from "@/components/ui/Container";
import { routes } from "@/config/navigation";
import { useNavigation } from "@/hooks/useNavigation";
import { cn, formatDate } from "@/utils/format";
import { DEFAULT_LEGAL_LINKS, withAnchors } from "./legalAnchors";
import { RichInline } from "./RichInline";

function TocList({ toc, className }) {
  return (
    <ol className={cn("space-y-1 text-[0.95rem]", className)}>
      {toc.map((item) => (
        <li key={item.id}>
          <a
            href={`#${item.id}`}
            className="block rounded-md py-1 text-ink underline-offset-4 hover:text-sage-800 hover:underline"
          >
            {item.text}
          </a>
          {item.children.length > 0 && (
            <ol className="mt-1 ml-3 space-y-1 border-l border-charcoal/10 pl-3 text-sm">
              {item.children.map((child) => (
                <li key={child.id}>
                  <a
                    href={`#${child.id}`}
                    className="block py-0.5 text-muted underline-offset-4 hover:text-sage-800 hover:underline"
                  >
                    {child.text}
                  </a>
                </li>
              ))}
            </ol>
          )}
        </li>
      ))}
    </ol>
  );
}

/** Legal text: paragraphs, numbered or plain headings, lists, tables, links and emphasis. */
export function LegalBody({ blocks }) {
  return (
    <div className="prose-legal">
      {blocks.map((block, index) => {
        switch (block.type) {
          case "paragraph":
            return (
              <p key={index}>
                <RichInline text={block.text} />
              </p>
            );
          case "heading": {
            const Heading = block.level === 3 ? "h3" : "h2";
            return (
              <Heading key={index} id={block.anchorId} className="scroll-mt-28">
                {block.text}
              </Heading>
            );
          }
          case "list": {
            const List = block.ordered ? "ol" : "ul";
            return (
              <List key={index}>
                {block.items.map((item, i) => (
                  <li key={i}>
                    <RichInline text={item} />
                  </li>
                ))}
              </List>
            );
          }
          case "table": {
            const [head, ...rows] = block.header_row ? block.rows : [null, ...block.rows];
            return (
              <div key={index} className="overflow-x-auto rounded-xl border border-charcoal/10">
                <table className="w-full border-collapse text-left text-[0.95rem]">
                  {block.caption && (
                    <caption className="px-4 pt-3 text-left text-sm text-muted">
                      {block.caption}
                    </caption>
                  )}
                  {head && (
                    <thead className="bg-cream">
                      <tr>
                        {head.map((cell, i) => (
                          <th key={i} scope="col" className="px-4 py-2.5 font-semibold">
                            {cell}
                          </th>
                        ))}
                      </tr>
                    </thead>
                  )}
                  <tbody>
                    {rows.map((row, r) => (
                      <tr key={r} className="border-t border-charcoal/10">
                        {row.map((cell, c) => (
                          <td key={c} className="px-4 py-2.5 align-top">
                            <RichInline text={cell} />
                          </td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            );
          }
          case "callout":
            return (
              <aside
                key={index}
                role="note"
                className="flex gap-3 rounded-2xl border border-sage-200 bg-sage-50 p-5"
              >
                <Info aria-hidden className="mt-1 size-5 shrink-0 text-sage-700" />
                <div>
                  {block.title && <p className="font-semibold text-charcoal">{block.title}</p>}
                  <p>
                    <RichInline text={block.text} />
                  </p>
                </div>
              </aside>
            );
          case "divider":
            return <hr key={index} className="border-charcoal/10" />;
          default:
            // Quotes, images and other article blocks keep their usual rendering.
            return <ArticleBody key={index} blocks={[block]} />;
        }
      })}
    </div>
  );
}

/** Links to the other legal pages: the CMS footer's "Legal" column, else the defaults. */
function useLegalLinks(currentPath) {
  const { footer } = useNavigation();
  const column = footer.find((group) => /legal/i.test(group.title ?? ""));
  const links = column?.items?.length ? column.items : DEFAULT_LEGAL_LINKS;
  return links.filter((link) => link.href && link.href !== currentPath);
}

function DateItem({ label, value }) {
  if (!value) return null;
  return (
    <div>
      <dt className="text-xs font-semibold tracking-[0.14em] text-sage-700 uppercase">{label}</dt>
      <dd className="mt-1 text-charcoal">
        <time dateTime={value}>{formatDate(value)}</time>
      </dd>
    </div>
  );
}

/**
 * The shared legal page layout, used by the built-in legal pages and by the CMS "Legal
 * document" section: a header (title, dates, summary), an optional notice, the document
 * in a comfortable reading column with an automatic table of contents (a sticky sidebar
 * on large screens, a collapsible list on phones and tablets), related legal links and a
 * pointer to the contact page.
 */
export function LegalDocument({
  title,
  eyebrow = "Legal",
  summary,
  effectiveDate,
  lastUpdated,
  notice,
  blocks,
  path,
  breadcrumbs,
  headingLevel = 1,
  showToc = true,
  showRelated = true,
  className,
}) {
  const { blocks: anchored, toc } = withAnchors(blocks);
  const related = useLegalLinks(path);
  const Title = headingLevel === 1 ? "h1" : "h2";
  const hasToc = showToc && toc.length > 1;
  const crumbs = breadcrumbs ?? [
    { name: "Home", href: routes.home },
    { name: title, href: path },
  ];

  return (
    <div data-legal-document className={cn("bg-ivory", className)}>
      <header className="border-b border-charcoal/[0.08] bg-cream">
        <Container size="wide" className="py-10 sm:py-14">
          {crumbs.length > 0 && <Breadcrumbs items={crumbs} className="mb-8" />}
          <div className="max-w-3xl">
            {eyebrow && (
              <p className="mb-3 text-xs font-semibold tracking-[0.16em] text-sage-700 uppercase">
                {eyebrow}
              </p>
            )}
            <Title className="text-4xl leading-tight font-medium text-balance sm:text-5xl">
              {title}
            </Title>
            <div aria-hidden className="mt-5 h-0.5 w-14 rounded-full bg-gold-400" />
            {summary && <p className="mt-5 text-lg text-muted sm:text-xl">{summary}</p>}
            {(effectiveDate || lastUpdated) && (
              <dl className="mt-6 flex flex-wrap gap-x-10 gap-y-3 text-[0.95rem]">
                <DateItem label="Effective date" value={effectiveDate} />
                <DateItem label="Last updated" value={lastUpdated} />
              </dl>
            )}
          </div>
        </Container>
      </header>

      <Container
        size="wide"
        className={cn(
          "py-10 sm:py-14",
          hasToc && "lg:grid lg:grid-cols-[15rem_minmax(0,1fr)] lg:gap-16",
        )}
      >
        {hasToc && (
          <aside className="hidden lg:block">
            <nav aria-label="Table of contents" className="sticky top-28">
              <p className="mb-3 text-xs font-semibold tracking-[0.14em] text-sage-700 uppercase">
                On this page
              </p>
              <TocList toc={toc} />
              <p className="mt-8 border-t border-charcoal/10 pt-5 text-sm text-muted">
                Questions about this document?{" "}
                <Link to={routes.contact} className="font-medium text-sage-700 underline">
                  Contact us
                </Link>
              </p>
            </nav>
          </aside>
        )}

        <div className="max-w-[70ch] min-w-0">
          {hasToc && (
            <details className="group mb-8 rounded-2xl border border-charcoal/10 bg-white/60 lg:hidden">
              <summary className="flex cursor-pointer list-none items-center justify-between gap-3 px-5 py-4 font-medium text-charcoal [&::-webkit-details-marker]:hidden">
                On this page
                <ChevronDown
                  aria-hidden
                  className="size-5 text-sage-700 transition-transform group-open:rotate-180"
                />
              </summary>
              <nav aria-label="Table of contents" className="border-t border-charcoal/10 px-5 py-4">
                <TocList toc={toc} />
              </nav>
            </details>
          )}

          {notice?.text && (
            <aside
              role="note"
              className="mb-8 flex gap-4 rounded-2xl border border-gold-300 bg-gold-100/60 p-5 text-[0.95rem] text-ink"
            >
              <Info aria-hidden className="mt-0.5 size-5 shrink-0 text-gold-700" />
              <div>
                {notice.title && <p className="font-semibold text-charcoal">{notice.title}</p>}
                <p className="mt-1 text-muted">{notice.text}</p>
              </div>
            </aside>
          )}

          <LegalBody blocks={anchored} />

          {showRelated && related.length > 0 && (
            <nav
              aria-label="Related legal pages"
              className="mt-14 border-t border-charcoal/10 pt-8"
            >
              <p className="text-xs font-semibold tracking-[0.14em] text-sage-700 uppercase">
                Related
              </p>
              <ul className="mt-4 grid gap-3 sm:grid-cols-2">
                {related.map((link) => (
                  <li key={link.href}>
                    <Link
                      to={link.href}
                      className="flex items-center justify-between gap-3 rounded-xl border border-charcoal/10 bg-white/60 px-5 py-4 font-medium text-charcoal transition-colors hover:border-sage-600 hover:text-sage-800"
                    >
                      {link.label}
                      <ArrowRight aria-hidden className="size-4 shrink-0 text-sage-700" />
                    </Link>
                  </li>
                ))}
              </ul>
            </nav>
          )}
        </div>
      </Container>
    </div>
  );
}
