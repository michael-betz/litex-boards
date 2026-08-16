#!/usr/bin/env python3

#
# This file is part of LiteX-Boards.
#
# Copyright (c) 2026 Yu Jin <lambda.jinyu@gmail.com>
# SPDX-License-Identifier: BSD-2-Clause

from migen import *

from litex.gen import *

from litex_boards.platforms import mlk_cu07_ku15p

from litex.soc.cores.clock import USPMMCM, USPIDELAYCTRL
from litex.soc.cores.led import LedChaser
from litex.soc.integration.builder import Builder
from litex.soc.integration.soc_core import SoCCore

from litedram.modules import MT40A512M16
from litedram.phy import usddrphy

# CRG ----------------------------------------------------------------------------------------------

class _CRG(LiteXModule):
    def __init__(self, platform, sys_clk_freq):
        self.rst       = Signal()
        self.cd_sys    = ClockDomain()
        self.cd_sys4x  = ClockDomain()
        self.cd_idelay = ClockDomain()
        self.cd_por     = ClockDomain(reset_less=True)

        # # #

        # Clk.
        clk100 = platform.request("clk100")

        # Power-on Reset.
        # Keep the POR independent of cpu_resetn, which can float low on some board revisions.
        por_count = Signal(16, reset=2**16 - 1)
        por_done  = Signal()
        self.comb += [
            self.cd_por.clk.eq(clk100),
            por_done.eq(por_count == 0),
        ]
        self.sync.por += If(~por_done, por_count.eq(por_count - 1))

        # MMCM.
        self.pll = pll = USPMMCM(speedgrade=-2)
        self.comb += pll.reset.eq(~por_done | self.rst)
        pll.register_clkin(clk100, 100e6)
        pll.create_clkout(self.cd_sys,    sys_clk_freq,   with_reset=False)
        pll.create_clkout(self.cd_sys4x,  4*sys_clk_freq, with_reset=False)
        pll.create_clkout(self.cd_idelay, 400e6)
        platform.add_false_path_constraints(self.cd_sys.clk, pll.clkin)

        # IDelayCtrl.
        self.idelayctrl = USPIDELAYCTRL(cd_ref=self.cd_idelay, cd_sys=self.cd_sys)

# BaseSoC ------------------------------------------------------------------------------------------

class BaseSoC(SoCCore):
    def __init__(self, sys_clk_freq=int(75e6), with_sdcard=False, with_led_chaser=False, **kwargs):
        platform = mlk_cu07_ku15p.Platform()

        # CRG --------------------------------------------------------------------------------------
        self.crg = _CRG(platform, sys_clk_freq)

        # SoCCore ----------------------------------------------------------------------------------
        SoCCore.__init__(self, platform, sys_clk_freq, ident="LiteX SoC on Milianke MLK-CU07-KU15P", **kwargs)

        # DDR4 SDRAM -------------------------------------------------------------------------------
        if not self.integrated_main_ram_size:
            self.ddrphy = usddrphy.USPDDRPHY(platform.request("ddram"),
                memtype          = "DDR4",
                sys_clk_freq     = sys_clk_freq,
                iodelay_clk_freq = 400e6)
            self.add_sdram("sdram",
                phy           = self.ddrphy,
                module        = MT40A512M16(sys_clk_freq, "1:4"),
                size          = 0x40000000,
                l2_cache_size = kwargs.get("l2_size", 8192)
            )

        # SDCard -----------------------------------------------------------------------------------
        if with_sdcard:
            self.add_sdcard()

        # Leds -------------------------------------------------------------------------------------
        if with_led_chaser:
            self.leds = LedChaser(
                pads         = platform.request_all("user_led"),
                sys_clk_freq = sys_clk_freq)

# Build --------------------------------------------------------------------------------------------

def main():
    from litex.build.parser import LiteXArgumentParser
    parser = LiteXArgumentParser(platform=mlk_cu07_ku15p.Platform, description="LiteX SoC on Milianke MLK-CU07-KU15P.")
    parser.add_target_argument("--sys-clk-freq",    default=75e6, type=float, help="System clock frequency.")
    parser.add_target_argument("--with-sdcard",     action="store_true",      help="Enable SDCard support.")
    parser.add_target_argument("--with-led-chaser", action="store_true",      help="Enable LED Chaser.")
    args = parser.parse_args()

    soc = BaseSoC(
        sys_clk_freq    = args.sys_clk_freq,
        with_sdcard     = args.with_sdcard,
        with_led_chaser = args.with_led_chaser,
        **parser.soc_argdict
    )
    builder = Builder(soc, **parser.builder_argdict)
    if args.build:
        builder.build(**parser.toolchain_argdict)

    if args.load:
        prog = soc.platform.create_programmer()
        prog.load_bitstream(builder.get_bitstream_filename(mode="sram"))

if __name__ == "__main__":
    main()
