#
# This file is part of LiteX-Boards.
#
# Copyright (c) 2026 Michael Betz <michael@betz-engineering.ch>
# SPDX-License-Identifier: BSD-2-Clause
#
# Obsidian A35 is a low cost FPGA carrier board with several SFP ports,
# many PMOD IOs and Arduino shield compatibility.
# It was developed at Berkeley Lab as a smart IO extender.
# It facilitates interfacing ADCs, DACs, sensors, UI elements or other
# peripherals to a central larger FPGA board or a PC.

from litex.build.generic_platform import Subsignal, Pins, IOStandard, Misc
from litex.build.xilinx import Xilinx7SeriesPlatform
from litex.build.openocd import OpenOCD

# IOs ----------------------------------------------------------------------------------------------

_io_common = [
    # MGTREFCLK0
    # R10: WR_CLK0 (125 MHz VCXO, DAC-tunable)
    # R11: WR_CLK0, SI5340B OUT0
    (
        "clk125",
        0,
        Subsignal("p", Pins("D6")),
        Subsignal("n", Pins("D5")),
    ),
    # R10: CLK20_VCXO (20 MHz VCXO, DAC-tunable), PAD NOT CLOCK-CAPABLE!
    # R11: CLK20_VCXO, SI5340B OUT2, PAD NOT CLOCK-CAPABLE!
    ("clk20", 0, Pins("D13"), IOStandard("LVCMOS33")),
    # MGTREFCLK1
    # R10: REF_CLK0 (Si5351A, channel 0 and 1, I2C-tunable, 2.5 kHz - 200 MHz)
    #   Note: the Si5351 needs to be configured to get HCSL compatible outputs.
    #   See Section 6.7 in the datasheet and register setting CLKx_INV.
    # R11: REF_CLK0, SI5340B OUT3
    (
        "clkmgt",
        0,
        Subsignal("p", Pins("B6")),
        Subsignal("n", Pins("B5")),
    ),
    # R10: CLK2 (Si5351A, channel 2, I2C-tunable, 2.5 kHz - 200 MHz)
    # R11: CLK2, fixed XO, 25 MHz, KC2520Z25.0000C1KX00
    ("clk2", 0, Pins("E15"), IOStandard("LVCMOS33")),
    # Gigabit Ethernet transceiver (RTL8211F-CG)
    # R10: CDCM61004RHB OSCOUT provides its 25 MHz clock
    # R11: SI5340B OUT1 provides its 25 MHz clock
    (
        "eth",
        0,
        Subsignal("rst_n", Pins("A13")),
        Subsignal("mdio", Pins("E18")),
        Subsignal("mdc", Pins("H14")),
        Subsignal("rx_ctl", Pins("D16")),
        Subsignal("rx_data", Pins("B16 C16 D14 C13")),
        Subsignal("tx_ctl", Pins("A17")),
        Subsignal("tx_data", Pins("B17 E16 E17 D18")),
        IOStandard("LVCMOS33"),
    ),
    (
        "eth_clocks",
        0,
        Subsignal("tx", Pins("D15")),
        Subsignal("rx", Pins("E13")),
        IOStandard("LVCMOS33"),
    ),
    # USB UART (FT2232HQ)
    (
        "serial",
        0,
        # FT2232 --> FPGA
        Subsignal("rx", Pins("H18")),
        # FT2232 <-- FPGA
        Subsignal("tx", Pins("F17")),
        IOStandard("LVCMOS33"),
    ),
    # FT2232 --> FPGA. To use the RTS signal, SW2 must be ON
    ("serial_rts", 0, Pins("B10"), IOStandard("LVCMOS33")),
    # SPI Boot Flash (S25FL128SAGMFI001)
    # use STARTUPE2 primitive to access the clock pin
    (
        "spiflash",
        0,
        Subsignal("cs_n", Pins("L15")),
        Subsignal("mosi", Pins("K16")),
        Subsignal("miso", Pins("L17")),
        IOStandard("LVCMOS33"),
    ),
    # I2C system bus, connected to (7 bit addresses):
    # R10:
    #   0x20: IO-extender for SFP0 and SFP1 status pins (TCA9535RTWR)
    #   0x21: IO-extender for SFP2 and SFP3 status pins (TCA9535RTWR)
    #   0x60: Clock synthesizer (Si5351A)
    #   0x50: 256Kb I2C Serial EEPROM with Pre-Programmed Serial Number (24AA256UID)
    #   0x70: I2C-switch for the 4 SFP ports (PCA9546ARGV)
    # R11:
    #   0x08: HUSB238, USB-PD trigger IC
    #   0x20: TCA9535 for SFP0-1 status, board revision, LED0-1, SI5340_IRQ_N
    #   0x21: TCA9535 for SFP2-3 status, SI5340_RSTN, 25M_CLK_DIS
    #   0x40: INA219A Voltage and Current Monitor
    #   0x50: 256Kb I2C Serial EEPROM with Pre-Programmed Serial Number (24AA256UID)
    #   0x70: I2C-switch for the 4 SFP ports (PCA9546ARGV)
    (
        "i2c_fpga",
        0,
        Subsignal("scl", Pins("H17")),
        Subsignal("sda", Pins("F14")),
        IOStandard("LVCMOS33"),
    ),
    # I2C pins of the Arduino host
    (
        "i2c_arduino",
        0,
        Subsignal("scl", Pins("J18")),
        Subsignal("sda", Pins("C12")),
        IOStandard("LVCMOS33"),
    ),
    # DDR3 DRAM chip (AS4C256M16D3)
    (
        "ddram",
        0,
        Subsignal("a", Pins(r"U2 V3 R7 P6 V2 V4 V7 T7 V8 U4 U1 U7 U6 U5 R6 M5"), IOStandard("SSTL15")),
        Subsignal("ba", Pins(r"T3 V6 R2"), IOStandard("SSTL15")),
        Subsignal("ras_n", Pins(r"R3"), IOStandard("SSTL15")),
        Subsignal("cas_n", Pins(r"T2"), IOStandard("SSTL15")),
        Subsignal("we_n", Pins(r"T4"), IOStandard("SSTL15")),
        Subsignal("cs_n", Pins(r"P5"), IOStandard("SSTL15")),
        Subsignal("dm", Pins(r"L5 M6"), IOStandard("SSTL15")),
        Subsignal("dq", Pins(r"K3 L4 K5 K6 J4 L2 J5 L3 N3 M1 N2 M4 N6 M2 P4 N4"), IOStandard("SSTL15")),
        Subsignal("dqs_p", Pins(r"K2 N1"), IOStandard("DIFF_SSTL15")),
        Subsignal("dqs_n", Pins(r"K1 P1"), IOStandard("DIFF_SSTL15")),
        Subsignal("clk_p", Pins(r"R5"), IOStandard("DIFF_SSTL15")),
        Subsignal("clk_n", Pins(r"T5"), IOStandard("DIFF_SSTL15")),
        Subsignal("cke", Pins(r"R1"), IOStandard("SSTL15")),
        Subsignal("odt", Pins(r"P3"), IOStandard("SSTL15")),
        Subsignal("reset_n", Pins(r"J6"), IOStandard("LVCMOS15")),
        Misc("SLEW=FAST"),
    ),
    (
        "sfp_tx",
        0,
        Subsignal("p", Pins("H2")),
        Subsignal("n", Pins("H1")),
    ),
    (
        "sfp_tx",
        1,
        Subsignal("p", Pins("F2")),
        Subsignal("n", Pins("F1")),
    ),
    (
        "sfp_tx",
        2,
        Subsignal("p", Pins("D2")),
        Subsignal("n", Pins("D1")),
    ),
    (
        "sfp_tx",
        3,
        Subsignal("p", Pins("B2")),
        Subsignal("n", Pins("B1")),
    ),
    (
        "sfp_rx",
        0,
        Subsignal("p", Pins("E4")),
        Subsignal("n", Pins("E3")),
    ),
    (
        "sfp_rx",
        1,
        Subsignal("p", Pins("A4")),
        Subsignal("n", Pins("A3")),
    ),
    (
        "sfp_rx",
        2,
        Subsignal("p", Pins("C4")),
        Subsignal("n", Pins("C3")),
    ),
    (
        "sfp_rx",
        3,
        Subsignal("p", Pins("G4")),
        Subsignal("n", Pins("G3")),
    ),
]

_io_R10 = [
    # 2x DAC for White Rabbit VCXO frequency control (DAC8550IDGK)
    # clk and din is shared between the 2 DACs
    # synca updates the clk125 tuning voltage
    # syncb updates the clk20 tuning voltage
    (
        "wr_dac",
        0,
        Subsignal("clk", Pins("C11")),
        Subsignal("din", Pins("B11")),
        Subsignal("synca", Pins("D11")),
        Subsignal("syncb", Pins("D10")),
        IOStandard("LVCMOS33"),
    ),
]

_io_R11 = [
    # SI5340B frequency synthesizer SPI interface
    (
        "spi_si5340",
        0,
        Subsignal("mosi", Pins("D10")),
        Subsignal("sclk", Pins("C11")),
        Subsignal("miso", Pins("B11")),
        Subsignal("cs_n", Pins("D11")),
        IOStandard("LVCMOS33"),
    )
]


# Connectors ---------------------------------------------------------------------------------------

_connectors_common = [
    # Digital Arduino host pins (D0 - D13)
    ("arduino_d", "G14 H16 A12 B12 C14 G17 G16 A15 C18 F18 C17 B15 B14 A14"),
    # Analog capable Arduino host pins connected to XADC
    # the order is: A0_P, A0_N, A2_P, A2_N, A1_P, A1_N, A3_P, A3_N
    # Analog Arduino host pins connected to XADC
    ("arduino_a_p", "D8 D9 B9 B10"),  # A0-AD0, A1-AD8, A2-AD1, A3-AD9
    ("arduino_a_n", "C8 C9 A9 A10"),  # all *_N pins are connected to GND
]

_connectors_R10 = [
    ("pmoda", "M16 N17 R18 U16 M17 N18 P18 V17"),  # J4
    ("pmodb", "T18 U17 U15 V14 R17 T17 V16 U14"),  # J5
    ("pmodc", "M15 N16 P15 K18 N14 P16 K17 L18"),  # J6
    ("pmodd", "J16 K15 F15 J14 J15 M14 G15 L14"),  # J7
    ("pmode", "U10 U9 V9 V11 V12 U12 V13 U11"),  # J14
    ("pmodf", "T13 T12 R13 T14 T15 P14 R16 R15"),  # J15
]

_connectors_R11 = [
    ("pmoda", "V12 V13 U11 V11 T12 U12 U9 V9"),  # J4
    ("pmodb", "U14 V14 T17 U17 V16 V17 U15 U16"),  # J5
    ("pmodc", "P15 P16 R18 T18 R16 R17 M14 N14"),  # J6
    ("pmodd", "J15 J16 J14 K15 K17 L18 M16 M17"),  # J7
    ("pmode", "M15 K18 N16 P18 N18 G15 F15 N17"),  # J14
    ("pmodf", "T13 U10 R13 T14 T15 P14 L14 R15"),  # J15
]


def raw_pmod_io(pmod="pmoda", iostd="LVCMOS33"):
    """use with platform.add_extension() to expose a PMOD as GPIO pins"""
    return [
        (
            pmod,
            0,
            Pins(" ".join([f"{pmod}:{i:d}" for i in range(8)])),
            IOStandard(iostd),
        )
    ]


# Platform -----------------------------------------------------------------------------------------
class Platform(Xilinx7SeriesPlatform):
    default_clk_name = "clk125"
    default_clk_period = 1e9 / 125e6

    def __init__(self, revision="1.1.0", toolchain="vivado"):
        if revision == "1.0.0":
            io = _io_common + _io_R10
            con = _connectors_common + _connectors_R10
        elif revision == "1.1.0":
            io = _io_common + _io_R11
            con = _connectors_common + _connectors_R11
        else:
            raise RuntimeError("Invalid revision")

        Xilinx7SeriesPlatform.__init__(self, "xc7a35t-csg325", io, con, toolchain=toolchain)
        self.toolchain.additional_commands = [
            (
                "write_cfgmem -force -format bin -interface spix1 -size 16 -loadbit "
                + '"up 0x0 {build_name}.bit" -file {build_name}.bin'
            )
        ]

        # clk20 is a frequency source, not a phase source, so having it enter on a non-CC pin is OK.
        self.add_platform_command("set_property CLOCK_DEDICATED_ROUTE FALSE [get_nets clk20_IBUF]")
        self.add_platform_command("set_property CONFIG_VOLTAGE 3.3 [current_design]")
        self.add_platform_command("set_property CFGBVS VCCO [current_design]")
        self.add_platform_command("set_property BITSTREAM.CONFIG.SPI_BUSWIDTH 1 [current_design]")
        self.add_platform_command("set_property BITSTREAM.CONFIG.CONFIGRATE 50 [current_design]")
        self.add_platform_command("set_property INTERNAL_VREF 0.75 [get_iobanks 34]")

    def create_programmer(self):
        return OpenOCD("openocd_xc7_ft2232.cfg", flash_proxy_basename="bscan_spi_xc7a35t.bit")

    def do_finalize(self, fragment):
        Xilinx7SeriesPlatform.do_finalize(self, fragment)
        self.add_period_constraint(self.lookup_request("clk20", loose=True), 1e9 / 20e6)
        self.add_period_constraint(self.lookup_request("clk125", loose=True), 1e9 / 125e6)
