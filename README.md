# Five-Stage Processor Pipeline Simulator (No Forwarding)

A cycle-accurate educational simulator for a classical 5-stage RISC processor pipeline written in Python. This simulator models instruction execution, data hazard detection (Read-After-Write / RAW), pipeline stalls, front-end backpressure, and performance metrics comparing pipelined vs. non-pipelined execution.

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
  - [Programmatic API](#programmatic-api)
- [Detailed Example & Output Walkthrough](#detailed-example--output-walkthrough)
- [Code Structure](#code-structure)
- [License](#license)

---

## Overview

In modern computer architecture, pipelining overlaps the execution of multiple instructions to increase throughput. However, data dependencies between instructions can introduce **data hazards** when an instruction depends on the result of an earlier instruction that has not yet completed.

This simulator models a **no-forwarding (stall-on-hazard)** 5-stage pipeline where dependent instructions must wait in the Decode stage (`ID`) until the producing instruction writes its result back to the register file (`WB`).

### Key Features

- **5-Stage Pipeline Execution**: Accurately tracks stages: `IF`, `ID`, `EX`, `MEM`, and `WB`.
- **Accurate Hazard & Stall Modeling**:
  - Automatically identifies Read-After-Write (RAW) data dependencies.
  - Inserts `STALL` cycles in the `ID` stage until the producer finishes `WB`.
  - Holds subsequent fetched instructions in the front end (`IF*`) when `ID` is blocked.
- **Split-Phase Register File**: Register writes occurring in `WB` are immediately visible to instructions in `ID` in the same clock cycle (write-before-read).
- **Flexible Input Parsing**: Accepts uppercase or lowercase instructions, optional commas, decimal or hexadecimal numbers (`0x...`), and space-delimited assignments.
- **Cycle-by-Cycle Visual Timeline**: Displays an ASCII table of instructions across all clock cycles.
- **Performance Evaluation**: Computes pipelined cycle count, theoretical non-pipelined cycle count, and speedup ratio ($S = \text{Cycles}_{\text{non-pipelined}} / \text{Cycles}_{\text{pipelined}}$).
- **Zero External Dependencies**: Implemented entirely with standard Python libraries.

---

## Pipeline Architecture

### Pipeline Stages

| Stage | Name | Description |
|:---:|:---|:---|
| **`IF`** | **Instruction Fetch** | Fetches the instruction into the pipeline. |
| **`IF*`** | **Fetch Held** | Instruction remains held in the fetch buffer because the decode stage (`ID`) is stalled or busy. |
| **`ID`** | **Instruction Decode & Register Read** | Decodes the instruction opcode and reads source registers. Resolves dependencies. |
| **`STALL`** | **Pipeline Bubble** | The instruction waits in decode until dependent source registers are written back by prior instructions. |
| **`EX`** | **Execute / Address Calculation** | Executes arithmetic/logical operations (`ADD`, `SUB`) or computes effective addresses. |
| **`MEM`** | **Memory Access** | Accesses data memory for `LOAD` (read) or `STORE` (write). |
| **`WB`** | **Write Back** | Writes results (from ALU or memory) back to the destination register. |

### Hardware Specifications

- **Registers**: 8 general-purpose registers: `R0` through `R7`. All registers default to `0` unless initialized.
- **Memory**: Byte- or word-addressable integer memory using non-negative integer or hex addresses (`0`, `4`, `100`, `0x64`). Uninitialized memory addresses read as `0`.
- **Word/Value Size**: Signed arbitrary-precision integers (Python standard integer model).

### Hazard Handling & Timing Rules

1. **No Forwarding / Bypassing**:
   Because there are no bypass datapaths from `EX` or `MEM` back to `EX`/`ID`, an instruction requiring a register value must wait until the producer completes its Write Back (`WB`) stage.
2. **Same-Cycle Write-Before-Read**:
   Register writes in `WB` take effect early enough in the clock cycle that an instruction stalled in `ID` can read the new register value and complete decode in that exact same cycle.
3. **Front-End Backpressure**:
   When an instruction $I_n$ stalls in `ID`, instruction $I_{n+1}$ cannot advance from `IF` into `ID`. It is held in the fetch buffer and marked as `IF*` on the timeline until `ID` is cleared.

---

## Instruction Set Architecture (ISA)

The simulator supports four fundamental RISC instructions:

| Instruction | Syntax Example | Semantics | Operands Read | Operands Written |
|:---|:---|:---|:---:|:---:|
| **`ADD`** | `ADD R1, R2, R3` | $R_1 \leftarrow R_2 + R_3$ | `R2`, `R3` | `R1` |
| **`SUB`** | `SUB R1, R2, R3` | $R_1 \leftarrow R_2 - R_3$ | `R2`, `R3` | `R1` |
| **`LOAD`** | `LOAD R1, 100` | $R_1 \leftarrow \text{Memory}[100]$ | None | `R1` |
| **`STORE`** | `STORE R1, 100` | $\text{Memory}[100] \leftarrow R_1$ | `R1` | None |

### Syntax & Parsing Rules

- **Case-Insensitive**: `add r1, r2, r3` is equivalent to `ADD R1, R2, R3`.
- **Delimiters**: Commas and spaces are interchangeable (e.g., `ADD R1 R2 R3` or `ADD R1, R2, R3`).
- **Numbers**: Values and memory addresses can be specified in decimal (e.g., `100`, `-5`) or hexadecimal (e.g., `0x64`, `0x10`).

---

## Installation & Requirements

- **Python**: Version **3.9** or newer (utilizes dataclasses and modern type annotations).
- **Dependencies**: None (pure standard library).

Clone or copy the project files to your local environment:

```bash
git clone <repository-url>
cd CA
```

Verify your Python version:

```bash
python --version
```

---

## Usage

### Interactive Command-Line Interface

Run the script directly from your terminal:

```bash
python pipeline_simulator.py
```

The interactive prompt guides you through three steps:

1. **Initial Register Values**: Assign starting values to registers (comma- or space-separated). Press **Enter** to skip and leave all registers at `0`.
   ```text
   Enter register values (e.g. R1=12, R2=8)> R1=10, R2=20
   ```
2. **Initial Memory Values**: Assign starting values to memory locations. Press **Enter** to skip.
   ```text
   Enter initial memory (e.g. 100=25)> 100=42, 104=99
   ```
3. **Program Instructions**: Enter instructions one line at a time. When finished, enter `DONE`.
   ```text
   I01> LOAD R3, 100
   I02> ADD R4, R3, R1
   I03> STORE R4, 200
   I04> DONE
   ```

---

### Programmatic API

You can import `pipeline_simulator` as a module in Python scripts or unit tests:

```python
from pipeline_simulator import Instruction, parse_instruction, simulate, print_report

# 1. Define instructions either with parse_instruction or Instruction dataclass
program = [
    parse_instruction("LOAD R1, 100"),
    parse_instruction("ADD R2, R1, R0"),
    parse_instruction("ADD R3, R0, R0"),
]

# 2. Run simulation with optional initial registers and memory
result = simulate(
    instructions=program,
    initial_registers={"R0": 0},
    initial_memory={100: 42},
)

# 3. Print the formatted human-readable report
print_report(program, result)

# 4. Or inspect the result fields directly
print(f"Total cycles: {result.pipeline_cycles}")
print(f"Calculated speedup: {result.speedup:.2f}x")
print(f"R2 value: {result.registers['R2']}")
```

---

## Detailed Example & Output Walkthrough

Consider the following program with a data dependency on `R1`:

```assembly
LOAD R1, 100     ; I1: Loads value 42 from memory[100] into R1 (WB occurs at cycle 5)
ADD R2, R1, R0   ; I2: Reads R1 (RAW hazard with I1; must wait for cycle 5 WB)
ADD R3, R0, R0   ; I3: Independent instruction (held in IF while I2 stalls decode)
```

### Execution Output

```text
========================================================================
SIMULATION RESULTS
========================================================================

PIPELINE TIMELINE
IF* = fetch held    STALL = instruction waiting in decode
Instruction                   1      2      3      4      5      6      7      8      9
LOAD R1, 100                 IF     ID     EX    MEM     WB                            
ADD R2, R1, R0                      IF  STALL  STALL     ID     EX    MEM     WB       
ADD R3, R0, R0                             IF    IF*    IF*     ID     EX    MEM     WB

DATA HAZARDS
  I2 reads R1 from I1: 2 stall cycle(s); producer writes back in cycle 5.

CYCLE SUMMARY
  Pipelined:        9 cycles
  Non-pipelined:    15 cycles
  Speedup:          1.67x

FINAL REGISTERS
  R0=0    R1=42    R2=42    R3=0
  R4=0    R5=0    R6=0    R7=0

FINAL MEMORY
  [100] = 42
========================================================================
```

### Timeline Breakdown

- **Cycle 1**: `I1` enters `IF`.
- **Cycle 2**: `I1` advances to `ID`; `I2` enters `IF`.
- **Cycle 3**:
  - `I1` moves to `EX`.
  - `I2` enters `ID`, detects that it needs `R1` (which `I1` writes in `WB` at cycle 5). `I2` stalls (`STALL`).
  - `I3` enters `IF`.
- **Cycle 4**:
  - `I1` moves to `MEM`.
  - `I2` continues to wait in `ID` (`STALL`).
  - `I3` cannot advance to `ID` because `I2` is stalling in `ID`. It is held in fetch (`IF*`).
- **Cycle 5**:
  - `I1` enters `WB` and writes `R1 = 42`.
  - In the same cycle, `I2` reads the updated `R1` and completes `ID`.
  - `I3` remains held in fetch (`IF*`).
- **Cycle 6**:
  - `I2` advances to `EX`.
  - `I3` is now free to advance into `ID`.
- **Cycles 7–9**: Remaining pipeline stages complete without further stalls.

---

## Code Structure

`pipeline_simulator.py` is organized into clean, functional components:

| Component | Purpose |
|:---|:---|
| **`Instruction`** | Frozen dataclass representing an instruction, its operands, and helper properties (`reads`, `writes`). |
| **`Hazard`** | Frozen dataclass capturing detected RAW hazards, consumer/producer instruction indices, register, producer WB cycle, and stall counts. |
| **`SimulationResult`** | Dataclass storing final register and memory maps, cycle-by-cycle timeline rows, detected hazards, and speedup metrics. |
| **Parsers** | `parse_instruction`, `parse_initial_registers`, and `parse_initial_memory` validate and sanitize input strings into strongly-typed structures. |
| **`simulate`** | Core scheduling algorithm. Computes cycle timing for front-end decode and writeback, tracks hazards, and executes instructions in program order. |
| **`print_report`** | Formats and prints the pipeline timeline, hazard list, cycle metrics, and register/memory dump to stdout. |
| **`main`** | Interactive CLI loop handling user prompts, error recovery, and execution reporting. |

---

## License

This project is open-source and intended for educational and computer architecture study purposes.
