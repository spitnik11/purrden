import { cats, catLabel, plantById } from "../game/content";
import { PLANTS, type WorldState } from "../game/types";
import {
  connectGuestCloud,
  disconnectCloud,
  flushOutbox,
  getCloudInfo,
  pullBootstrap,
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

let selectedPlantId: string = PLANTS[0].id;
let selectedSlot: number | null = null;
let garden: GardenPixi | null = null;
let tickTimer: number | null = null;
let autoCompleteInFlight = false;
let cloudInfo: CloudInfo | null = null;

function $(sel: string, root: ParentNode = document): HTMLElement {
  const el = root.querySelector(sel);
  if (!el) throw new Error(`Missing ${sel}`);
  return el as HTMLElement;
}

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
  const store = getStore();
  const { projection: p, focus, lastEvents, persistentStorage } = store;

  const cloudBit = cloudInfo
    ? cloudInfo.sessionId
      ? ` · cloud ${cloudInfo.status}${cloudInfo.pendingCount ? ` (${cloudInfo.pendingCount} pending)` : ""}`
      : " · cloud off"
    : "";
  $("header .save-meta").textContent =
    `v${p.saveVersion} · energy ${p.growthEnergy} · food ${p.food} · streak ${p.streakDays}d · spawns ${p.pendingSpawnWindows}` +
    (persistentStorage === true
      ? " · persistent storage"
      : persistentStorage === false
        ? " · storage not persisted"
        : "") +
    cloudBit;

  // Cloud panel
  const cloudStatus = document.getElementById("cloud-status");
  if (cloudStatus && cloudInfo) {
    const api =
      cloudInfo.apiReachable === true
        ? "API up"
        : cloudInfo.apiReachable === false
          ? "API down"
          : "API ?";
    cloudStatus.textContent = cloudInfo.sessionId
      ? `${cloudInfo.status} · ${api} · player ${cloudInfo.playerId?.slice(0, 8) ?? "?"}… · pending ${cloudInfo.pendingCount}` +
        (cloudInfo.lastError ? ` · err: ${cloudInfo.lastError}` : "")
      : `offline · ${api} — start Purrden-API-Dev.bat then Connect guest`;
  }
  const btnConnect = document.getElementById("btn-cloud-connect") as HTMLButtonElement | null;
  const btnSync = document.getElementById("btn-cloud-sync") as HTMLButtonElement | null;
  const btnPull = document.getElementById("btn-cloud-pull") as HTMLButtonElement | null;
  const btnDisc = document.getElementById("btn-cloud-disconnect") as HTMLButtonElement | null;
  if (btnConnect) btnConnect.disabled = !!cloudInfo?.sessionId;
  if (btnSync) btnSync.disabled = !cloudInfo?.sessionId;
  if (btnPull) btnPull.disabled = !cloudInfo?.sessionId;
  if (btnDisc) btnDisc.disabled = !cloudInfo?.sessionId;

  // Timer
  const display = $("timer-display");
  const remaining = focus ? focusRemaining() : Number(($("#focus-minutes") as HTMLSelectElement).value) * 60;
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
            <button class="primary" id="btn-cloud-connect">Connect guest</button>
            <button id="btn-cloud-sync">Sync now</button>
            <button id="btn-cloud-pull">Pull bootstrap</button>
            <button class="danger" id="btn-cloud-disconnect">Disconnect</button>
          </div>
          <p class="muted" style="margin-top:0.5rem">
            Requires local API (Desktop: <code>Purrden-API-Dev.bat</code>). Connect creates a guest cloud account and flushes the outbox.
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
  $("#btn-cloud-sync").onclick = () => void cloudAction("sync");
  $("#btn-cloud-pull").onclick = () => void cloudAction("pull");
  $("#btn-cloud-disconnect").onclick = () => void cloudAction("disconnect");
}

async function refreshCloud(ping = false): Promise<void> {
  try {
    cloudInfo = await getCloudInfo({ ping });
  } catch {
    cloudInfo = {
      status: "error",
      sessionId: null,
      playerId: null,
      lastSuccessAt: null,
      lastError: "cloud info failed",
      pendingCount: 0,
      lastAcceptedVersion: 0,
      apiReachable: false,
    };
  }
}

async function cloudAction(kind: "connect" | "sync" | "pull" | "disconnect"): Promise<void> {
  try {
    clearError();
    if (kind === "connect") {
      cloudInfo = await connectGuestCloud();
      const store = getStore();
      store.lastEvents = [
        `Cloud guest connected · flushed outbox`,
        ...store.lastEvents,
      ].slice(0, 12);
    } else if (kind === "sync") {
      const r = await flushOutbox();
      const store = getStore();
      store.lastEvents = [
        `Cloud sync · sent ${r.sent} acked ${r.acked} rej ${r.rejected} dup ${r.dups}`,
        ...store.lastEvents,
      ].slice(0, 12);
      cloudInfo = await getCloudInfo();
    } else if (kind === "pull") {
      if (!confirm("Replace local projection with cloud bootstrap? Unsynced local-only changes may be lost.")) {
        return;
      }
      await pullBootstrap();
      await reloadFromDb();
      const store = getStore();
      store.lastEvents = ["Pulled cloud bootstrap", ...store.lastEvents].slice(0, 12);
      cloudInfo = await getCloudInfo();
    } else {
      await disconnectCloud();
      cloudInfo = await getCloudInfo();
      getStore().lastEvents = ["Cloud disconnected", ...getStore().lastEvents].slice(0, 12);
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

