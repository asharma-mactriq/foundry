// forge/packages/utils/src/wsClient.ts
import { io, Socket } from "socket.io-client";
import type { TelemetryMessage } from "@forge/types";

export class WSClient {
  private socket: Socket;

  constructor(url: string) {
    this.socket = io(url, { transports: ["websocket"] });
  }

  connect() {
    if (!this.socket.connected) this.socket.connect();
  }

  subscribe(cb: (msg: TelemetryMessage) => void) {
    this.socket.on("telemetry", cb);
    return () => this.socket.off("telemetry", cb);
  }
}
