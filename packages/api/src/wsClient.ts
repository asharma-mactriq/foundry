import { io, Socket } from "socket.io-client";
import { TelemetryMessage } from "@forge/types/index";
import { commandStore } from "@forge/stores";

export class WSClient {
  private socket: Socket;

  constructor(url: string) {
    console.log("INIT SOCKET.IO CLIENT:", url);
    this.socket = io(url, {
      transports: ["websocket"],
    });
  }

  connect() {
    console.log("CONNECTING TO SOCKET.IO…");
    this.socket.connect();

    this.socket.on("connect", () => {
      console.log("SOCKET.IO CONNECTED:", this.socket.id);
    });

    this.socket.on("connect_error", (err) => {
      console.error("SOCKET.IO CONNECTION ERROR:", err);
    });

    // --- COMMAND EVENTS ---
// --- COMMAND EVENTS ---
  this.socket.on("command_ack", (msg) => {
    console.log("COMMAND ACK:", msg);
    commandStore.handleAck({ id: msg.cmd_id, status: msg.status ?? "acked" });
  });

  this.socket.on("command_timeout", (msg) => {
    console.log("COMMAND TIMEOUT:", msg);
    commandStore.handleAck({ id: msg.cmd_id, status: "timeout" });
  });

  this.socket.on("command_failed", (msg) => {
    console.log("COMMAND FAILED:", msg);
    commandStore.handleAck({
      id: msg.cmd_id,
      status: "failed",
      error: msg.error,
    });
  });

  // Remove the duplicate one!
  this.socket.on("command_status", (msg) => {
    console.log("COMMAND STATUS:", msg);
    commandStore.updateStatus(msg.cmd_id, msg.status);
  });
  }

  subscribe(cb: (msg: TelemetryMessage) => void) {
    this.socket.on("telemetry", (msg: TelemetryMessage) => {
      console.log("SOCKET.IO MESSAGE:", msg);
      cb(msg);
    });
  }
}
