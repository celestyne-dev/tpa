import { ArrowRight } from "lucide-react";
import { Link } from "react-router";
import { ContentImage } from "@/components/ui/ContentImage";
import { routes } from "@/config/navigation";
import { cn } from "@/utils/format";

/**
 * "About the author" at the end of an article: portrait, name, bio and a link to their
 * page. Shown only for real author records with a bio (the same rule as author pages);
 * nothing is filled in when the record has no bio.
 */
export function AuthorBox({ author, profile, className }) {
  if (!profile?.bio || profile.is_person === false) return null;
  const hasPage = author?.has_page ?? profile.has_page;
  const name = profile.name ?? author?.name;
  return (
    <section
      aria-labelledby="about-author-heading"
      className={cn(
        "flex flex-col gap-5 rounded-[var(--radius-card)] border border-charcoal/[0.08] bg-cream p-6 sm:flex-row sm:p-8",
        className,
      )}
    >
      {profile.image?.src && (
        <span className="relative block size-20 shrink-0 overflow-hidden rounded-full bg-beige">
          <ContentImage image={profile.image} fill sizes="80px" className="object-cover" />
        </span>
      )}
      <div className="min-w-0">
        <p className="text-xs font-semibold tracking-[0.16em] text-sage-700 uppercase">
          About the author
        </p>
        <h2 id="about-author-heading" className="mt-1.5 text-2xl font-medium">
          {hasPage ? (
            <Link
              to={routes.author(profile.slug ?? author.slug)}
              rel="author"
              className="underline-offset-4 hover:text-sage-800 hover:underline"
            >
              {name}
            </Link>
          ) : (
            name
          )}
        </h2>
        <p className="mt-3 leading-relaxed text-ink">{profile.bio}</p>
        {hasPage && (
          <Link
            to={routes.author(profile.slug ?? author.slug)}
            className="mt-4 inline-flex items-center gap-1.5 text-sm font-semibold text-sage-700 underline-offset-4 hover:underline"
          >
            More articles by {name}
            <ArrowRight aria-hidden className="size-4" />
          </Link>
        )}
      </div>
    </section>
  );
}
