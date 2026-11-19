#include "json_bindings.hpp"
#include "json.hpp"
#include <lualib.h>

#include <cmath>
#include <cstdint>
#include <stdexcept>
#include <string>

namespace json_bindings {
namespace {
using Json = nlohmann::json;
// USSI's API dump is multi-megabyte JSON with hundreds of thousands of
// values. Keep parsing, encoding, and Lua table conversion bounded.
constexpr size_t kMaxInput = 16 * 1024 * 1024;
constexpr size_t kMaxOutput = 16 * 1024 * 1024;
constexpr size_t kMaxItems = 1'000'000;
constexpr unsigned kMaxDepth = 128;

struct Budget { size_t items = 0; };

Json to_json(lua_State* L, int index, unsigned depth, Budget& budget,
             const void* ancestors[], unsigned ancestor_count) {
    if (depth > kMaxDepth) throw std::runtime_error("JSON nesting exceeds 128 levels");
    if (++budget.items > kMaxItems) throw std::runtime_error("JSON value exceeds 1000000 items");
    switch (lua_type(L, index)) {
        case LUA_TNIL: return nullptr;
        case LUA_TBOOLEAN: return lua_toboolean(L, index) != 0;
        case LUA_TNUMBER: {
            const double value = lua_tonumber(L, index);
            if (!std::isfinite(value)) throw std::runtime_error("JSON cannot encode NaN or infinity");
            // Avoid turning ordinary integral Luau numbers into a JSON decimal
            // such as 7.0 while retaining exact IEEE-754 integers.
            constexpr double kMaxExactInteger = 9007199254740991.0;
            if (std::floor(value) == value && std::abs(value) <= kMaxExactInteger)
                return static_cast<int64_t>(value);
            return value;
        }
        case LUA_TSTRING: {
            size_t length = 0;
            const char* value = lua_tolstring(L, index, &length);
            if (length > kMaxInput) throw std::runtime_error("JSON string exceeds 16 MiB");
            return std::string(value, length);
        }
        case LUA_TTABLE: break;
        default: throw std::runtime_error(std::string("JSON cannot encode ") + lua_typename(L, lua_type(L, index)));
    }

    const void* identity = lua_topointer(L, index);
    for (unsigned i = 0; i < ancestor_count; ++i)
        if (ancestors[i] == identity) throw std::runtime_error("JSON cannot encode cyclic tables");
    if (ancestor_count >= kMaxDepth) throw std::runtime_error("JSON nesting exceeds 128 levels");
    const int table = lua_absindex(L, index);
    size_t entries = 0, max_index = 0;
    bool has_array_key = false, has_object_key = false;
    lua_pushnil(L);
    while (lua_next(L, table) != 0) {
        ++entries;
        if (entries > kMaxItems - budget.items) {
            lua_pop(L, 2);
            throw std::runtime_error("JSON value exceeds 1000000 items");
        }
        int key_type = lua_type(L, -2);
        if (key_type == LUA_TNUMBER) {
            double key = lua_tonumber(L, -2);
            if (!std::isfinite(key) || key < 1 || std::floor(key) != key
                || key > static_cast<double>(kMaxItems)) {
                lua_pop(L, 2);
                throw std::runtime_error("JSON array indices must be positive integers");
            }
            has_array_key = true;
            if (static_cast<size_t>(key) > max_index) max_index = static_cast<size_t>(key);
        } else if (key_type == LUA_TSTRING) {
            has_object_key = true;
        } else {
            lua_pop(L, 2);
            throw std::runtime_error("JSON object keys must be strings");
        }
        lua_pop(L, 1);
    }
    if (has_array_key && has_object_key)
        throw std::runtime_error("JSON table cannot mix array and object keys");
    if (has_array_key && max_index != entries)
        throw std::runtime_error("JSON array indices must be contiguous from 1");

    const void* nested[kMaxDepth];
    for (unsigned i = 0; i < ancestor_count; ++i) nested[i] = ancestors[i];
    nested[ancestor_count] = identity;
    if (has_array_key || entries==0) {
        Json result = Json::array();
        for (size_t i = 1; i <= max_index; ++i) {
            lua_rawgeti(L, table, static_cast<int>(i));
            result.push_back(to_json(L, -1, depth + 1, budget, nested, ancestor_count + 1));
            lua_pop(L, 1);
        }
        return result;
    }

    Json result = Json::object();
    lua_pushnil(L);
    while (lua_next(L, table) != 0) {
        size_t length = 0;
        const char* key = lua_tolstring(L, -2, &length);
        if (!key) { lua_pop(L, 2); throw std::runtime_error("JSON object keys must be strings"); }
        if (length > kMaxInput) { lua_pop(L, 2); throw std::runtime_error("JSON key exceeds 16 MiB"); }
        std::string owned_key(key, length);
        Json value = to_json(L, -1, depth + 1, budget, nested, ancestor_count + 1);
        result[std::move(owned_key)] = std::move(value);
        lua_pop(L, 1);
    }
    return result;
}

void push_json(lua_State* L, const Json& value, unsigned depth, Budget& budget) {
    if (depth > kMaxDepth) throw std::runtime_error("JSON nesting exceeds 128 levels");
    if (++budget.items > kMaxItems) throw std::runtime_error("JSON value exceeds 1000000 items");
    if (value.is_null()) { lua_pushnil(L); return; }
    if (value.is_boolean()) { lua_pushboolean(L, value.get<bool>()); return; }
    if (value.is_number()) { lua_pushnumber(L, value.get<double>()); return; }
    if (value.is_string()) {
        const auto& text = value.get_ref<const std::string&>();
        if (text.size() > kMaxInput) throw std::runtime_error("JSON string exceeds 16 MiB");
        lua_pushlstring(L, text.data(), text.size()); return;
    }
    if (value.is_array()) {
        if (value.size() > kMaxItems - budget.items) throw std::runtime_error("JSON value exceeds 1000000 items");
        lua_createtable(L, static_cast<int>(value.size()), 0);
        int table = lua_absindex(L, -1);
        for (size_t i = 0; i < value.size(); ++i) {
            push_json(L, value[i], depth + 1, budget);
            lua_rawseti(L, table, static_cast<int>(i + 1));
        }
        return;
    }
    if (value.is_object()) {
        if (value.size() > kMaxItems - budget.items) throw std::runtime_error("JSON value exceeds 1000000 items");
        lua_createtable(L, 0, static_cast<int>(value.size()));
        int table = lua_absindex(L, -1);
        for (auto it = value.begin(); it != value.end(); ++it) {
            lua_pushlstring(L,it.key().data(),it.key().size());
            push_json(L, it.value(), depth + 1, budget);
            lua_rawset(L, table);
        }
        return;
    }
    throw std::runtime_error("unsupported JSON value");
}

void validate_parse_bounds(const char* raw, size_t length) {
    unsigned depth = 0;
    size_t elements = 0;
    bool in_string = false, escaped = false;
    for (size_t i = 0; i < length; ++i) {
        const char ch = raw[i];
        if (in_string) {
            if (escaped) escaped = false;
            else if (ch == '\\') escaped = true;
            else if (ch == '"') in_string = false;
            continue;
        }
        if (ch == '"') { in_string = true; continue; }
        if (ch == '[' || ch == '{') {
            if (++depth > kMaxDepth) throw std::runtime_error("JSON nesting exceeds 128 levels");
            if (++elements > kMaxItems) throw std::runtime_error("JSON value exceeds 1000000 items");
        } else if (ch == ']' || ch == '}') {
            if (depth) --depth;
        } else if (ch == ',') {
            if (++elements > kMaxItems) throw std::runtime_error("JSON value exceeds 1000000 items");
        }
    }
}

int encode_value(lua_State* L) {
    Json encoded;
    std::string error;
    try {
        Budget budget;
        const void* ancestors[kMaxDepth];
        encoded = to_json(L, 2, 0, budget, ancestors, 0);
    } catch (const std::exception& exception) { error = exception.what(); }
    if (!error.empty()) { luaL_error(L, "%s", error.c_str()); return 0; }
    std::string text;
    try { text = encoded.dump(-1, ' ', false, Json::error_handler_t::strict); }
    catch (const std::exception&) { luaL_error(L, "JSON string contains invalid UTF-8"); return 0; }
    if (text.size() > kMaxOutput) { luaL_error(L, "JSON output exceeds 16 MiB"); return 0; }
    lua_pushlstring(L, text.data(), text.size());
    return 1;
}

int decode_value(lua_State* L) {
    size_t length = 0;
    const char* raw = luaL_checklstring(L, 2, &length);
    if (length > kMaxInput) { luaL_error(L, "JSON input exceeds 16 MiB"); return 0; }
    try { validate_parse_bounds(raw, length); }
    catch (const std::exception& exception) {
        std::string message = exception.what();
        luaL_error(L, "%s", message.c_str());
        return 0;
    }
    Json value;
    std::string error;
    try { value = Json::parse(raw, raw + length); }
    catch (const std::exception& exception) { error = exception.what(); }
    if (!error.empty()) { luaL_error(L, "Can't parse JSON"); return 0; }
    try {
        Budget budget;
        push_json(L, value, 0, budget);
    } catch (const std::exception& exception) {
        std::string message = exception.what();
        luaL_error(L, "%s", message.c_str());
        return 0;
    }
    return 1;
}

int dispatch(lua_State* L) {
    int operation = static_cast<int>(lua_tointeger(L, lua_upvalueindex(1)));
    return operation == 0 ? encode_value(L) : decode_value(L);
}
}

bool push_method(lua_State* L, const char* name) {
    if (!name) return false;
    int operation;
    if (std::string(name) == "JSONEncode") operation = 0;
    else if (std::string(name) == "JSONDecode") operation = 1;
    else return false;
    lua_pushinteger(L, operation);
    lua_pushcclosurek(L, dispatch, name, 1, nullptr);
    return true;
}
}
