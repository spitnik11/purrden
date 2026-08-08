# Content ID convention

**Rule:** persisted state and game logic may only reference stable content IDs — never filenames,
atlas coordinates, or raw asset paths.

## Pattern

```text
<kind>:<slug>:v<major>
```

| Kind | Example | Notes |
|---|---|---|
| `cat` | `cat:mizzle:v1` | Species/archetype identity; evolution stages are metadata, not new IDs unless identity splits |
| `plant` | `plant:fern:v1` | Placeable garden content |
| `biome` | `biome:meadow:v1` | Garden biome unlock |
| `ruleset` | `ruleset:2026.09.0` | Balance/tuning package version (calendar-ish) |
| `sprite` | `cat:mizzle:v1:idle:0` | Frame-level art identity (manifest only; saves use cat/plant IDs) |
| `palette` | `palette:purrden-core:v1` | Style bible palette package |
| `recipe` | `recipe:cat-master:v3` | Art generation recipe version |

## Versioning

- **`:v1`** is the durable game identity. Art repacks, palette tweaks, and re-exports do **not** bump
  the content ID if gameplay identity is unchanged.
- Breaking gameplay identity (new species behavior, incompatible bond curve) → new ID
  (`cat:mizzle:v2`) with migration rules if needed.
- Ruleset versions are packages (`2026.09.0`); visits store the ruleset/content version used for
  that spawn so replays stay honest.

## Forbidden

```text
assets/cats/puddle-final-final3.png   ✗
public/atlases/cats-2026.09.0.png     ✗ in saves (OK in build output only)
```

Manifest mapping (build-time only):

```json
{
  "cat:mizzle:v1": {
    "atlas": "cats-2026.09.0",
    "frames": { "idle": [0, 1], "blink": [2] }
  }
}
```
