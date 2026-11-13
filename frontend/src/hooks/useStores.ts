import { useSyncExternalStore } from "react";
import { healthStore } from "../lib/health";
import { runStore } from "../lib/runs";

export const useRuns = () => useSyncExternalStore(runStore.subscribe, runStore.getAll);

export const useRun = (id: string | undefined) =>
  useSyncExternalStore(runStore.subscribe, () => (id ? runStore.get(id) : undefined));

export const useHealth = () => useSyncExternalStore(healthStore.subscribe, healthStore.get);
