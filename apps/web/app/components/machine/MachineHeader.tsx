"use client";

import { Circle } from "lucide-react";
import { cn } from "@forge/lib/utils";

export default function MachineHeader({
  machineId,
  lastUpdate,
  latest,
}: {
  machineId: string;
  lastUpdate?: number;
  latest?: any;
}) {
  const age = lastUpdate ? Date.now() - lastUpdate : Infinity;
  const isLive = age < 3000;

  return (
    <div className="flex flex-col md:flex-row items-center justify-between p-4 bg-white shadow-sm rounded-md">
      
      {/* LEFT: MACHINE ID + STATUS */}
      <div className="flex items-center gap-4">
        <h1 className="text-2xl font-semibold">Machine {machineId}</h1>

        <div className="flex items-center gap-1">
          <Circle
            className={cn(
              "h-3 w-3",
              isLive ? "text-green-500" : "text-red-500"
            )}
            fill={isLive ? "green" : "red"}
          />
          <span className="text-sm">
            {isLive ? "LIVE" : "OFFLINE"}
          </span>
        </div>

        {lastUpdate && (
          <span className="text-xs text-muted-foreground">
            updated {Math.floor(age)}ms ago
          </span>
        )}
      </div>

      {/* RIGHT: PROGRAM + PASS INFO */}
      <div className="flex items-center gap-6 text-sm">
        <div>
          <div className="text-muted-foreground">Program</div>
          <div className="font-medium">{latest?.program?.name ?? "-"}</div>
        </div>

        <div>
          <div className="text-muted-foreground">Current Pass</div>
          <div className="font-medium">{latest?.program?.current_pass ?? 0}</div>
        </div>

        <div>
          <div className="text-muted-foreground">AI Mode</div>
          <div className="font-medium">
            {latest?.program?.ai_mode ? "ON" : "OFF"}
          </div>
        </div>
      </div>

    </div>
  );
}
