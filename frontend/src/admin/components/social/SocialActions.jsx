import { Link } from "react-router";
import { usePermissions } from "../../hooks/usePermissions";
import { socialComposeLink, socialPostsLink } from "../../pages/social/socialLinks";

const link = "text-sage-800 underline hover:text-sage-900";

/**
 * Links into Admin › Social Publishing for one Media Library image (and, from an editor,
 * the article or quote collection it sits in). Nothing is posted from here: the links open
 * the composer with the image pre-selected. `newTab` keeps unsaved editor changes open.
 */
export function SocialActions({ mediaId, articleId, newTab = false, className = "" }) {
  const { can } = usePermissions();
  if (!mediaId || !can("social.view")) return null;
  const target = newTab ? { target: "_blank", rel: "noreferrer" } : {};
  const compose = (extra) => socialComposeLink({ media: mediaId, article: articleId, ...extra });
  return (
    <nav aria-label="Social publishing" className={className}>
      <ul className="flex flex-wrap gap-x-4 gap-y-1 text-sm">
        {can("social.publish") && (
          <>
            <li>
              <Link className={link} to={compose({ platform: "pinterest" })} {...target}>
                Send to Pinterest
              </Link>
            </li>
            <li>
              <Link className={link} to={compose({ platform: "instagram" })} {...target}>
                Publish to Instagram
              </Link>
            </li>
            <li>
              <Link className={link} to={compose({ schedule: true })} {...target}>
                Schedule social post
              </Link>
            </li>
          </>
        )}
        <li>
          <Link className={link} to={socialPostsLink(mediaId)} {...target}>
            View social posts
          </Link>
        </li>
      </ul>
    </nav>
  );
}
