"""A small five-stage, no-forwarding processor pipeline simulator."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable


REGISTER_COUNT = 8
STAGES = ("IF", "ID", "EX", "MEM", "WB")


@dataclass(frozen=True)
class Instruction:
    opcode: str
    destination: str | None = None
    source: str | None = None
    left: str | None = None
    right: str | None = None
    address: int | None = None

    def __str__(self) -> str:
        if self.opcode in ("ADD", "SUB"):
            return f"{self.opcode} {self.destination}, {self.left}, {self.right}"
        if self.opcode == "LOAD":
            return f"LOAD {self.destination}, {self.address}"
        return f"STORE {self.source}, {self.address}"

    @property
    def reads(self) -> tuple[str, ...]:
        if self.opcode in ("ADD", "SUB"):
            return (self.left, self.right)  # type: ignore[return-value]
        if self.opcode == "STORE":
            return (self.source,)  # type: ignore[return-value]
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
    stalls: int


@dataclass
class SimulationResult:
    registers: dict[str, int]
    memory: dict[int, int]
    timeline: list[dict[int, str]]
    hazards: list[Hazard]
    pipeline_cycles: int
    non_pipeline_cycles: int

    @property
    def speedup(self) -> float:
        if self.pipeline_cycles == 0:
            return 0.0
        return self.non_pipeline_cycles / self.pipeline_cycles


def _validate_register(token: str) -> str:
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
) -> SimulationResult:
    """Execute instructions and schedule their five pipeline stages.

    Register writes in WB are visible to ID in the same cycle. There is no
    forwarding; a dependent instruction waits in ID until the producer's WB.
    """
    program = list(instructions)
    registers = {f"R{index}": 0 for index in range(REGISTER_COUNT)}
    if initial_registers:
        for name, value in initial_registers.items():
            registers[_validate_register(name)] = value
    memory = dict(initial_memory or {})
    if any(address < 0 for address in memory):
        raise ValueError("Memory addresses must be non-negative.")

    # Schedule decode entry/completion while modeling a front end held by stalls.
    fetch_cycles: list[int] = []
    id_entry_cycles: list[int] = []
    id_cycles: list[int] = []
    wb_cycles: list[int] = []
    timeline: list[dict[int, str]] = [dict() for _ in program]
    hazards: list[Hazard] = []

    for index, instruction in enumerate(program):
        fetch_cycle = 1 if index == 0 else id_entry_cycles[index - 1]
        earliest_id = fetch_cycle + 1
        id_entry = earliest_id if index == 0 else max(
            earliest_id, id_cycles[index - 1] + 1
        )

        latest_producer_wb = id_entry
        producers: list[tuple[int, str, int]] = []
        for register in instruction.reads:
            for producer_index in range(index - 1, -1, -1):
                if program[producer_index].writes == register:
                    producers.append((producer_index, register, wb_cycles[producer_index]))
                    latest_producer_wb = max(latest_producer_wb, wb_cycles[producer_index])
                    break

        id_cycle = latest_producer_wb
        stall_count = id_cycle - id_entry
        for producer_index, register, producer_wb in producers:
            hazards.append(
                Hazard(index, producer_index, register, producer_wb, stall_count)
            )

        fetch_cycles.append(fetch_cycle)
        id_entry_cycles.append(id_entry)
        id_cycles.append(id_cycle)
        wb_cycles.append(id_cycle + 3)

        row = timeline[index]
        row[fetch_cycle] = "IF"
        for cycle in range(fetch_cycle + 1, id_entry):
            row[cycle] = "IF*"
        for cycle in range(id_entry, id_cycle):
            row[cycle] = "STALL"
        for offset, stage in enumerate(STAGES[1:]):
            row[id_cycle + offset] = stage

    # Execute in program order; the timing schedule is independent of values.
    for instruction in program:
        if instruction.opcode == "ADD":
            registers[instruction.destination] = (
                registers[instruction.left] + registers[instruction.right]
            )
        elif instruction.opcode == "SUB":
            registers[instruction.destination] = (
                registers[instruction.left] - registers[instruction.right]
            )
        elif instruction.opcode == "LOAD":
            registers[instruction.destination] = memory.get(instruction.address, 0)
        else:
            memory[instruction.address] = registers[instruction.source]

    pipeline_cycles = wb_cycles[-1] if wb_cycles else 0
    return SimulationResult(
        registers=registers,
        memory=memory,
        timeline=timeline,
        hazards=hazards,
        pipeline_cycles=pipeline_cycles,
        non_pipeline_cycles=len(program) * len(STAGES),
    )


def print_report(instructions: list[Instruction], result: SimulationResult) -> None:
    print("\n" + "=" * 72)
    print("SIMULATION RESULTS")
    print("=" * 72)

    if not instructions:
        print("\nNo instructions were entered.")
    else:
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

        print("\nDATA HAZARDS")
        if not result.hazards:
            print("  No data hazards.")
        else:
            for hazard in result.hazards:
                print(
                    f"  I{hazard.instruction_index + 1} reads {hazard.register} "
                    f"from I{hazard.producer_index + 1}: {hazard.stalls} stall "
                    f"cycle(s); producer writes back in cycle {hazard.producer_wb_cycle}."
                )

    print("\nCYCLE SUMMARY")
    print(f"  Pipelined:        {result.pipeline_cycles} cycles")
    print(f"  Non-pipelined:    {result.non_pipeline_cycles} cycles")
    if result.pipeline_cycles:
        print(f"  Speedup:          {result.speedup:.2f}x")
    else:
        print("  Speedup:          N/A")

    print("\nFINAL REGISTERS")
    register_names = list(result.registers)
    for start in range(0, len(register_names), 4):
        names = register_names[start : start + 4]
        print("  " + "    ".join(
            f"{name}={result.registers[name]}" for name in names
        ))

    print("\nFINAL MEMORY")
    if result.memory:
        for address, value in sorted(result.memory.items()):
            print(f"  [{address}] = {value}")
    else:
        print("  (empty)")
    print("=" * 72)


def main() -> None:
    print("=" * 72)
    print("FIVE-STAGE PIPELINE SIMULATOR")
    print("=" * 72)
    print("Enter starting register and memory values. Press Enter to skip either.")

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
    print_report(instructions, simulate(instructions, initial_registers, initial_memory))


if __name__ == "__main__":
    main()