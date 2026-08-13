import { cats, catLabel, plantById } from "../game/content";
import { PLANTS, type WorldState } from "../game/types";
import {
  claimLocalAsCloud,
  connectGuestCloud,
  disconnectCloud,
  flushOutbox,
  getCloudInfo,
  joinCloudSession,
  pullBootstrap,
  reconcileCloud,
  type CloudInfo,
} from "../cloud/outbox";
import {
  dispatch,
  exportSaveJson,
  getStore,
  importSaveJson,
  loadOrCreateStore,
  reloadFromDb,
  subscribe,
  tryAutoCompleteFocus,
} from "../save/store";
import { elapsedSeconds } from "@domain/focus-session.mjs";
import { GardenPixi } from "./garden-pixi";
import { onBroadcast } from "../lib/locks";
import { $, $maybe, shellReady } from "./dom";

let selectedPlantId: string = PLANTS[0].id;
let selectedSlot: number | null = null;
let garden: GardenPixi | null = null;
let tickTimer: number | null = null;
let autoCompleteInFlight = false;
let cloudInfo: CloudInfo | null = null;

function formatTime(totalSeconds: number): string {
  const s = Math.max(0, Math.floor(totalSeconds));
  const m = Math.floor(s / 60);
  const r = s % 60;
  return `${String(m).padStart(2, "0")}:${String(r).padStart(2, "0")}`;
}

function focusRemaining(): number {
  const { focus } = getStore();
  if (!focus) return 0;
  if (focus.state === "completed" || focus.state === "cancelled" || focus.state === "idle") {
    return focus.targetSeconds;
  }
  const elapsed = elapsedSeconds(
    {
      ...focus,
    },
    Date.now(),
  );
  return Math.max(0, focus.targetSeconds - elapsed);
}

async function run(type: Parameters<typeof dispatch>[0], payload?: Record<string, unknown>) {
  try {
    clearError();
    await dispatch(type, payload ?? {});
  } catch (e) {
    showError(e instanceof Error ? e.message : String(e));
  }
}

function showError(msg: string) {
  const el = document.getElementById("error-banner");
  if (!el) return;
  el.hidden = false;
  el.textContent = msg;
}

function clearError() {
  const el = document.getElementById("error-banner");
  if (!el) return;
  el.hidden = true;
  el.textContent = "";
}

function render(): void {
  // Subscribe may fire before mountShell finishes wiring — never hard-crash the app.
  if (!shellReady()) return;

  try {
    renderShell();
  } catch (e) {
    console.error("render failed", e);
    showError(e instanceof Error ? e.message : String(e));
  }
}

function renderShell(): void {
  const store = getStore();
  const { projection: p, focus, lastEvents } = store;
  const saveMeta = $maybe("header .save-meta");
  if (saveMeta) {
    saveMeta.textContent = `Energy ${p.growthEnergy} · Food ${p.food} · Visits ${p.pendingSpawnWindows}`;
  }

  // Cloud panel
  const cloudStatus = $maybe("cloud-status");
  if (cloudStatus && cloudInfo) {
    const api =
      cloudInfo.apiReachable === true
        ? "API up"
        : cloudInfo.apiReachable === false
          ? "API down"
          : "API ?";
    cloudStatus.textContent = cloudInfo.sessionId
      ? `${cloudInfo.status} · ${api} · player ${cloudInfo.playerId?.slice(0, 8) ?? "?"}… · pending ${cloudInfo.pendingCount}` +
        (cloudInfo.deviceCount ? ` · devices ${cloudInfo.deviceCount}` : "") +
        (cloudInfo.lastError ? ` · err: ${cloudInfo.lastError}` : "")
      : `offline · ${api} — start API then connect / claim / join`;
  }
  const shareEl = $maybe("cloud-share-id") as HTMLInputElement | null;
  if (shareEl && cloudInfo?.shareSessionId && cloudInfo.sessionId) {
    shareEl.value = cloudInfo.shareSessionId;
  }
  const connected = !!cloudInfo?.sessionId;
  const setDis = (id: string, dis: boolean) => {
    const b = $maybe(id) as HTMLButtonElement | null;
    if (b) b.disabled = dis;
  };
  setDis("btn-cloud-connect", connected);
  setDis("btn-cloud-claim", connected);
  setDis("btn-cloud-join", connected);
  setDis("btn-cloud-sync", !connected);
  setDis("btn-cloud-reconcile", !connected);
  setDis("btn-cloud-pull", !connected);
  setDis("btn-cloud-disconnect", !connected);
  setDis("btn-cloud-copy-share", !connected);

  // Timer — must use #id (or bare id via normalizeSelector)
  const display = $("timer-display");
  const focusMinutes = $maybe("focus-minutes") as HTMLSelectElement | null;
  const remaining = focus
    ? focusRemaining()
    : Number(focusMinutes?.value ?? 25) * 60;
  if (focus?.state === "running") {
    display.className = "timer-display running";
    display.textContent = formatTime(focusRemaining());
  } else if (focus?.state === "paused") {
    display.className = "timer-display paused";
    display.textContent = formatTime(focusRemaining());
  } else if (focus?.state === "completed") {
    display.className = "timer-display";
    display.textContent = "00:00";
  } else {
    display.className = "timer-display";
    display.textContent = formatTime(remaining);
  }

  const running = focus?.state === "running";
  const paused = focus?.state === "paused";
  ($("#btn-start") as HTMLButtonElement).disabled = running || paused;
  ($("#btn-pause") as HTMLButtonElement).disabled = !running;
  ($("#btn-resume") as HTMLButtonElement).disabled = !paused;
  ($("#btn-complete") as HTMLButtonElement).disabled = !(running || paused);
  ($("#btn-cancel") as HTMLButtonElement).disabled = !(running || paused);
  ($("#btn-spawn") as HTMLButtonElement).disabled =
    p.pendingSpawnWindows < 1 && !(document.getElementById("force-spawn") as HTMLInputElement)?.checked;

  // World selects
  (["precipitation", "daylight", "season", "moon"] as const).forEach((k) => {
    const sel = document.getElementById(`world-${k}`) as HTMLSelectElement | null;
    if (sel) sel.value = p.world[k];
  });

  // Slots list
  const list = $("#slots-list");
  list.innerHTML = "";
  for (const slot of p.slots) {
    const li = document.createElement("li");
    const plant = slot.plantId ? plantById(slot.plantId) : null;
    const left = document.createElement("div");
    left.innerHTML = `<strong>Slot ${slot.index + 1}</strong>
      <div class="muted">${plant ? plant.label : "bare soil"}${
        slot.visitor
          ? ` · <span style="color:var(--good)">${catLabel(slot.visitor.catId)}</span> (${slot.visitor.stage}, bond ${slot.visitor.bond})`
          : ""
      }</div>`;
    const actions = document.createElement("div");
    actions.className = "row";
    if (!slot.plantId && !slot.visitor) {
      const plantBtn = document.createElement("button");
      plantBtn.textContent = "Plant here";
      plantBtn.onclick = () => run("garden.plant_place", { slotIndex: slot.index, plantId: selectedPlantId });
      actions.append(plantBtn);
    }
    if (slot.plantId && !slot.visitor) {
      const rem = document.createElement("button");
      rem.textContent = "Remove plant";
      rem.onclick = () => run("garden.plant_remove", { slotIndex: slot.index });
      actions.append(rem);
    }
    if (slot.visitor) {
      const feed = document.createElement("button");
      feed.textContent = "Feed";
      feed.className = "primary";
      feed.onclick = () => run("garden.feed_visitor", { slotIndex: slot.index });
      const collect = document.createElement("button");
      collect.textContent = "Collect";
      collect.onclick = () => run("garden.collect_visitor", { slotIndex: slot.index });
      actions.append(feed, collect);
      if (slot.visitor.explanation.length) {
        left.innerHTML += `<div class="muted">why: ${slot.visitor.explanation.join(", ")}</div>`;
      }
    }
    li.append(left, actions);
    list.append(li);
  }

  // Plant picker
  document.querySelectorAll(".plant-picker button").forEach((btn) => {
    const id = (btn as HTMLElement).dataset.plant!;
    btn.classList.toggle("active", id === selectedPlantId);
  });

  // Dex
  const dex = $("#dex-grid");
  dex.innerHTML = "";
  for (const cat of cats) {
    const entry = p.collection[cat.id];
    const card = document.createElement("div");
    card.className = "dex-card";
    card.innerHTML = entry
      ? `<strong>${catLabel(cat.id)}</strong><div class="muted">${entry.stage} · bond ${entry.bond} · ×${entry.visitCount}</div>`
      : `<strong class="muted">???</strong><div class="muted">${cat.rarity}</div>`;
    dex.append(card);
  }

  // Log
  const log = $("#event-log");
  log.innerHTML = "";
  for (const e of lastEvents) {
    const li = document.createElement("li");
    li.textContent = e;
    log.append(li);
  }

  garden?.render(p);

  // Keep ticking while focus running/paused (pause still needs wall-clock for resume UI)
  const needsTick = focus?.state === "running" || focus?.state === "paused";
  if (needsTick && tickTimer == null) {
    tickTimer = window.setInterval(() => {
      void tickFocus();
    }, 250);
  }
  if (!needsTick && tickTimer != null) {
    clearInterval(tickTimer);
    tickTimer = null;
  }
}

async function tickFocus(): Promise<void> {
  const { focus } = getStore();
  if (focus?.state === "running" && !autoCompleteInFlight) {
    const remaining = focusRemaining();
    if (remaining <= 0) {
      autoCompleteInFlight = true;
      try {
        await tryAutoCompleteFocus();
      } finally {
        autoCompleteInFlight = false;
      }
    }
  }
  render();
}

function mountShell(root: HTMLElement): void {
  root.innerHTML = `
    <header class="app-header">
      <div>
        <h1>Purrden</h1>
        <div class="tag">Phase 1 · offline vertical slice</div>
      </div>
      <div class="save-meta muted"></div>
    </header>
    <div id="error-banner" class="error-banner" hidden></div>
    <div class="grid">
      <section class="panel">
        <h2>Garden</h2>
        <div id="garden-host" aria-label="Garden scene"></div>
        <ul class="slots-list" id="slots-list"></ul>
        <div class="muted" style="margin-top:0.75rem">Selected plant:</div>
        <div class="plant-picker" id="plant-picker"></div>
      </section>
      <div style="display:grid;gap:1rem">
        <section class="panel">
          <h2>Focus</h2>
          <div class="timer-display" id="timer-display">25:00</div>
          <div class="row">
            <label class="muted">Duration
              <select id="focus-minutes">
                <option value="0.05">3s (dev)</option>
                <option value="1">1 min</option>
                <option value="5">5 min</option>
                <option value="25" selected>25 min</option>
              </select>
            </label>
          </div>
          <div class="row" style="margin-top:0.75rem">
            <button class="primary" id="btn-start">Start</button>
            <button id="btn-pause">Pause</button>
            <button id="btn-resume">Resume</button>
            <button id="btn-complete">Complete</button>
            <button class="danger" id="btn-cancel">Cancel</button>
          </div>
          <p class="muted" style="margin-top:0.75rem">
            Timer uses persisted timestamps — closing the tab is safe. Completing awards growth energy and a spawn window.
            Auto-completes when time hits zero; multi-tab locks prevent double rewards.
          </p>
        </section>
        <section class="panel">
          <h2>World (fake)</h2>
          <div class="row">
            <label>Rain
              <select id="world-precipitation">
                <option value="none">none</option>
                <option value="drizzle">drizzle</option>
                <option value="rain">rain</option>
                <option value="storm">storm</option>
              </select>
            </label>
            <label>Light
              <select id="world-daylight">
                <option value="dawn">dawn</option>
                <option value="day">day</option>
                <option value="dusk">dusk</option>
                <option value="night">night</option>
              </select>
            </label>
            <label>Season
              <select id="world-season">
                <option value="spring">spring</option>
                <option value="summer">summer</option>
                <option value="autumn">autumn</option>
                <option value="winter">winter</option>
              </select>
            </label>
            <label>Moon
              <select id="world-moon">
                <option value="new">new</option>
                <option value="first_quarter">first quarter</option>
                <option value="full">full</option>
                <option value="last_quarter">last quarter</option>
              </select>
            </label>
          </div>
          <div class="row" style="margin-top:0.75rem">
            <button id="btn-apply-world">Apply world</button>
            <button class="primary" id="btn-spawn">Advance spawn</button>
            <label class="muted"><input type="checkbox" id="force-spawn" /> force</label>
          </div>
        </section>
        <section class="panel">
          <h2>Cat dex</h2>
          <div class="dex-grid" id="dex-grid"></div>
        </section>
        <section class="panel">
          <h2>Cloud save</h2>
          <p class="muted" id="cloud-status">Checking…</p>
          <div class="row" style="margin-top:0.5rem">
            <button class="primary" id="btn-cloud-claim">Claim local garden</button>
            <button id="btn-cloud-connect">Empty guest</button>
            <button id="btn-cloud-join">Join session…</button>
          </div>
          <div class="row" style="margin-top:0.5rem">
            <button id="btn-cloud-sync">Sync now</button>
            <button id="btn-cloud-reconcile">Reconcile</button>
            <button id="btn-cloud-pull">Pull bootstrap</button>
            <button class="danger" id="btn-cloud-disconnect">Disconnect</button>
          </div>
          <div class="row" style="margin-top:0.5rem">
            <label class="muted" style="flex:1">Share session
              <input id="cloud-share-id" readonly style="width:100%;margin-top:0.25rem;font-family:var(--mono);font-size:0.75rem;padding:0.35rem;border-radius:6px;border:1px solid #566c86;background:#111320;color:#f4f4f4" />
            </label>
            <button id="btn-cloud-copy-share" style="align-self:end">Copy</button>
          </div>
          <p class="muted" style="margin-top:0.5rem">
            API on :8000 (Vite proxies <code>/api</code>). Claim uploads this garden as genesis; join pastes another browser’s share id for multi-device.
          </p>
        </section>
        <section class="panel">
          <h2>Save</h2>
          <div class="row">
            <button id="btn-export">Export JSON</button>
            <label class="file-btn">Import JSON
              <input type="file" id="import-file" accept="application/json,.json" class="sr-only" />
            </label>
          </div>
          <p class="muted" style="margin-top:0.5rem">Autosaves every action into IndexedDB. Manual export is the durable backup.</p>
          <h2 style="margin-top:1rem">Events</h2>
          <ul class="log" id="event-log"></ul>
        </section>
      </div>
    </div>
  `;

  const menuLabels = ["Focus", "World", "Cat dex", "Cloud save", "Save"];
  const side = root.querySelector(".grid > div:last-child");
  const gardenPanel = root.querySelector(".grid > .panel");
  if (side && gardenPanel) {
    gardenPanel.classList.add("game-stage");
    const nav = document.createElement("nav");
    nav.className = "game-menu";
    nav.setAttribute("aria-label", "Game menus");
    [...side.querySelectorAll<HTMLElement>(":scope > .panel")].forEach((panel, index) => {
      const id = `menu-panel-${index}`;
      panel.id = id;
      panel.classList.add("menu-panel");
      panel.setAttribute("role", "dialog");
      panel.setAttribute("aria-modal", "false");
      panel.setAttribute("aria-label", menuLabels[index] ?? `Menu ${index + 1}`);
      panel.hidden = true;
      const close = document.createElement("button");
      close.type = "button";
      close.className = "menu-close";
      close.setAttribute("aria-label", "Close menu");
      close.textContent = "Close";
      close.onclick = () => { panel.hidden = true; button.setAttribute("aria-expanded", "false"); button.focus(); };
      panel.prepend(close);
      const button = document.createElement("button");
      button.type = "button";
      button.textContent = menuLabels[index] ?? `Menu ${index + 1}`;
      button.setAttribute("aria-controls", id);
      button.setAttribute("aria-expanded", "false");
      button.onclick = () => {
        const opening = panel.hidden;
        side.querySelectorAll<HTMLElement>(".menu-panel").forEach((item) => (item.hidden = true));
        nav.querySelectorAll("button").forEach((item) => item.setAttribute("aria-expanded", "false"));
        panel.hidden = !opening;
        button.setAttribute("aria-expanded", String(opening));
        if (opening) panel.querySelector<HTMLElement>("button, select, input")?.focus();
      };
      nav.append(button);
    });
    gardenPanel.prepend(nav);
    root.addEventListener("keydown", (event) => {
      if (event.key !== "Escape") return;
      side.querySelectorAll<HTMLElement>(".menu-panel").forEach((item) => (item.hidden = true));
      nav.querySelectorAll("button").forEach((item) => item.setAttribute("aria-expanded", "false"));
    });
  }

  const picker = $("#plant-picker");
  for (const plant of PLANTS) {
    const b = document.createElement("button");
    b.type = "button";
    b.dataset.plant = plant.id;
    b.textContent = plant.label;
    b.onclick = () => {
      selectedPlantId = plant.id;
      render();
    };
    picker.append(b);
  }

  $("#btn-start").onclick = () => {
    const minutes = Number(($("#focus-minutes") as HTMLSelectElement).value);
    const payload =
      minutes < 1
        ? { seconds: Math.max(1, Math.round(minutes * 60)) }
        : { minutes };
    void run("focus.start", payload);
  };
  $("#btn-pause").onclick = () => void run("focus.pause");
  $("#btn-resume").onclick = () => void run("focus.resume");
  $("#btn-complete").onclick = () => void run("focus.complete");
  $("#btn-cancel").onclick = () => void run("focus.cancel");
  $("#btn-apply-world").onclick = () => {
    const world: Partial<WorldState> = {
      precipitation: ($("#world-precipitation") as HTMLSelectElement).value as WorldState["precipitation"],
      daylight: ($("#world-daylight") as HTMLSelectElement).value as WorldState["daylight"],
      season: ($("#world-season") as HTMLSelectElement).value as WorldState["season"],
      moon: ($("#world-moon") as HTMLSelectElement).value as WorldState["moon"],
    };
    void run("world.set", { world });
  };
  $("#btn-spawn").onclick = () => {
    const force = ($("#force-spawn") as HTMLInputElement).checked;
    void run("world.advance_spawn", { force });
  };
  $("#btn-export").onclick = async () => {
    const json = await exportSaveJson();
    const blob = new Blob([json], { type: "application/json" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = `purrden-save-${getStore().projection.saveVersion}.json`;
    a.click();
    URL.revokeObjectURL(a.href);
  };
  $("#import-file").addEventListener("change", async (ev) => {
    const file = (ev.target as HTMLInputElement).files?.[0];
    if (!file) return;
    try {
      await importSaveJson(await file.text());
    } catch (e) {
      showError(e instanceof Error ? e.message : String(e));
    }
  });

  $("#btn-cloud-connect").onclick = () => void cloudAction("connect");
  $("#btn-cloud-claim").onclick = () => void cloudAction("claim");
  $("#btn-cloud-join").onclick = () => void cloudAction("join");
  $("#btn-cloud-sync").onclick = () => void cloudAction("sync");
  $("#btn-cloud-reconcile").onclick = () => void cloudAction("reconcile");
  $("#btn-cloud-pull").onclick = () => void cloudAction("pull");
  $("#btn-cloud-disconnect").onclick = () => void cloudAction("disconnect");
  $("#btn-cloud-copy-share").onclick = async () => {
    const id = cloudInfo?.shareSessionId;
    if (!id) return;
    try {
      await navigator.clipboard.writeText(id);
      getStore().lastEvents = ["Share session copied", ...getStore().lastEvents].slice(0, 12);
      render();
    } catch {
      prompt("Copy this session id for the other browser:", id);
    }
  };
}

async function refreshCloud(ping = false): Promise<void> {
  try {
    cloudInfo = await getCloudInfo({ ping });
  } catch {
    cloudInfo = {
      status: "error",
      sessionId: null,
      shareSessionId: null,
      playerId: null,
      lastSuccessAt: null,
      lastError: "cloud info failed",
      pendingCount: 0,
      lastAcceptedVersion: 0,
      apiReachable: false,
      deviceCount: 0,
    };
  }
}

function pushEvent(msg: string): void {
  const store = getStore();
  store.lastEvents = [msg, ...store.lastEvents].slice(0, 12);
}

async function cloudAction(
  kind: "connect" | "claim" | "join" | "sync" | "reconcile" | "pull" | "disconnect",
): Promise<void> {
  try {
    clearError();
    if (kind === "connect") {
      cloudInfo = await connectGuestCloud();
      pushEvent("Cloud empty guest connected · outbox flushed");
      await reloadFromDb();
    } else if (kind === "claim") {
      cloudInfo = await claimLocalAsCloud();
      pushEvent("Local garden claimed as cloud genesis");
      await reloadFromDb();
    } else if (kind === "join") {
      const id = prompt("Paste share session id from the other browser:");
      if (!id?.trim()) return;
      cloudInfo = await joinCloudSession(id.trim());
      pushEvent(`Joined cloud session · pulled bootstrap`);
      await reloadFromDb();
    } else if (kind === "sync") {
      const r = await flushOutbox();
      pushEvent(`Cloud sync · sent ${r.sent} acked ${r.acked} rej ${r.rejected} dup ${r.dups}`);
      cloudInfo = await getCloudInfo();
    } else if (kind === "reconcile") {
      const msg = await reconcileCloud();
      pushEvent(msg);
      await reloadFromDb();
      cloudInfo = await getCloudInfo({ ping: true });
    } else if (kind === "pull") {
      if (!confirm("Replace local projection with cloud bootstrap? Unsynced local-only changes may be lost.")) {
        return;
      }
      await pullBootstrap();
      await reloadFromDb();
      pushEvent("Pulled cloud bootstrap");
      cloudInfo = await getCloudInfo();
    } else {
      await disconnectCloud();
      cloudInfo = await getCloudInfo();
      pushEvent("Cloud disconnected");
    }
  } catch (e) {
    showError(e instanceof Error ? e.message : String(e));
    await refreshCloud();
  }
  render();
}

export async function startApp(root: HTMLElement): Promise<void> {
  mountShell(root);
  await loadOrCreateStore();
  await refreshCloud();

  garden = new GardenPixi($("#garden-host"), (index) => {
    selectedSlot = index;
    const slot = getStore().projection.slots[index];
    if (!slot.plantId && !slot.visitor) {
      void run("garden.plant_place", { slotIndex: index, plantId: selectedPlantId });
    }
  });
  await garden.init();

  subscribe(() => {
    void refreshCloud(false).finally(() => render());
  });
  onBroadcast(async (msg) => {
    if (
      msg.type === "SAVE_UPDATED" ||
      msg.type === "FOCUS_UPDATED" ||
      msg.type === "WORLD_UPDATED" ||
      msg.type === "SYNC_COMPLETE"
    ) {
      await reloadFromDb();
      await refreshCloud(false);
      render();
    }
  });

  // One API reachability ping at startup (not every render).
  void refreshCloud(true).then(() => render());
  render();
  void selectedSlot;
}
