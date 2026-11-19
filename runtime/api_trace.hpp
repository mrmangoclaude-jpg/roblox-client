#pragma once
#include <string>

struct lua_State;

// Opt-in diagnostics: when ROVE_TRACE_API_FILE names a file, every instance member read/write, Instance.new and
// wait made by game scripts (not the runtime's own bootstrap code) is appended to it with the calling position.
// A polling loop repeats the same few lines, which shows what a script is waiting for.
bool api_trace_enabled();
void api_trace(lua_State* L, const char* kind, const std::string& what);
// Samples the running thread's top frames (including C functions) when a CPU quantum expires.
void api_trace_stack(lua_State* L);
// Diagnostic tools (not part of the product) may set this to observe every VM interrupt site: calls, returns and
// loop back-edges. It stays null in normal runs.
extern void (*api_trace_interrupt_hook)(lua_State*);
