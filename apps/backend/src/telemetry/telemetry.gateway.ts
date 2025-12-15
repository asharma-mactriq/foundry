import {
  WebSocketGateway,
  WebSocketServer,
} from '@nestjs/websockets';
import { Server } from 'socket.io';

@WebSocketGateway({
  cors: {
    origin: '*',
  },
})
export class TelemetryGateway {
  @WebSocketServer()
  server: Server;

  // machine-specific broadcast
  broadcast(machineId: string, data: any) {
    const payload = { machineId, data };
    console.log("WS BROADCAST:", payload);

    // send event to all frontend clients
    this.server.emit('telemetry', payload);
  }
}
