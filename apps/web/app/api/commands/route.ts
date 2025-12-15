// apps/web/app/api/commands/route.ts

export async function POST(req: Request) {
  const body = await req.json();

  const { command, payload } = body;

  // ---- FIX: Rewrite to what Python expects ----
  const pythonBody = {
    name: command,
    payload: payload ?? {}
  };

  const res = await fetch("http://localhost:8000/commands/dispatch", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(pythonBody),
  });

  const data = await res.json();

  return new Response(JSON.stringify(data), {
    status: res.status,
    headers: { "Content-Type": "application/json" },
  });
}
