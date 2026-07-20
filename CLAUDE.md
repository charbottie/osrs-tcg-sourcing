# Claude Session Context — OSRS TCG Vault

## Who You're Working With
**Lottie** (Charlotte Taylor, Supercell) — OSRS data analytics background, wants to contribute to the Bronzeman TCG RuneLite plugin. She participated in a private Discord ticket with the plugin developers (see `discord/private-ticket.md`).

## Session Protocol
- **Always show context % at the start of each response** (estimate, e.g. "~40% context used")
- **Update `PROJECT_LOG.md`** at the end of each session with what was done
- **Keep README.md and CLAUDE.md current** when project state changes meaningfully

## Project Goal
Help Lottie understand the codebase well enough to contribute to `Felmeme/bronzeman-tcg`. Start with quick wins (card browser, CI automation), build toward harder features (ID-based lookup, wiki integration).

## Key People
- **Az [TCG]** (GitHub: Azderi) — OSRS TCG core plugin. Not involved in Bronzeman dev directly but willing to add fields to Card.json if needed.
- **Felmeme [TCG]** (GitHub: Felmeme) — Bronzeman TCG developer. Open to collaboration. Uses IntelliJ; commits himself (Claude edits files, Felmeme commits).

## Repos (cloned locally)
- `plugins/osrs-tcg/` → `Azderi/osrs-tcg`
- `plugins/bronzeman-tcg/` → `Felmeme/bronzeman-tcg`

## Architecture in 60 Seconds

**OSRS TCG**: Players earn credits via gameplay → open packs → collect cards. State stored in RuneLite ConfigManager as `RLTCG_v2:base64(XOR(gzip(JSON)))`. Cards have no numeric IDs — name is the key. 6,376 cards: 1,227 Monster + 5,149 Resource.

**Bronzeman TCG**: Reads OSRS TCG ownership and enforces restrictions (can't attack uncollected NPCs, can't pick up uncollected items, can't gather without appropriate cards). Uses two mechanisms:
1. **PluginMessage API** (`osrstcg/query-owned-names`) — preferred, event-driven
2. **Config decode fallback** — `TcgCollectionReader` with 5-second cache

Enforcement via `MenuOptionClicked`: hide menu entries + consume click if locked.

## Key Files
| File | What it does |
|------|-------------|
| `plugins/bronzeman-tcg/src/.../BronzemanTcgPlugin.java` | Main enforcement engine |
| `plugins/bronzeman-tcg/src/.../TcgCollectionReader.java` | Reads OSRS TCG state |
| `plugins/bronzeman-tcg/src/.../CardNameCatalog.java` | Entity→card name mapping |
| `plugins/bronzeman-tcg/src/.../BronzemanTcgConfig.java` | All settings (17 sections) |
| `plugins/bronzeman-tcg/CLAUDE.md` | **Felmeme's own handoff doc — READ THIS FIRST** |
| `plugins/osrs-tcg/src/.../OwnedCardNamesApiService.java` | Inter-plugin API |
| `plugins/osrs-tcg/src/.../CardDefinition.java` | Card data model |
| `research/card-catalog.json` | Full card catalog snapshot |

## Bronzeman CLAUDE.md
The Bronzeman plugin has its own `plugins/bronzeman-tcg/CLAUDE.md` — this is Felmeme's handoff document from prior AI-assisted development sessions. It contains:
- Current status of every feature
- Deferred items and known bugs
- Operational notes (build, release flow, wiki scraping rules)
- Backlog and roadmap

Always read it before making changes to the Bronzeman plugin.

## Contribution Rules (from Bronzeman CLAUDE.md)
- **Never rename a config keyName** — wipes player settings
- **Never set a non-empty default on user-editable list fields** — RuneLite re-injects it
- **Plan before implementing** — write a plan grounded in existing code, discuss before coding
- **Owner commits** — Claude edits files and verifies build; Felmeme commits/pushes
- Prefer fewer config options, not more

## Documentation Files
- `docs/osrs-tcg-architecture.md` — Core plugin classes, credit system, inter-plugin API
- `docs/bronzeman-architecture.md` — Enforcement engine, catalog system, all settings
- `docs/data-structures.md` — Card.json schema, state format, catalog snapshot format
- `docs/opportunities.md` — Contribution ideas with effort/dependency assessment
- `PROJECT_LOG.md` — Session history

## Build (Bronzeman)
```bash
export JAVA_HOME="/c/Program Files/Eclipse Adoptium/jdk-11.0.31.11-hotspot"
./gradlew build --no-daemon
./gradlew run   # dev client
```
