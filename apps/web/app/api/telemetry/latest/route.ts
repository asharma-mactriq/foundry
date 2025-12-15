export async function GET() {
  const res = await fetch("http://localhost:3001/telemetry/edge1/history");
  const data = await res.json();
  return Response.json(data);
}
