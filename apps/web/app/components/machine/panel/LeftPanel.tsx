export const LeftPanel = ({ machineId, latest, history }) => {
  return (
    <section className="flex flex-col h-full gap-3">
      <div className="rounded-xl border bg-white p-3">
        <h3 className="text-sm font-semibold mb-2">Telemetry</h3>
        
        <div className="grid grid-cols-2 gap-2 text-xs">
          <div>Flow: <span className="font-mono">{latest?.raw.flow ?? "--"}</span></div>
          <div>Gap: <span className="font-mono">{latest?.raw.gap ?? "--"}</span></div>
          <div>Pressure: <span className="font-mono">{latest?.raw.pressure ?? "--"}</span></div>
        </div>
      </div>

      <div className="rounded-xl border bg-white p-3 flex-1">
        <h3 className="text-sm font-semibold mb-2">History</h3>
        {/* put sparkline here */}
        <div className="text-xs text-slate-500">
          Entries: {history?.length ?? 0}
        </div>
      </div>

      <div className="rounded-xl border bg-white p-3">
        <h3 className="text-sm font-semibold mb-2">Health & Warnings</h3>
        <div className="text-xs">OK</div>
      </div>
    </section>
  );
};


// "use client";

// import React from "react";

// interface Props {
//   machineId: string;
// }

// export const LeftPanel: React.FC<Props> = () => {
//   // plug your existing Machine Status / telemetry cards here
//   return (
//     <section className="flex flex-col h-full gap-3">
//       <div className="flex-0 rounded-xl border bg-white p-3">
//         <h3 className="mb-2 text-sm font-semibold">Telemetry</h3>
//         <p className="text-xs text-slate-500">
//           Flow / Gap / Pressure cards go here.
//         </p>
//       </div>

//       <div className="flex-1 rounded-xl border bg-white p-3">
//         <h3 className="mb-2 text-sm font-semibold">History</h3>
//         <p className="text-xs text-slate-500">
//           Mini graphs / sparklines over last 50 entries.
//         </p>
//       </div>

//       <div className="flex-0 rounded-xl border bg-white p-3">
//         <h3 className="mb-2 text-sm font-semibold">Health & Warnings</h3>
//         <p className="text-xs text-slate-500">
//           Pressure low / valve stuck / gap lost etc.
//         </p>
//       </div>
//     </section>
//   );
// };
