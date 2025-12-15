"use client";

import React from "react";
import { MachineCommands } from "../MachineCommandPanel";
import { CommandTable } from "../CommandTable";

interface Props {
  machineId: string;
}

export const RightPanel: React.FC<Props> = () => {
  return (
    <aside className="flex flex-col h-full gap-3">
      <MachineCommands />
      <CommandTable />
    </aside>
  );
};
