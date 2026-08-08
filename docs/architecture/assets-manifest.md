# Asset manifest & placeholder atlas

## Rule

Saves and game logic reference **content IDs only** (`cat:mizzle:v1`, `plant:fern:v1`).  
They never store sprite paths or atlas coordinates.

## Layout

| Path | Role |
|---|---|
| `content/assets/manifest.json` | Versioned visual recipes per content ID |
| `apps/web/src/assets/palette.ts` | Style-bible palette names → RGB |
| `apps/web/src/assets/placeholder-draw.ts` | Deterministic 32×32 / 16×16 pixel draw |
| `apps/web/src/assets/atlas.ts` | Texture cache + nearest sampling |
| `art/accepted/` | Future human-promoted PNGs (Art Factory) |

## Swap path (scalable)

When Art Factory promotes a sprite:

1. Write PNG under `art/accepted/<id>/`  
2. Build step packs `public/assets/atlases/…`  
3. Update manifest frame rects (or a parallel `frames` map)  
4. `atlas.ts` loads real textures first, placeholders as fallback  

No save migration required.

## Pixel contract

- Cats 32×32, plants 16×16, integer display scale only  
- Nearest-neighbor sampling (`scaleMode: "nearest"`)  
- Binary alpha + palette colors only (placeholder pipeline)
