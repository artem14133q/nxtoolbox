// Console information from libnx services. Compiled only with devkitA64 (lives in source/).
// Every service is optional: whatever cannot be read stays "unknown".
#include <switch.h>
#include <stdio.h>
#include <string.h>
#include <unistd.h>
#include <netinet/in.h>
#include <arpa/inet.h>
#include "sysinfo_hw.h"

// Atmosphere's own spl configuration items (not in libnx)
static constexpr u32 EXO_API_VERSION = 65000;
static constexpr u32 EXO_EMUMMC_TYPE = 65007;

// Sensor and fan device codes (firmware 10.0.0+)
static constexpr u32 TS_DEVICE_INTERNAL = 0x41000001;   // board (PCB) side
static constexpr u32 TS_DEVICE_EXTERNAL = 0x41000002;   // SoC side
static constexpr u32 FAN_DEVICE = 0x3D000001;

static bool s_initialized = false;
static bool s_set, s_setsys, s_setcal, s_spl, s_psm, s_ts, s_clk, s_nifm, s_ns;
static bool s_fan_open = false;
static FanController s_fan;
static sysinfo_t s_static;                               // values that never change

static const char *model_name(const u64 hw) {
    switch (hw) {
        case 0:  return "Switch (Erista)";
        case 1:  return "Switch (Copper)";
        case 2:  return "Switch Lite";
        case 3:  return "Switch (Mariko)";
        case 4:  return "Switch (Calcio)";
        case 5:  return "Switch OLED";
        default: return "Unknown";
    }
}

static const char *region_name(const SetRegion r) {
    static const char *const names[] = { "Japan", "Americas", "Europe", "Australia",
                                         "China", "Korea", "Taiwan" };
    return (unsigned)r < sizeof(names) / sizeof(names[0]) ? names[r] : "Unknown";
}

static void read_static() {
    sysinfo_t *s = &s_static;
    memset(s, 0, sizeof(*s));
    s->emummc = -1;
    s->retail = -1;

    u64 v = 0;
    if (s_spl) {
        if (R_SUCCEEDED(splGetConfig(SplConfigItem_HardwareType, &v)))
            snprintf(s->model, sizeof(s->model), "%s", model_name(v));
        if (R_SUCCEEDED(splGetConfig(SplConfigItem_IsRetail, &v)))
            s->retail = v != 0;
        if (R_SUCCEEDED(splGetConfig((SplConfigItem)EXO_API_VERSION, &v)))
            snprintf(s->atmosphere, sizeof(s->atmosphere), "%u.%u.%u",
                     (unsigned)((v >> 56) & 0xFF), (unsigned)((v >> 48) & 0xFF),
                     (unsigned)((v >> 40) & 0xFF));
        if (R_SUCCEEDED(splGetConfig((SplConfigItem)EXO_EMUMMC_TYPE, &v)))
            s->emummc = v != 0;
    }
    if (s_setsys) {
        SetSysFirmwareVersion fw;
        if (R_SUCCEEDED(setsysGetFirmwareVersion(&fw)))
            snprintf(s->firmware, sizeof(s->firmware), "%s", fw.display_version);
        SetSysDeviceNickName nick;
        if (R_SUCCEEDED(setsysGetDeviceNickname(&nick)))
            snprintf(s->nickname, sizeof(s->nickname), "%s", nick.nickname);
    }
    if (!s->firmware[0]) {
        const u32 h = hosversionGet();
        snprintf(s->firmware, sizeof(s->firmware), "%u.%u.%u",
                 HOSVER_MAJOR(h), HOSVER_MINOR(h), HOSVER_MICRO(h));
    }
    if (s_setcal) {
        SetCalSerialNumber sn;
        if (R_SUCCEEDED(setcalGetSerialNumber(&sn)))
            snprintf(s->serial, sizeof(s->serial), "%s", sn.number);
    }
    if (s_set) {
        SetRegion region;
        if (R_SUCCEEDED(setGetRegionCode(&region)))
            snprintf(s->region, sizeof(s->region), "%s", region_name(region));
        u64 lang = 0;
        if (R_SUCCEEDED(setGetSystemLanguage(&lang))) {
            char code[9] = {};
            memcpy(code, &lang, sizeof(lang));            // the code is stored as text: "en-US"
            snprintf(s->language, sizeof(s->language), "%s", code);
        }
    }
}

static void init_services() {
    if (s_initialized) return;
    s_initialized = true;
    s_set    = R_SUCCEEDED(setInitialize());
    s_setsys = R_SUCCEEDED(setsysInitialize());
    s_setcal = R_SUCCEEDED(setcalInitialize());
    s_spl    = R_SUCCEEDED(splInitialize());
    s_psm    = R_SUCCEEDED(psmInitialize());
    s_ts     = R_SUCCEEDED(tsInitialize());
    s_clk    = hosversionAtLeast(8, 0, 0) && R_SUCCEEDED(clkrstInitialize());
    s_nifm   = R_SUCCEEDED(nifmInitialize(NifmServiceType_User));
    s_ns     = R_SUCCEEDED(nsInitialize());
    timeInitialize();
    if (hosversionAtLeast(10, 0, 0) && R_SUCCEEDED(fanInitialize()))
        s_fan_open = R_SUCCEEDED(fanOpenController(&s_fan, FAN_DEVICE));
    read_static();
}

static double temperature(const u32 device, const TsLocation old_location) {
    if (hosversionAtLeast(10, 0, 0)) {
        TsSession session;
        float t = 0;
        if (R_FAILED(tsOpenSession(&session, device))) return SYSINFO_NO_VALUE;
        const Result rc = tsSessionGetTemperature(&session, &t);
        tsSessionClose(&session);
        return R_SUCCEEDED(rc) ? t : SYSINFO_NO_VALUE;
    }
    s32 t = 0;
    return R_SUCCEEDED(tsGetTemperature(old_location, &t)) ? t : SYSINFO_NO_VALUE;
}

static int clock_mhz(const PcvModuleId module) {
    ClkrstSession session;
    u32 hz = 0;
    if (R_FAILED(clkrstOpenSession(&session, module, 3))) return -1;
    const Result rc = clkrstGetClockRate(&session, &hz);
    clkrstCloseSession(&session);
    return R_SUCCEEDED(rc) ? (int)(hz / 1000000) : -1;
}

void sysinfo_hw_read(sysinfo_t *out) {
    init_services();
    *out = s_static;

    // Mode
    out->docked = appletGetOperationMode() == AppletOperationMode_Console;
    out->boost = appletGetPerformanceMode() == ApmPerformanceMode_Boost;

    // Power
    out->battery = out->charger = out->power_ok = -1;
    out->battery_health = SYSINFO_NO_VALUE;
    if (s_psm) {
        u32 pct = 0;
        if (R_SUCCEEDED(psmGetBatteryChargePercentage(&pct))) out->battery = (int)pct;
        double age = 0;
        if (R_SUCCEEDED(psmGetBatteryAgePercentage(&age))) out->battery_health = age;
        PsmChargerType charger;
        if (R_SUCCEEDED(psmGetChargerType(&charger))) out->charger = (int)charger;
        bool enough = false;
        if (R_SUCCEEDED(psmIsEnoughPowerSupplied(&enough))) out->power_ok = enough;
    }

    // Thermal
    out->temp_soc = out->temp_pcb = out->fan = SYSINFO_NO_VALUE;
    if (s_ts) {
        out->temp_pcb = temperature(TS_DEVICE_INTERNAL, TsLocation_Internal);
        out->temp_soc = temperature(TS_DEVICE_EXTERNAL, TsLocation_External);
    }
    float level = 0;
    if (s_fan_open && R_SUCCEEDED(fanControllerGetRotationSpeedLevel(&s_fan, &level)))
        out->fan = level * 100.0;

    // Clocks
    out->cpu_mhz = out->gpu_mhz = out->mem_mhz = -1;
    if (s_clk) {
        out->cpu_mhz = clock_mhz(PcvModuleId_CpuBus);
        out->gpu_mhz = clock_mhz(PcvModuleId_GPU);
        out->mem_mhz = clock_mhz(PcvModuleId_EMC);
    }

    // Memory and storage
    u64 v = 0;
    out->ram_used = R_SUCCEEDED(svcGetInfo(&v, InfoType_UsedMemorySize, CUR_PROCESS_HANDLE, 0)) ? (int64_t)v : -1;
    out->ram_total = R_SUCCEEDED(svcGetInfo(&v, InfoType_TotalMemorySize, CUR_PROCESS_HANDLE, 0)) ? (int64_t)v : -1;
    out->sd_free = out->sd_total = out->nand_free = out->nand_total = -1;
    if (s_ns) {
        s64 size = 0;
        if (R_SUCCEEDED(nsGetFreeSpaceSize(NcmStorageId_SdCard, &size)))       out->sd_free = size;
        if (R_SUCCEEDED(nsGetTotalSpaceSize(NcmStorageId_SdCard, &size)))      out->sd_total = size;
        if (R_SUCCEEDED(nsGetFreeSpaceSize(NcmStorageId_BuiltInUser, &size)))  out->nand_free = size;
        if (R_SUCCEEDED(nsGetTotalSpaceSize(NcmStorageId_BuiltInUser, &size))) out->nand_total = size;
    }

    // Network
    out->net_type = out->wifi_bars = out->online = -1;
    if (s_nifm) {
        NifmInternetConnectionType type;
        NifmInternetConnectionStatus status;
        u32 bars = 0;
        if (R_SUCCEEDED(nifmGetInternetConnectionStatus(&type, &bars, &status))) {
            out->net_type = (int)type;
            out->wifi_bars = (int)bars;
            out->online = status == NifmInternetConnectionStatus_Connected;
        } else {
            out->net_type = 0;                            // no connection at all
            out->online = 0;
        }
    }
    const struct in_addr ip = { .s_addr = (in_addr_t)gethostid() };
    snprintf(out->ip, sizeof(out->ip), "%s", out->net_type > 0 ? inet_ntoa(ip) : "");

    // Time
    u64 now = 0;
    TimeCalendarTime cal;
    TimeCalendarAdditionalInfo extra;
    if (R_SUCCEEDED(timeGetCurrentTime(TimeType_UserSystemClock, &now)) &&
        R_SUCCEEDED(timeToCalendarTimeWithMyRule(now, &cal, &extra))) {
        snprintf(out->date, sizeof(out->date), "%04u-%02u-%02u",
                 (unsigned)cal.year, (unsigned)cal.month, (unsigned)cal.day);
        snprintf(out->time, sizeof(out->time), "%02u:%02u:%02u",
                 (unsigned)cal.hour, (unsigned)cal.minute, (unsigned)cal.second);
    }
    out->uptime_s = (int64_t)(armTicksToNs(armGetSystemTick()) / 1000000000ULL);
}