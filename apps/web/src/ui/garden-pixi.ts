import { Application, Container, Graphics, Text } from "pixi.js";
import type { GameProjection } from "../game/types";
import { catLabel, plantById } from "../game/content";

const SLOT_W = 72;
const SLOT_H = 72;
const GAP = 12;

/** PixiJS garden with nearest-neighbor placeholder pixel sprites. */
export class GardenPixi {
  app: Application | null = null;
  root: Container | null = null;
  private host: HTMLElement;
  private onSlotClick: (index: number) => void;

  constructor(host: HTMLElement, onSlotClick: (index: number) => void) {
    this.host = host;
    this.onSlotClick = onSlotClick;
  }

  async init(): Promise<void> {
    const app = new Application();
    await app.init({
      width: 340,
      height: 200,
      background: "#257179",
      antialias: false,
      resolution: Math.min(window.devicePixelRatio || 1, 2),
      autoDensity: true,
    });
    this.host.replaceChildren(app.canvas);
    app.canvas.style.imageRendering = "pixelated";
    app.canvas.style.width = "100%";
    app.canvas.style.maxWidth = "420px";
    app.canvas.style.borderRadius = "8px";
    this.app = app;
    this.root = new Container();
    app.stage.addChild(this.root);
  }

  render(proj: GameProjection): void {
    if (!this.app || !this.root) return;
    this.root.removeChildren();

    // ground strip
    const ground = new Graphics();
    ground.rect(0, 140, 340, 60).fill(0x38b764);
    this.root.addChild(ground);

    // sky accents by daylight
    const sky = new Graphics();
    const skyColor =
      proj.world.daylight === "night"
        ? 0x1a1c2c
        : proj.world.daylight === "dusk"
          ? 0x4a3f6b
          : proj.world.daylight === "dawn"
            ? 0xef7d57
            : 0x41a6f6;
    this.app.renderer.background.color = skyColor;
    sky.circle(300, 28, 18).fill(
      proj.world.daylight === "night" ? 0xf4f4f4 : 0xffcd75,
    );
    this.root.addChild(sky);

    if (proj.world.precipitation === "rain" || proj.world.precipitation === "drizzle") {
      const rain = new Graphics();
      for (let i = 0; i < 24; i++) {
        const x = 10 + ((i * 37) % 320);
        const y = 10 + ((i * 17) % 120);
        rain.rect(x, y, 1, 6).fill(0x73eff7);
      }
      this.root.addChild(rain);
    }

    proj.slots.forEach((slot, i) => {
      const x = 16 + i * (SLOT_W + GAP);
      const y = 90;
      const pad = new Graphics();
      pad.roundRect(x, y, SLOT_W, SLOT_H, 6).fill(0x333c57).stroke({
        width: 2,
        color: 0x94b0c2,
      });
      pad.eventMode = "static";
      pad.cursor = "pointer";
      pad.on("pointertap", () => this.onSlotClick(i));
      this.root!.addChild(pad);

      if (slot.plantId) {
        const plant = plantById(slot.plantId);
        const g = new Graphics();
        const color =
          plant?.placementKey === "pond"
            ? 0x3b5dc9
            : plant?.placementKey === "fern"
              ? 0x38b764
              : plant?.placementKey === "sunny_rock"
                ? 0x8b5e34
                : 0xea90b4;
        g.rect(x + 20, y + 36, 32, 20).fill(color);
        if (plant?.placementKey === "fern") {
          g.rect(x + 32, y + 18, 8, 20).fill(0xa7f070);
        }
        this.root!.addChild(g);
      }

      if (slot.visitor) {
        const cat = new Graphics();
        // body
        cat.roundRect(x + 18, y + 22, 36, 28, 6).fill(0x94b0c2);
        // ears
        cat.rect(x + 20, y + 14, 8, 10).fill(0x94b0c2);
        cat.rect(x + 44, y + 14, 8, 10).fill(0x94b0c2);
        // eyes
        cat.rect(x + 26, y + 30, 4, 4).fill(0x1a1c2c);
        cat.rect(x + 42, y + 30, 4, 4).fill(0x1a1c2c);
        this.root!.addChild(cat);

        const label = new Text({
          text: catLabel(slot.visitor.catId).slice(0, 8),
          style: {
            fontFamily: "monospace",
            fontSize: 10,
            fill: 0xf4f4f4,
          },
        });
        label.x = x + 8;
        label.y = y + 2;
        this.root!.addChild(label);
      } else {
        const label = new Text({
          text: slot.plantId ? "empty" : "slot",
          style: {
            fontFamily: "monospace",
            fontSize: 10,
            fill: 0x94b0c2,
          },
        });
        label.x = x + 16;
        label.y = y + 8;
        this.root!.addChild(label);
      }
    });
  }

  destroy(): void {
    this.app?.destroy(true);
    this.app = null;
    this.root = null;
  }
}
