#!/usr/bin/env python3

#
# This file is part of LiteX-Boards.
#
# Copyright (c) 2022 Gwenhael Goavec-Merou <gwenhael.goavec-merou@trabucayre.com>
# SPDX-License-Identifier: BSD-2-Clause

# Build/Use:
# The current support is sufficient to run LiteX BIOS on Cortex-A53 core #0:
# ./alinx_axu2cga.py --build --load
# LiteX BIOS can then be executed on hardware using JTAG with the following xsct script from:
# https://github.com/trabucayre/litex-template/
# make -f Makefile.axu2cga load will build everything and run xsct in the end.
#
# Relies on https://github.com/lucaceresoli/zynqmp-pmufw-builder to create a generic PMU firmware;
# first build will take a while because it includes a cross-toolchain.

from migen import *

from litex.gen import *

from litex_boards.platforms import alinx_axu2cga

from litex.soc.cores.clock import *
from litex.soc.integration.soc import *
from litex.soc.integration.soc import SoCRegion
from litex.soc.integration.builder import *
from litex.soc.cores.led import LedChaser

# CRG ----------------------------------------------------------------------------------------------

class _CRG(LiteXModule):
    def __init__(self, platform, sys_clk_freq, use_psu_clk=False):
        self.rst    = Signal()
        self.cd_sys = ClockDomain()

        # # #

        if use_psu_clk:
            self.comb += [
                ClockSignal("sys").eq(ClockSignal("ps")),
                ResetSignal("sys").eq(ResetSignal("ps") | self.rst),
            ]
        else:
            # Clk
            clk25 = platform.request("clk25")

            # PLL
            self.pll = pll = USMMCM(speedgrade=-1)
            self.comb += pll.reset.eq(self.rst)
            pll.register_clkin(clk25, 25e6)
            pll.create_clkout(self.cd_sys, sys_clk_freq)
            # Ignore sys_clk to pll.clkin path created by SoC's rst.
            platform.add_false_path_constraints(self.cd_sys.clk, pll.clkin)

# BaseSoC ------------------------------------------------------------------------------------------

class BaseSoC(SoCCore):
    def __init__(self, sys_clk_freq=25e6, with_led_chaser=True, **kwargs):
        platform = alinx_axu2cga.Platform()

        # CRG --------------------------------------------------------------------------------------
        use_psu_clk = (kwargs.get("cpu_type", None) == "zynqmp")
        self.crg = _CRG(platform, sys_clk_freq, use_psu_clk)

        # SoCCore ----------------------------------------------------------------------------------
        if kwargs.get("cpu_type", None) == "zynqmp":
            kwargs["integrated_sram_size"] = 0
            kwargs["with_uart"] = False
        SoCCore.__init__(self, platform, sys_clk_freq, ident="LiteX SoC on Alinx AXU2CGA", **kwargs)

        # ZynqMP Integration ---------------------------------------------------------------------
        if kwargs.get("cpu_type", None) == "zynqmp":
            self.cpu.config.update(platform.psu_config)

            self.bus.add_region("sram", SoCRegion(
                origin = self.cpu.mem_map["sram"],
                size   = 1 * GIGABYTE)  # DDR
            )
            self.bus.add_region("rom", SoCRegion(
                origin = self.cpu.mem_map["rom"],
                size   = 512 * MEGABYTE // 8,
                linker = True)
            )
            self.constants["CONFIG_CLOCK_FREQUENCY"] = 1199880127
            self.cpu.set_libxil({
                "STDIN_BASEADDRESS"                         : "0xFF010000",
                "STDOUT_BASEADDRESS"                        : "0xFF010000",
                "XPAR_PSU_DDR_0_S_AXI_BASEADDR"             : "0x00000000",
                "XPAR_PSU_DDR_0_S_AXI_HIGHADDR"             : "0x7FFFFFFF",
                "XPAR_PSU_DDR_1_S_AXI_BASEADDR"             : "0x800000000",
                "XPAR_PSU_DDR_1_S_AXI_HIGHADDR"             : "0x87FFFFFFF",
                "XPAR_CPU_CORTEXA53_0_TIMESTAMP_CLK_FREQ"   : "99999005",
            })

        # Leds -------------------------------------------------------------------------------------
        if with_led_chaser:
            self.leds = LedChaser(
                pads         = platform.request_all("user_led"),
                sys_clk_freq = sys_clk_freq)

# Build --------------------------------------------------------------------------------------------

def main():
    from litex.build.parser import LiteXArgumentParser
    parser = LiteXArgumentParser(platform=alinx_axu2cga.Platform, description="LiteX SoC on Alinx AXU2CGA.")
    parser.add_target_argument("--cable",        default="ft232",          help="JTAG interface.")
    parser.add_target_argument("--sys-clk-freq", default=25e6, type=float, help="System clock frequency.")
    parser.set_defaults(cpu_type="zynqmp")
    args = parser.parse_args()

    soc = BaseSoC(
        sys_clk_freq = args.sys_clk_freq,
        **parser.soc_argdict
    )
    builder = Builder(soc, **parser.builder_argdict)
    if args.build:
        builder.build(**parser.toolchain_argdict)

    if args.load:
        prog = soc.platform.create_programmer(args.cable)
        prog.load_bitstream(builder.get_bitstream_filename(mode="sram"))

if __name__ == "__main__":
    main()
