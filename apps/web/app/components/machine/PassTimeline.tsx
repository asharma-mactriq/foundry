"use client";

import {
  Card,
  CardHeader,
  CardTitle,
  CardContent,
} from "@forge/ui/components/ui/card";
import { Badge } from "@forge/ui/components/ui/badge";
import { cn } from "@forge/lib/utils";
import type { TelemetryPayload } from "@forge/types";

type TimelineItem = {
  ts: number;
  source: "machine" | "program";
  label: string;
  details?: string;
  severity: "ok" | "info" | "warning" | "error";
};

function formatTime(ts: number | undefined) {
  if (!ts) return "-";
  // ts from Python is seconds; frontend uses ms → normalise
  const millis = ts < 10_000_000_000 ? ts * 1000 : ts;
  const d = new Date(millis);
  return d.toLocaleTimeString(undefined, { hour12: false });
}

function buildTimeline(history: TelemetryPayload[]): TimelineItem[] {
  const items: TimelineItem[] = [];

  let lastMachineEvent: string | null = null;
  let lastProgramEvent: string | null = null;
  let lastPass: number | null = null;

  for (const h of history) {
    const raw = h.raw ?? {};
    const m = h.machine ?? {};
    const p = h.program ?? {};

    // Machine-level events: plate_enter / plate_stable / plate_exit
    if (m.last_event && m.last_event !== lastMachineEvent) {
      items.push({
        ts: m.last_event_ts ?? raw.ts ?? Date.now(),
        source: "machine",
        label: m.last_event,
        details: `gap=${m.gap} flow=${raw.flow ?? "-"} pressure=${raw.pressure ?? "-"}`,
        severity:
          m.last_event === "plate_exit"
            ? "info"
            : m.last_event === "plate_stable"
            ? "ok"
            : "info",
      });
      lastMachineEvent = m.last_event;
    }

    // Program-level events: pass_enter / pass_exit / pass_stable etc.
    if (p.last_event && p.last_event !== lastProgramEvent) {
      items.push({
        ts: p.last_event_ts ?? raw.ts ?? Date.now(),
        source: "program",
        label: p.last_event,
        details: p.current_pass
          ? `pass=${p.current_pass} actual=${p.total_actual_paint ?? "-"}`
          : undefined,
        severity:
          p.last_event === "pass_exit"
            ? "ok"
            : p.last_event === "pass_stable"
            ? "info"
            : "info",
      });
      lastProgramEvent = p.last_event;
    }

    // Pass change (even if last_event didn’t change)
    if (typeof p.current_pass === "number" && p.current_pass !== lastPass) {
      items.push({
        ts: raw.ts ?? Date.now(),
        source: "program",
        label: `pass_change`,
        details: `Pass → ${p.current_pass}`,
        severity: "info",
      });
      lastPass = p.current_pass;
    }
  }

  // Sort by time and keep last 30 entries
  return items
    .sort((a, b) => a.ts - b.ts)
    .slice(-30);
}

const severityStyles: Record<TimelineItem["severity"], string> = {
  ok: "bg-green-100 text-green-700 border-green-300",
  info: "bg-blue-100 text-blue-700 border-blue-300",
  warning: "bg-yellow-100 text-yellow-700 border-yellow-300",
  error: "bg-red-100 text-red-700 border-red-300",
};

const sourceBadge: Record<TimelineItem["source"], string> = {
  machine: "MACHINE",
  program: "PROGRAM",
};

export default function WorkflowTimeline({
  history,
}: {
  history: TelemetryPayload[];
}) {
  if (!history?.length) {
    return (
      <Card className="mt-6">
        <CardHeader>
          <CardTitle className="text-sm font-medium">
            Workflow Timeline
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="text-sm text-muted-foreground">
            No events yet. Waiting for telemetry...
          </div>
        </CardContent>
      </Card>
    );
  }

  const timeline = buildTimeline(history);

  return (
    <Card className="mt-6">
      <CardHeader>
        <CardTitle className="text-sm font-medium">
          Workflow Timeline
        </CardTitle>
      </CardHeader>
      <CardContent>
        <div className="space-y-2 max-h-64 overflow-auto pr-1">
          {timeline.map((item, idx) => (
            <div
              key={`${item.ts}-${idx}`}
              className="flex items-start justify-between gap-3 text-sm py-1 border-b last:border-b-0"
            >
              <div className="flex flex-col">
                <span className="text-xs text-muted-foreground">
                  {formatTime(item.ts)}
                </span>
                <span className="font-medium capitalize">
                  {item.label.replaceAll("_", " ")}
                </span>
                {item.details && (
                  <span className="text-xs text-muted-foreground">
                    {item.details}
                  </span>
                )}
              </div>

              <div className="flex flex-col items-end gap-1">
                <Badge
                  variant="outline"
                  className={cn(
                    "text-[10px] px-2 py-0.5",
                    severityStyles[item.severity]
                  )}
                >
                  {item.severity.toUpperCase()}
                </Badge>
                <Badge
                  variant="outline"
                  className="text-[10px] px-2 py-0.5 bg-slate-100 text-slate-700 border-slate-300"
                >
                  {sourceBadge[item.source]}
                </Badge>
              </div>
            </div>
          ))}
        </div>
      </CardContent>
    </Card>
  );
}
