"use client";

import { useEffect, useState } from "react";
import { io } from "socket.io-client";
import FlowChart from "./components/charts/FlowChart";

export default function Page() {
  const [data, setData] = useState<any>(null);
  const [status, setStatus] = useState<any>(null);
  const [history, setHistory] = useState<any[]>([]);

  useEffect(() => {
    const socket = io("http://localhost:3001");

    socket.on("connect", () => {
      console.log("Connected:", socket.id);
    });

   socket.on("telemetry", (payload) => {
  setData(payload);

  setStatus({
    lastUpdate: Date.now(),
    age: 0,
    state: "LIVE",
  });

  setHistory((prev) => {
    const newHist = [...prev, { ...payload, receivedAt: Date.now() }];
    return newHist.slice(-50);
  });
});

    return () => {
      socket.disconnect();
    };
  }, []);

  // Update age every 1 sec
  useEffect(() => {
    const interval = setInterval(() => {
      setStatus((prev: any) => {
        if (!prev) return prev;

        const newAge = prev.age + 1000;

        return {
          ...prev,
          age: newAge,
          state: newAge < 3000 ? "LIVE" : "STALE",
        };
      });
    }, 1000);

    return () => clearInterval(interval);
  }, []);

  return (
    <div>
      <h1>Live Telemetry</h1>
      <pre>{JSON.stringify(data, null, 2)}</pre>

      {status && (
        <div style={{ marginTop: 20, fontSize: 18 }}>
          <p><b>Status:</b> {status.state}</p>
          <p><b>Last Updated:</b> {Math.round(status.age / 1000)} sec ago</p>
        </div>
      )}

<h2>Recent Telemetry</h2>
<ul>
  {history.slice(-20).map((item, index) => (
    <li key={index}>
      Flow: {item.flow} | Gap: {item.gap} | {new Date(item.receivedAt).toLocaleTimeString()}
    </li>
  ))}
</ul>

{history.length > 1 && (
  <div style={{ width: "100%", height: 300 }}>
    <FlowChart data={history} />
  </div>
)}


    </div>
  );
}


// "use client";

// import { useEffect, useState } from "react";
// import { io } from "socket.io-client";

// export default function Page() {
//   const [data, setData] = useState<any>(null);

//   useEffect(() => {
//     const socket = io("http://localhost:3001");

//     socket.on("connect", () => {
//       console.log("Connected:", socket.id);
//     });

//     socket.on("telemetry", (payload) => {
//       console.log("Received:", payload);
//       setData(payload);
//     });

//     return () => {
//       socket.disconnect();
//     };
//   }, []);

//   return (
//     <div>
//       <h1>Live Telemetry</h1>
//       <pre>{JSON.stringify(data, null, 2)}</pre>
//     </div>
//   );
// }
