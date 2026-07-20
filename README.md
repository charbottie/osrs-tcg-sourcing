# OSRS TCG Research Vault

Research and documentation workspace for contributing to the **OSRS TCG** and **Bronzeman TCG** RuneLite plugins.

## Who's Involved

| Person | Role | GitHub |
|--------|------|--------|
| Az [TCG] | Core OSRS TCG plugin developer | [Azderi](https://github.com/Azderi) |
| Felmeme [TCG] | Bronzeman TCG plugin developer | [Felmeme](https://github.com/Felmeme) |
| Lottie | Contributor / collaborator (this repo) | — |

## Repositories

| Plugin | Repo | Live |
|--------|------|------|
| OSRS TCG (core) | [Azderi/osrs-tcg](https://github.com/Azderi/osrs-tcg) | Plugin Hub v0.17.2 |
| Bronzeman TCG | [Felmeme/bronzeman-tcg](https://github.com/Felmeme/bronzeman-tcg) | Plugin Hub |

Both repos are cloned locally in `plugins/`.

## Links

- Discord: OSRS TCG server (see `discord/`)
- Card catalog API: `https://osrs-tcg.xyz/catalog/Card.json`
- Live profiles: `https://osrs-tcg.xyz/<username>`

## Folder Structure

```
osrs_tcg/
├── discord/                  # Discord exports (announcements, FAQ, private ticket)
├── plugins/
│   ├── osrs-tcg/             # Az's core TCG plugin source
│   └── bronzeman-tcg/        # Felmeme's Bronzeman plugin source
├── docs/                     # Architecture analysis (living docs)
│   ├── osrs-tcg-architecture.md
│   ├── bronzeman-architecture.md
│   ├── data-structures.md
│   └── opportunities.md
├── research/
│   └── card-catalog.json     # Snapshot of Card.json (6,376 cards)
├── PROJECT_LOG.md            # Session log
├── README.md                 # This file
└── CLAUDE.md                 # Claude session context
```

## Quick Reference

- **6,376 total cards**: 1,227 Monster cards + 5,149 Resource cards
- Cards have **no numeric IDs** — name is the sole key
- Bronzeman reads OSRS TCG state via compressed ConfigManager data (`RLTCG_v2:` encoding)
- Bronzeman also has a PluginMessage API (`osrstcg` / `query-owned-names`) for live updates
- NPC matching uses bundled static snapshots (`tracked_monster_names.json`), regenerated via Python script

See `docs/opportunities.md` for contribution ideas.
