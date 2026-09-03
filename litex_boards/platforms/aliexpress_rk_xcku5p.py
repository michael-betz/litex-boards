#
# This file is part of LiteX-Boards.
#
# Copyright (c) 2026 Aria Wegrzyn <git@ariac.at>
# SPDX-License-Identifier: BSD-2-Clause

# Documentation for the board can be found here:
# https://github.com/tommythorn/rk-xcku5p-f-v1.2/

from litex.build.generic_platform import *
from litex.build.xilinx import XilinxUSPPlatform
from litex.build.openfpgaloader import OpenFPGALoader

# IOs ----------------------------------------------------------------------------------------------

_io = [
    # Clk.
    ("clk200", 0,
        Subsignal("p", Pins("T24"), IOStandard("DIFF_SSTL12")),
        Subsignal("n", Pins("U24"), IOStandard("DIFF_SSTL12"))
    ),

    # LEDs.
    ("user_led", 0, Pins("H9"), IOStandard("LVCMOS33")),
    ("user_led", 1, Pins("J9"), IOStandard("LVCMOS33")),
    ("user_led", 2, Pins("G11"), IOStandard("LVCMOS33")),
    ("user_led", 3, Pins("H11"), IOStandard("LVCMOS33")),

    # UART.
    ("serial", 0,
        Subsignal("tx", Pins("AC14")),
        Subsignal("rx", Pins("AD13")),
        IOStandard("LVCMOS33")
    ),

    # DDR4
    ("ddram", 0,
        Subsignal("a",       Pins(
                "Y22  Y25  W23  V26  R26  U26 R21 W25",
                "R20  Y26  R25  V23  AA24 W26"),
            IOStandard("SSTL12_DCI")),
        Subsignal("ba",      Pins("P21 P26"), IOStandard("SSTL12_DCI")),
        Subsignal("bg",      Pins("R22"), IOStandard("SSTL12_DCI")),
        Subsignal("ras_n",   Pins("T25"), IOStandard("SSTL12_DCI")),  # A16
        Subsignal("cas_n",   Pins("AA25"), IOStandard("SSTL12_DCI")), # A15
        Subsignal("we_n",    Pins("P23"), IOStandard("SSTL12_DCI")),  # A14
        Subsignal("cs_n",    Pins("P25"), IOStandard("SSTL12_DCI")),
        Subsignal("act_n",   Pins("P24"), IOStandard("SSTL12_DCI")),
        Subsignal("alert_n", Pins("U25"), IOStandard("SSTL12_DCI")),
        Subsignal("par",     Pins("Y23"), IOStandard("SSTL12_DCI")),
        Subsignal("dq",      Pins(
                "AF24 AF25 AD24 AB26 AC24 AB25 AD25 AB24",
                "AC21 AD23 AD21 AC22 AB21 AE23 AE21 AC23",
                "AE16 AD19 AD16 AF17 AC19 AF19 AF18 AE17",
                "AA20 AA18 AA19 Y18  AB20 Y17  AB19 AA17"),
            IOStandard("POD12_DCI")),
        Subsignal("dqs_p",   Pins(
                "AC26 AA22 AC18 AB17"),
            IOStandard("DIFF_POD12")),
        Subsignal("dqs_n",   Pins(
                "AD26 AB22 AD18 AC17"),
            IOStandard("DIFF_POD12")),
        Subsignal("dm",     Pins(
                "AE25 AE22 AD20 Y20"), # also selects chip
            IOStandard("POD12_DCI")),
        Subsignal("clk_p",   Pins("V24"), IOStandard("DIFF_SSTL12_DCI")),
        Subsignal("clk_n",   Pins("W24"), IOStandard("DIFF_SSTL12_DCI")),
        Subsignal("cke",     Pins("P20"), IOStandard("SSTL12_DCI")),
        Subsignal("odt",     Pins("R23"), IOStandard("SSTL12_DCI")),
        Subsignal("reset_n", Pins("P19"), IOStandard("SSTL12")),
        Misc("SLEW=FAST"),
    ),
]

# Platform -----------------------------------------------------------------------------------------

class Platform(XilinxUSPPlatform):
    default_clk_name   = "clk200"
    default_clk_period = 1e9/200e6

    def __init__(self, toolchain="vivado"):
        XilinxUSPPlatform.__init__(self, "xcku5p-ffvb676-2-i", _io, toolchain=toolchain)

    def create_programmer(self):
        return OpenFPGALoader(cable="ft2232", fpga_part="xcku5p-2ffvb676")

    def do_finalize(self, fragment):
        XilinxUSPPlatform.do_finalize(self, fragment)
        self.add_period_constraint(self.lookup_request("clk200", loose=True), 1e9/200e6)

        # Shutdown on overheating
        self.add_platform_command("set_property BITSTREAM.CONFIG.OVERTEMPSHUTDOWN ENABLE [current_design]")

        # Reduce programming time
        self.add_platform_command("set_property BITSTREAM.GENERAL.COMPRESS TRUE [current_design]")
