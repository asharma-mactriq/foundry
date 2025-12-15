import { Injectable } from '@nestjs/common';
import { TelemetryGateway } from './telemetry.gateway';

@Injectable()
export class TelemetryService {
  private store: Record<string, any> = {};   // machineId → latest telemetry
  private historyLimit = 50;

  constructor(private gateway: TelemetryGateway) {}

  update(machineId: string, data: any) {
    console.log("SERVICE UPDATE:", machineId, data);

    const now = Date.now();

    // update store
    const prev = this.store[machineId] ?? { history: [] };

    const history = [...prev.history, { ...data, receivedAt: now }]
      .slice(-this.historyLimit);

    this.store[machineId] = {
      latest: data,
      lastUpdate: now,
      history,
    };

    // broadcast to UI
    this.gateway.broadcast(machineId, data);
  }

  getLatest(machineId: string) {
    return this.store[machineId]?.latest ?? null;
  }

  getHistory(machineId: string) {
    return this.store[machineId]?.history ?? [];
  }

  getStatus(machineId: string) {
    const d = this.store[machineId];
    if (!d) return { status: 'UNKNOWN' };

    const age = Date.now() - d.lastUpdate;
    return {
      status: age < 3000 ? 'LIVE' : 'STALE',
      age,
      lastUpdate: d.lastUpdate,
    };
  }
}

