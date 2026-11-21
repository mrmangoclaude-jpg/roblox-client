#include "api_trace.hpp"
#include <lua.h>
#include <lualib.h>
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

void api_trace_raw(const char* kind, const std::string& what) {
    FILE* file = trace_file();
    if (!file) return;
    std::fprintf(file, "%s %s\n", kind, what.c_str());
    std::fflush(file);
}

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
    // A C function on top (string.gsub, string.find, ...) is what a hot loop is chewing on: show its arguments (string lengths with a
    // short escaped prefix, numbers, other types). Only strings are read; lua_tolstring would convert a number in place.
    {
        lua_Debug top{};
        if (lua_getinfo(L, 0, "s", &top) && top.short_src && std::strcmp(top.short_src, "[C]") == 0) {
            const int count = lua_gettop(L);
            for (int i = 1; i <= count && i <= 4; ++i) {
                const int type = lua_type(L, i);
                line += " | a" + std::to_string(i) + "=";
                if (type == LUA_TSTRING) {
                    size_t length = 0;
                    const char* text = lua_tolstring(L, i, &length);
                    line += "str(" + std::to_string(length) + ")'";
                    for (size_t k = 0; k < length && k < 24; ++k) {
                        const unsigned char c = static_cast<unsigned char>(text[k]);
                        if (c >= 32 && c < 127 && c != '\'') line += static_cast<char>(c);
                        else { char hex[8]; std::snprintf(hex, sizeof hex, "\\x%02x", c); line += hex; }
                    }
                    line += "'";
                } else if (type == LUA_TNUMBER) {
                    line += "num(" + std::to_string(lua_tonumber(L, i)) + ")";
                } else {
                    line += lua_typename(L, type);
                }
            }
        }
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
    std::string detail = what;
    // Writes carry the assigned value at stack index 3; recording it reveals the
    // exact UDim2/CFrame constants Luraph feeds into its stage-key derivation.
    if (std::strcmp(kind, "set") == 0 && lua_gettop(L) >= 3) {
        lua_pushvalue(L, 3);
        size_t length = 0;
        const char* text = luaL_tolstring(L, -1, &length);
        if (text) detail += "=" + std::string(text, length < 120 ? length : 120);
        lua_pop(L, 2);
    }
    ++lines;
    std::fprintf(file, "%s %s @ %s\n", kind, detail.c_str(), caller.c_str());
    std::fflush(file);
}
