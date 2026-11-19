#pragma once
#include <string>

struct lua_State;

// Opt-in diagnostics: when ROVE_TRACE_API_FILE names a file, every instance member read/write, Instance.new and
// wait made by game scripts (not the runtime's own bootstrap code) is appended to it with the calling position.
// A polling loop repeats the same few lines, which shows what a script is waiting for.
bool api_trace_enabled();
void api_trace(lua_State* L, const char* kind, const std::string& what);
