// Focus-session state machine (pure, zero-build ESM).
// Authority is timestamps in the save store — not setInterval.
// States: idle → running → paused → completed | cancelled
//
// Elapsed focus seconds = sum of closed running segments + (now - current segment start if running).
// Completion is a pure function of targetSeconds and accumulated running time at a decision instant.

export const FocusState = Object.freeze({
  IDLE: "idle",
  RUNNING: "running",
  PAUSED: "paused",
  COMPLETED: "completed",
  CANCELLED: "cancelled",
});

/**
 * @typedef {Object} FocusSession
 * @property {string} id
 * @property {string} state
 * @property {number} targetSeconds
 * @property {number|null} startedAt        ms epoch when first started
 * @property {number|null} runningSince     ms epoch of current running segment start
 * @property {number} accumulatedMs         closed running segments only
 * @property {number|null} completedAt
 * @property {number|null} cancelledAt
 * @property {string} source                activity source id (e.g. "focus_timer")
 */

export function createFocusSession({ id, targetSeconds, source = "focus_timer", now = Date.now() }) {
  if (!id) throw new Error("id required");
  if (!Number.isInteger(targetSeconds) || targetSeconds <= 0) {
    throw new Error("targetSeconds must be a positive integer");
  }
  return {
    id,
    state: FocusState.IDLE,
    targetSeconds,
    startedAt: null,
    runningSince: null,
    accumulatedMs: 0,
    completedAt: null,
    cancelledAt: null,
    source,
    updatedAt: now,
  };
}

export function startFocus(session, now = Date.now()) {
  assertState(session, [FocusState.IDLE, FocusState.PAUSED], "start");
  const next = { ...session };
  if (next.state === FocusState.IDLE) next.startedAt = now;
  next.state = FocusState.RUNNING;
  next.runningSince = now;
  next.updatedAt = now;
  return next;
}

export function pauseFocus(session, now = Date.now()) {
  assertState(session, [FocusState.RUNNING], "pause");
  const next = { ...session };
  next.accumulatedMs += now - next.runningSince;
  next.runningSince = null;
  next.state = FocusState.PAUSED;
  next.updatedAt = now;
  return next;
}

export function cancelFocus(session, now = Date.now()) {
  assertState(session, [FocusState.RUNNING, FocusState.PAUSED, FocusState.IDLE], "cancel");
  const next = { ...session };
  if (next.state === FocusState.RUNNING && next.runningSince != null) {
    next.accumulatedMs += now - next.runningSince;
    next.runningSince = null;
  }
  next.state = FocusState.CANCELLED;
  next.cancelledAt = now;
  next.updatedAt = now;
  return next;
}

/** Elapsed focused milliseconds at instant `now` (does not mutate). */
export function elapsedMs(session, now = Date.now()) {
  let ms = session.accumulatedMs;
  if (session.state === FocusState.RUNNING && session.runningSince != null) {
    ms += now - session.runningSince;
  }
  return Math.max(0, ms);
}

export function elapsedSeconds(session, now = Date.now()) {
  return Math.floor(elapsedMs(session, now) / 1000);
}

/**
 * Attempt completion. Returns same session if target not yet reached.
 * Completing from RUNNING closes the open segment first.
 */
export function completeFocus(session, now = Date.now()) {
  assertState(session, [FocusState.RUNNING, FocusState.PAUSED], "complete");
  let next = { ...session };
  if (next.state === FocusState.RUNNING && next.runningSince != null) {
    next.accumulatedMs += now - next.runningSince;
    next.runningSince = null;
    next.state = FocusState.PAUSED; // transient before complete
  }
  const elapsed = Math.floor(next.accumulatedMs / 1000);
  if (elapsed < next.targetSeconds) {
    // Not ready — restore running if we were running
    if (session.state === FocusState.RUNNING) {
      return { ...session }; // no mutation if incomplete
    }
    return next;
  }
  next.state = FocusState.COMPLETED;
  next.completedAt = now;
  next.updatedAt = now;
  return next;
}

/** Growth energy granted on completion (neutral domain term). Integer, pure. */
export function growthEnergyFor(session) {
  if (session.state !== FocusState.COMPLETED) return 0;
  // 1 energy per full minute focused, min 1 if any completion (target reached).
  return Math.max(1, Math.floor(session.targetSeconds / 60));
}

function assertState(session, allowed, action) {
  if (!allowed.includes(session.state)) {
    throw new Error(`cannot ${action} from state=${session.state}`);
  }
}
