"""IDE hints: the built-in `sysinfo` module (information about the console).

sysinfo.read() returns a dict. Values that cannot be read on this console/firmware are None.
"""
from typing import Dict, Optional, Union

CHARGER_NONE: int         # charger values
CHARGER_OK: int
CHARGER_LOW_POWER: int
CHARGER_UNSUPPORTED: int
NET_NONE: int             # net_type values
NET_WIFI: int
NET_ETHERNET: int


def read() -> Dict[str, Optional[Union[str, int, float, bool]]]:
    """Keys:
    model, serial, nickname, region, language (str); docked, boost (bool);
    firmware, atmosphere (str); emummc, retail (bool);
    battery (int %), battery_health (float %), charger (int, CHARGER_*), power_ok (bool);
    temp_soc, temp_pcb (float degrees C), fan (float %);
    cpu_mhz, gpu_mhz, mem_mhz (int);
    ram_used, ram_total (this app), sd_free, sd_total, nand_free, nand_total (int bytes);
    net_type (int, NET_*), wifi_bars (int 0..3), online (bool), ip (str);
    date ("YYYY-MM-DD"), time ("HH:MM:SS"), uptime (int seconds)."""
    ...
