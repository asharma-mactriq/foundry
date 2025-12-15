"use client";

import { makeAutoObservable } from "mobx";
import { CommandEntry, CommandStatus } from "@forge/types";

class CommandStore {
  commands: CommandEntry[] = [];

  constructor() {
    makeAutoObservable(this, {}, { autoBind: true });
  }

  addCommand(command: CommandEntry) {
    this.commands.unshift(command);
  }

  updateStatus(id: string, status: CommandStatus, extra: Partial<CommandEntry> = {}) {
    const cmd = this.commands.find(c => c.id === id);
    if (!cmd) return;
    Object.assign(cmd, { status, ...extra });
  }


//   async send(name: string, payload: any = {}) {
//   const id = crypto.randomUUID();
//   const createdAt = Date.now();

//   const newCommand: CommandEntry = {
//     id,
//     name,
//     payload,
//     createdAt,
//     status: "pending",
//   };

//   this.addCommand(newCommand);

//   try {
//     const res = await fetch(`/api/commands`, {
//       method: "POST",
//       headers: { "Content-Type": "application/json" },
//       body: JSON.stringify({
//         command: name,   // frontend → proxy format
//         payload,
//       }),
//     });

//     if (!res.ok) {
//       throw new Error(await res.text());
//     }

//     this.updateStatus(id, "sent", { sentAt: Date.now() });
//   } catch (err: any) {
//     this.updateStatus(id, "failed", { error: err.message });
//   }

//   return id;
// }

// async send(name: string, payload: any = {}) {
//   const createdAt = Date.now();

//   // call backend → backend returns real cmd_id
//   const res = await fetch(`/api/commands`, {
//     method: "POST",
//     headers: { "Content-Type": "application/json" },
//     body: JSON.stringify({ command: name, payload }),
//   });

//   const data = await res.json();
//   const id = data.cmd_id;   // use backend id

//   const newCommand: CommandEntry = {
//     id,
//     name,
//     payload,
//     createdAt,
//     status: "pending",
//   };

//   this.addCommand(newCommand);
//   this.updateStatus(id, "sent", { sentAt: Date.now() });

//   return id;
// }

async send(name: string, payload: any = {}) {
  console.log("SEND:", name, payload); // TEMP for debugging

  const createdAt = Date.now();

  const res = await fetch(`/api/commands`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      command: name,       // Backend expects this exact key
      payload: payload ?? {}
    }),
  });

  if (!res.ok) {
    const txt = await res.text();
    console.error("SEND FAILED:", txt);
    throw new Error(txt);
  }

  const data = await res.json();
  const id = data.cmd_id;

  const newCommand = {
    id,
    name,
    payload,
    createdAt,
    status: "pending",
  };

  commandStore.addCommand(newCommand);
  commandStore.updateStatus(id, "sent", { sentAt: Date.now() });

  return id;
}


  // Call from websocket
  handleAck(event: any) {
    const { id, status } = event;

    if (status === "acked") {
      this.updateStatus(id, "acked", { ackAt: Date.now() });
    } else if (status === "timeout") {
      this.updateStatus(id, "timeout");
    } else if (status === "failed") {
      this.updateStatus(id, "failed", { error: event.error });
    }
  }
}

export const commandStore = new CommandStore();
