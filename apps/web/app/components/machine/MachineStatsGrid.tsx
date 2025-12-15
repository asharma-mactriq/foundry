"use client";

import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@forge/ui/components/ui/card";
import { Badge } from "@forge/ui/components/ui/badge";
import { cn } from "@forge/lib/utils";
import type { TelemetryPayload } from "@forge/types";

export default function MachineStatsGrid({ latest }: { latest?: TelemetryPayload | null }) {
  if (!latest)
    return (
      <div className="text-sm text-muted-foreground">
        Waiting for telemetry...
      </div>
    );

  const raw = latest.raw;
  const m = latest.machine;
  const p = latest.program;

  const tiles = [
    {
      label: "Flow",
      value: raw.flow,
      unit: "ml/s",
      status: raw.flow > 0 ? "ok" : "idle",
    },
    {
      label: "Pressure",
      value: raw.pressure,
      unit: "psi",
      status: raw.pressure > 1 ? "ok" : "warning",
    },
    {
      label: "Gap Detect",
      value: m.gap_detected ? "YES" : "NO",
      status: m.gap_detected ? "ok" : "error",
    },
    {
      label: "Plate Stable",
      value: m.stable_window ? "YES" : "NO",
      status: m.stable_window ? "ok" : "warning",
    },
    {
      label: "Plate Transition",
      value: m.plate_transition ? "YES" : "NO",
      status: m.plate_transition ? "info" : "idle",
    },
    {
      label: "Machine State",
      value: m.state,
      status: m.state === "DISPENSING" ? "ok" : "info",
    },
    {
      label: "Current Pass",
      value: m.current_pass ?? "-",
      status: "info",
    },
    {
      label: "Pressure OK",
      value: m.pressure_ok ? "YES" : "NO",
      status: m.pressure_ok ? "ok" : "error",
    },
    {
      label: "Program Running",
      value: p.running ? "YES" : "NO",
      status: p.running ? "ok" : "idle",
    },
    {
      label: "Program Pass",
      value: `${p.current_pass} / ${p.total_passes}`,
      status: p.running ? "ok" : "idle",
    },
    {
      label: "Target Volume",
      value: p.target_volume,
      unit: "ml",
      status: "info",
    },
    {
      label: "Actual Volume",
      value: p.actual_volume,
      unit: "ml",
      status: p.actual_volume > p.target_volume ? "warning" : "ok",
    },
    {
      label: "Override",
      value: p.override ? "YES" : "NO",
      status: p.override ? "warning" : "idle",
    },
    {
      label: "Refill Required",
      value: p.refill_required ? "YES" : "NO",
      status: p.refill_required ? "error" : "ok",
    },
  ];

  const statusColor = {
    ok: "bg-green-100 text-green-700 border-green-300",
    warning: "bg-yellow-100 text-yellow-700 border-yellow-300",
    error: "bg-red-100 text-red-700 border-red-300",
    idle: "bg-gray-100 text-gray-600 border-gray-300",
    info: "bg-blue-100 text-blue-700 border-blue-300",
  };

  return (
    <div className="grid grid-cols-2 md:grid-cols-3 xl:grid-cols-4 gap-4 mt-4">
      {tiles.map((tile) => (
        <Card key={tile.label} className="shadow-sm border">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium">{tile.label}</CardTitle>
          </CardHeader>
          <CardContent className="flex items-center justify-between">
            <div className="text-xl font-semibold">
              {tile.value}
              {tile.unit && (
                <span className="text-sm text-muted-foreground ml-1">
                  {tile.unit}
                </span>
              )}
            </div>

            <Badge
              variant="outline"
              className={cn(
                statusColor[tile.status as keyof typeof statusColor]
              )}
            >
              {String(tile.status).toUpperCase()}
            </Badge>
          </CardContent>
        </Card>
      ))}
    </div>
  );
}
