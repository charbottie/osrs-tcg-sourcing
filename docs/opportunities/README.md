# Contribution Opportunities

Ranked by value and actionability. Each has a full plan doc.

| # | Feature | Effort | Dependency | Doc |
|---|---------|--------|-----------|-----|
| 01 | Card browser panel (grouped by skill) | Medium | None — Bronzeman roadmap item | [→](01-card-browser.md) |
| 02 | Card sourcing panel (where to get it) | Medium-High | PR to OSRS TCG + wiki data | [→](02-sourcing-panel.md) |
| 03 | ID-based entity lookup | Medium | Az adds IDs to Card.json | [→](03-id-based-lookup.md) |
| 04 | Auto-regenerate catalogs via CI | Small | None | [→](04-auto-regenerate-catalogs.md) |
| 05 | Wiki loot table integration (data pipeline) | Large | Wiki scraping infra | [→](05-wiki-loot-pipeline.md) |
| 06 | Fix encoded name defect in snapshot generator | Tiny | None | [→](06-fix-encoded-names.md) |

## Reading Order
Start with `05-wiki-loot-pipeline.md` since it's a prerequisite for `02-sourcing-panel.md` (the main feature the user wants to build). Then read `02` for the full product plan. `01` (card browser) can be worked in parallel as it's self-contained in Bronzeman.
