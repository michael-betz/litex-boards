#
# This file is part of LiteX-Boards.
#
# Copyright (c) 2025 Aaron Hagan <amhagan@kent.edu>
# Copyright (c) 2026 Richard Vodden <richard@vodden.com>
# SPDX-License-Identifier: BSD-2-Clause
#
# The ALINX AX7035B FPGA development board, equipped with an AMD Artix-7
# XC7A35T-2FGG484I.
# https://www.en.alinx.com/Product/FPGA-Development-Boards/Artix-7/AX7035B.html
#
# This platform also describes the earlier AX7035: the two differ only in the
# Ethernet PHY fitted and are otherwise pin compatible. Only the AX7035B is
# still sold - the AX7035 and board revision V1.0 are discontinued.

import subprocess

from litex.build.generic_platform import *
from litex.build.xilinx           import Xilinx7SeriesPlatform
from litex.build.openfpgaloader   import OpenFPGALoader

# IOs ----------------------------------------------------------------------------------------------
_io = [
    # Clock
    ("clk50", 0, Pins("Y18"), IOStandard("LVCMOS33")),

    # DDR3 SDRAM
    ("ddram", 0,
        Subsignal("a",     Pins("AA8 U5 Y9 Y8 V5 W7 U6 V7 T5 W9 AA6 T6 Y6 R6"), IOStandard("SSTL15")),
        Subsignal("ba",    Pins("AB8 W5 Y7"), IOStandard("SSTL15")),
        Subsignal("ras_n", Pins("AB7"), IOStandard("SSTL15")),
        Subsignal("cas_n", Pins("T4"), IOStandard("SSTL15")),
        Subsignal("we_n",  Pins("W6"), IOStandard("SSTL15")),
        Subsignal("dm",    Pins("AB1 W2"), IOStandard("SSTL15")),
        Subsignal("dq",    Pins("V4 AB2 AB3 AA1 AA5 Y4 AB5 AA4", 
                                "V2 Y1 U1 Y2 T1 W1 U2 U3"),
            IOStandard("SSTL15"),
            Misc("IN_TERM=UNTUNED_SPLIT_50")),
        Subsignal("dqs_p", Pins("Y3 R3"), IOStandard("DIFF_SSTL15"), Misc("IN_TERM=UNTUNED_SPLIT_50")),
        Subsignal("dqs_n", Pins("AA3 R2"), IOStandard("DIFF_SSTL15"), Misc("IN_TERM=UNTUNED_SPLIT_50")),
        Subsignal("clk_p", Pins("V9"), IOStandard("DIFF_SSTL15")),
        Subsignal("clk_n", Pins("V8"), IOStandard("DIFF_SSTL15")),
        Subsignal("cke",   Pins("R4"), IOStandard("SSTL15")),
        Subsignal("odt",   Pins("AB6"), IOStandard("SSTL15")),
        Subsignal("reset_n", Pins("T3"), IOStandard("LVCMOS15")),
        Subsignal("cs_n",  Pins("U7"), IOStandard("SSTL15")), # Fix me
        Misc("SLEW=FAST"),
    ),

    # RGMII Ethernet
    ("eth_clocks", 0,
        Subsignal("tx", Pins("L14"), Misc("SLEW=FAST")),
        Subsignal("rx", Pins("K18")),
        IOStandard("LVCMOS33")
    ),
    ("eth", 0,
        Subsignal("rst_n",   Pins("L15")),
        Subsignal("mdio",    Pins("K16")),
        Subsignal("mdc",     Pins("K17")),
        Subsignal("rx_ctl",   Pins("M21")),
        Subsignal("rx_data", Pins("K19 M15 J17 J20")),
        Subsignal("tx_ctl",  Pins("L19"), Misc("SLEW=FAST")), # labelled txen in the manual
        Subsignal("tx_data", Pins("J21 M20 L18 L20"), Misc("SLEW=FAST")),
        IOStandard("LVCMOS33"),
    ),

    # HDMI In -- UNVERIFIED, left commented. The available pin-assignment table covers the output
    # only, and the equivalent output block needed two corrections, so treat these as unchecked.
    # ("hdmi_in", 0,
    #     Subsignal("clk_p",   Pins("K4"), IOStandard("TMDS_33")),
    #     Subsignal("clk_n",   Pins("J4"), IOStandard("TMDS_33")),
    #     Subsignal("data0_p", Pins("M1"), IOStandard("TMDS_33")),
    #     Subsignal("data0_n", Pins("L1"), IOStandard("TMDS_33")),
    #     Subsignal("data1_p", Pins("P2"), IOStandard("TMDS_33")),
    #     Subsignal("data1_n", Pins("N2"), IOStandard("TMDS_33")),
    #     Subsignal("data2_p", Pins("R1"), IOStandard("TMDS_33")),
    #     Subsignal("data2_n", Pins("P1"), IOStandard("TMDS_33")),
    #     Subsignal("scl",     Pins("N5"), IOStandard("LVCMOS33")),
    #     Subsignal("sda",     Pins("L6"), IOStandard("LVCMOS33")),
    #     Subsignal("hpd_en",  Pins("P6"), IOStandard("LVCMOS33")),
    #     Subsignal("cec",     Pins("M5"), IOStandard("LVCMOS33")),
    # ),

    # HDMI Out (manual part 9, connector J6).
    #
    # Direct FPGA TMDS -- there is no transmitter chip, so this pairs with VideoS7HDMIPHY, not
    # VideoDVIPHY. Bank 35 carries all of these pins and its TMDS termination to +3.3V sets
    # VCCO_35 = 3.3V, as TMDS_33 requires.
    #
    # out_en (M6) gates the TPS2051B supplying HDMI_5V to the connector. It must be asserted for
    # the sink to be powered, and also for DDC/EDID to work at all: scl/sda cross a level
    # translator whose far side is pulled up to that switched rail.
    #
    # CEC is absent deliberately: the connector pin exists but no CEC net reaches the FPGA.
    ("hdmi_out", 0,
        Subsignal("clk_p",   Pins("E1"), IOStandard("TMDS_33")),
        Subsignal("clk_n",   Pins("D1"), IOStandard("TMDS_33")),
        Subsignal("data0_p", Pins("G1"), IOStandard("TMDS_33")),
        Subsignal("data0_n", Pins("F1"), IOStandard("TMDS_33")),
        Subsignal("data1_p", Pins("H2"), IOStandard("TMDS_33")),
        Subsignal("data1_n", Pins("G2"), IOStandard("TMDS_33")),
        Subsignal("data2_p", Pins("K1"), IOStandard("TMDS_33")),
        Subsignal("data2_n", Pins("J1"), IOStandard("TMDS_33")),
        Subsignal("scl",     Pins("P4"), IOStandard("LVCMOS33")),
        Subsignal("sda",     Pins("N3"), IOStandard("LVCMOS33")),
        Subsignal("out_en",  Pins("M6"), IOStandard("LVCMOS33")),
        Subsignal("hpd",     Pins("P5"), IOStandard("LVCMOS33")),
    ),

    # USB FIFO - 
    # ("usb_fifo", 0, 
    #     Subsignal("data",   Pins("K22 K21 J22 H18 H22 J15 H20 G20")),
    #     Subsignal("rxf_n",  Pins("H19")),
    #     Subsignal("txe_n",  Pins("H15")),
    #     Subsignal("rd_n",   Pins("L21")),
    #     Subsignal("wr_n",   Pins("G17")),
    #     Subsignal("siwua",  Pins("H17")),
    #     Subsignal("clkout", Pins("J19")),
    #     Subsignal("oe_n",   Pins("G18")),
    #     Misc("SLEW=FAST"),
    #     Drive(8),
    #     IOStandard("LVCMOS33"),
    # ),

    # USB JTAG
    # ("usb_jtag", 0,
    #     Subsignal("tck", Pins("K22")),
    #     Subsignal("tdi", Pins("K21")),
    #     Subsignal("tdo", Pins("J22")),
    #     Subsignal("tms", Pins("H18")),
    #     IOStandard("LVCMOS33")
    # ),

    # SDCard.
    ("sdcard", 0,
        Subsignal("data", Pins("P16 R17 N14 N13")),
        Subsignal("cmd",  Pins("P15")),
        Subsignal("clk",  Pins("N15")),
        Subsignal("cd_n",   Pins("R16")),
        Misc("SLEW=FAST"),
        IOStandard("LVCMOS33"),
    ),

    # USB UART
    ("serial", 0,
        Subsignal("tx", Pins("G16"), IOStandard("LVCMOS33")),
        Subsignal("rx", Pins("G15"), IOStandard("LVCMOS33")),
    ),

    # QSPI Flash - Micron N25Q128, 128 Mbit (16 MB), 3.3V CMOS.
    #
    # Pins per the AX7035B manual, part 7. Note QSPI_CLK is CCLK_0 (L12), a
    # dedicated configuration pin in BANK0: it is deliberately NOT declared
    # here, because on 7-series the clock is driven through the STARTUPE2
    # primitive, which litespi instantiates itself (litespi/clkgen.py,
    # `if device.startswith("xc7")`). Constraining L12 as a user IO would fail.
    # The remaining signals are on BANK14 dedicated pins D00-D03 and FCS_B.
    ("spiflash", 0,
        Subsignal("cs_n", Pins("T19")),
        Subsignal("mosi", Pins("P22")),  # QSPI_DQ0
        Subsignal("miso", Pins("R22")),  # QSPI_DQ1
        Subsignal("wp",   Pins("P21")),  # QSPI_DQ2
        Subsignal("hold", Pins("R21")),  # QSPI_DQ3
        IOStandard("LVCMOS33"),
    ),
    ("spiflash4x", 0,
        Subsignal("cs_n", Pins("T19")),
        Subsignal("dq",   Pins("P22 R22 P21 R21")),
        IOStandard("LVCMOS33"),
    ),

    # EEPROM (Microchip 24LC04, manual part 14). Separate bus from the
    # temperature sensor below, and a different IO standard.
    #
    # Deliberately NO internal pull-up here, unlike i2c_tmp: the schematic shows
    # R81/R82, 4.7k to +3.3V, on EEPROM_I2C_SCL/SDA. This bus is properly
    # terminated on the board and needs no help from the FPGA.
    ("i2c_eeprom", 0,
        Subsignal("sda", Pins("N19")),
        Subsignal("scl", Pins("N18")),
        IOStandard("LVCMOS33")
    ),

    # Temperature sensor (LM75-compatible, manual part 16).
    #
    # LVCMOS33, not LVCMOS25: these pins share bank 15 with the Ethernet RGMII clock, so VCCO is
    # 3.3V and Vivado rejects the mixture with a DRC BIVC-1 conflicting-Vcc error.
    #
    # PULLUP is required, not belt-and-braces: this bus has no pull-up on the board at all (the
    # EEPROM bus does, R81/R82). Without it SDA recovers only on pin leakage, taking ~1.3 ms, and
    # i2c-litex samples the ACK far sooner -- so every address appears to ACK and all reads return
    # zero. Manual part 16 claims pull-ups here and is wrong.
    ("i2c_tmp", 0,
        Subsignal("sda", Pins("N22")),
        Subsignal("scl", Pins("M22")),
        IOStandard("LVCMOS33"),
        Misc("PULLUP TRUE")
    ),

    # 7-segment display, 6 digits (manual part 15, "Digital Tube").
    #
    # Collapsed from 14 separate single-pin resources into one grouped resource --
    # that is the litex-boards convention and it lets the target request the whole
    # display in one call.
    #
    # ✅ PINS VERIFIED against the manual's part 15 pin table (2026-08-15) -- and for
    # once the inherited commented-out block was RIGHT. That is one correct out of
    # six; the other five (MIPI lane pins, the LVCMOS25 bank conflict, the flash
    # pinout, the LM75 pull-ups, HDMI's cec/out_en swap) were all wrong, so the
    # check was still worth making.
    #
    # Banks verified from Vivado too: M16/M17 are in bank 15 and the other twelve in
    # bank 35 -- both 3.3V, so LVCMOS33 coexists with the HDMI TMDS_33 pins sharing
    # bank 35, and none of these collide with the HDMI pins.
    #
    # "seg" is segment order a b c d e f g dp -- the manual calls these DIG0..DIG7,
    # which is thoroughly confusing since DIG normally means digit-select.
    #
    # ⚠️ "an" is ordered RIGHT TO LEFT: the manual's SEL0 (M2) is "the first digital
    # tube from the right". So an[0] / digit0 is the RIGHTMOST digit and an[5] the
    # leftmost -- write a 6-digit number with the most significant value in digit5.
    ("seven_seg", 0,
        Subsignal("an",  Pins("M2 N4 L5 L4 M16 M17")),
        Subsignal("seg", Pins("J5 M3 J6 H5 G4 K6 K3 H4")),
        IOStandard("LVCMOS33")
    ),

    # MIPI 0 - FPC expansion port (camera). Pins per the AX7035B user manual,
    # "FPC Expansion Ports Pin Assignment":
    #   MIPI_LAN0_N D2 / MIPI_LAN0_P E2   MIPI_LAN1_N E3 / MIPI_LAN1_P F3
    #   MIPI_CLK_N  G3 / MIPI_CLK_P  H3
    #
    # NOTE: IOStandard is unverified. MIPI_DPHY is an UltraScale+ standard; the
    # only 7-series precedent in litex-boards (seeedstudio_spartan_edge_
    # accelerator, xc7s15) is marked "Untested" and splits p/n across
    # MIPI_DPHY and LVCMOS12H. On Artix-7 MIPI RX is normally LVDS_25 plus an
    # external resistor network. Check the bank VCCO before enabling.
    # ("camera", 0,
    #     Subsignal("clkp",    Pins("H3")),
    #     Subsignal("clkn",    Pins("G3")),
    #     Subsignal("dp",      Pins("E2 F3")),
    #     Subsignal("dn",      Pins("D2 E3")),
    #     IOStandard("MIPI_DPHY")
    # ),
    # ("mipi_gpio", 0,
    #     Subsignal("gpio",    Pins("H13")),
    #     IOStandard("LVCMOS33")
    # ),
    # ("mipi_clk", 0,
    #     Subsignal("clk",     Pins("H14")),
    #     IOStandard("LVCMOS33")
    # ),
    # ("mipi_i2c", 0,
    #     Subsignal("scl",     Pins("J14")),
    #     Subsignal("sda",     Pins("G13")),
    #     IOStandard("LVCMOS33")
    # ),

    # User Buttons

    ("user_btn", 0, Pins("M13"), IOStandard("LVCMOS33")),
    ("user_btn", 1, Pins("K14"), IOStandard("LVCMOS33")),
    ("user_btn", 2, Pins("K13"), IOStandard("LVCMOS33")),
    ("user_btn", 3, Pins("L13"), IOStandard("LVCMOS33")),

    ("cpu_reset_n", 0, Pins("F20"), IOStandard("LVCMOS33")),

    # Leds
    ("user_led", 0, Pins("F19"), IOStandard("LVCMOS33")),
    ("user_led", 1, Pins("E21"), IOStandard("LVCMOS33")),
    ("user_led", 2, Pins("D20"), IOStandard("LVCMOS33")),
    ("user_led", 3, Pins("C20"), IOStandard("LVCMOS33")),
]

# Expansion headers J9 and J10 (manual part 17): 40-pin 0.1" headers, 34 signal
# pins each, all on 3.3V banks.
#
# Keys are the PHYSICAL pin numbers off the silkscreen, NOT a 1..34 sequence.
# Pins 1/2 are GND/+5V and 37-40 are GND/GND/+3.3V/+3.3V, so the first signal pin
# is 3. These were originally drafted as "io1".."io34", which silently shifted
# everything by two -- platform.request("J9:io1") would hand you the pin labelled
# 3 on the board. Integer keys matching the silkscreen follow the convention in
# enclustra_mercury_kx2.py and remove the trap.
#
# All 68 signal pins verified against the manual's pin table, and audited clash-free
# against _io, 2026-08-15.
_connectors = [
    ("J9", {
         3 : "D16",       4 : "E16",
         5 : "F14",       6 : "F13",
         7 : "E14",       8 : "E13",
         9 : "D15",      10 : "D14",
        11 : "B13",      12 : "C13",
        13 : "A14",      14 : "A13",
        15 : "C15",      16 : "C14",
        17 : "A16",      18 : "A15",
        19 : "B16",      20 : "B15",
        21 : "B18",      22 : "B17",
        23 : "A19",      24 : "A18",
        25 : "C19",      26 : "C18",
        27 : "A20",      28 : "B20",
        29 : "C17",      30 : "D17",
        31 : "D19",      32 : "E19",
        33 : "E18",      34 : "F18",
        35 : "E17",      36 : "F16",
    }),
    ("J10", {
         3 : "P17",       4 : "N17",
         5 : "R19",       6 : "P19",
         7 : "T18",       8 : "R18",
         9 : "U21",      10 : "T21",
        11 : "V22",      12 : "U22",
        13 : "V20",      14 : "U20",
        15 : "W22",      16 : "W21",
        17 : "Y22",      18 : "Y21",
        19 : "AA21",     20 : "AA20",
        21 : "AB22",     22 : "AB21",
        23 : "AB20",     24 : "AA19",
        25 : "W20",      26 : "W19",
        27 : "AB18",     28 : "AA18",
        29 : "V19",      30 : "V18",
        31 : "W17",      32 : "V17",
        33 : "U18",      34 : "U17",
        35 : "R14",      36 : "P14",
    }),
]

# Platform -----------------------------------------------------------------------------------------
class Platform(Xilinx7SeriesPlatform):
    default_clk_name   = "clk50"
    default_clk_period = 1e9/50e6

    def __init__(self):
        Xilinx7SeriesPlatform.__init__(self, "xc7a35t-fgg484-2", _io, toolchain="vivado")
        self.toolchain.additional_commands = ["write_cfgmem -force -format bin -interface spix4 -size 16 -loadbit \"up 0x0 {build_name}.bit\" -file {build_name}.bin"]
        self.add_platform_command("set_property INTERNAL_VREF 0.750 [get_iobanks 34]")

        self.toolchain.bitstream_commands = [
            "set_property BITSTREAM.CONFIG.SPI_BUSWIDTH 4 [current_design]",
            "set_property BITSTREAM.CONFIG.CONFIGRATE 16 [current_design]",
            "set_property BITSTREAM.GENERAL.COMPRESS TRUE [current_design]",
            "set_property CFGBVS VCCO [current_design]",
            "set_property CONFIG_VOLTAGE 3.3 [current_design]",
        ]

        self.toolchain.additional_commands = [
            # Non-Multiboot SPI-Flash bitstream generation.
            "write_cfgmem -force -format bin -interface spix4 -size 16 -loadbit \"up 0x0 {build_name}.bit\" -file {build_name}.bin",

            # Multiboot SPI-Flash Operational bitstream generation.
            "set_property BITSTREAM.CONFIG.TIMER_CFG 0x0001fbd0 [current_design]",
            "set_property BITSTREAM.CONFIG.CONFIGFALLBACK Enable [current_design]",
            "write_bitstream -force {build_name}_operational.bit ",
            "write_cfgmem -force -format bin -interface spix4 -size 16 -loadbit \"up 0x0 {build_name}_operational.bit\" -file {build_name}_operational.bin",

            # Multiboot SPI-Flash Fallback bitstream generation.
            "set_property BITSTREAM.CONFIG.NEXT_CONFIG_ADDR 0x00400000 [current_design]",
            "write_bitstream -force {build_name}_fallback.bit ",
            "write_cfgmem -force -format bin -interface spix4 -size 16 -loadbit \"up 0x0 {build_name}_fallback.bit\" -file {build_name}_fallback.bin"
        ]

    def detect_ftdi_chip(self):
        lsusb_log = subprocess.run(['lsusb'], capture_output=True, text=True)
        for ftdi_chip in ["ft232", "ft2232", "ft4232"]:
            if f"Future Technology Devices International, Ltd {ftdi_chip.upper()}" in lsusb_log.stdout:
                return ftdi_chip
        return None

    def create_programmer(self, name="openfpgaloader"):
        ftdi_chip = self.detect_ftdi_chip()
        return OpenFPGALoader(cable=ftdi_chip, fpga_part=f"xc7a35tfgg484", freq=30e6)

    def do_finalize(self, fragment):
        Xilinx7SeriesPlatform.do_finalize(self, fragment)
        self.add_period_constraint(self.lookup_request("clk50", loose=True), 1e9/50e6)

