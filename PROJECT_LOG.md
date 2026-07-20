# Project Log

---

## 2026-07-19 — Session 1: Initial Setup & Research

**Goal**: Orient Lottie in the OSRS TCG ecosystem and establish a usable vault structure.

### What was done

**Research**:
- Read all 3 Discord exports (Announcements, FAQ, private ticket with Az/Felmeme/Lottie)
- Found GitHub repos via API search:
  - `Azderi/osrs-tcg` — Az's core TCG plugin (Java, Gradle, 13 stars)
  - `Felmeme/bronzeman-tcg` — Felmeme's Bronzeman plugin (Java, Gradle, Plugin Hub live)
  - `Sqwiglyy/groupman-tcg` — separate competing implementation, not the one we're working with
- Fetched `OsrsTcgPlugin.java`, `CardDatabase.java`, `CardDefinition.java`, `CardNameCatalog.java`, `TcgCollectionReader.java` via WebFetch before cloning
- Discovered `plugins/bronzeman-tcg/CLAUDE.md` — Felmeme's own detailed handoff doc from prior AI sessions

**Setup**:
- Created folder structure: `discord/`, `plugins/`, `docs/`, `research/`
- Moved Discord exports into `discord/` with clean names
- Cloned both repos into `plugins/`
- Fetched and saved `research/card-catalog.json` (6,376 cards, 2.8MB)

**Documentation written**:
- `docs/data-structures.md` — Card.json schema (Monster + Resource fields), state encoding, catalog snapshot format
- `docs/osrs-tcg-architecture.md` — Package structure, credit system, inter-plugin API, state persistence, debug commands
- `docs/bronzeman-architecture.md` — Class structure, OSRS TCG data reading (2 methods), enforcement flow, catalog system, all config sections, operational notes
- `docs/opportunities.md` — 7 contribution ideas ranked by effort/dependency

### Key findings

1. **Cards have no numeric IDs** — name is the sole key. This is the root of the name-matching complexity in Bronzeman.

2. **Two inter-plugin communication paths**: 
   - PluginMessage API (instant, event-driven) — built in both plugins, awaiting upstream release
   - Config decode fallback (TcgCollectionReader, 5s cache) — always available

3. **Bronzeman is further along than expected** — full skill suite implemented (cooking, smithing, crafting, herblore, fletching, hunting, farming, thieving, runecrafting, sailing, mining, woodcutting, fishing). Already on Plugin Hub with real users.

4. **Felmeme's CLAUDE.md is the ground truth** for Bronzeman's current state. Read it before making any changes to that plugin.

5. **Next agreed feature in Bronzeman**: card browser panel (grouped card view by skill/type). Design is Felmeme/owner's call.

6. **Wiki integration**: both devs have been in touch with wiki team. Scraping rules — plain page URLs, 1 req/sec, cache everything, never api.php at runtime.

### Context used this session
~45% (estimated)
