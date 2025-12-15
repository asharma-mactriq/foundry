import { Module } from '@nestjs/common';
import { AppController } from './app.controller';
import { AppService } from './app.service';
import { ClientsModule, Transport } from '@nestjs/microservices';

import { DevicesModule } from './devices/devices.module';
import { ComponentsModule } from './components/components.module';
import { TelemetryModule } from './telemetry/telemetry.module';
import { MqttModule } from './mqtt/mqtt.module';
import { MachinesModule } from './machines/machines.module';
import { CommandModule } from './command/command.module';

@Module({
  imports: [
ClientsModule.register([
      {
        name: 'MQTT_SERVICE',
        transport: Transport.MQTT,
        options: {
          url: 'mqtt://localhost:1883',
        },
      },
    ]),
    DevicesModule, ComponentsModule, TelemetryModule , MqttModule, MachinesModule, CommandModule],
  controllers: [AppController],
  providers: [AppService],
})
export class AppModule {}
