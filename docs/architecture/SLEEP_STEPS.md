# Sleep and step subsystems — architecture

```mermaid
flowchart TB
  subgraph device["Device / firmware (unchanged)"]
    IMU["LSM6DS3 acc+gyro 104 Hz"] --> BLE["BLE v1/v2 packets"]
    PPG["MAX30102"] --> BLE
    FG["finger gate:<br/>streams only with finger"] -.-> BLE
  end
  BLE --> RT["RuntimeEngine (pure, signal-time)"]
  subgraph live["Live path (unchanged calculations)"]
    RT --> TR["tremor v3"]
    RT --> CV["PPG / HRV"]
    RT --> ST{"step_counter="}
    ST -- default --> S1["StepCounter v1.1"]
    ST -- periodic --> S2["PeriodicStepCounter 2.0"]
    ST -- gated --> S3["GatedStepCounter 3.0-dev"]
  end
  RT --> REC["SessionRecorder<br/>capture.csv (79 cols) + metadata.json<br/>+ step_algorithm, step_algorithm_version,<br/>sleep_algorithm_version"]
  subgraph offline["Offline path (new, independent)"]
    REC --> SLP["parkinsense.sleep.api.analyze_file<br/>features → logistic regression → night summary"]
  end
  SLP --> DASH["Dashboard: Sleep (estimate) page"]
  REC --> DASH2["Dashboard: Activity page"]
  subgraph bench["Benchmarks (public datasets, not ParkinSense)"]
    EXT["data/external: Walch, Clemson, Karas"] --> SB["sleep_bench (LOSO)"]
    EXT --> TB["steps_bench / steps_select"]
    SB --> PAR["sleep/params.py"]
  end
```

Boundaries that matter:

* `parkinsense/sleep/` imports nothing from `motion/` or `ppg/`; its only other dependency is `replay.load` (lazily, to parse
  capture formats). Nothing outside the dashboard imports `sleep/`. Sleep reads a recording after the fact, so it cannot change a
  tremor or cardiovascular value.
* Only the step *selector* touched the runtime: `RuntimeEngine(step_counter=...)` and three metadata keys. The default
  path, the 79-column capture schema and every pre-existing test are unchanged.
* Versions are independent: sleep algorithm / epoch schema, step algorithm, pipeline, firmware, capture schema, protocol.
