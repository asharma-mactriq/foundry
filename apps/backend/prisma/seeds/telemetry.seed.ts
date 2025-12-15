import { PrismaClient } from "@prisma/client";

export async function seedTelemetry(prisma: PrismaClient) {
  console.log("Seeding telemetry…");

  // 1️⃣ Fetch components (must already exist)
  const components = await prisma.component.findMany();

  if (components.length === 0) {
    console.warn("No components found. Telemetry not seeded.");
    return;
  }

  // 2️⃣ Generate telemetry rows for each component
  const telemetryData = components.flatMap((component) => [
    {
      componentId: component.id,
      timestamp: new Date(),
      type: component.type === "sensor" ? "distance" : "flow_rate",
      value: component.type === "sensor" ? 12.5 : 3.7,
    },
    {
      componentId: component.id,
      timestamp: new Date(Date.now() - 1000 * 60),
      type: component.type === "sensor" ? "distance" : "flow_rate",
      value: component.type === "sensor" ? 14.1 : 3.9,
    },
  ]);

  // 3️⃣ Insert telemetry
  await prisma.telemetry.createMany({
    data: telemetryData,
  });

  console.log("Telemetry seeded successfully.");
}
