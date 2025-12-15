import { makeAutoObservable } from "mobx";

class TimelineStore {
  entries = [];

  constructor() {
    makeAutoObservable(this);
  }

  add(entry) {
    this.entries.push({
      ...entry,
      ts: Date.now()
    });
    this.entries = this.entries.slice(-50); // keep last 50
  }
}

export const timelineStore = new TimelineStore();
