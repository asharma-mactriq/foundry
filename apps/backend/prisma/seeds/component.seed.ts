import { PrismaClient } from '@prisma/client';

export async function seedComponents(prisma: PrismaClient) {
  const devices = await prisma.device.findMany();

  for (const device of devices) {
    if (device.type === 'esp32') {
      await prisma.component.createMany({
        data: [
          { name: 'Ultrasonic Sensor', type: 'sensor', deviceId: device.id },
          { name: 'Flow Meter', type: 'sensor', deviceId: device.id },
          { name: 'Solenoid Valve', type: 'actuator', deviceId: device.id }
        ],
      });
    }

    if (device.type === 'camera') {
      await prisma.component.create({
        data: {
          name: 'Video Feed',
          type: 'camera',
          deviceId: device.id
        }
      });
    }
  }
}
