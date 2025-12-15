import { Injectable, Logger, OnModuleInit } from '@nestjs/common';
import * as mqtt from 'mqtt';
import { TelemetryService } from '../telemetry/telemetry.service';
import { TelemetryGateway } from '../telemetry/telemetry.gateway';

@Injectable()
export class MqttService implements OnModuleInit {
  private readonly logger = new Logger('MqttService');
  private client: mqtt.MqttClient;
  private broker = process.env.MQTT_BROKER ?? 'mqtt://127.0.0.1:1883';

  constructor(
    private readonly telemetry: TelemetryService,
    private readonly gateway: TelemetryGateway,
  ) {}

  onModuleInit() {
    this.connect();


  }

  connect() {
    this.client = mqtt.connect(this.broker);

    this.client.on('connect', () => {
      this.logger.log(`Connected to MQTT ${this.broker}`);

      this.client.subscribe('devices/+/telemetry', { qos: 0 });
      this.client.subscribe('machine/+/status', { qos: 0 });
      this.client.subscribe('edge/rules/audit', { qos: 0 });
    });

    this.client.on('message', (topic, payload) => {
      try {
        const msg = JSON.parse(payload.toString());
        this.logger.debug(`msg on ${topic}: ${JSON.stringify(msg)}`);

        // Detect telemetry topic
        if (topic.match(/^devices\/.+\/telemetry$/) ||
            topic.match(/^machine\/.+\/status$/)) {

          const match = topic.match(/devices\/([^/]+)\/telemetry|machine\/([^/]+)\/status/);
          const machineId = match ? (match[1] || match[2]) : 'unknown';

          // Update storage + WS
          this.telemetry.update(machineId, msg);

         

        } else if (topic === 'edge/rules/audit') {
          this.logger.log(`Rule audit: ${JSON.stringify(msg)}`);
        }

      } catch (e) {
        this.logger.error('Invalid MQTT message', e);
      }
    });

    this.client.on('error', (err) => {
      this.logger.error('MQTT error', err);
    });
  }

  publish(topic: string, payload: any) {
    if (!this.client || !this.client.connected) {
      this.logger.warn('MQTT not connected - cannot publish');
      return;
    }
    this.client.publish(topic, JSON.stringify(payload));
  }
}
