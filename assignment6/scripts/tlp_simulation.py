"""
gem5 SE-mode simulation config for TLP assignment.

Runs a multi-process daxpy workload on MinorCPU cores with configurable
FloatSimdFU opLat/issueLat parameters. Each core runs a worker process
that computes its portion of the DAXPY array.

Usage:
    gem5.opt tlp_simulation.py <binary> <num_cores> <array_size> <opLat> <issueLat>
"""

import argparse
import sys

import m5
from m5.objects import *
from m5.objects.BaseMinorCPU import (
    MinorDefaultFloatSimdFU,
    MinorDefaultIntFU,
    MinorDefaultIntMulFU,
    MinorDefaultIntDivFU,
    MinorDefaultPredFU,
    MinorDefaultMemFU,
    MinorDefaultMiscFU,
    MinorFUPool,
)


def create_custom_fu_pool(op_lat, issue_lat):
    float_simd_fu = MinorDefaultFloatSimdFU()
    float_simd_fu.opLat = op_lat
    float_simd_fu.issueLat = issue_lat

    return MinorFUPool(funcUnits=[
        MinorDefaultIntFU(),
        MinorDefaultIntFU(),
        MinorDefaultIntMulFU(),
        MinorDefaultIntDivFU(),
        float_simd_fu,
        MinorDefaultPredFU(),
        MinorDefaultMemFU(),
        MinorDefaultMiscFU(),
    ])


def build_system(binary_path, num_cores, array_size, op_lat, issue_lat):
    system = System()
    system.clk_domain = SrcClockDomain(
        clock="2GHz", voltage_domain=VoltageDomain()
    )
    system.mem_mode = "timing"
    system.mem_ranges = [AddrRange("512MB")]

    system.cpu = [X86MinorCPU(cpu_id=i) for i in range(num_cores)]

    custom_pool = create_custom_fu_pool(op_lat, issue_lat)
    for cpu in system.cpu:
        cpu.executeFuncUnits = custom_pool
        cpu.createThreads()

    system.membus = SystemXBar()

    for cpu in system.cpu:
        cpu.icache = Cache(size="32kB", assoc=4, tag_latency=1,
                           data_latency=1, response_latency=1,
                           mshrs=4, tgts_per_mshr=8)
        cpu.dcache = Cache(size="32kB", assoc=4, tag_latency=1,
                           data_latency=1, response_latency=1,
                           mshrs=4, tgts_per_mshr=8)
        cpu.icache_port = cpu.icache.cpu_side
        cpu.dcache_port = cpu.dcache.cpu_side
        cpu.icache.mem_side = system.membus.cpu_side_ports
        cpu.dcache.mem_side = system.membus.cpu_side_ports

        cpu.createInterruptController()
        cpu.interrupts[0].pio = system.membus.mem_side_ports
        cpu.interrupts[0].int_requestor = system.membus.cpu_side_ports
        cpu.interrupts[0].int_responder = system.membus.mem_side_ports

    system.mem_ctrl = MemCtrl()
    system.mem_ctrl.dram = DDR3_1600_8x8()
    system.mem_ctrl.dram.range = system.mem_ranges[0]
    system.mem_ctrl.port = system.membus.mem_side_ports

    system.system_port = system.membus.cpu_side_ports

    system.workload = SEWorkload.init_compatible(binary_path)

    for i, cpu in enumerate(system.cpu):
        process = Process(pid=100 + i)
        process.cmd = [binary_path, str(i), str(num_cores), str(array_size)]
        cpu.workload = process

    return system


def main():
    parser = argparse.ArgumentParser(description="TLP MinorCPU simulation")
    parser.add_argument("binary", help="Path to the daxpy_worker binary")
    parser.add_argument("num_cores", type=int, help="Number of cores/workers")
    parser.add_argument("array_size", type=int, help="Array size")
    parser.add_argument("op_lat", type=int, help="FloatSimdFU operation latency")
    parser.add_argument("issue_lat", type=int, help="FloatSimdFU issue latency")

    args = parser.parse_args()

    print(f"Starting simulation: cores={args.num_cores}, "
          f"opLat={args.op_lat}, issueLat={args.issue_lat}, "
          f"array_size={args.array_size}")

    system = build_system(
        args.binary, args.num_cores, args.array_size,
        args.op_lat, args.issue_lat,
    )

    root = Root(full_system=False, system=system)
    m5.instantiate()

    exit_event = m5.simulate()
    print(f"Simulation done. Exit cause: {exit_event.getCause()}")


if __name__ == "__m5_main__":
    main()
