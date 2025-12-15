import { useEffect, useRef } from "react";
import useSWR from "swr";
import { useTelemetryStore } from "@forge/stores/telemetry";
import { WSClient } from "@forge/utils";
import type { TelemetryPayload } from "@forge/types";

const API = process.env.NEXT_PUBLIC_API_URL!;
const ws = new WSClient(process.env.NEXT_PUBLIC_WS_URL!);

const fetcher = (url: string) => fetch(url).then((r) => r.json());

export function useTelemetry(machineId: string) {
  const push = useTelemetryStore((s) => s.push);
  const loadInitial = useTelemetryStore((s) => s.loadInitial);
  const machine = useTelemetryStore((s) => s.machines[machineId]);

  const initialized = useRef(false);

  const { data: historyData } = useSWR<TelemetryPayload[]>(
    `${API}/machine/${machineId}/history`,
    fetcher,
    {
      dedupingInterval: 3000,
      revalidateOnFocus: false,
    }
  );

  useEffect(() => {
    if (initialized.current) return;
    if (!historyData || !Array.isArray(historyData)) return;

    const latest = historyData.at(-1) ?? null;

    loadInitial(machineId, latest, historyData);
    initialized.current = true;
  }, [historyData, machineId, loadInitial]);

  useEffect(() => {
    ws.connect();

    const unsubscribe = ws.subscribe((msg) => {
      if (msg.machineId === machineId) {
        initialized.current = true;
        push(machineId, msg.data);
      }
    });

    return unsubscribe;
  }, [machineId, push]);

  return {
    latest: machine?.latest ?? null,
    history: machine?.history ?? [],
    lastUpdate: machine?.lastUpdate ?? null,
  };
}
