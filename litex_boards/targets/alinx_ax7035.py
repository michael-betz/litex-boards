#!/usr/bin/env python3

#
# This file is part of LiteX-Boards.
#
# Copyright (c) 2025 Aaron Hagan <amhagan@kent.edu>
# Copyright (c) 2026 Richard Vodden <richard@vodden.com>
# SPDX-License-Identifier: BSD-2-Clause
#
# The ALINX AX7035B FPGA development board (also covers the earlier AX7035).
# https://www.en.alinx.com/Product/FPGA-Development-Boards/Artix-7/AX7035B.html

from migen import *

from litex.gen import *

from litex_boards.platforms import alinx_ax7035

from litex.soc.cores.clock import *
from litex.soc.interconnect.csr import *
from litex.soc.integration.soc_core import *
from litex.soc.integration.builder import *
from litex.soc.cores.led import LedChaser
from litex.soc.cores.gpio import GPIOIn

from litedram.modules import MT41J128M16
from litedram.phy import s7ddrphy

from litex.soc.cores.video import VideoS7HDMIPHY
from litex.soc.cores.bitbang import I2CMaster

from litespi.modules import N25Q128A13
from litespi.opcodes import SpiNorFlashOpCodes as Codes

from liteeth.phy.s7rgmii import LiteEthPHYRGMII

# CRG ----------------------------------------------------------------------------------------------
class _CRG(LiteXModule):
    def __init__(self, platform, sys_clk_freq, with_video_pll=False, video_pix_clk=74.25e6):
        self.rst          = Signal()
        self.cd_sys       = ClockDomain()
        self.cd_sys4x     = ClockDomain()
        self.cd_sys4x_dqs = ClockDomain()
        self.cd_idelay    = ClockDomain()
        if with_video_pll:
            self.cd_hdmi   = ClockDomain()
            self.cd_hdmi5x = ClockDomain()

        # Clk/Rst.
        clk50 = platform.request("clk50")
        rst_n  = platform.request("cpu_reset_n")

        # Main PLL.
        self.pll = pll = S7PLL(speedgrade=-2)
        self.comb += pll.reset.eq(~rst_n | self.rst)
        pll.register_clkin(clk50, 50e6)
        pll.create_clkout(self.cd_sys,       sys_clk_freq)
        pll.create_clkout(self.cd_sys4x,     4*sys_clk_freq)
        pll.create_clkout(self.cd_sys4x_dqs, 4*sys_clk_freq, phase=90)
        pll.create_clkout(self.cd_idelay,    200e6)
        platform.add_false_path_constraints(self.cd_sys.clk, pll.clkin)

        # IDELAY Ctrl.
        self.idelayctrl = S7IDELAYCTRL(self.cd_idelay)

        # Video PLL ------------------------------------------------------------------------------
        # hdmi5x is the 10:1 serialiser clock (two coupled OSERDESE2 per channel). A separate MMCM
        # is needed because the pixel clock is unrelated to sys_clk_freq; MMCMs are hard blocks, so
        # this costs no logic.
        #
        # video_pix_clk defaults to 74.25 MHz (1280x720@60) rather than 40 MHz (800x600@60) because
        # add_video_framebuffer selects between two pipelines on `pix_clk >= sys_clk_freq`. Below
        # sys_clk it converts width in the sys domain and crosses a narrow CDC, which cannot sustain
        # the pixel rate here; above it, it crosses at full DRAM width and converts in the video
        # domain.
        if with_video_pll:
            self.video_pll = video_pll = S7MMCM(speedgrade=-2)
            # `self.comb +=` matters: a bare `video_pll.reset.eq(...)` builds an expression and
            # discards it, leaving the reset unconnected.
            self.comb += video_pll.reset.eq(~rst_n | self.rst)
            video_pll.register_clkin(clk50, 50e6)
            # 74.25 MHz is not reachable from a 50 MHz reference: LiteX searches integer feedback
            # multipliers only, so the best fit is M=59/D=4 -> 73.75 MHz pixel and ~59.6 Hz refresh.
            # Tightening the margin does not improve it, it just fails to find a config.
            video_pll.create_clkout(self.cd_hdmi,   video_pix_clk)
            video_pll.create_clkout(self.cd_hdmi5x, 5*video_pix_clk)

# 7-Segment Display --------------------------------------------------------------------------------

class SevenSegmentDisplay(LiteXModule):
    """Hardware-multiplexed 6-digit 7-segment driver.

    Multiplexing is done in gateware rather than by bit-banging GPIOs from Linux:
    the display needs a few kHz of scanning to look steady, and a userspace loop
    would visibly flicker whenever the system is busy.

    Software writes one raw segment byte per digit and the scan runs by itself.
    Raw segments (not a BCD decoder) so arbitrary patterns and the decimal point
    are possible.

    The display is common anode and both the segment and select lines are active
    low (manual part 15), so the polarity reset value 0b11 is correct. Polarity is
    a runtime CSR rather than hardcoded so it can be corrected without a rebuild.

    CSRs:
      digit0..5 : 8-bit raw segments, bit order a b c d e f g dp (bit0 = a)
                  digit0 is the RIGHTMOST tube (manual SEL0 = "first from the right")
      enable    : 1 = scan, 0 = all digits blanked
      polarity  : bit0 = invert anodes, bit1 = invert segments (reset 0b11 = correct)
    """
    def __init__(self, pads, sys_clk_freq, refresh_freq=1e3):
        # Each digit CSR must be its own attribute: LiteX's CSR gatherer walks attributes
        # and does not descend into a list, so `self.digits = [CSRStorage(8), ...]`
        # elaborates cleanly but produces no digit registers at all.
        n_digits = len(pads.an)
        digits   = []
        for i in range(n_digits):
            csr = CSRStorage(8, name=f"digit{i}",
                description=f"Digit {i} raw segments: bit0=a .. bit6=g, bit7=dp. "
                            f"digit0 is the RIGHTMOST tube.")
            setattr(self, f"digit{i}", csr)
            digits.append(csr)

        self.enable   = CSRStorage(1, reset=1, description="Enable the scan.")
        self.polarity = CSRStorage(2, reset=0b11,
            description="bit0: invert anodes. bit1: invert segments. Reset 0b11 = both active-low, "
                        "which manual part 15 confirms for this common-anode display.")

        # # #

        # Scan counter: refresh_freq is the per-digit rate, so a full pass over all
        # digits happens refresh_freq/n_digits times a second. 1 kHz per digit gives
        # ~167 Hz whole-display refresh, well above flicker.
        tick_max = int(sys_clk_freq / refresh_freq) - 1
        tick     = Signal(max=tick_max + 1)
        index    = Signal(max=n_digits)

        self.sync += [
            If(tick == tick_max,
                tick.eq(0),
                If(index == (n_digits - 1),
                    index.eq(0),
                ).Else(
                    index.eq(index + 1),
                ),
            ).Else(
                tick.eq(tick + 1),
            ),
        ]

        # Select the active digit and its segment pattern.
        an_raw  = Signal(n_digits)
        seg_raw = Signal(8)

        self.comb += [
            If(self.enable.storage,
                an_raw.eq(1 << index),
            ),
            Case(index, {
                i: seg_raw.eq(digits[i].storage) for i in range(n_digits)
            }),
        ]

        # Apply the runtime polarity.
        self.comb += [
            pads.an.eq(Mux(self.polarity.storage[0], ~an_raw, an_raw)),
            pads.seg.eq(Mux(self.polarity.storage[1], ~seg_raw, seg_raw)),
        ]

# BaseSoC ------------------------------------------------------------------------------------------
class BaseSoC(SoCCore):
    def __init__(self,
                 sys_clk_freq           = int(50e6),
                 with_ethernet          = False,
                 eth_ip                 = "192.168.1.50",
                 remote_ip              = "192.168.1.100",
                 eth_dynamic_ip         = False,
                 with_led_chaser        = True,
                 with_buttons           = True,
                 with_video_terminal    = False,
                 with_video_framebuffer = False,
                 video_timings          = "1280x720@60Hz",
                 with_spi_flash         = False,
                 with_i2c               = False,
                 with_i2c_eeprom        = False,
                 with_xadc              = False,
                 with_seven_seg         = False,
                 **kwargs):

        self.platform = alinx_ax7035.Platform()
        platform = self.platform

        # CRG --------------------------------------------------------------------------------------
        # Derive the video PLL frequency from the SAME timings string the framebuffer uses, so the
        # two can never disagree -- a hand-set pixel clock that does not match the mode is exactly
        # the kind of silent mismatch this board has been bitten by before.
        from litex.soc.cores.video import video_timings as _video_timings
        with_video = with_video_terminal or with_video_framebuffer
        video_pix_clk = _video_timings[video_timings]["pix_clk"]
        self.crg = _CRG(platform, sys_clk_freq, with_video_pll=with_video,
            video_pix_clk=video_pix_clk)

        # SoCCore ----------------------------------------------------------------------------------
        SoCCore.__init__(self, platform, sys_clk_freq, ident="LiteX SoC on ALINX AX7035", **kwargs)

        # DDR3 SDRAM -------------------------------------------------------------------------------
        self.ddrphy = s7ddrphy.A7DDRPHY(platform.request("ddram"),
            memtype          = "DDR3",
            nphases          = 4,
            sys_clk_freq     = sys_clk_freq,
            iodelay_clk_freq = 200e6)

        self.add_sdram("sdram",
            phy           = self.ddrphy,
            module        = MT41J128M16(sys_clk_freq, "1:4"),
            l2_cache_size = kwargs.get("l2_size", 8192)
        )

        # SPI Flash --------------------------------------------------------------------------------
        if with_spi_flash:
            # Micron N25Q128, 128 Mbit, 3.3V (A13 is the 3V part; A11 is 1.8V). The default
            # clk_freq is kept: the BIOS calibration settles on the divisor floor (25 MHz) here.
            #
            # Needs LiteSPI 6dbbc66 or later ("Fix STARTUPE2 issue with en_int"); before it the
            # clock free-ran between transfers and the PHY deadlocked in XFER-END on roughly half
            # of cold boots.
            self.add_spi_flash(mode="4x", module=N25Q128A13(Codes.READ_1_1_4), with_master=True)

        # I2C --------------------------------------------------------------------------------------
        if with_i2c:
            # Bit-banged I2C: this CSR layout is the one Linux's i2c-litex driver expects.
            # add_i2c_master() instantiates litei2c, which has a different layout the driver
            # will not drive.
            #
            # Attributes must be named i2c0, i2c1, ...: json2dts emits one "litex,i2c" node per
            # i2c<N> CSR base and uses that name as the DT label, so &i2cN resolves in overlays.
            # i2c0 is the LM75 (part 16), i2c1 the EEPROM (part 14).
            self.i2c0 = I2CMaster(pads=platform.request("i2c_tmp"))

        if with_i2c_eeprom:
            self.i2c1 = I2CMaster(pads=platform.request("i2c_eeprom"))

        # XADC -------------------------------------------------------------------------------------
        if with_xadc:
            # On-die system monitor (junction temperature and supply rails). A hard macro, so it
            # costs no BRAM, almost no logic and no pins. The attribute must be named xadc:
            # json2dts keys its "litex,hwmon-xadc" node on exactly that CSR base name.
            from litex.soc.cores.xadc import S7SystemMonitor
            self.xadc = S7SystemMonitor()

        # 7-Segment Display ------------------------------------------------------------------------
        if with_seven_seg:
            # Plain CSR peripheral: no device tree node and no kernel driver, driven by writing
            # one raw segment byte per digit.
            self.seven_seg = SevenSegmentDisplay(
                pads         = platform.request("seven_seg"),
                sys_clk_freq = sys_clk_freq)

        # Ethernet ---------------------------------------------------------------------------------
        if with_ethernet:
            self.ethphy = LiteEthPHYRGMII(
                clock_pads = self.platform.request("eth_clocks"),
                pads       = self.platform.request("eth"))
            # The PHY's own constraints are replaced by the two below: the RX clock is sourced by
            # the 88E1518 rather than the FPGA, so it is constrained as a plain 125 MHz input and
            # declared asynchronous to the system clock.
            self.add_ethernet(
                phy                     = self.ethphy,
                dynamic_ip              = eth_dynamic_ip,
                local_ip                = eth_ip,
                remote_ip               = remote_ip,
                with_timing_constraints = False,
            )
            platform.add_period_constraint(self.platform.lookup_request("eth_clocks").rx, 8.0)
            platform.add_false_path_constraints(
                self.platform.lookup_request("clk50"),
                self.platform.lookup_request("eth_clocks").rx
            )

        # Video ------------------------------------------------------------------------------------
        # The FPGA drives TMDS directly (no HDMI transmitter on this board), so this is
        # VideoS7HDMIPHY, which serialises 10:1 through paired OSERDESE2 and needs the hdmi and
        # hdmi5x domains from the video PLL above.
        if with_video:
            hdmi_pads = platform.request("hdmi_out")

            # HDMI1_OUT_EN gates U16 (TPS2051B), which supplies HDMI1_5V to connector pin 18. It
            # must be high or the sink is unpowered -- and the DDC/EDID bus dies with it, since
            # scl/sda cross U17 (NVT2002DP) whose far side is pulled up to that same switched rail.
            # Tied on here; move it to a CSR if EDID hot-plug sequencing is ever wanted.
            self.comb += hdmi_pads.out_en.eq(1)

            self.videophy = VideoS7HDMIPHY(hdmi_pads, clock_domain="hdmi")
            if with_video_terminal:
                self.add_video_terminal(phy=self.videophy, timings=video_timings, clock_domain="hdmi")
            if with_video_framebuffer:
                # Place the framebuffer explicitly, high in DRAM. LiteX's 0x40c00000 default
                # declares a region that overlaps the DTB, OpenSBI and initramfs load addresses
                # used here. Setting mem_map also makes add_video_framebuffer skip its own
                # bus.add_region(), so that region is never declared.
                self.mem_map["video_framebuffer"] = 0x4f000000

                # rgb565 rather than the rgb888 default: it halves the DRAM read bandwidth and the
                # framebuffer size, and json2dts emits "r5g6b5" for 16-bit depth automatically.
                #
                # A deep FIFO matters more than it looks. VideoFrameBuffer advances the video timing
                # generator only while pixel data flows (vtg_sink.ready.eq(source.valid &
                # source.ready)), so a DMA underrun does not merely tear -- it stretches hsync/vsync
                # until the mode is out of spec and the sink rejects it outright.
                self.add_video_framebuffer(phy=self.videophy, timings=video_timings,
                    clock_domain="hdmi", format="rgb565", fifo_depth=65536)

        # Leds -------------------------------------------------------------------------------------
        if with_led_chaser:
           self.leds = LedChaser(
               pads         = platform.request_all("user_led"),
               sys_clk_freq = sys_clk_freq)

        # Buttons ----------------------------------------------------------------------------------
        if with_buttons:
            # Named switches rather than buttons: litex_json2dts_linux emits a "litex,gpio" input
            # node only for a CSR base called switches (or leds for outputs), so any other name
            # leaves Linux with no node for the four keys.
            self.switches = GPIOIn(
                pads     = platform.request_all("user_btn"),
                with_irq = self.irq.enabled
            )
            if self.irq.enabled:
                # GPIOIn(with_irq=True) builds the event manager but does not route an interrupt;
                # only an add_*() helper does that. Without this the IRQ is never allocated.
                self.irq.add("switches", use_loc_if_exists=True)

# Build --------------------------------------------------------------------------------------------
def main():
    from litex.build.parser import LiteXArgumentParser
    parser = LiteXArgumentParser(platform=alinx_ax7035.Platform, description="LiteX SoC on ALINX AX7035B.")
    parser.add_target_argument("--flash",           action="store_true",       help="Flash bitstream.")
    parser.add_target_argument("--sys-clk-freq",    default=50e6, type=float,  help="System clock frequency.")
    parser.add_target_argument("--with-ethernet",   action="store_true",       help="Enable Ethernet support.")
    parser.add_target_argument("--eth-ip",          default="192.168.1.50",    help="Ethernet/Etherbone IP address.")
    parser.add_target_argument("--remote-ip",       default="192.168.1.100",   help="Remote IP address of TFTP server.")
    parser.add_target_argument("--eth-dynamic-ip",  action="store_true",       help="Enable dynamic Ethernet IP assignment.")
    parser.add_target_argument("--with-spi-flash",  action="store_true",       help="Enable SPI Flash (MMAPed).")
    parser.add_target_argument("--with-i2c",        action="store_true",       help="Enable I2C master on the LM75 bus.")
    parser.add_target_argument("--with-i2c-eeprom", action="store_true",       help="Enable I2C master on the EEPROM bus.")
    parser.add_target_argument("--with-xadc",       action="store_true",       help="Enable XADC system monitor.")
    parser.add_target_argument("--with-seven-seg",  action="store_true",       help="Enable the 6-digit 7-segment display.")
    parser.add_target_argument("--with-sdcard",     action="store_true",       help="Enable SDCard support.")
    viopts = parser.target_group.add_mutually_exclusive_group()
    viopts.add_argument("--with-video-terminal",    action="store_true", help="Enable Video Terminal (HDMI).")
    viopts.add_argument("--with-video-framebuffer", action="store_true", help="Enable Video Framebuffer (HDMI).")
    args = parser.parse_args()

    soc = BaseSoC(
        sys_clk_freq           = args.sys_clk_freq,
        with_ethernet          = args.with_ethernet,
        eth_ip                 = args.eth_ip,
        remote_ip              = args.remote_ip,
        eth_dynamic_ip         = args.eth_dynamic_ip,
        with_video_terminal    = args.with_video_terminal,
        with_video_framebuffer = args.with_video_framebuffer,
        with_spi_flash         = args.with_spi_flash,
        with_i2c               = args.with_i2c,
        with_i2c_eeprom        = args.with_i2c_eeprom,
        with_xadc              = args.with_xadc,
        with_seven_seg         = args.with_seven_seg,
        **parser.soc_argdict
    )
    if args.with_sdcard:
        soc.add_sdcard()

    builder = Builder(soc, **parser.builder_argdict)
    if args.build:
        builder.build(**parser.toolchain_argdict)

    if args.load:
        prog = soc.platform.create_programmer()
        prog.load_bitstream(builder.get_bitstream_filename(mode="sram"))

    if args.flash:
        prog = soc.platform.create_programmer()
        prog.flash(0, builder.get_bitstream_filename(mode="flash"))

if __name__ == "__main__":
    main()

