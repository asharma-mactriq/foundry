import { Controller, Get, Param } from '@nestjs/common';
import { TelemetryService } from '../telemetry/telemetry.service';

@Controller('machine')
export class MachinesController {
  constructor(private readonly telemetry: TelemetryService) {}

  @Get(':id/status')
  getStatus(@Param('id') id: string) {
    return this.telemetry.getStatus(id);
  }

  @Get(':id/latest')
  getLatest(@Param('id') id: string) {
    return this.telemetry.getLatest(id);
  }

  @Get(':id/history')
  getHistory(@Param('id') id: string) {
    return this.telemetry.getHistory(id);
  }
}
