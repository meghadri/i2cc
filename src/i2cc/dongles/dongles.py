import time
from dataclasses import dataclass
from typing import Callable, NamedTuple

import serial
from i2c_api import I2CLogger, I2CMaster
from i2capi_i2cdriver import I2CMasterI2CDriver
from i2cdriver import I2CDriver
from serial.serialutil import SerialTimeoutException
from serial.tools.list_ports_common import ListPortInfo

from i2cc.dummy_i2cmaster import DummyI2CMaster


@dataclass(frozen=True)
class I2CMasterContainer:
    driver: I2CMaster
    port: str
    display_name: str


class DongleRef(NamedTuple):
    make_and_model: str
    cons: Callable[[str, I2CLogger], I2CMasterContainer]
    comp_port_filter: dict[str, Callable[[ListPortInfo], bool]]


def mk_I2CMasterI2CDriver(port: str, logger: I2CLogger) -> I2CMasterContainer:
    if check_device_port(port, logger):
        return I2CMasterContainer(
            driver=I2CMasterI2CDriver(I2CDriver(port), logger=logger), port=port, display_name="I2CDriver"
        )


def mk_DummyI2CMaster(port: str, logger: I2CLogger) -> I2CMasterContainer:
    return I2CMasterContainer(driver=DummyI2CMaster(), port=port, display_name="DummyI2CDriver")


SUPPORTED_DONGLES = [
    DongleRef(
        make_and_model="Demo :: DummyI2CDriver",
        cons=mk_DummyI2CMaster,
        comp_port_filter={
            "win32": lambda _: True,
            "cygwin": lambda _: True,
            "linux": lambda _: True,
        },
    ),
    DongleRef(
        make_and_model="Excamera Labs :: I2CDriver",
        cons=mk_I2CMasterI2CDriver,
        comp_port_filter={
            "win32": lambda _: True,
            "cygwin": lambda _: True,
            "linux": lambda p: p.product == "FT230X Basic UART",
        },
    ),
]

def check_device_port(port: str, logger: I2CLogger) -> bool:
    # On MS-Windows the COM port will be available in the drop down even if no device is actually connected
    # The `I2CDriver` class during construction tests by writing a character to the device with no write timeout
    # The write() being a blocking call, causes the program to freeze. This check here guards against that.
    # Alternatively, the i2cdriver library could be modified.

    # This replicates the logic on `I2CDriver.__init__` with a `write_timeout`
    ok: bool = True

    i2c_device = serial.Serial(port, 1000000,  write_timeout=2)
    try:
        i2c_device.reset_input_buffer()
        i2c_device.reset_output_buffer()

        written: int = i2c_device.write(b'@')
        i2c_device.flush()
        time.sleep(.250)    # wait for 250 ms

    except SerialTimeoutException:
        ok = False
        print(f'Device not found on port {port}')
    finally:
        i2c_device.close()

    return ok


SUPPORTED_DONGLES_DICT = {a.make_and_model: a for a in SUPPORTED_DONGLES}
