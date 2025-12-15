import { create } from "zustand";
import type { TelemetryPayload } from "@forge/types";

type MachineTelemetry = {
  latest?: TelemetryPayload;
  history: TelemetryPayload[];
  lastUpdate?: number;
};

export const useTelemetryStore = create<{
  machines: Record<string, MachineTelemetry>;
  push: (id: string, t: TelemetryPayload) => void;
  loadInitial: (id: string, latest: TelemetryPayload | null, history: TelemetryPayload[]) => void;
}>((set) => ({
  machines: {},

  push: (id, data) =>
    set((state) => {
      const prev = state.machines[id] ?? { history: [] };

      return {
        machines: {
          ...state.machines,
          [id]: {
            latest: data,
            lastUpdate: Date.now(),
            history: [...prev.history, data],
          },
        },
      };
    }),

  loadInitial: (id, latest, history) =>
    set((state) => ({
      machines: {
        ...state.machines,
        [id]: {
          latest,
          history,
          lastUpdate: Date.now(),
        },
      },
    })),
}));


// import { create } from "zustand";
// import { Telemetry } from "@forge/types";

// type MachineTelemetry = {
//   latest?: Telemetry;
//   history: Telemetry[];
//   lastUpdate?: number;
// };

// export const useTelemetryStore = create<{
//   machines: Record<string, MachineTelemetry>;
//   push: (id: string, t: Telemetry) => void;
// }>((set) => ({
//   machines: {},
//   // live update
//   push: (id, data) => 
//     set((state) => {
//       const prev = state.machines[id] ?? {
//         latest: null,
//         history: [],
//       };

//       return {
//         machines: {
//           ...state.machines,
//           [id]: {
//             latest: data,
//             lastUpdate: Date.now(),
//             history: [...prev.history, data],
//           },
//         },
//       };
//     }),

//   // initial load
// loadInitial: (id, latest, history) =>
//   set(state => ({
//     machines: {
//       ...state.machines,
//       [id]: {
//         latest,
//         history,
//         lastUpdate: Date.now(),
//       },
//     },
//   })),

// }));

