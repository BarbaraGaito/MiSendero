import { spawn, ChildProcessWithoutNullStreams } from "node:child_process";
import path from "node:path";
import { z } from "zod";
import { featureSpec, FeatureVector } from "./features";
export interface RankingPrediction { scores: number[]; modelVersion: string }
export interface Ranker { predict(features: FeatureVector[]): Promise<RankingPrediction | null> }

/** One private Python child per Node process. No shell, listener, training or account data. */
export class LocalRanker implements Ranker {
  private child: ChildProcessWithoutNullStreams | null = null;
  private startup: Promise<boolean> | null = null;
  private ready: ((value: boolean) => void) | null = null;
  private version: string | null = null;
  private buffer = "";
  private counter = 0;
  private pending = new Map<number, { count: number; resolve: (value: RankingPrediction | null) => void; timer: ReturnType<typeof setTimeout> }>();
  constructor(private directory = process.env.TRAIL_ML_MODEL_DIR, private executable = process.env.TRAIL_ML_PYTHON || "python3") {}
  start(): Promise<boolean> {
    if (!this.directory) return Promise.resolve(false);
    if (this.startup) return this.startup;
    this.startup = new Promise((resolve) => {
      this.ready = resolve;
      const timer = setTimeout(() => this.stop(), 15000); timer.unref();
      const settle = this.ready;
      this.ready = (value) => { clearTimeout(timer); settle(value); };
      try {
        const env: NodeJS.ProcessEnv = { NODE_ENV: process.env.NODE_ENV || "production", PYTHONUNBUFFERED: "1", PYTHONNOUSERSITE: "1", TRAIL_ML_TRUSTED_SHA256: process.env.TRAIL_ML_TRUSTED_SHA256 || "", OMP_NUM_THREADS: "1", OPENBLAS_NUM_THREADS: "1" };
        for (const key of ["PATH", "Path", "SystemRoot", "WINDIR", "TEMP", "TMP", "HOME"]) if (process.env[key]) env[key] = process.env[key];
        this.child = spawn(this.executable, ["-u", path.resolve(__dirname, "../../ml/serve.py"), "--model-dir", path.resolve(this.directory!)], { shell: false, windowsHide: true, env, stdio: "pipe" });
        this.child.stdout.setEncoding("utf8");
        this.child.stdout.on("data", (chunk: string) => this.receive(chunk));
        this.child.stdout.on("error", () => this.stop());
        this.child.stderr.resume();
        this.child.stderr.on("error", () => this.stop());
        this.child.on("error", () => this.stop());
        this.child.on("exit", () => this.stop());
        this.child.stdin.on("error", () => this.stop());
      } catch { this.stop(); }
    });
    return this.startup;
  }
  private receive(chunk: string) {
    this.buffer += chunk;
    if (this.buffer.length > 1024 * 1024) return this.stop();
    let end: number;
    while ((end = this.buffer.indexOf("\n")) >= 0) {
      const line = this.buffer.slice(0, end); this.buffer = this.buffer.slice(end + 1);
      try {
        const message = JSON.parse(line);
        if (!this.version) {
          const ready = z.object({ type: z.literal("ready"), modelVersion: z.string().min(1).max(100), featureSchemaVersion: z.literal(featureSpec.version) }).strict().parse(message);
          this.version = ready.modelVersion; this.ready?.(true); this.ready = null;
        } else {
          const result = z.object({ id: z.number().int(), scores: z.array(z.number().finite()).max(10000) }).strict().parse(message);
          const pending = this.pending.get(result.id);
          if (!pending || pending.count !== result.scores.length) return this.stop();
          clearTimeout(pending.timer); this.pending.delete(result.id);
          pending.resolve({ scores: result.scores, modelVersion: this.version });
        }
      } catch { return this.stop(); }
    }
  }
  async predict(features: FeatureVector[]): Promise<RankingPrediction | null> {
    if (!features.length || features.length > 10000) return null;
    // Startup runs once in the background. An unready worker must not hold up the API.
    if (!this.version || !this.child) { void this.start(); return null; }
    return new Promise((resolve) => {
      const id = ++this.counter;
      const timer = setTimeout(() => this.stop(), Math.min(5000, Math.max(100, Number(process.env.TRAIL_ML_TIMEOUT_MS) || 1500)));
      this.pending.set(id, { count: features.length, resolve, timer });
      this.child!.stdin.write(`${JSON.stringify({ id, features })}\n`, (error) => { if (error) this.stop(); });
    });
  }
  stop() {
    const child = this.child; this.child = null; this.version = null;
    this.ready?.(false); this.ready = null;
    for (const pending of this.pending.values()) { clearTimeout(pending.timer); pending.resolve(null); }
    this.pending.clear(); this.buffer = "";
    if (child && !child.killed) child.kill();
  }
}
export const localRanker = new LocalRanker();
process.once("exit", () => localRanker.stop());
