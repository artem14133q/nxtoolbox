// Python module `sysinfo`: information about the console (see sysinfo_hw.h).
// No libnx headers here, only sysinfo_hw.h.
#include <string.h>
#include "py/runtime.h"
#include "py/obj.h"
#include "sysinfo_hw.h"

// Unknown values become None
static void put_str(const mp_obj_t d, const qstr key, const char *value) {
    mp_obj_dict_store(d, MP_OBJ_NEW_QSTR(key),
                      value[0] ? mp_obj_new_str(value, strlen(value)) : mp_const_none);
}

static void put_int(const mp_obj_t d, const qstr key, const int64_t value) {
    mp_obj_dict_store(d, MP_OBJ_NEW_QSTR(key),
                      value >= 0 ? mp_obj_new_int_from_ll(value) : mp_const_none);
}

static void put_float(const mp_obj_t d, const qstr key, const double value) {
    mp_obj_dict_store(d, MP_OBJ_NEW_QSTR(key),
                      value > SYSINFO_NO_VALUE + 1 ? mp_obj_new_float(value) : mp_const_none);
}

static void put_bool(const mp_obj_t d, const qstr key, const int value) {
    mp_obj_dict_store(d, MP_OBJ_NEW_QSTR(key),
                      value >= 0 ? mp_obj_new_bool(value) : mp_const_none);
}

// sysinfo.read() -> dict; see stubs/sysinfo.pyi for the keys
static mp_obj_t mod_read() {
    static sysinfo_t s;
    sysinfo_hw_read(&s);

    const mp_obj_t d = mp_obj_new_dict(40);
    put_str(d, MP_QSTR_model, s.model);
    put_str(d, MP_QSTR_serial, s.serial);
    put_str(d, MP_QSTR_nickname, s.nickname);
    put_str(d, MP_QSTR_region, s.region);
    put_str(d, MP_QSTR_language, s.language);
    put_bool(d, MP_QSTR_docked, s.docked);
    put_bool(d, MP_QSTR_boost, s.boost);

    put_str(d, MP_QSTR_firmware, s.firmware);
    put_str(d, MP_QSTR_atmosphere, s.atmosphere);
    put_bool(d, MP_QSTR_emummc, s.emummc);
    put_bool(d, MP_QSTR_retail, s.retail);

    put_int(d, MP_QSTR_battery, s.battery);
    put_float(d, MP_QSTR_battery_health, s.battery_health);
    put_int(d, MP_QSTR_charger, s.charger);
    put_bool(d, MP_QSTR_power_ok, s.power_ok);

    put_float(d, MP_QSTR_temp_soc, s.temp_soc);
    put_float(d, MP_QSTR_temp_pcb, s.temp_pcb);
    put_float(d, MP_QSTR_fan, s.fan);

    put_int(d, MP_QSTR_cpu_mhz, s.cpu_mhz);
    put_int(d, MP_QSTR_gpu_mhz, s.gpu_mhz);
    put_int(d, MP_QSTR_mem_mhz, s.mem_mhz);

    put_int(d, MP_QSTR_ram_used, s.ram_used);
    put_int(d, MP_QSTR_ram_total, s.ram_total);
    put_int(d, MP_QSTR_sd_free, s.sd_free);
    put_int(d, MP_QSTR_sd_total, s.sd_total);
    put_int(d, MP_QSTR_nand_free, s.nand_free);
    put_int(d, MP_QSTR_nand_total, s.nand_total);

    put_int(d, MP_QSTR_net_type, s.net_type);
    put_int(d, MP_QSTR_wifi_bars, s.wifi_bars);
    put_bool(d, MP_QSTR_online, s.online);
    put_str(d, MP_QSTR_ip, s.ip);

    put_str(d, MP_QSTR_date, s.date);
    put_str(d, MP_QSTR_time, s.time);
    put_int(d, MP_QSTR_uptime, s.uptime_s);
    return d;
}
static MP_DEFINE_CONST_FUN_OBJ_0(mod_read_obj, mod_read);

static const mp_rom_map_elem_t sysinfo_module_globals_table[] = {
    { MP_ROM_QSTR(MP_QSTR___name__), MP_ROM_QSTR(MP_QSTR_sysinfo) },
    { MP_ROM_QSTR(MP_QSTR_read),     MP_ROM_PTR(&mod_read_obj) },

    // charger values
    { MP_ROM_QSTR(MP_QSTR_CHARGER_NONE),        MP_ROM_INT(0) },
    { MP_ROM_QSTR(MP_QSTR_CHARGER_OK),          MP_ROM_INT(1) },
    { MP_ROM_QSTR(MP_QSTR_CHARGER_LOW_POWER),   MP_ROM_INT(2) },
    { MP_ROM_QSTR(MP_QSTR_CHARGER_UNSUPPORTED), MP_ROM_INT(3) },
    // net_type values
    { MP_ROM_QSTR(MP_QSTR_NET_NONE),     MP_ROM_INT(0) },
    { MP_ROM_QSTR(MP_QSTR_NET_WIFI),     MP_ROM_INT(1) },
    { MP_ROM_QSTR(MP_QSTR_NET_ETHERNET), MP_ROM_INT(2) },
};
static MP_DEFINE_CONST_DICT(sysinfo_module_globals, sysinfo_module_globals_table);

const mp_obj_module_t sysinfo_user_cmodule = {
    .base = { &mp_type_module },
    .globals = (mp_obj_dict_t *)&sysinfo_module_globals,
};

MP_REGISTER_MODULE(MP_QSTR_sysinfo, sysinfo_user_cmodule);