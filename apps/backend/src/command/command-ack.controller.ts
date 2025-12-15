import { Controller, Post, Body } from '@nestjs/common';
import { CommandGateway } from '../gateways/command.gateway';

@Controller('command-acks')
export class CommandAckController {
  constructor(private gateway: CommandGateway) {}

  @Post()
  handleAck(@Body() body: any) {
    const { cmd_id, status, error } = body;

    if (status === "acked") {
      this.gateway.emitAck(cmd_id);
    } else if (status === "timeout") {
      this.gateway.emitTimeout(cmd_id);
    } else if (status === "failed") {
      this.gateway.emitFailed(cmd_id, error ?? "unknown");
    }

    return { ok: true };
  }
}
