// --- RAW SENSOR TELEMETRY ---
export type RawTelemetry = {
  flow: number;
  gap: number;
  pressure?: number;
  ts: number;
};

// --- MACHINE STATE (DRIVEN BY ORCHESTRATOR) ---
export type MachineState = {
  mode: string;                       // idle | running | paused | refill | error
  pass: number;                       // current pass
  direction: "left" | "right" | "unknown";
  platePosition?: number;
  velocity?: number;
  lastEvent?: string;
  error?: string | null;
};

// --- PROGRAM STATE (FROM FORECAST/WORKFLOW ENGINE) ---
export type ProgramState = {
  programId: string;
  step: number;
  expectedPaint: number;
  actualPaint?: number;
  nextRefillAt?: number;
  forecast?: any;
  overrides?: Record<string, any>;
};

// --- TOTAL TELEMETRY PAYLOAD ---
export type TelemetryPayload = {
  raw: RawTelemetry;
  machine: MachineState;
  program: ProgramState;
  receivedAt: number;
};

// --- MESSAGE SENT OVER WEBSOCKET ---
export type TelemetryMessage = {
  machineId: string;
  data: TelemetryPayload;
};
