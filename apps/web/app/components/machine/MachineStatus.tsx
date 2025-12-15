"use client";

import React from "react";

interface Props {
  machineId: string;
}

export const MachineStatusBar: React.FC<Props> = ({ machineId }) => {
  // later: wire to heartbeat / mqtt / mode / errors
  return (
    <header className="h-11 border-b bg-white px-4 flex items-center justify-between">
      <div className="flex items-center gap-3">
        <span className="text-sm font-semibold">Machine: {machineId}</span>
        <span className="inline-flex items-center gap-1 text-xs">
          <span className="h-2 w-2 rounded-full bg-green-500" /> Heartbeat OK
        </span>
        <span className="text-xs text-slate-500">Mode: RUNNING</span>
      </div>
      <div className="flex items-center gap-3 text-xs text-slate-500">
        <span>Errors: 0</span>
        <span>MQTT: Connected</span>
        <span>Uptime: 00:00:00</span>
      </div>
    </header>
  );
};
