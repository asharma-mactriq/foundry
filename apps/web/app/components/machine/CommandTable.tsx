"use client";

import React from "react";
import { observer } from "mobx-react-lite";
import { commandStore } from "@forge/stores/commands";

export const CommandTable: React.FC = observer(() => {
  const commands = commandStore.commands;

  return (
    <section className="flex-1 rounded-xl border bg-white p-3 min-h-0 flex flex-col">
      <h3 className="mb-2 text-sm font-semibold">Command Queue</h3>

      <div className="flex-1 min-h-0 overflow-auto">
        <table className="w-full border-collapse text-[11px]">
          <thead>
            <tr className="border-b bg-slate-50 text-[10px] uppercase tracking-wide text-slate-500">
              <th className="px-1 py-1 text-left">ID</th>
              <th className="px-1 py-1 text-left">Command</th>
              <th className="px-1 py-1 text-left">Status</th>
              <th className="px-1 py-1 text-left">Created</th>
              <th className="px-1 py-1 text-left">Sent</th>
              <th className="px-1 py-1 text-left">Ack</th>
              <th className="px-1 py-1 text-left">Error</th>
            </tr>
          </thead>
          <tbody>
            {commands.length === 0 ? (
              <tr>
                <td
                  colSpan={7}
                  className="px-1 py-2 text-center text-[11px] text-slate-400"
                >
                  No commands yet.
                </td>
              </tr>
            ) : (
              commands.map((cmd) => (
                <tr
                  key={cmd.id}
                  className="border-b last:border-b-0 hover:bg-slate-50/60"
                >
                  <td className="px-1 py-1 align-top font-mono text-[10px] text-slate-500">
                    {cmd.id ? cmd.id.slice(0, 6) : "---"}
                  </td>

                  <td className="px-1 py-1 align-top">{cmd.name}</td>
                  <td className="px-1 py-1 align-top">
                    <StatusPill status={cmd.status} />
                  </td>
                  <td className="px-1 py-1 align-top">
                    {formatTime(cmd.createdAt)}
                  </td>
                  <td className="px-1 py-1 align-top">
                    {cmd.sentAt ? formatTime(cmd.sentAt) : "-"}
                  </td>
                  <td className="px-1 py-1 align-top">
                    {cmd.ackAt ? formatTime(cmd.ackAt) : "-"}
                  </td>
                  <td className="px-1 py-1 align-top text-[10px] text-red-500">
                    {cmd.error || "-"}
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </section>
  );
});

function formatTime(t?: number) {
  if (!t) return "-";
  return new Date(t).toLocaleTimeString();
}

function StatusPill({ status }: { status: string }) {
  let cls =
    "inline-flex items-center rounded-full px-2 py-[1px] text-[10px] font-medium";
  let label = status;

  switch (status) {
    case "pending":
      cls += " bg-amber-100 text-amber-800";
      label = "Pending";
      break;
    case "sent":
      cls += " bg-sky-100 text-sky-800";
      label = "Sent";
      break;
    case "acked":
      cls += " bg-emerald-100 text-emerald-800";
      label = "Acked";
      break;
    case "timeout":
      cls += " bg-orange-100 text-orange-800";
      label = "Timeout";
      break;
    case "failed":
      cls += " bg-red-100 text-red-800";
      label = "Failed";
      break;
    default:
      cls += " bg-slate-100 text-slate-700";
  }

  return <span className={cls}>{label}</span>;
}
