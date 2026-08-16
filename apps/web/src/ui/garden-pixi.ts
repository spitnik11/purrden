import { Application, Container, Graphics, Sprite, Text } from "pixi.js";
import { getCatTexture, getPlantTexture, preloadAllPlaceholders, preloadRealAtlas } from "../assets/atlas";
import { catLabel, plantById } from "../game/content";
import type { GameProjection } from "../game/types";
import { hexNumber } from "../assets/palette";

const VIEW_W = 960;
const VIEW_H = 540;
const WORLD_W = 1920;
const SLOT_W = 112;
const SLOT_H = 96;
const GAP = 96;
/** Display scale for native 32×32 cats (integer only). */
const CAT_SCALE = 2;
const PLANT_SCALE = 2;

/**
 * PixiJS garden — content-ID sprites via placeholder atlas (nearest sampling).
 * Falls back to simple Graphics if a texture is missing (forward-compatible).
 */
export class GardenPixi {
  app: Application | null = null;
  root: Container | null = null;
  private host: HTMLElement;
  private onSlotClick: (index: number) => void;
  private cameraX = 0;
  private projection: GameProjection | null = null;

  constructor(host: HTMLElement, onSlotClick: (index: number) => void) {
    this.host = host;
    this.onSlotClick = onSlotClick;
  }

  async init(): Promise<void> {
    const app = new Application();
    await app.init({
      width: VIEW_W,
      height: VIEW_H,
      background: "#257179",
      antialias: false,
      resolution: Math.min(window.devicePixelRatio || 1, 2),
      autoDensity: true,
      // Prefer crisp pixels when possible
      roundPixels: true,
    });
    this.host.replaceChildren(app.canvas);
    app.canvas.style.imageRendering = "pixelated";
    app.canvas.style.width = "100%";
    app.canvas.style.height = "100%";
    this.app = app;
    this.root = new Container();
    app.stage.addChild(this.root);
    preloadAllPlaceholders();
    await preloadRealAtlas();
  }

  render(proj: GameProjection): void {
    if (!this.app || !this.root) return;
    this.projection = proj;
    this.root.removeChildren();
    this.host.dataset.camera = String(this.cameraX);

    // ground strip
    const ground = new Graphics();
    ground.rect(-this.cameraX, 390, WORLD_W, 150).fill(hexNumber("moss"));
    ground.rect(-this.cameraX, 440, WORLD_W, 100).fill(hexNumber("soil"));
    this.root.addChild(ground);

    // sky / lighting via palette (no blur filters)
    const skyColor =
      proj.world.daylight === "night"
        ? hexNumber("ink")
        : proj.world.daylight === "dusk"
          ? hexNumber("dusk")
          : proj.world.daylight === "dawn"
            ? hexNumber("clay")
            : hexNumber("cool_blue");
    this.app.renderer.background.color = skyColor;

    const farX = -this.cameraX * 0.2;
    const far = new Graphics();
    far.moveTo(farX, 320).lineTo(farX + 260, 210).lineTo(farX + 560, 300).lineTo(farX + 880, 190).lineTo(farX + 1240, 285).lineTo(farX + 1560, 205).lineTo(farX + 1960, 315).lineTo(farX + 1960, 390).lineTo(farX, 390).fill(hexNumber("deep"));
    this.root.addChild(far);
    const near = new Graphics();
    for (let x = -100; x < WORLD_W; x += 150) near.circle(x + 45 - this.cameraX * 0.5, 355, 70).fill(hexNumber("pine"));
    this.root.addChild(near);

    const sun = new Graphics();
    sun.circle(830 - this.cameraX * 0.05, 92, 42).fill(
      proj.world.daylight === "night" ? hexNumber("cloud") : hexNumber("gold"),
    );
    this.root.addChild(sun);

    if (proj.world.precipitation === "rain" || proj.world.precipitation === "drizzle") {
      const rain = new Graphics();
      for (let i = 0; i < 54; i++) {
        const x = 10 + ((i * 97) % 940);
        const y = 10 + ((i * 47) % 380);
        rain.rect(x, y, 1, 6).fill(hexNumber("ice"));
      }
      this.root.addChild(rain);
    }

    proj.slots.forEach((slot, i) => {
      const x = 180 + i * (SLOT_W + GAP * 3) - this.cameraX;
      const y = 330;
      const pad = new Graphics();
      pad.roundRect(x, y, SLOT_W, SLOT_H, 6).fill(hexNumber("coal")).stroke({
        width: 2,
        color: hexNumber("mist"),
      });
      pad.eventMode = "static";
      pad.cursor = "pointer";
      pad.on("pointertap", () => this.onSlotClick(i));
      this.root!.addChild(pad);

      if (slot.plantId) {
        const tex = getPlantTexture(slot.plantId);
        if (tex) {
          const spr = new Sprite(tex);
          spr.roundPixels = true;
          spr.scale.set(PLANT_SCALE);
          spr.x = x + Math.floor((SLOT_W - 16 * PLANT_SCALE) / 2);
          spr.y = y + SLOT_H - 16 * PLANT_SCALE - 8;
          this.root!.addChild(spr);
        } else {
          this.drawPlantFallback(slot.plantId, x, y);
        }
      }

      if (slot.visitor) {
        const stage = slot.visitor.stage || "kitten";
        const tex = getCatTexture(slot.visitor.catId, stage);
        if (tex) {
          const spr = new Sprite(tex);
          spr.roundPixels = true;
          spr.scale.set(CAT_SCALE);
          spr.x = x + Math.floor((SLOT_W - 32 * CAT_SCALE) / 2);
          spr.y = y + SLOT_H - 32 * CAT_SCALE - 4;
          this.root!.addChild(spr);
        } else {
          this.drawCatFallback(x, y);
        }

        const label = new Text({
          text: catLabel(slot.visitor.catId).slice(0, 8),
          style: {
            fontFamily: "monospace",
            fontSize: 10,
            fill: hexNumber("cloud"),
          },
        });
        label.x = x + 8;
        label.y = y + 2;
        this.root!.addChild(label);
      } else if (!slot.plantId) {
        const label = new Text({
          text: "slot",
          style: {
            fontFamily: "monospace",
            fontSize: 10,
            fill: hexNumber("mist"),
          },
        });
        label.x = x + 20;
        label.y = y + 28;
        this.root!.addChild(label);
      }
    });

    const guideTexture = getCatTexture("cat:mizzle:v1", "kitten");
    if (guideTexture) {
      const guide = new Sprite(guideTexture);
      guide.roundPixels = true;
      guide.scale.set(CAT_SCALE);
      guide.x = VIEW_W / 2 - 32;
      guide.y = 376;
      this.root.addChild(guide);
    }
  }

  pan(delta: number): number {
    this.cameraX = Math.max(0, Math.min(WORLD_W - VIEW_W, this.cameraX + delta));
    if (this.projection) this.render(this.projection);
    return Math.round(this.cameraX / 320) + 1;
  }

  private drawPlantFallback(plantId: string, x: number, y: number): void {
    const plant = plantById(plantId);
    const g = new Graphics();
    const color =
      plant?.placementKey === "pond"
        ? hexNumber("sky")
        : plant?.placementKey === "fern"
          ? hexNumber("moss")
          : plant?.placementKey === "sunny_rock"
            ? hexNumber("bark")
            : hexNumber("rose");
    g.rect(x + 20, y + 36, 32, 20).fill(color);
    if (plant?.placementKey === "fern") {
      g.rect(x + 32, y + 18, 8, 20).fill(hexNumber("leaf"));
    }
    this.root!.addChild(g);
  }

  private drawCatFallback(x: number, y: number): void {
    const cat = new Graphics();
    cat.roundRect(x + 18, y + 22, 36, 28, 6).fill(hexNumber("mist"));
    cat.rect(x + 20, y + 14, 8, 10).fill(hexNumber("mist"));
    cat.rect(x + 44, y + 14, 8, 10).fill(hexNumber("mist"));
    cat.rect(x + 26, y + 30, 4, 4).fill(hexNumber("ink"));
    cat.rect(x + 42, y + 30, 4, 4).fill(hexNumber("ink"));
    this.root!.addChild(cat);
  }

  destroy(): void {
    this.app?.destroy(true);
    this.app = null;
    this.root = null;
  }
}
