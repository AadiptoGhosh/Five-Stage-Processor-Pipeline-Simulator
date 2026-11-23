# Five-Stage Processor Pipeline Simulator

A cycle-accurate educational simulator for a classical 5-stage RISC processor pipeline written in Python. The simulator models instruction execution, Read-After-Write (RAW) data hazard detection, pipeline stalls, front-end backpressure, **data forwarding (bypassing)**, and performance metrics — comparing pipelined vs. non-pipelined execution **both with and without forwarding** in a single run.

---

## Table of Contents

- [Overview](#overview)
- [Pipeline Architecture](#pipeline-architecture)
  - [Pipeline Stages](#pipeline-stages)
  - [Hardware Specifications](#hardware-specifications)
  - [Hazard Handling & Timing Rules](#hazard-handling--timing-rules)
- [Instruction Set Architecture (ISA)](#instruction-set-architecture-isa)
- [Installation & Requirements](#installation--requirements)
- [Usage](#usage)
  - [Interactive Command-Line Interface](#interactive-command-line-interface)
  - [Summary Mode](#summary-mode)
  - [Programmatic API](#programmatic-api)
- [Detailed Example & Output Walkthrough](#detailed-example--output-walkthrough)
  - [Without Forwarding](#without-forwarding)
  - [With Forwarding](#with-forwarding)
  - [Forwarding Comparison](#forwarding-comparison)
- [Summary Mode Example](#summary-mode-example)
- [Code Structure](#code-structure)
- [License](#license)

---

## Overview

In modern computer architecture, pipelining overlaps the execution of multiple instructions to increase throughput. However, data dependencies between instructions introduce **data hazards** when an instruction depends on the result of an earlier one that has not yet completed.

This simulator models a full **5-stage pipeline** in two modes side-by-side:

| Mode | Description |
|:---|:---|
| **Without Forwarding** | Dependent instructions stall in `ID` until the producer completes `WB`. |
| **With Forwarding** | Bypass datapaths forward results from `EX`/`MEM`/`WB` to `EX`, reducing stalls. |

Both simulations run on the same program, then a **Forwarding Comparison** table summarises the cycles and stall time saved.

### Key Features

- **5-Stage Pipeline Execution**: Accurately tracks `IF`, `ID`, `EX`, `MEM`, and `WB`.
- **Dual-Mode Simulation**: Runs both no-forwarding and forwarding simulations and verifies they produce identical final register and memory state.
- **Accurate Hazard & Stall Modeling**:
  - Automatically identifies RAW data dependencies.
  - Inserts `STALL` cycles in `ID` until the operand is ready.
  - Holds subsequent instructions in `IF*` (fetch-held) when `ID` is blocked.
- **Data Forwarding / Bypassing**:
  - ALU-to-ALU: result forwarded from EX of the producer to EX of the consumer (1-cycle stall instead of 3).
  - Load-use: LOAD result forwarded from MEM to EX of the next non-STORE consumer (1-cycle stall instead of 2).
  - Load-to-store: LOAD result forwarded to MEM of an immediately following STORE (no stall needed).
- **Split-Phase Register File**: Writes in `WB` are visible to `ID` in the same cycle (write-before-read).
- **Flexible Input Parsing**: Case-insensitive opcodes, optional commas, decimal or hex numbers/addresses.
- **Cycle-by-Cycle Visual Timeline**: ASCII table showing every instruction across all clock cycles.
- **`--summary` Flag**: Omit the full timeline and per-hazard details; show only aggregate dependency and cycle counts.
- **Performance Evaluation**: Pipelined cycles, sequential-equivalent cycles, speedup ratio, and forwarding comparison table.
- **Zero External Dependencies**: Pure Python standard library.

---

## Pipeline Architecture

### Pipeline Stages

| Stage | Name | Description |
|:---:|:---|:---|
| **`IF`** | **Instruction Fetch** | Fetches the instruction into the pipeline. |
| **`IF*`** | **Fetch Held** | Instruction held in the fetch buffer because `ID` is stalled or busy. |
| **`ID`** | **Instruction Decode & Register Read** | Decodes the opcode, reads source registers, detects and resolves dependencies. |
| **`STALL`** | **Pipeline Bubble** | Instruction waits in decode until the required source register is ready. |
| **`EX`** | **Execute / Address Calculation** | Executes ALU ops (`ADD`, `SUB`) or computes effective addresses. |
| **`MEM`** | **Memory Access** | Reads data memory (`LOAD`) or writes data memory (`STORE`). |
| **`WB`** | **Write Back** | Writes ALU or memory results back to the destination register. |

### Hardware Specifications

- **Registers**: 8 general-purpose registers `R0`–`R7`. All default to `0` unless initialised.
- **Memory**: Integer memory with non-negative decimal (`100`, `0`) or hex (`0x64`) addresses. Uninitialised locations read as `0`.
- **Word/Value Size**: Signed arbitrary-precision integers (Python's standard `int`).
- **Clock Period**: Configurable in nanoseconds; defaults to `1.0 ns`.

### Hazard Handling & Timing Rules

#### Without Forwarding
- A dependent instruction must wait in `ID` until the producer completes `WB` (3 cycles after the producer's `ID`).
- Same-cycle write-before-read: an instruction in `ID` can read a register being written in `WB` in that same cycle, so it completes `ID` without an extra stall.

#### With Forwarding
- **ALU → ALU**: result forwarded from the producer's `EX` to the consumer's `EX` — the consumer stalls 1 cycle in `ID` (instead of 3).
- **LOAD → non-STORE consumer** (load-use hazard): result forwarded from `MEM` to `EX` — the consumer stalls 1 cycle in `ID`.
- **LOAD → STORE** (immediately following): value forwarded in the `MEM` stage — no stall required.

#### Front-End Backpressure
When instruction $I_n$ stalls in `ID`, instruction $I_{n+1}$ cannot advance from `IF` to `ID`. It is held in the fetch buffer and shown as `IF*` on the timeline until `ID` is cleared.

---

## Instruction Set Architecture (ISA)

| Instruction | Syntax Example | Semantics | Reads | Writes |
|:---|:---|:---|:---:|:---:|
| **`ADD`** | `ADD R1, R2, R3` | $R_1 \leftarrow R_2 + R_3$ | `R2`, `R3` | `R1` |
| **`SUB`** | `SUB R1, R2, R3` | $R_1 \leftarrow R_2 - R_3$ | `R2`, `R3` | `R1` |
| **`LOAD`** | `LOAD R1, 100` | $R_1 \leftarrow \text{Memory}[100]$ | — | `R1` |
| **`STORE`** | `STORE R1, 100` | $\text{Memory}[100] \leftarrow R_1$ | `R1` | — |

### Syntax & Parsing Rules

- **Case-Insensitive**: `add r1, r2, r3` is equivalent to `ADD R1, R2, R3`.
- **Delimiters**: Commas and spaces are interchangeable (`ADD R1 R2 R3` or `ADD R1, R2, R3`).
- **Numbers**: Decimal (e.g., `100`, `-5`) or hexadecimal (e.g., `0x64`, `0x10`).

---

## Installation & Requirements

- **Python**: Version **3.9** or newer (uses dataclasses and modern type annotations).
- **Dependencies**: None — pure standard library.

```bash
git clone <repository-url>
cd CA
python --version   # must be 3.9+
```

---

## Usage

### Interactive Command-Line Interface

```bash
python pipeline_simulator.py
```

The interactive prompt guides you through four steps:

1. **Clock period** (optional — press **Enter** to use the default `1.0 ns`):
   ```text
   Enter clock period in nanoseconds [1.0]> 2.0
   ```
2. **Initial Register Values** (optional — press **Enter** to skip):
   ```text
   Enter register values (e.g. R1=12, R2=8)> R0=5
   ```
3. **Initial Memory Values** (optional — press **Enter** to skip):
   ```text
   Enter initial memory (e.g. 100=25)> 100=42
   ```
4. **Program Instructions** — one per line, type `DONE` when finished:
   ```text
   I01> LOAD R1, 100
   I02> ADD R2, R1, R0
   I03> ADD R3, R0, R0
   I04> DONE
   ```

The simulator then prints three sections:
- **SIMULATION RESULTS – WITHOUT FORWARDING** — full timeline, hazard details, cycle counts.
- **SIMULATION RESULTS – WITH FORWARDING** — same, with forwarding active.
- **FORWARDING COMPARISON** — side-by-side metrics table.

### Summary Mode

Pass `--summary` to suppress the per-instruction timeline and per-hazard details, showing only aggregate counts:

```bash
python pipeline_simulator.py --summary
```

---

### Programmatic API

```python
from pipeline_simulator import parse_instruction, simulate, print_report, print_comparison

program = [
    parse_instruction("LOAD R1, 100"),
    parse_instruction("ADD R2, R1, R0"),
    parse_instruction("ADD R3, R0, R0"),
]

initial_registers = {"R0": 0}
initial_memory    = {100: 42}

without_fwd = simulate(program, initial_registers, initial_memory, 1e-9)
with_fwd    = simulate(program, initial_registers, initial_memory, 1e-9, forwarding=True)

print_report(program, without_fwd)         # full timeline + hazard list
print_report(program, with_fwd)
print_comparison(without_fwd, with_fwd)   # side-by-side comparison table

# Or inspect fields directly
print(f"No-fwd cycles:  {without_fwd.pipeline_cycles}")
print(f"Fwd cycles:     {with_fwd.pipeline_cycles}")
print(f"Speedup (fwd):  {with_fwd.speedup:.2f}x")
print(f"R2 value:       {with_fwd.registers['R2']}")
```

---

## Detailed Example & Output Walkthrough

**Program** (3 instructions, `memory[100] = 42`, `R0 = 0`):

```assembly
LOAD R1, 100     ; I1: R1 ← memory[100] = 42  (WB at cycle 5)
ADD  R2, R1, R0  ; I2: R2 ← R1 + R0           (RAW hazard on R1 from I1)
ADD  R3, R0, R0  ; I3: R3 ← R0 + R0           (independent)
```

---

### Without Forwarding

```text
========================================================================
SIMULATION RESULTS - WITHOUT FORWARDING
========================================================================

PIPELINE TIMELINE
IF* = fetch held    STALL = instruction waiting in decode
Instruction                   1      2      3      4      5      6      7      8      9
LOAD R1, 100                 IF     ID     EX    MEM     WB
ADD R2, R1, R0                      IF  STALL  STALL     ID     EX    MEM     WB
ADD R3, R0, R0                             IF    IF*    IF*     ID     EX    MEM     WB

DATA DEPENDENCIES AND STALLS
  A dependency may require no stall if its value is available in time.
  I2 reads R1 from I1: operand wait 2 cycle(s) (2.000e-09 s); producer writes back in cycle 5.
  Total pipeline time spent stalled on data hazards: 2 cycle(s) (2.000e-09 s).
  The required data dependency cannot be removed without changing program behavior. Its stall delay can be reduced with forwarding or safe instruction scheduling.

CYCLE SUMMARY
  Clock period:     1.000e-09 s/cycle
  Pipelined:        9 cycles
  Sequential base:  15 cycles
  Speedup:          1.67x

FINAL REGISTERS
  R0=0    R1=42    R2=42    R3=0
  R4=0    R5=0    R6=0    R7=0

FINAL MEMORY
  [100] = 42
========================================================================
```

#### Timeline Breakdown (No Forwarding)

| Cycle | I1 (LOAD R1,100) | I2 (ADD R2,R1,R0) | I3 (ADD R3,R0,R0) |
|:---:|:---:|:---:|:---:|
| 1 | IF | — | — |
| 2 | ID | IF | — |
| 3 | EX | STALL (waits for R1) | IF |
| 4 | MEM | STALL | IF* |
| 5 | **WB** (R1←42) | **ID** (reads R1=42) | IF* |
| 6 | — | EX | ID |
| 7 | — | MEM | EX |
| 8 | — | WB | MEM |
| 9 | — | — | WB |

- Cycles 3–4: I2 stalls in `ID` (R1 not yet available; I3 is held in `IF*`).
- Cycle 5: I1 writes R1 in `WB`; I2 reads it in the same cycle and completes `ID`.

---

### With Forwarding

```text
========================================================================
SIMULATION RESULTS - WITH FORWARDING
========================================================================

PIPELINE TIMELINE
IF* = fetch held    STALL = instruction waiting in decode
Instruction                   1      2      3      4      5      6      7      8
LOAD R1, 100                 IF     ID     EX    MEM     WB
ADD R2, R1, R0                      IF  STALL     ID     EX    MEM     WB
ADD R3, R0, R0                             IF    IF*     ID     EX    MEM     WB

DATA DEPENDENCIES AND STALLS
  A dependency may require no stall if its value is available in time.
  I2 reads R1 from I1: operand wait 1 cycle(s) (1.000e-09 s); producer writes back in cycle 5.
  Total pipeline time spent stalled on data hazards: 1 cycle(s) (1.000e-09 s).
  The required data dependency cannot be removed without changing program behavior. Its stall delay can be reduced with forwarding or safe instruction scheduling.

CYCLE SUMMARY
  Clock period:     1.000e-09 s/cycle
  Pipelined:        8 cycles
  Sequential base:  15 cycles
  Speedup:          1.88x

FINAL REGISTERS
  R0=0    R1=42    R2=42    R3=0
  R4=0    R5=0    R6=0    R7=0

FINAL MEMORY
  [100] = 42
========================================================================
```

> [!NOTE]
> With forwarding, the LOAD-use hazard still requires **1 stall** (the value is not available until the end of I1's `MEM` stage), but the 2nd stall cycle is eliminated. Total pipeline time drops from 9 → 8 cycles.

---

### Forwarding Comparison

```text
FORWARDING COMPARISON
  Metric                           Without           With
  Total cycles                           9              8
  Hazard stall cycles                    2              1
  Hazard stall time (s)          2.000e-09      1.000e-09
  Cycles saved: 1 (1.000e-09 s)
  Pipeline speedup: 1.12x
```

---

## Summary Mode Example

For a 4-instruction program with more dependencies (`--summary` flag):

```assembly
LOAD  R1, 100    ; I1
ADD   R2, R1, R0 ; I2  — RAW on R1
SUB   R3, R2, R1 ; I3  — RAW on R2 and R1
STORE R3, 200    ; I4  — RAW on R3
```

```bash
python pipeline_simulator.py --summary
# (R0=5, memory[100]=42)
```

**Without Forwarding:**
```text
========================================================================
SIMULATION RESULTS - WITHOUT FORWARDING
========================================================================

DATA DEPENDENCY SUMMARY
  Dependencies:     4
  Stall cycles:     6
  Stall time:       6.000e-09 s

CYCLE SUMMARY
  Clock period:     1.000e-09 s/cycle
  Pipelined:        14 cycles
  Sequential base:  20 cycles
  Speedup:          1.43x

FINAL REGISTERS
  R0=5    R1=42    R2=47    R3=5
  R4=0    R5=0    R6=0    R7=0

FINAL MEMORY
  [100] = 42
  [200] = 5
========================================================================
```

**With Forwarding:**
```text
========================================================================
SIMULATION RESULTS - WITH FORWARDING
========================================================================

DATA DEPENDENCY SUMMARY
  Dependencies:     4
  Stall cycles:     1
  Stall time:       1.000e-09 s

CYCLE SUMMARY
  Clock period:     1.000e-09 s/cycle
  Pipelined:        9 cycles
  Sequential base:  20 cycles
  Speedup:          2.22x

FINAL REGISTERS
  R0=5    R1=42    R2=47    R3=5
  R4=0    R5=0    R6=0    R7=0

FINAL MEMORY
  [100] = 42
  [200] = 5
========================================================================
```

**Forwarding Comparison:**
```text
FORWARDING COMPARISON
  Metric                           Without           With
  Total cycles                          14              9
  Hazard stall cycles                    6              1
  Hazard stall time (s)          6.000e-09      1.000e-09
  Cycles saved: 5 (5.000e-09 s)
  Pipeline speedup: 1.56x
```

---

## Code Structure

`pipeline_simulator.py` is organised into clean, functional components:

| Component | Purpose |
|:---|:---|
| **`Instruction`** | Frozen dataclass for an instruction, its operands, and `reads`/`writes` helper properties. |
| **`Hazard`** | Frozen dataclass capturing a detected RAW hazard: consumer/producer indices, register name, producer WB cycle, and stall count. |
| **`SimulationResult`** | Dataclass storing final register and memory maps, the cycle-by-cycle timeline, detected hazards, stall counts, cycle totals, and the forwarding flag. |
| **Parsers** | `parse_instruction`, `parse_initial_registers`, `parse_initial_memory`, `parse_clock_period` — validate and sanitise input strings into strongly-typed structures. |
| **`simulate`** | Core scheduling engine. Computes cycle timing for every pipeline stage, tracks hazards, applies forwarding logic, and executes instructions in program order to produce final register/memory state. |
| **`print_report`** | Formats and prints the pipeline timeline (or summary), hazard/stall details, cycle metrics, and register/memory dump. Accepts a `summary=True` flag to suppress verbose output. |
| **`print_comparison`** | Prints a side-by-side table comparing no-forwarding vs. forwarding simulation results. |
| **`main`** | Interactive CLI loop: prompts for clock period, initial state, and instructions; runs both simulations; prints both reports and the comparison. Supports `--summary` via argparse. |

---

## License

This project is open-source and intended for educational and computer architecture study purposes.
