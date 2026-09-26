// Interface between the nxapp MicroPython module (launcher API) and source/main.c.
// This header must NOT include <switch.h>: the qstr generator reads it on the host PC.
#pragma once
#include <stddef.h>

// What the app does after the launcher exits
void app_request_run(const char *py_path);   // run a script, e.g. "/switch/NXToolBox/scripts/x.py"
void app_request_quit();                 // exit the app
void app_request_restart();              // run the launcher again (e.g. after an update)

// Handles at most one pending network connection. Returns true and fills kind/text
// if something happened:
//   "upload" - a file was uploaded, text = path relative to /switch/NXToolBox
//   "run"    - a script arrived over the network; the launcher must exit so it can run
//   "info"   - a message (e.g. a rejected connection)
bool app_poll_network(char *kind, size_t kind_size, char *text, size_t text_size);

// A string kept in memory between launcher runs (current folder, selection...)
const char *app_get_state();
void        app_set_state(const char *s, size_t len);

// For display
const char *app_ip();        // "" if the network is unavailable
int         app_port();
const char *app_password();