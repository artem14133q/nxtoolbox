// Console information: thin layer between the sysinfo MicroPython module and libnx services.
// This header must NOT include <switch.h>: the qstr generator reads it on the host PC.
#pragma once
#include <stdint.h>
#include <stdbool.h>

#define SYSINFO_NO_VALUE (-1000.0)   // "unknown" for the floating point fields

// Unknown integers are negative, unknown strings are empty
typedef struct {
    // console
    char    model[32];          // "Switch OLED"
    char    serial[32];
    char    nickname[128];
    char    region[16];
    char    language[16];       // "en-US"
    int     docked;             // 1 docked (TV), 0 handheld
    int     boost;              // 1 boost/performance mode, 0 normal
    // firmware
    char    firmware[32];       // "18.1.0"
    char    atmosphere[16];     // "1.8.0", "" if not detected
    int     emummc;             // 1 emuMMC, 0 sysMMC
    int     retail;             // 1 retail unit, 0 development unit
    // power
    int     battery;            // charge, %
    double  battery_health;     // capacity compared to a new battery, %
    int     charger;            // 0 none, 1 charger, 2 low-power charger, 3 not supported
    int     power_ok;           // 1 the charger supplies enough power
    // thermal
    double  temp_soc;           // °C
    double  temp_pcb;           // °C
    double  fan;                // rotation level, %
    // clocks, MHz
    int     cpu_mhz, gpu_mhz, mem_mhz;
    // memory and storage, bytes
    int64_t ram_used, ram_total;        // this app
    int64_t sd_free, sd_total;
    int64_t nand_free, nand_total;      // internal storage (user partition)
    // network
    int     net_type;           // 0 none, 1 Wi-Fi, 2 Ethernet
    int     wifi_bars;          // 0..3
    int     online;             // 1 internet connection is up
    char    ip[16];
    // time
    char    date[16];           // "2026-09-27"
    char    time[16];           // "14:03:22"
    int64_t uptime_s;
} sysinfo_t;

void sysinfo_hw_read(sysinfo_t *out);