#include "api_trace.hpp"
#include <lua.h>
#include <cstdio>
#include <cstdlib>
#include <cstring>

namespace {
FILE* trace_file() {
    static FILE* file = [] {
        const char* path = std::getenv("ROVE_TRACE_API_FILE");
        return path && *path ? std::fopen(path, "a") : nullptr;
    }();
    return file;
}
}

bool api_trace_enabled() { return trace_file() != nullptr; }

void (*api_trace_interrupt_hook)(lua_State*) = nullptr;

void api_trace_stack(lua_State* L) {
    FILE* file = trace_file();
    static size_t samples = 0;
    if (!file || samples >= 3000) return;
    {
        lua_Debug top{};
        if (lua_getinfo(L, 0, "s", &top) && top.short_src && std::strncmp(top.short_src, "script-runtime", 14) == 0) return;
    }
    ++samples;
    std::string line;
    for (int level = 0; level < 7; ++level) {
        lua_Debug ar{};
        if (!lua_getinfo(L, level, "snl", &ar)) break;
        if (!line.empty()) line += " < ";
        line += std::string(ar.short_src ? ar.short_src : "?") + ":" + std::to_string(ar.currentline);
        if (ar.name) line += std::string("(") + ar.name + ")";
    }
    std::fprintf(file, "stack %s\n", line.c_str());
    std::fflush(file);
}

void api_trace(lua_State* L, const char* kind, const std::string& what) {
    FILE* file = trace_file();
    static size_t lines = 0;
    if (!file || lines >= 400000) return;
    std::string caller = "?";
    for (int level = 1; level <= 8; ++level) {
        lua_Debug ar{};
        if (!lua_getinfo(L, level, "sl", &ar)) break;
        const char* source = ar.short_src ? ar.short_src : "?";
        if (std::strcmp(source, "[C]") != 0) {
            caller = std::string(source) + ":" + std::to_string(ar.currentline);
            break;
        }
    }
    if (caller.rfind("script-runtime", 0) == 0 || caller.rfind("=script-runtime", 0) == 0
        || caller.rfind("persistent-source", 0) == 0) return;
    ++lines;
    std::fprintf(file, "%s %s @ %s\n", kind, what.c_str(), caller.c_str());
    std::fflush(file);
}
