"""A small five-stage processor pipeline simulator."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from decimal import Decimal, localcontext
import math
from typing import Iterable


REGISTER_COUNT = 8
STAGES = ("IF", "ID", "EX", "MEM", "WB")
DEFAULT_CLOCK_PERIOD_SECONDS = 1e-9


@dataclass(frozen=True)
class Instruction:
    opcode: str
    destination: str | None = None
    source: str | None = None
    left: str | None = None
    right: str | None = None
    address: int | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.opcode, str):
            raise ValueError("Instruction opcode must be a string.")
        opcode = self.opcode.upper()
        if opcode not in ("ADD", "SUB", "LOAD", "STORE"):
            raise ValueError(f"Unknown instruction {self.opcode!r}.")
        object.__setattr__(self, "opcode", opcode)

        register_fields = {
            "ADD": ("destination", "left", "right"),
            "SUB": ("destination", "left", "right"),
            "LOAD": ("destination",),
            "STORE": ("source",),
        }[opcode]
        for field_name in ("destination", "source", "left", "right"):
            register = getattr(self, field_name)
            if field_name not in register_fields:
                if register is not None:
                    raise ValueError(f"{opcode} does not accept {field_name}.")
                continue
            if not isinstance(register, str):
                raise ValueError(f"{opcode} requires a register for {field_name}.")
            object.__setattr__(self, field_name, _validate_register(register))

        if opcode in ("LOAD", "STORE"):
            if isinstance(self.address, bool) or not isinstance(self.address, int):
                raise ValueError(f"{opcode} requires a non-negative integer address.")
            if self.address < 0:
                raise ValueError("Memory addresses must be non-negative.")
        elif self.address is not None:
            raise ValueError(f"{opcode} does not accept a memory address.")

    def __str__(self) -> str:
        if self.opcode in ("ADD", "SUB"):
            return f"{self.opcode} {self.destination}, {self.left}, {self.right}"
        assert self.address is not None
        if self.opcode == "LOAD":
            return f"LOAD {self.destination}, {_format_integer(self.address)}"
        return f"STORE {self.source}, {_format_integer(self.address)}"

    @property
    def reads(self) -> tuple[str, ...]:
        if self.opcode in ("ADD", "SUB"):
            assert self.left is not None and self.right is not None
            return (self.left, self.right)
        if self.opcode == "STORE":
            assert self.source is not None
            return (self.source,)
        return ()

    @property
    def writes(self) -> str | None:
        return self.destination


@dataclass(frozen=True)
class Hazard:
    instruction_index: int
    producer_index: int
    register: str
    producer_wb_cycle: int
    wait_cycles: int

    @property
    def stalls(self) -> int:
        """Return the operand's wait, retained for compatibility with callers."""
        return self.wait_cycles


@dataclass
class SimulationResult:
    registers: dict[str, int]
    memory: dict[int, int]
    timeline: list[dict[int, str]]
    hazards: list[Hazard]
    data_hazard_stall_cycles: int
    clock_period_seconds: float
    pipeline_cycles: int
    non_pipeline_cycles: int
    forwarding: bool = False

    @property
    def speedup(self) -> float | None:
        if self.pipeline_cycles == 0:
            return None
        return self.non_pipeline_cycles / self.pipeline_cycles


def _format_duration(cycles: int, clock_period_seconds: float) -> str:
    duration = cycles * clock_period_seconds
    if math.isfinite(duration):
        return f"{duration:.3e}"
    with localcontext() as context:
        context.prec = 28
        return f"{Decimal.from_float(clock_period_seconds) * cycles:.3e}"


def _format_integer(value: int) -> str:
    try:
        return str(value)
    except ValueError:
        return hex(value)


def _validate_register(token: str) -> str:
    if not isinstance(token, str):
        raise ValueError("Register name must be a string.")
    register = token.upper()
    valid = {f"R{index}" for index in range(REGISTER_COUNT)}
    if register not in valid:
        raise ValueError(f"Invalid register {token!r}; use R0 through R7.")
    return register


def _parse_address(token: str) -> int:
    try:
        base = 0 if token.lower().startswith(("0x", "+0x", "-0x")) else 10
        address = int(token, base)
    except ValueError as error:
        raise ValueError(f"Invalid memory address {token!r}; use a non-negative integer.") from error
    if address < 0:
        raise ValueError("Memory addresses must be non-negative.")
    return address


def _parse_integer(token: str) -> int:
    try:
        base = 0 if token.lower().lstrip("+-").startswith("0x") else 10
        return int(token, base)
    except ValueError as error:
        raise ValueError(f"Invalid integer value {token!r}.") from error


def parse_clock_period(line: str) -> float:
    """Parse a positive clock period in nanoseconds and return seconds."""
    try:
        period_ns = float(line) if line else DEFAULT_CLOCK_PERIOD_SECONDS * 1e9
    except ValueError as error:
        raise ValueError("Clock period must be a positive number of nanoseconds.") from error
    if not math.isfinite(period_ns) or period_ns <= 0:
        raise ValueError("Clock period must be a positive finite number of nanoseconds.")
    period_seconds = period_ns * 1e-9
    if period_seconds == 0:
        raise ValueError("Clock period is too small to represent in seconds.")
    return period_seconds


def parse_initial_registers(line: str) -> dict[str, int]:
    """Parse comma- or space-separated initial values such as R1=10, R2=-3."""
    initial_registers: dict[str, int] = {}
    for assignment in line.replace(",", " ").split():
        parts = assignment.split("=", 1)
        if len(parts) != 2:
            raise ValueError(f"Expected REGISTER=VALUE, got {assignment!r}.")
        register = _validate_register(parts[0])
        initial_registers[register] = _parse_integer(parts[1])
    return initial_registers


def parse_initial_memory(line: str) -> dict[int, int]:
    """Parse comma- or space-separated memory values such as 100=25, 104=-1."""
    initial_memory: dict[int, int] = {}
    for assignment in line.replace(",", " ").split():
        parts = assignment.split("=", 1)
        if len(parts) != 2:
            raise ValueError(f"Expected ADDRESS=VALUE, got {assignment!r}.")
        address = _parse_address(parts[0])
        initial_memory[address] = _parse_integer(parts[1])
    return initial_memory


def parse_instruction(line: str) -> Instruction:
    """Parse one instruction, accepting optional commas and mixed case."""
    parts = line.replace(",", " ").split()
    if not parts:
        raise ValueError("Enter an instruction.")

    opcode = parts[0].upper()
    expected = {"ADD": 4, "SUB": 4, "LOAD": 3, "STORE": 3}
    if opcode not in expected:
        raise ValueError(f"Unknown instruction {parts[0]!r}; use ADD, SUB, LOAD, or STORE.")
    if len(parts) != expected[opcode]:
        raise ValueError(f"{opcode} expects {expected[opcode] - 1} operand(s).")

    if opcode in ("ADD", "SUB"):
        return Instruction(
            opcode=opcode,
            destination=_validate_register(parts[1]),
            left=_validate_register(parts[2]),
            right=_validate_register(parts[3]),
        )
    if opcode == "LOAD":
        return Instruction(
            opcode=opcode,
            destination=_validate_register(parts[1]),
            address=_parse_address(parts[2]),
        )
    return Instruction(
        opcode=opcode,
        source=_validate_register(parts[1]),
        address=_parse_address(parts[2]),
    )


def simulate(
    instructions: Iterable[Instruction],
    initial_registers: dict[str, int] | None = None,
    initial_memory: dict[int, int] | None = None,
    clock_period_seconds: float = DEFAULT_CLOCK_PERIOD_SECONDS,
    *,
    forwarding: bool = False,
) -> SimulationResult:
    """Schedule and execute the five pipeline stages for each instruction.

    Register writes in WB are visible to ID in the same cycle. With forwarding,
    arithmetic and load results can be passed to EX in the following cycle.
    An immediately preceding load can also forward store data to MEM.
    """
    program = list(instructions)
    if any(not isinstance(instruction, Instruction) for instruction in program):
        raise TypeError("instructions must contain only Instruction objects.")
    if isinstance(clock_period_seconds, bool) or not isinstance(
        clock_period_seconds, (int, float)
    ):
        raise ValueError("clock_period_seconds must be a positive finite number.")
    try:
        clock_period_seconds = float(clock_period_seconds)
    except OverflowError as error:
        raise ValueError(
            "clock_period_seconds must be a positive finite number."
        ) from error
    if not math.isfinite(clock_period_seconds) or clock_period_seconds <= 0:
        raise ValueError("clock_period_seconds must be a positive finite number.")
    if not isinstance(forwarding, bool):
        raise TypeError("forwarding must be a boolean.")

    registers = {f"R{index}": 0 for index in range(REGISTER_COUNT)}
    if initial_registers is not None:
        if not isinstance(initial_registers, dict):
            raise TypeError("initial_registers must be a dict.")
        for name, value in initial_registers.items():
            if isinstance(value, bool) or not isinstance(value, int):
                raise ValueError(
                    f"Initial value for register {name!r} must be an integer."
                )
            registers[_validate_register(name)] = value
    if initial_memory is not None and not isinstance(initial_memory, dict):
        raise TypeError("initial_memory must be a dict.")
    memory = dict(initial_memory) if initial_memory is not None else {}
    for address, value in memory.items():
        if isinstance(address, bool) or not isinstance(address, int):
            raise ValueError("Memory addresses must be integers.")
        if address < 0:
            raise ValueError("Memory addresses must be non-negative.")
        if isinstance(value, bool) or not isinstance(value, int):
            raise ValueError(
                f"Initial value at memory address {_format_integer(address)} must be an integer."
            )

    # Schedule decode entry/completion while modeling a front end held by stalls.
    id_entry_cycles: list[int] = []
    id_cycles: list[int] = []
    wb_cycles: list[int] = []
    dependencies: list[dict[str, int]] = []
    timeline: list[dict[int, str]] = [dict() for _ in program]
    hazards: list[Hazard] = []
    latest_writers: dict[str, int] = {}
    data_hazard_stall_cycles = 0

    for index, instruction in enumerate(program):
        fetch_cycle = 1 if index == 0 else id_entry_cycles[index - 1]
        earliest_id = fetch_cycle + 1
        id_entry = earliest_id if index == 0 else max(
            earliest_id, id_cycles[index - 1] + 1
        )

        latest_ready_id = id_entry
        producers: list[tuple[int, str, int, int]] = []
        instruction_dependencies: dict[str, int] = {}
        for register in dict.fromkeys(instruction.reads):
            producer_index = latest_writers.get(register)
            if producer_index is None:
                continue
            producer_wb = wb_cycles[producer_index]
            if forwarding:
                ready_id = id_cycles[producer_index] + (
                    2 if (
                        program[producer_index].opcode == "LOAD"
                        and instruction.opcode != "STORE"
                    ) else 1
                )
            else:
                ready_id = producer_wb
            producers.append((producer_index, register, producer_wb, ready_id))
            instruction_dependencies[register] = producer_index
            latest_ready_id = max(latest_ready_id, ready_id)

        id_cycle = latest_ready_id
        stall_count = id_cycle - id_entry
        data_hazard_stall_cycles += stall_count
        for producer_index, register, producer_wb, ready_id in producers:
            hazards.append(
                Hazard(
                    index,
                    producer_index,
                    register,
                    producer_wb,
                    max(0, ready_id - id_entry),
                )
            )

        dependencies.append(instruction_dependencies)
        id_entry_cycles.append(id_entry)
        id_cycles.append(id_cycle)
        wb_cycles.append(id_cycle + 3)
        if instruction.writes is not None:
            latest_writers[instruction.writes] = index

        row = timeline[index]
        row[fetch_cycle] = "IF"
        for cycle in range(fetch_cycle + 1, id_entry):
            row[cycle] = "IF*"
        for cycle in range(id_entry, id_cycle):
            row[cycle] = "STALL"
        for offset, stage in enumerate(STAGES[1:]):
            row[id_cycle + offset] = stage

    pipeline_cycles = wb_cycles[-1] if wb_cycles else 0
    operands: list[dict[str, int]] = [{} for _ in program]
    results: list[int | None] = [None for _ in program]
    events: list[list[tuple[int, str]]] = [[] for _ in range(pipeline_cycles + 1)]
    for index, row in enumerate(timeline):
        for cycle, stage in row.items():
            if stage in ("ID", "EX", "MEM", "WB"):
                events[cycle].append((index, stage))
    for cycle, cycle_events in enumerate(events):
        for index, stage in cycle_events:
            instruction = program[index]
            if stage == "WB" and instruction.opcode in ("ADD", "SUB", "LOAD"):
                assert instruction.destination is not None
                result = results[index]
                assert result is not None
                registers[instruction.destination] = result
            elif stage == "MEM":
                if instruction.opcode == "LOAD":
                    assert instruction.address is not None
                    results[index] = memory.get(instruction.address, 0)
                elif instruction.opcode == "STORE":
                    assert instruction.address is not None
                    assert instruction.source is not None
                    producer_index = dependencies[index].get(instruction.source)
                    if (
                        forwarding
                        and producer_index is not None
                        and program[producer_index].opcode == "LOAD"
                        and wb_cycles[producer_index] == cycle
                    ):
                        forwarded_result = results[producer_index]
                        assert forwarded_result is not None
                        operands[index][instruction.source] = forwarded_result
                    memory[instruction.address] = operands[index][instruction.source]
            elif stage == "EX":
                if forwarding:
                    for register, producer_index in dependencies[index].items():
                        load_for_store_in_mem = (
                            instruction.opcode == "STORE"
                            and program[producer_index].opcode == "LOAD"
                            and wb_cycles[producer_index] == cycle + 1
                        )
                        if (
                            wb_cycles[producer_index] > id_cycles[index]
                            and not load_for_store_in_mem
                        ):
                            forwarded_result = results[producer_index]
                            assert forwarded_result is not None
                            operands[index][register] = forwarded_result
                if instruction.opcode == "ADD":
                    assert instruction.left is not None and instruction.right is not None
                    results[index] = (
                        operands[index][instruction.left]
                        + operands[index][instruction.right]
                    )
                elif instruction.opcode == "SUB":
                    assert instruction.left is not None and instruction.right is not None
                    results[index] = (
                        operands[index][instruction.left]
                        - operands[index][instruction.right]
                    )
            elif stage == "ID":
                operands[index] = {
                    register: registers[register] for register in instruction.reads
                }

    return SimulationResult(
        registers=registers,
        memory=memory,
        timeline=timeline,
        hazards=hazards,
        data_hazard_stall_cycles=data_hazard_stall_cycles,
        clock_period_seconds=clock_period_seconds,
        pipeline_cycles=pipeline_cycles,
        non_pipeline_cycles=len(program) * len(STAGES),
        forwarding=forwarding,
    )


def print_report(
    instructions: list[Instruction],
    result: SimulationResult,
    *,
    summary: bool = False,
) -> None:
    print("\n" + "=" * 72)
    mode = "WITH FORWARDING" if result.forwarding else "WITHOUT FORWARDING"
    print(f"SIMULATION RESULTS - {mode}")
    print("=" * 72)

    if not instructions:
        print("\nNo instructions were entered.")
    elif not summary:
        print("\nPIPELINE TIMELINE")
        print("IF* = fetch held    STALL = instruction waiting in decode")
        last_cycle = result.pipeline_cycles
        instruction_width = max(24, max(len(str(instruction)) for instruction in instructions) + 2)
        print(f"{'Instruction':<{instruction_width}}" + "".join(
            f"{cycle:>7}" for cycle in range(1, last_cycle + 1)
        ))
        for instruction, row in zip(instructions, result.timeline):
            cells = "".join(
                f"{row.get(cycle, ''):>7}" for cycle in range(1, last_cycle + 1)
            )
            print(f"{str(instruction):<{instruction_width}}{cells}")

        print("\nDATA DEPENDENCIES AND STALLS")
        if not result.hazards:
            print("  No data dependencies between instructions.")
        else:
            print("  A dependency may require no stall if its value is available in time.")
            for hazard in result.hazards:
                print(
                    f"  I{hazard.instruction_index + 1} reads {hazard.register} "
                    f"from I{hazard.producer_index + 1}: "
                    f"operand wait {hazard.wait_cycles} cycle(s) "
                    f"({_format_duration(hazard.wait_cycles, result.clock_period_seconds)} s); "
                    f"producer writes back in cycle {hazard.producer_wb_cycle}."
                )
            print(
                "  Total pipeline time spent stalled on data hazards: "
                f"{result.data_hazard_stall_cycles} cycle(s) "
                f"({_format_duration(result.data_hazard_stall_cycles, result.clock_period_seconds)} s)."
            )
            print(
                "  The required data dependency cannot be removed without "
                "changing program behavior. Its stall delay can be reduced "
                "with forwarding or safe instruction scheduling."
            )
    else:
        print("\nDATA DEPENDENCY SUMMARY")
        print(f"  Dependencies:     {len(result.hazards)}")
        print(f"  Stall cycles:     {result.data_hazard_stall_cycles}")
        print(
            "  Stall time:       "
            f"{_format_duration(result.data_hazard_stall_cycles, result.clock_period_seconds)} s"
        )

    print("\nCYCLE SUMMARY")
    print(f"  Clock period:     {result.clock_period_seconds:.3e} s/cycle")
    print(f"  Pipelined:        {result.pipeline_cycles} cycles")
    print(f"  Sequential base:  {result.non_pipeline_cycles} cycles")
    speedup = result.speedup
    if speedup is not None:
        print(f"  Speedup:          {speedup:.2f}x")
    else:
        print("  Speedup:          N/A")

    print("\nFINAL REGISTERS")
    register_names = list(result.registers)
    for start in range(0, len(register_names), 4):
        names = register_names[start : start + 4]
        print("  " + "    ".join(
            f"{name}={_format_integer(result.registers[name])}" for name in names
        ))

    print("\nFINAL MEMORY")
    if result.memory:
        for address, value in sorted(result.memory.items()):
            print(f"  [{_format_integer(address)}] = {_format_integer(value)}")
    else:
        print("  (empty)")
    print("=" * 72)


def print_comparison(without: SimulationResult, with_forwarding: SimulationResult) -> None:
    print("\nFORWARDING COMPARISON")
    print(f"  {'Metric':<25}{'Without':>15}{'With':>15}")
    print(
        f"  {'Total cycles':<25}{without.pipeline_cycles:>15}"
        f"{with_forwarding.pipeline_cycles:>15}"
    )
    print(
        f"  {'Hazard stall cycles':<25}{without.data_hazard_stall_cycles:>15}"
        f"{with_forwarding.data_hazard_stall_cycles:>15}"
    )
    print(
        f"  {'Hazard stall time (s)':<25}"
        f"{_format_duration(without.data_hazard_stall_cycles, without.clock_period_seconds):>15}"
        f"{_format_duration(with_forwarding.data_hazard_stall_cycles, with_forwarding.clock_period_seconds):>15}"
    )
    saved = without.pipeline_cycles - with_forwarding.pipeline_cycles
    print(f"  Cycles saved: {saved} ({_format_duration(saved, without.clock_period_seconds)} s)")
    if with_forwarding.pipeline_cycles:
        print(f"  Pipeline speedup: {without.pipeline_cycles / with_forwarding.pipeline_cycles:.2f}x")
    else:
        print("  Pipeline speedup: N/A")


def main(*, summary: bool = False) -> None:
    print("=" * 72)
    print("FIVE-STAGE PIPELINE SIMULATOR")
    print("=" * 72)
    print("Enter starting register and memory values. Press Enter to skip either.")

    while True:
        try:
            period_input = input("Enter clock period in nanoseconds [1.0]> ").strip()
        except EOFError:
            period_input = ""
        try:
            clock_period_seconds = parse_clock_period(period_input)
        except ValueError as error:
            print(f"Input error: {error}")
            continue
        break

    initial_registers: dict[str, int] = {}
    initial_memory: dict[int, int] = {}
    for prompt, parser, destination in (
        ("Enter register values (e.g. R1=12, R2=8)> ", parse_initial_registers, initial_registers),
        ("Enter initial memory (e.g. 100=25)> ", parse_initial_memory, initial_memory),
    ):
        while True:
            try:
                values = parser(input(prompt).strip())
            except EOFError:
                values = {}
                break
            except ValueError as error:
                print(f"Input error: {error}")
                continue
            destination.update(values)
            break

    print("\nPROGRAM INPUT")
    print("Enter one instruction per line: ADD, SUB, LOAD, or STORE.")
    print("Type DONE when the program is complete.")
    instructions: list[Instruction] = []
    while True:
        try:
            line = input(f"I{len(instructions) + 1:02d}> ").strip()
        except EOFError:
            break
        if line.upper() == "DONE":
            break
        if not line:
            continue
        try:
            instructions.append(parse_instruction(line))
        except ValueError as error:
            print(f"Input error: {error}")
    without_forwarding = simulate(
        instructions,
        initial_registers,
        initial_memory,
        clock_period_seconds,
    )
    with_forwarding = simulate(
        instructions,
        initial_registers,
        initial_memory,
        clock_period_seconds,
        forwarding=True,
    )
    if (without_forwarding.registers != with_forwarding.registers
            or without_forwarding.memory != with_forwarding.memory):
        raise RuntimeError("Forwarding and no-forwarding results do not match.")
    print_report(instructions, without_forwarding, summary=summary)
    print_report(instructions, with_forwarding, summary=summary)
    print_comparison(without_forwarding, with_forwarding)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--summary", action="store_true",
        help="omit the full timeline and individual dependency details",
    )
    args = parser.parse_args()
    main(summary=args.summary)