#pragma once

struct lua_State;

// The Roblox utf8 library has three members that standalone Luau lacks: graphemes, nfcnormalize and nfdnormalize.
// Adds them to the table on top of the stack (the utf8 library table).
void install_utf8_extras(lua_State* L);

// coroutine.finally and the version()/settings() globals that standalone Luau lacks.
void install_roblox_global_extras(lua_State* L);

// Rebuilds the os library the way the real client holds it: exactly clock, date, difftime and time, in a table presized for
// four fields and filled in that order, which fixes the order pairs() visits them (clock, difftime, time, date).
void install_roblox_os_layout(lua_State* L);
