#pragma once

struct lua_State;

// The Roblox utf8 library has three members that standalone Luau lacks: graphemes, nfcnormalize and nfdnormalize.
// Adds them to the table on top of the stack (the utf8 library table).
void install_utf8_extras(lua_State* L);
