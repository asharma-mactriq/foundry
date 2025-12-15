"use client";

import {
  LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer
} from "recharts";

export default function FlowChart({ data }: { data: any[] }) {
  if (!data || data.length < 2) return <div>Waiting for chart data…</div>;

  const formatted = data.map((d: any) => ({
    time: new Date(d.receivedAt).toLocaleTimeString(),
    flow: d.flow,
  }));

  return (
    <div style={{ width: "100%", height: "100%" }}>
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={formatted}>
          <Line type="monotone" dataKey="flow" stroke="#00aaff" dot={false} />
          <XAxis dataKey="time" hide />
          <YAxis />
          <Tooltip />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
