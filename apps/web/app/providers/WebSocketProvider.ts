"use client";

import { createContext, useContext, useEffect } from "react";
import { WSClient } from "@forge/api/index";

const WSContext = createContext<WSClient | null>(null);

export function WebSocketProvider({ children }: any) {
  useEffect(() => {
    const ws = new WSClient("http://localhost:3001");
    ws.connect();
    console.log("WSClient started");
  }, []);

  return children;
}
