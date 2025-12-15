// src/mqtt/mqtt.module.ts
import { Module } from '@nestjs/common';
import { MqttService } from './mqtt.service';
import { TelemetryModule } from '../telemetry/telemetry.module';
import { TelemetryGateway } from '../telemetry/telemetry.gateway';

@Module({
  imports: [TelemetryModule, ],
  providers: [MqttService, TelemetryGateway],
  exports: [MqttService],
})
export class MqttModule {}
