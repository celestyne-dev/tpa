/**
 * Articles and quote collections share the article editor, revisions, review and
 * publishing tools; these are the words and admin paths that differ between them.
 */
export const CONTENT_KINDS = {
  article: {
    key: "article",
    plural: "Articles",
    singular: "article",
    newTitle: "New article",
    newLabel: "New article",
    untitled: "Untitled article",
    base: "/admin/articles",
    back: "← Back to articles",
    description: "Create, edit and publish editorial content.",
  },
  quotes: {
    key: "quotes",
    plural: "Quotes",
    singular: "quote collection",
    newTitle: "New quote collection",
    newLabel: "New quote collection",
    untitled: "Untitled quote collection",
    base: "/admin/quotes",
    back: "← Back to quote collections",
    description:
      "Quote collections at /quotes: numbered quotes with images between them, your own reflections and related articles. New collections start with indexing off.",
  },
};

export const contentKind = (type) => CONTENT_KINDS[type] ?? CONTENT_KINDS.article;
