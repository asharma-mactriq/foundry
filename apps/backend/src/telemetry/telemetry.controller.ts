import { Controller, Post, Get, Body, Param } from '@nestjs/common';
import { TelemetryService } from './telemetry.service';

@Controller('telemetry')
export class TelemetryController {
  constructor(private readonly service: TelemetryService) {}

  // 🐛 FIX 1: Change ingest to match the service's update signature.
  // We'll use a route parameter for the machineId.
  @Post(':machineId/ingest') // Route now includes machineId
  ingest(@Param('machineId') machineId: string, @Body() body: any) {
    console.log(`INGESTED for ${machineId}:`, body);
    
    // Call the correct service method: update(), which handles all logic.
    this.service.update(machineId, body); 
    return { status: 'ok', machineId };
  }

  // 🐛 FIX 2: All GET methods now require a machineId route parameter.
  @Get(':machineId/latest')
  latest(@Param('machineId') machineId: string) {
    return this.service.getLatest(machineId);
  }

  @Get(':machineId/status')
  status(@Param('machineId') machineId: string) {
    return this.service.getStatus(machineId);
  }

  @Get(':machineId/history')
  history(@Param('machineId') machineId: string) {
    return this.service.getHistory(machineId);
  }
}