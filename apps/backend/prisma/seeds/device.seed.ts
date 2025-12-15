import { PrismaClient } from '@prisma/client';

export async function seedDevices(prisma: PrismaClient) {
  await prisma.device.createMany({
    data: [
      { name: 'ESP32 Test Device', type: 'esp32' },
      { name: 'CCTV Camera', type: 'camera' },
    ],
  });
}
