import { Module } from '@nestjs/common';
import { TelemetryModule } from 'src/telemetry/telemetry.module';
import { MachinesController } from './machines.controller';

@Module({
  imports: [TelemetryModule],
  controllers: [MachinesController],
})
export class MachinesModule {}
