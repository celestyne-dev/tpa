/**
 * robots.txt for the prerendered site.
 *
 * - Search engines and AI *search* crawlers (OAI-SearchBot, ChatGPT-User, Claude-SearchBot,
 *   Claude-User, PerplexityBot, Perplexity-User, ...) follow the general rules: the public
 *   site is open, private and utility paths are not.
 * - AI *model-training* crawlers get their own group with `Disallow: /` unless approved one
 *   by one in Admin › Settings › Technical (the API lists the ones still blocked).
 * - Previews, staging and local builds are never crawlable at all.
 */
export const DEFAULT_BLOCKED_TRAINING_CRAWLERS = [
  "GPTBot",
  "ClaudeBot",
  "Google-Extended",
  "Applebot-Extended",
  "CCBot",
  "Meta-ExternalAgent",
  "Bytespider",
];

/** Crawlers that must never be blocked by this file (search visibility). */
export const SEARCH_CRAWLERS = [
  "Googlebot",
  "Bingbot",
  "OAI-SearchBot",
  "ChatGPT-User",
  "Claude-SearchBot",
  "Claude-User",
  "PerplexityBot",
  "Perplexity-User",
  "DuckDuckBot",
  "Applebot",
];

export const PRIVATE_PATHS = [
  "/api/",
  "/admin/",
  "/account",
  "/cart",
  "/checkout",
  "/purchases",
  "/newsletter/",
  "/resources/access",
  "/learn/",
  "/certificates/",
];

const TOKEN = /^[A-Za-z][A-Za-z0-9._-]{0,63}$/;

export function buildRobots({ allowIndexing, siteUrl, blockedTrainingCrawlers }) {
  if (!allowIndexing) {
    // Previews, staging and local builds must never be indexed.
    return "User-agent: *\nDisallow: /\n";
  }
  const blocked = (blockedTrainingCrawlers ?? DEFAULT_BLOCKED_TRAINING_CRAWLERS).filter(
    (token) =>
      TOKEN.test(token) && !SEARCH_CRAWLERS.some((s) => s.toLowerCase() === token.toLowerCase()),
  );
  const lines = ["User-agent: *", "Allow: /", ...PRIVATE_PATHS.map((p) => `Disallow: ${p}`), ""];
  if (blocked.length > 0) {
    lines.push(
      "# AI model-training crawlers: not allowed unless approved in Admin > Settings > Technical.",
      "# Search engines and AI search crawlers follow the rules above.",
    );
    for (const token of blocked) lines.push(`User-agent: ${token}`, "Disallow: /", "");
  }
  lines.push(`Sitemap: ${siteUrl}/sitemap.xml`, "");
  return lines.join("\n");
}

/**
 * Minimal robots.txt reader: may `agent` fetch `path`? (Longest matching rule wins; the
 * agent's own group replaces `*`.) Used to check the generated file.
 */
export function isAllowed(robots, agent, path) {
  const groups = [];
  let current = null;
  for (const raw of robots.split("\n")) {
    const line = raw.replace(/#.*/, "").trim();
    if (!line) continue;
    const [key, ...rest] = line.split(":");
    const value = rest.join(":").trim();
    const field = key.trim().toLowerCase();
    if (field === "user-agent") {
      if (!current || current.rules.length > 0) groups.push((current = { agents: [], rules: [] }));
      current.agents.push(value.toLowerCase());
    } else if ((field === "allow" || field === "disallow") && current) {
      current.rules.push({ allow: field === "allow", path: value });
    }
  }
  const own = groups.filter((g) => g.agents.includes(agent.toLowerCase()));
  const rules = (own.length ? own : groups.filter((g) => g.agents.includes("*"))).flatMap(
    (g) => g.rules,
  );
  let best = null;
  for (const rule of rules) {
    if (rule.path && path.startsWith(rule.path) && (!best || rule.path.length > best.path.length))
      best = rule;
  }
  return best ? best.allow : true;
}
