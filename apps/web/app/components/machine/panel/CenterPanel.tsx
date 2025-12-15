import WorkflowTimeline from "../PassTimeline"

export const CenterPanel = ({ latest }) => {
  return (
    <section className="flex flex-col h-full gap-3">

      <div className="rounded-xl border bg-white p-3">
        <h3 className="text-sm font-semibold">Workflow View</h3>
        <div className="text-xs">
          Current mode: {latest?.machine.mode ?? "--"}
          <br />
          Step: {latest?.program.step ?? "--"}
        </div>
      </div>

      <div className="rounded-xl border bg-white p-3">
        <h3 className="text-sm font-semibold">Program Execution</h3>
        <div className="text-xs">
          Program: {latest?.program.programId ?? "—"}
          <br />
          Active Pass: {latest?.machine.pass ?? "--"}
        </div>
      </div>

      <div className="rounded-xl border bg-white p-3">
        <h3 className="text-sm font-semibold">Pass Tracker</h3>
        {/* later: show ✔ active etc */}
        <div className="text-xs">Pass: {latest?.machine.pass}</div>
      </div>

      <div className="rounded-xl border bg-white p-3 flex-1 overflow-auto">
        <h3 className="text-sm font-semibold">Forecast Table</h3>
        <WorkflowTimeline history={latest?.program.history || []} />
        <div className="text-xs text-slate-500">
          Coming soon: predicted vs actual.
        </div>
      </div>

    </section>
  );
};
