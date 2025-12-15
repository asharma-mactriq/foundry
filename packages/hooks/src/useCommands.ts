import {commandStore} from '@forge/stores'

export function useCommands() {
  return {
    commands: commandStore.commands,
    
    setMode: (mode: string) => commandStore.send("system.set_mode", { mode }),
    
    startProgram: () => commandStore.send("program.start"),
    stopProgram:   () => commandStore.send("program.stop"),
    nextPass:      (pass_no: number) => commandStore.send("program.next_pass", { pass_no }),
    loadProgram:   (program_id: string) => commandStore.send("program.load", { program_id }),

    trackStart: () => commandStore.send("motion.track_start"),
    trackStop:  () => commandStore.send("motion.track_stop"),

    openDispense: (open_ms: number) =>
      commandStore.send("dispense.open", { open_ms }),

    stopDispense: () => commandStore.send("dispense.stop"),

    pulseDispense: (open_ms: number, gap_ms: number, count: number) =>
      commandStore.send("dispense.pulse", { open_ms, gap_ms, count }),

    flush: (duration_ms: number) =>
      commandStore.send("pressure.flush", { duration_ms }),

    reprime: () => commandStore.send("pressure.reprime"),
    pressureCheck: () => commandStore.send("pressure.check"),

    visionStart: () => commandStore.send("vision.start"),
    visionStop:  () => commandStore.send("vision.stop"),
    visionCapture: () => commandStore.send("vision.capture"),

    emergencyStop: () => commandStore.send("system.emergency_stop"),
    resetFault:    () => commandStore.send("system.reset_fault"),


  };
}
