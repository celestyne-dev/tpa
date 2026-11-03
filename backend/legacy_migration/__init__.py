"""Legacy website inventory and SEO migration toolkit (Batch 12.4A).

Standard library only, so it runs on the current VPS, a laptop or CI without the app's
dependencies. Every network operation is a read-only GET to an allowed host; nothing
here changes the legacy website, DNS or the new CMS. Applying approved redirects to the
CMS is a separate, explicit Flask command (``flask legacy import-redirects --apply``).

    python -m legacy_migration inventory ...   # crawl the legacy site (read-only)
    python -m legacy_migration map ...         # propose KEEP / REDIRECT_301 / RETIRE_410 / REVIEW
    python -m legacy_migration validate ...    # check a reviewed mapping file
    python -m legacy_migration gone-conf ...   # Nginx 410 rules for approved retirements
    python -m legacy_migration compare ...     # prelaunch: legacy URLs against the new site
    python -m legacy_migration sitemap-check . # new sitemap: canonical, indexable URLs only
    python -m legacy_migration report ...      # totals for the migration report

See docs/legacy-migration.md for the workflow and the CSV formats.
"""

__version__ = "1.0"
