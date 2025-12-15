import { Controller, Post, Body } from '@nestjs/common';
import { MqttService } from 'src/mqtt/mqtt.service';

@Controller('programs')
export class ProgramsController {
  constructor(private readonly mqtt: MqttService) {}

  @Post('start')
  startProgram(@Body() dto: any) {
    const msg = {
      cmd: 'start_program',
      programId: dto.programId,
      passes: dto.passes,
      params: dto.params || {},
    };

    this.mqtt.publish('edge/commands', msg);
    return { ok: true };
  }

  @Post('stop')
  stopProgram(@Body() dto: any) {
    this.mqtt.publish('edge/commands', { cmd: 'stop_program' });
    return { ok: true };
  }
}
