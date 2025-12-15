"use client";

import { useParams } from "next/navigation";
import { useTelemetry } from "@forge/hooks/useTelemetry";
import MachineStatsGrid from "../../components/machine/MachineStatsGrid";
import WorkflowTimeline from "app/components/machine/PassTimeline";
import { LeftPanel } from "app/components/machine/panel/LeftPanel";
import { CenterPanel } from "app/components/machine/panel/CenterPanel";
import { RightPanel } from "app/components/machine/panel/RightPanel";
export default function MachinePage() {
  const { id } = useParams() as { id: string };
  const { latest, history, lastUpdate } = useTelemetry(id);
  console.log("MachinePage telemetry:", { latest, history, lastUpdate });
  return (
    <div className="p-4 space-y-6">

      {/* <div className="px-2 py-2">
      <MachineStatsGrid latest={latest} />
      </div> */}

      {/* <WorkflowTimeline history={history} /> */}
       <main className="flex-1 px-4 pb-4 pt-10">
        <div className="grid h-full grid-cols-[280px_minmax(0,1fr)_340px] gap-4">
          <LeftPanel machineId={id} latest={latest} history={history} />
          <CenterPanel latest={latest} />
          <RightPanel machineId={id} />
        </div>
      </main>

    </div>
  );
}
