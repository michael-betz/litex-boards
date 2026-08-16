#!/usr/bin/env python3

#
# This file is part of LiteX-Boards.
#
# Copyright (c) 2025 Gwenhael Goavec-Merou <gwenhael.goavec-merou@trabucayre.com>
# SPDX-License-Identifier: BSD-2-Clause

from migen import *

from litex.gen import *

from litex_boards.platforms import puzhi_p7_starlite

from litex.soc.integration.soc import *
from litex.soc.integration.soc import SoCRegion
from litex.soc.integration.builder import *

from litex.soc.cores.clock import *
from litex.soc.cores.led import LedChaser

from liteeth.phy.s7rgmii import LiteEthPHYRGMII

# CRG ----------------------------------------------------------------------------------------------

class _CRG(LiteXModule):
    def __init__(self, platform, sys_clk_freq, use_ps7_clk=False, with_eth=False):
        self.rst    = Signal()
        self.cd_sys = ClockDomain()

        # # #

        if use_ps7_clk:
            self.comb += ClockSignal("sys").eq(ClockSignal("ps7"))
            self.comb += ResetSignal("sys").eq(ResetSignal("ps7") | self.rst)

            if with_eth:
                self.cd_rgmii = ClockDomain()
                self.pll = pll = S7PLL(speedgrade=-1)
                self.comb += pll.reset.eq(ResetSignal("sys"))
                pll.register_clkin(ClockSignal("sys", sys_clk_freq))
                # Ignore rgmii_clk to pll.clkin path created by SoC's rst.
                platform.add_false_path_constraints(self.cd_sys.clk, pll.clkin)

                pll.create_clkout(self.cd_rgmii, 125e6)
        else:
            # Clk.
            clk50          = platform.request("clk50")
            self.cd_idelay = ClockDomain()

            # PLL.
            self.pll = pll = S7PLL(speedgrade=-1)
            self.comb += pll.reset.eq(self.rst)
            pll.register_clkin(clk50, 50e6)
            pll.create_clkout(self.cd_sys,    sys_clk_freq)
            pll.create_clkout(self.cd_idelay, 200e6)
            # Ignore sys_clk to pll.clkin path created by SoC's rst.
            platform.add_false_path_constraints(self.cd_sys.clk, pll.clkin)

            # IdelayCtrl.
            self.idelayctrl = S7IDELAYCTRL(self.cd_idelay)

# BaseSoC ------------------------------------------------------------------------------------------

class BaseSoC(SoCCore):
    def __init__(self, variant="xc7z020", toolchain="vivado", sys_clk_freq=100e6,
            with_ethernet   = False,
            with_etherbone  = False,
            eth_ip          = "192.168.1.50",
            remote_ip       = None,
            eth_dynamic_ip  = False,
            with_led_chaser = True,
            **kwargs):
        platform = puzhi_p7_starlite.Platform(variant=variant, toolchain=toolchain)

        # CRG --------------------------------------------------------------------------------------
        with_ps7 = (kwargs.get("cpu_type", None) == "zynq7000")
        self.crg = _CRG(platform, sys_clk_freq, with_ps7)

        # SoCCore ----------------------------------------------------------------------------------
        if with_ps7:
            kwargs["integrated_sram_size"] = 0
            kwargs["with_uart"]            = False
        else:
            if kwargs.get("uart_name", None) == "crossover":
                kwargs["with_jtagbone"] = True
        SoCCore.__init__(self, platform, sys_clk_freq, ident="LiteX SoC on Puzhi PZ Starlite", **kwargs)

        # Zynq7000 Integration ---------------------------------------------------------------------
        if with_ps7:
            self.cpu.set_ps7(name="Zynq",
                config={
                    **platform.ps7_config,
                    "PCW_FPGA0_PERIPHERAL_FREQMHZ"     : sys_clk_freq / 1e6,
                    "PCW_SDIO_PERIPHERAL_FREQMHZ"      : "125",
                    "PCW_ACT_ENET0_PERIPHERAL_FREQMHZ" : "125.000000",
                    "PCW_ENET0_RESET_ENABLE"           : "0",
                })

            self.bus.add_region("sram", SoCRegion(
                origin = self.cpu.mem_map["sram"],
                size   = 512 * MEGABYTE - self.cpu.mem_map["sram"])
            )
            self.bus.add_region("rom", SoCRegion(
                origin = self.cpu.mem_map["rom"],
                size   = 256 * MEGABYTE // 8,
                linker = True)
            )
            self.constants["CONFIG_CLOCK_FREQUENCY"] = 666666687
            self.bus.add_region("flash", SoCRegion(origin=0xFC00_0000, size=0x4_0000, mode="rwx"))

            # Enable PS/MIO Ethernet.
            self.cpu.add_ethernet(0, "MIO 16 .. 27", "MIO 52 .. 53")

            # Enable UART0.
            self.cpu.add_uart(0, "MIO 10 .. 11")

            # Enable SDIO.
            self.cpu.add_sdio(0, "MIO 40 .. 45", None, None, None)
            self.cpu.set_libxil({
                "STDOUT_BASEADDRESS"            : "0xE0000000",
                "XPAR_PS7_DDR_0_S_AXI_BASEADDR" : "0x00100000",
                "XPAR_PS7_DDR_0_S_AXI_HIGHADDR" : "0x1FFFFFFF",
            })

        if not with_ps7 and (with_ethernet or with_etherbone):
            self.ethphy = LiteEthPHYRGMII(
                clock_pads = self.platform.request("eth_clocks", 0),
                pads       = self.platform.request("eth", 0))
            if with_etherbone:
                self.add_etherbone(phy=self.ethphy, ip_address=eth_ip, with_ethmac=with_ethernet)
            elif with_ethernet:
                self.add_ethernet(phy=self.ethphy, dynamic_ip=eth_dynamic_ip, local_ip=eth_ip, remote_ip=remote_ip, software_debug=True)

        # Leds -------------------------------------------------------------------------------------
        if with_led_chaser:
            self.leds = LedChaser(
                pads         = platform.request_all("user_led"),
                sys_clk_freq = sys_clk_freq)

# Build --------------------------------------------------------------------------------------------

def main():
    from litex.build.parser import LiteXArgumentParser
    parser = LiteXArgumentParser(platform=puzhi_p7_starlite.Platform, description="LiteX SoC on Puzhi PZ Starlite")
    parser.add_target_argument("--variant",      default="xc7z020",         help="Board variant (xc7z020 or xc7z010).")
    parser.add_target_argument("--sys-clk-freq", default=100e6, type=float, help="System clock frequency.")

    # Ethernet.
    parser.add_target_argument("--with-ethernet",  action="store_true",     help="Enable Ethernet support.")
    parser.add_target_argument("--with-etherbone", action="store_true",     help="Enable Etherbone support.")
    parser.add_target_argument("--eth-ip",         default="192.168.1.50",  help="Ethernet/Etherbone IP address.")
    parser.add_target_argument("--remote-ip",      default="192.168.1.100", help="Remote IP address of TFTP server.")
    parser.add_target_argument("--eth-dynamic-ip", action="store_true",     help="Enable dynamic Ethernet IP assignment.")

    parser.set_defaults(cpu_type="zynq7000")
    args = parser.parse_args()
    if args.with_etherbone and args.eth_dynamic_ip:
        parser.error("--eth-dynamic-ip cannot be used with Etherbone.")

    soc = BaseSoC(
        variant        = args.variant,
        toolchain      = args.toolchain,
        sys_clk_freq   = args.sys_clk_freq,
        with_ethernet  = args.with_ethernet,
        with_etherbone = args.with_etherbone,
        eth_ip         = args.eth_ip,
        remote_ip      = args.remote_ip,
        eth_dynamic_ip = args.eth_dynamic_ip,
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
