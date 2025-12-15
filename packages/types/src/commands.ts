export type CommandStatus =
  | "pending"
  | "sent"
  | "acked"
  | "timeout"
  | "failed";

export interface CommandEntry {
  id: string;
  name: string;
  payload?: any;
  createdAt: number;
  sentAt?: number;
  ackAt?: number;
  status: CommandStatus;
  error?: string;
}
