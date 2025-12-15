// apps/backend/src/gateways/command.gateway.ts
import { WebSocketGateway, WebSocketServer } from '@nestjs/websockets';
import { Server } from 'socket.io';

@WebSocketGateway({ cors: { origin: '*' } })
export class CommandGateway {
  @WebSocketServer()
  server: Server;

  emitAck(cmd_id: string) {
    this.server.emit("command_ack", { cmd_id });
  }

  emitTimeout(cmd_id: string) {
    this.server.emit("command_timeout", { cmd_id });
  }

  emitFailed(cmd_id: string, error: string) {
    this.server.emit("command_failed", { cmd_id, error });
  }
}
