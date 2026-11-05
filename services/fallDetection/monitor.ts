import * as Crypto from "expo-crypto";
import { Accelerometer } from "expo-sensors";
import { AppState, Platform, Vibration } from "react-native";
import contract from "./modelContract.json";
import { DetectorStats, FallDetector } from "./detector";
import { saveFallEvent } from "./fallEvents";
import { FallModel, loadFallModel } from "./model";

// Real monitoring state, derived from the samples that actually arrive, never from assumptions:
// if the operating system stops delivering accelerometer data the state says so.
export type MonitorState = "off" | "starting" | "monitoring" | "interrupted" | "degraded_rate" | "unavailable";

export interface MonitorContext { trailId: number | null; startedAt: number | null }

export interface MonitorSnapshot {
  state: MonitorState;
  reason: string | null;
  appState: string;
  sensorAvailable: boolean | null;
  measuredRateHz: number | null;
  lastSampleAt: number | null;
  startedAt: number | null;
  /** Milliseconds during which samples were flowing / not flowing since monitoring started. */
  monitoredMs: number;
  interruptedMs: number;
  model: { id: string; version: string; status: "experimental" } | null;
  counters: DetectorStats | null;
  pendingEventId: string | null;
}

export interface FallAlarm { eventId: string; context: MonitorContext; probability: number; detectedAt: number }

const STALL_MS = 2000;
const MIN_RATE_HZ = 40;
const RATE_WINDOW_MS = 5000;
const WATCHDOG_MS = 1000;
const VIBRATION_PATTERN = [0, 500, 300, 500, 300, 500];

const initial = (): MonitorSnapshot => ({
  state: "off", reason: null, appState: AppState.currentState ?? "unknown", sensorAvailable: null, measuredRateHz: null,
  lastSampleAt: null, startedAt: null, monitoredMs: 0, interruptedMs: 0, model: null, counters: null, pendingEventId: null,
});

type Listener = (snapshot: MonitorSnapshot) => void;
type AlarmListener = (alarm: FallAlarm) => void;

export class FallMonitor {
  private snapshot: MonitorSnapshot = initial();
  private listeners = new Set<Listener>();
  private alarmListeners = new Set<AlarmListener>();
  private subscription: { remove(): void } | null = null;
  private appSubscription: { remove(): void } | null = null;
  private watchdog: ReturnType<typeof setInterval> | null = null;
  private detector: FallDetector | null = null;
  private model: FallModel | null = null;
  private context: MonitorContext = { trailId: null, startedAt: null };
  private generation = 0;
  private recent: number[] = [];       // receive times (ms) of the last few seconds
  private lastTick = 0;
  private lastSampleReceived: number | null = null;   // kept off the snapshot: 50 Hz must not re-render the UI

  getSnapshot = () => this.snapshot;

  subscribe = (listener: Listener) => { this.listeners.add(listener); return () => { this.listeners.delete(listener); }; };
  onAlarm = (listener: AlarmListener) => { this.alarmListeners.add(listener); return () => { this.alarmListeners.delete(listener); }; };

  private update(patch: Partial<MonitorSnapshot>) {
    this.snapshot = { ...this.snapshot, ...patch };
    this.listeners.forEach((listener) => listener(this.snapshot));
  }

  /** The assistance screen was answered: new alarms may be raised again (after the cooldown). */
  clearPending(eventId?: string) {
    if (!eventId || this.snapshot.pendingEventId === eventId) this.update({ pendingEventId: null });
  }

  async start(context: MonitorContext, options: { requestPermission?: boolean; now?: () => number } = {}): Promise<MonitorSnapshot> {
    if (this.subscription && this.context.trailId === context.trailId && this.context.startedAt === context.startedAt) return this.snapshot;
    this.stop();
    const generation = ++this.generation;
    const now = options.now ?? Date.now;
    this.context = context;
    this.update({ ...initial(), state: "starting", startedAt: now() });
    try {
      this.model = loadFallModel();
    } catch (error) {
      return this.fail(generation, `No se pudo cargar el modelo local: ${error instanceof Error ? error.message : "error desconocido"}`);
    }
    this.update({ model: { id: this.model.id, version: this.model.version, status: "experimental" } });
    let available = false;
    try { available = await Accelerometer.isAvailableAsync(); } catch { available = false; }
    if (generation !== this.generation) return this.snapshot;
    this.update({ sensorAvailable: available });
    if (!available) return this.fail(generation, "Este teléfono no informa un acelerómetro disponible.");
    try {
      let permission = await Accelerometer.getPermissionsAsync();
      if (permission.status !== "granted" && options.requestPermission && permission.canAskAgain) permission = await Accelerometer.requestPermissionsAsync();
      if (generation !== this.generation) return this.snapshot;
      if (permission.status !== "granted") return this.fail(generation, "Falta el permiso de movimiento. Activalo en los ajustes del teléfono.");
    } catch { /* Platforms without a permission API grant access implicitly. */ }
    if (generation !== this.generation) return this.snapshot;

    this.detector = new FallDetector({ classify: this.model.classify, threshold: this.model.threshold });
    this.recent = [];
    this.lastSampleReceived = null;
    this.lastTick = now();
    Accelerometer.setUpdateInterval(1000 / contract.sampleRateHz);
    this.subscription = Accelerometer.addListener((sample) => this.onSample(sample, now));
    this.appSubscription = AppState.addEventListener("change", (appState) => this.update({ appState }));
    this.watchdog = setInterval(() => this.check(now()), WATCHDOG_MS);
    this.update({ reason: "Esperando datos del acelerómetro." });
    return this.snapshot;
  }

  private fail(generation: number, reason: string) {
    if (generation === this.generation) {
      this.releaseResources();
      this.update({ state: "unavailable", reason });
    }
    return this.snapshot;
  }

  private onSample(sample: { x: number; y: number; z: number; timestamp: number }, now: () => number) {
    const detector = this.detector;
    if (!detector) return;
    const received = now();
    this.recent.push(received);
    const timestampMs = Number.isFinite(sample.timestamp) ? sample.timestamp * 1000 : received;
    this.lastSampleReceived = received;
    for (const event of detector.push(timestampMs, sample.x, sample.y, sample.z)) {
      if (event.type === "alarm") this.raise(event.probability, event.peakG);
    }
  }

  private raise(probability: number, peakG: number) {
    if (this.snapshot.pendingEventId) return;     // one assistance request at a time
    const eventId = Crypto.randomUUID();
    const alarm: FallAlarm = { eventId, context: this.context, probability, detectedAt: Date.now() };
    this.update({ pendingEventId: eventId });
    void saveFallEvent({
      id: eventId, detectedAt: alarm.detectedAt, trailId: this.context.trailId, startedAt: this.context.startedAt,
      modelId: this.model?.id ?? "unknown", modelVersion: this.model?.version ?? "unknown", score: probability,
      peakG,
    }).catch(() => undefined);
    try { Vibration.vibrate(VIBRATION_PATTERN); } catch { /* Vibration is a convenience, never a requirement. */ }
    this.alarmListeners.forEach((listener) => listener(alarm));
  }

  private check(now: number) {
    if (!this.subscription) return;
    const elapsed = now - this.lastTick;
    this.lastTick = now;
    const last = this.lastSampleReceived;
    const counters = this.detector ? { ...this.detector.stats } : null;
    this.recent = this.recent.filter((t) => now - t <= RATE_WINDOW_MS);
    const span = this.recent.length > 1 ? this.recent[this.recent.length - 1] - this.recent[0] : 0;
    const rate = span >= 2000 ? ((this.recent.length - 1) / span) * 1000 : null;
    const stalled = last === null ? now - (this.snapshot.startedAt ?? now) > STALL_MS : now - last > STALL_MS;
    if (stalled) {
      const background = this.snapshot.appState !== "active";
      this.update({
        state: "interrupted", measuredRateHz: null, lastSampleAt: last, counters, interruptedMs: this.snapshot.interruptedMs + elapsed,
        reason: background
          ? "La app está en segundo plano y el sistema dejó de entregar datos del acelerómetro: sin protección."
          : "El acelerómetro dejó de enviar datos: sin protección hasta que se reanude.",
      });
      return;
    }
    if (last === null) return;
    if (rate !== null && rate < MIN_RATE_HZ) {
      this.update({ state: "degraded_rate", measuredRateHz: rate, lastSampleAt: last, counters, monitoredMs: this.snapshot.monitoredMs + elapsed,
        reason: `El teléfono entrega ${rate.toFixed(0)} Hz, menos de los ${MIN_RATE_HZ} Hz necesarios: se descartan ventanas dudosas.` });
      return;
    }
    this.update({ state: "monitoring", measuredRateHz: rate, lastSampleAt: last, counters, monitoredMs: this.snapshot.monitoredMs + elapsed,
      reason: null });
  }

  private releaseResources() {
    this.subscription?.remove();
    this.appSubscription?.remove();
    if (this.watchdog) clearInterval(this.watchdog);
    this.subscription = null;
    this.appSubscription = null;
    this.watchdog = null;
    this.detector?.reset();
    this.detector = null;
    this.recent = [];
  }

  stop() {
    this.generation++;
    this.releaseResources();
    this.update({ ...initial(), appState: this.snapshot.appState, sensorAvailable: this.snapshot.sensorAvailable, model: this.snapshot.model });
    this.context = { trailId: null, startedAt: null };
  }
}

export const fallMonitor = new FallMonitor();

/** Explicit, user-initiated check used when the switch is turned on. */
export const requestSensorPermission = async (): Promise<{ granted: boolean; available: boolean }> => {
  let available = false;
  try { available = await Accelerometer.isAvailableAsync(); } catch { available = false; }
  if (!available) return { granted: false, available };
  try {
    let permission = await Accelerometer.getPermissionsAsync();
    if (permission.status !== "granted" && permission.canAskAgain) permission = await Accelerometer.requestPermissionsAsync();
    return { granted: permission.status === "granted", available };
  } catch { return { granted: true, available }; }   // no permission API on this platform
};
export const platformLimitations = Platform.OS === "ios"
  ? "En iPhone el sistema suspende la app al bloquear la pantalla o cambiar de app: la detección solo es confiable con MiSendero abierta y la pantalla encendida."
  : "En Android la detección continúa solo mientras el sistema siga entregando datos del acelerómetro; con pantalla bloqueada o ahorro de batería puede detenerse y la app lo indicará.";
