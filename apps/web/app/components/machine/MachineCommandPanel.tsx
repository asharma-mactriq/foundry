"use client";

import React, { useState } from "react";
import { observer } from "mobx-react-lite";
import { useCommands } from "@forge/hooks/useCommands";

export const MachineCommands: React.FC = observer(() => {
  const cmd = useCommands();
  const [busy, setBusy] = useState(false);

  async function handleClick(action: () => Promise<any>) {
    if (busy) return;
    try {
      setBusy(true);
      await action();
    } finally {
      setBusy(false);
    }
  }

  const btnBase =
    "text-xs px-2 py-1 rounded border transition disabled:opacity-50 disabled:cursor-not-allowed";
  const primary = `${btnBase} bg-emerald-600 text-white border-emerald-700`;
  const danger = `${btnBase} bg-red-600 text-white border-red-700`;
  const neutral = `${btnBase} bg-slate-100 text-slate-800 border-slate-300`;
  const warn = `${btnBase} bg-amber-500 text-white border-amber-600`;

  return (
    <section className="rounded-xl border bg-white p-3">
      <div className="mb-2 flex items-center justify-between">
        <h3 className="text-sm font-semibold">Commands</h3>
        {busy && (
          <span className="text-[10px] uppercase tracking-wide text-slate-500">
            Sending…
          </span>
        )}
      </div>

      <div className="flex gap-2 mb-2">
        <button className={neutral} disabled={busy}
          onClick={() => handleClick(() => cmd.setMode("manual"))}>
          Manual
        </button>

        <button className={neutral} disabled={busy}
          onClick={() => handleClick(() => cmd.setMode("semi_auto"))}>
          Semi Auto
        </button>

        <button className={primary} disabled={busy}
          onClick={() => handleClick(() => cmd.setMode("auto"))}>
          Auto Mode
        </button>
      </div>


      <div className="space-y-2 text-xs">
        <div className="flex flex-wrap gap-2">
          <button
            className={primary}
            disabled={busy}
            onClick={() => handleClick(cmd.startProgram)}
          >
            Start Program
          </button>
          <button
            className={neutral}
            disabled={busy}
            onClick={() => handleClick(cmd.stopProgram)}
          >
            Pause
          </button>
          <button
            className={neutral}
            disabled={busy}
            onClick={() => handleClick(cmd.emergencyStop)}
          >
            Reset
          </button>
          <button
            className={danger}
            disabled={busy}
            onClick={() => handleClick(cmd.abortProgram)}
          >
            Abort
          </button>
        </div>

        <div className="flex flex-wrap gap-2 pt-1 border-t border-dashed border-slate-200 mt-1">
          <button
            className={neutral}
            disabled={busy}
            onClick={() => handleClick(cmd.openValve)}
          >
            Open Valve
          </button>
          <button
            className={neutral}
            disabled={busy}
            onClick={() => handleClick(cmd.closeValve)}
          >
            Close Valve
          </button>
        </div>

        <div className="flex flex-wrap gap-2 pt-1 border-t border-dashed border-slate-200 mt-1">
          <button
            className={warn}
            disabled={busy}
            onClick={() => handleClick(cmd.refill)}
          >
            Refill Sequence
          </button>
          <button
            className={neutral}
            disabled={busy}
            onClick={() => handleClick(cmd.calibrate)}
          >
            Calibrate
          </button>
          <button
            className={neutral}
            disabled={busy}
            onClick={() => handleClick(cmd.resetErrors)}
          >
            Reset Errors
          </button>
        </div>
      </div>
    </section>
  );
});


