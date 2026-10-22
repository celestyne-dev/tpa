import { Link } from "react-router";
import { Seo } from "@/components/seo/Seo";
import { Container } from "@/components/ui/Container";
import { Notice } from "@/components/ui/Notice";
import { PageHeader } from "@/components/ui/PageHeader";
import { routes } from "@/config/navigation";
import { formatDate } from "@/utils/format";

/** Shared layout for legal documents. DRAFT pending legal review, clearly labelled. */
export function LegalPage({ title, path, description, metaDescription, lastUpdated, children }) {
  return (
    <>
      <Seo title={title} description={metaDescription ?? description} path={path} />
      <PageHeader
        eyebrow="Legal"
        title={title}
        description={description}
        breadcrumbs={[
          { name: "Home", href: routes.home },
          { name: title, href: path },
        ]}
      />
      <Container size="narrow" className="py-14 sm:py-20">
        <Notice title="Draft — pending legal review">
          This document is a working draft provided for transparency while the Think Positive Always
          website is being developed. It has not yet been reviewed by a legal professional and will
          be updated before commercial features such as purchases, accounts, or newsletter
          subscriptions are launched.
        </Notice>
        <p className="mt-8 text-sm text-muted">
          Last updated: <time dateTime={lastUpdated}>{formatDate(lastUpdated)}</time>
        </p>
        <div className="prose-legal mt-6">{children}</div>
      </Container>
    </>
  );
}

export function ContactSentence() {
  return (
    <p>
      If you have questions about this document, please visit our{" "}
      <Link to={routes.contact} className="font-medium text-sage-700 underline underline-offset-4">
        contact page
      </Link>{" "}
      for the current ways to reach us.
    </p>
  );
}
