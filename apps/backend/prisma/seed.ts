import 'dotenv/config';
import { PrismaClient } from '@prisma/client';
import { seedDevices } from './seeds/device.seed';
import { seedComponents } from './seeds/component.seed';
import { seedTelemetry } from './seeds/telemetry.seed';

const prisma = new PrismaClient();

async function main() {
  await seedDevices(prisma);
  await seedComponents(prisma);
  await seedTelemetry(prisma);
}

main()
  .catch((e) => console.error(e))
  .finally(async () => await prisma.$disconnect())