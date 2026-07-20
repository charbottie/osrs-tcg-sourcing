# 02a — Sourcing Panel UI Mockups

These are ASCII wireframes showing the panel layout for each card type. All views live inside the existing `CollectionAlbumWindow` — no new windows.

---

## Current State (No Sourcing Panel)

Clicking an unowned card does nothing. Clicking an owned card shows trade controls at the bottom.

```
┌─────────────────────────────────────────────────┐
│  [Search________] [Filter ▼] [All ▼]  < 1/47 > │
├─────────────────────────────────────────────────┤
│                                                  │
│  [img] Abyssal whip  [img] Abyssal dagger  ...   │
│  [img] Tanzanite fang  [img] Magic fang    ...   │
│  ...                                             │
│                                                  │
├─────────────────────────────────────────────────┤
│                    [Trade] [Party]               │
└─────────────────────────────────────────────────┘
```

---

## Proposed: Master-Detail Split

Click any card → bottom panel slides up with sourcing info. Click empty space → collapses back.

```
┌─────────────────────────────────────────────────┐
│  [Search________] [Filter ▼] [All ▼]  < 1/47 > │
├─────────────────────────────────────────────────┤
│                                                  │
│  [img] Abyssal whip ◀ selected                  │
│  [img] Abyssal dagger  [img] Tanzanite fang ...  │
│  ...                                             │
│                                                  │
├ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─┤  ← detail panel
│  Abyssal whip                             [×]   │
│  Dropped by                                     │
│  ✓ Abyssal demon           Rare  1/512          │
│  ✓ Grotesque Guardians     Rare  1/1000         │
│                                                  │
│  Quests                                         │
│  (none required to access these monsters)       │
├─────────────────────────────────────────────────┤
│                    [Trade] [Party]               │
└─────────────────────────────────────────────────┘
```

`✓` = you own that monster card. `✗` = you don't. Instantly scannable.

---

## View: Item Card — Multiple Drop Sources

```
┌─────────────────────────────────────────────────┐
│  Rune full helm                           [×]   │
│  ─────────────────────────────────────────────  │
│  Dropped by                                     │
│  ✓ Abyssal demon        Uncommon  1/64          │
│  ✗ Greater demon        Uncommon  1/64          │
│  ✗ Cockroach soldier    Common    1/10          │
│  ✗ Fire giant           Common    1/20          │
│  ─────────────────────────────────────────────  │
│  Quests                                         │
│  (none)                                         │
└─────────────────────────────────────────────────┘
```

---

## View: Item Card — Quest-Locked (No Prerequisites)

```
┌─────────────────────────────────────────────────┐
│  Silverlight                              [×]   │
│  ─────────────────────────────────────────────  │
│  Dropped by                                     │
│  (not a drop — quest reward)                    │
│  ─────────────────────────────────────────────  │
│  Quests                                         │
│  ✓ Demon Slayer          Reward                 │
└─────────────────────────────────────────────────┘
```

---

## View: Item Card — Quest-Locked (With Prerequisites)

```
┌─────────────────────────────────────────────────┐
│  Zenyte shard                             [×]   │
│  ─────────────────────────────────────────────  │
│  Dropped by                                     │
│  ✗ Demonic gorilla      Uncommon  1/100         │
│  ─────────────────────────────────────────────  │
│  Quests required to access                      │
│  ✓ Monkey Madness II    (unlocks Demonic gorilla)│
│    └─ requires: Monkey Madness I                │
│         └─ requires: Tree Gnome Village ✓       │
└─────────────────────────────────────────────────┘
```

The prerequisite chain indents under the quest name. Completed quests get a ✓ (in future — this requires RuneLite quest state API, may not be available in Phase 1).

---

## View: Monster Card — What It Drops

```
┌─────────────────────────────────────────────────┐
│  Abyssal demon                            [×]   │
│  Monster · Slayer 85                            │
│  ─────────────────────────────────────────────  │
│  TCG card drops                                 │
│  ✓ Abyssal whip         Rare    1/512           │
│  ✗ Abyssal head         Rare    1/512           │
│  ✗ Abyssal dagger       V.Rare  1/1000          │
│  ✓ Rune full helm       Uncommon 1/64           │
│  ─────────────────────────────────────────────  │
│  Quests                                         │
│  (none required)                                │
└─────────────────────────────────────────────────┘
```

Monster cards show what drops you can get from them, filtered to only TCG cards. `✓`/`✗` shows ownership of each drop card.

---

## View: Monster Card — Quest Requirement

```
┌─────────────────────────────────────────────────┐
│  Demonic gorilla                          [×]   │
│  Monster · No slayer req                        │
│  ─────────────────────────────────────────────  │
│  TCG card drops                                 │
│  ✗ Zenyte shard         Uncommon  1/100         │
│  ✗ Ballista spring      Common    1/25          │
│  ─────────────────────────────────────────────  │
│  Requires quests                                │
│  ✗ Monkey Madness II                           │
│    └─ Monkey Madness I, Tree Gnome Village,    │
│       Royal Trouble                             │
└─────────────────────────────────────────────────┘
```

---

## View: Shop-Bought Item

```
┌─────────────────────────────────────────────────┐
│  Tinderbox                                [×]   │
│  ─────────────────────────────────────────────  │
│  Available from shops                           │
│  No monsters required · No quests required      │
└─────────────────────────────────────────────────┘
```

---

## View: Boss with Multiple Access Methods

```
┌─────────────────────────────────────────────────┐
│  Zulrah                                   [×]   │
│  Monster · No slayer req                        │
│  ─────────────────────────────────────────────  │
│  TCG card drops                                 │
│  ✗ Tanzanite fang       Rare    1/512           │
│  ✗ Magic fang           Rare    1/512           │
│  ✗ Serpentine visage    Rare    1/512           │
│  ✓ Onyx                 Uncommon 1/128          │
│  ✓ Zulrah's scales      Always  1/1             │
│  ─────────────────────────────────────────────  │
│  Requires quests                                │
│  ✓ Regicide                                     │
│    └─ Underground Pass, Plague City             │
└─────────────────────────────────────────────────┘
```

---

## Colour Coding (RuneLite conventions)

| Element | Colour |
|---------|--------|
| ✓ owned card name | `Color(0, 200, 83)` — green |
| ✗ unowned card name | `Color(200, 200, 200)` — grey |
| Rarity label: Always/Common | `Color(0, 200, 83)` — green |
| Rarity label: Uncommon | `Color(180, 180, 0)` — yellow |
| Rarity label: Rare | `Color(0, 150, 255)` — blue |
| Rarity label: Very Rare | `Color(160, 0, 220)` — purple |
| Rarity label: Extremely Rare | `Color(255, 100, 0)` — orange |
| Fraction text | `Color(150, 150, 150)` — dim grey |
| Quest name (complete) | `Color(0, 200, 83)` — green |
| Quest name (incomplete) | `Color(200, 200, 200)` — grey |
| Section headers | `Color(255, 255, 255)` — white bold |

---

## Layout Notes

- Detail panel height: ~160px fixed (fits ~5 drop rows + quest row)
- Overflow: scroll within detail panel if many drops
- Card grid shrinks proportionally when detail panel is open
- `[×]` close button collapses detail panel, grid returns to full height
- Fraction text right-aligned against the panel edge
- Rarity label between card name and fraction

---

## Phase 1 Scope (Minimal Viable)

Skip quest completion status (requires RuneLite quest state integration):
- Phase 1: show quest names without ✓/✗
- Phase 2: add quest completion check via `QuestState` API

Phase 1 UI for quests:
```
│  Requires quests                                │
│  Monkey Madness II                             │
│    └─ Monkey Madness I, Tree Gnome Village     │
```
No tick marks — just informational. Adds value immediately without the quest API complexity.
