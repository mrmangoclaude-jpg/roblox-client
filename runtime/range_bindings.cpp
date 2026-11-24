#include "range_bindings.hpp"
#include "vector2_bindings.hpp"

#include <lua.h>
#include <lualib.h>
#include <cmath>
#include <limits>
#include <cstdio>
#include <cstring>
#include <algorithm>
#include <new>

namespace {
constexpr const char* kNumberRangeMeta = "LocalRuntime.NumberRange";
constexpr const char* kRectMeta = "LocalRuntime.Rect";

struct NumberRangeValue { float min, max; };
struct RectValue { float min_x, min_y, max_x, max_y; };

bool has_metatable(lua_State* L, int index, const char* name) {
    if (!lua_getmetatable(L, index)) return false;
    luaL_getmetatable(L, name);
    bool matches = lua_rawequal(L, -1, -2) != 0;
    lua_pop(L, 2);
    return matches;
}

float checked_component(lua_State* L, int index, const char* description) {
    double value = luaL_checknumber(L, index);
    if (!std::isfinite(value) || std::abs(value) > static_cast<double>(std::numeric_limits<float>::max())) {
        luaL_error(L, "%s must be finite and representable as a float", description);
    }
    return static_cast<float>(value);
}

void push_number_range(lua_State* L, float min, float max) {
    auto* value = static_cast<NumberRangeValue*>(lua_newuserdatadtor(L, sizeof(NumberRangeValue), nullptr));
    new (value) NumberRangeValue{min, max};
    luaL_getmetatable(L, kNumberRangeMeta);
    lua_setmetatable(L, -2);
}

void push_rect(lua_State* L, float min_x, float min_y, float max_x, float max_y) {
    auto* value = static_cast<RectValue*>(lua_newuserdatadtor(L, sizeof(RectValue), nullptr));
    new (value) RectValue{std::min(min_x, max_x), std::min(min_y, max_y),
                          std::max(min_x, max_x), std::max(min_y, max_y)};
    luaL_getmetatable(L, kRectMeta);
    lua_setmetatable(L, -2);
}

int number_range_new(lua_State* L) {
    int count = lua_gettop(L);
    if (count == 1) {
        float value = checked_component(L, 1, "NumberRange value");
        push_number_range(L, value, value);
        return 1;
    }
    if (count != 2) {
        luaL_error(L, "NumberRange.new expects one or two numbers");
        return 0;
    }
    float min = checked_component(L, 1, "NumberRange minimum");
    float max = checked_component(L, 2, "NumberRange maximum");
    if (min > max) {
        luaL_error(L, "NumberRange minimum must be less than or equal to maximum");
        return 0;
    }
    push_number_range(L, min, max);
    return 1;
}

int number_range_index(lua_State* L) {
    auto* range = static_cast<NumberRangeValue*>(luaL_checkudata(L, 1, kNumberRangeMeta));
    const char* key = luaL_checkstring(L, 2);
    if (std::strcmp(key, "Min") == 0) lua_pushnumber(L, range->min);
    else if (std::strcmp(key, "Max") == 0) lua_pushnumber(L, range->max);
    else { luaL_error(L, "%s is not a valid member of NumberRange", key); }
    return 1;
}

int number_range_equal(lua_State* L) {
    bool a_valid = has_metatable(L, 1, kNumberRangeMeta);
    bool b_valid = has_metatable(L, 2, kNumberRangeMeta);
    if (!a_valid || !b_valid) { lua_pushboolean(L, false); return 1; }
    auto* a = static_cast<NumberRangeValue*>(lua_touserdata(L, 1));
    auto* b = static_cast<NumberRangeValue*>(lua_touserdata(L, 2));
    lua_pushboolean(L, a->min == b->min && a->max == b->max);
    return 1;
}

int number_range_tostring(lua_State* L) {
    auto* value = static_cast<NumberRangeValue*>(luaL_checkudata(L, 1, kNumberRangeMeta));
    char buffer[128];
    int length = std::snprintf(buffer, sizeof(buffer), "%g, %g", value->min, value->max);
    lua_pushlstring(L, buffer, static_cast<size_t>(length));
    return 1;
}

int rect_new(lua_State* L) {
    int count = lua_gettop(L);
    if(count==0){push_rect(L,0,0,0,0);return 1;}
    if (count == 2) {
        double min_x, min_y, max_x, max_y;
        if (!read_vector2(L, 1, min_x, min_y)) {
            luaL_error(L, "Rect.new expects Vector2 min and max values");
            return 0;
        }
        if (!read_vector2(L, 2, max_x, max_y)) {
            luaL_error(L, "Rect.new expects Vector2 min and max values");
            return 0;
        }
        const double float_max = static_cast<double>(std::numeric_limits<float>::max());
        if (!std::isfinite(min_x) || !std::isfinite(min_y) || !std::isfinite(max_x) || !std::isfinite(max_y)
            || std::abs(min_x) > float_max || std::abs(min_y) > float_max
            || std::abs(max_x) > float_max || std::abs(max_y) > float_max) {
            luaL_error(L, "Rect coordinates must be finite and representable as floats");
            return 0;
        }
        push_rect(L, static_cast<float>(min_x), static_cast<float>(min_y),
                  static_cast<float>(max_x), static_cast<float>(max_y));
        return 1;
    }
    if (count != 4) {
        lua_pushfstring(L, "Invalid number of arguments: %d", count);
        lua_error(L);
        return 0;
    }
    // Roblox coerces unusable Rect components to zero (Rect.new("x",1,1,1) == 0,1,1,1),
    // but a numeric value that is not representable as a float is rejected
    // rather than silently converted to infinity (Studio-verified: 3.5e38 errors,
    // FLT_MAX is accepted).
    auto lenient = [](lua_State* L, int index) -> double {
        int type = lua_type(L, index);
        return (type == LUA_TNUMBER || (type == LUA_TSTRING && lua_isnumber(L, index)))
            ? lua_tonumber(L, index) : 0.0;
    };
    double min_x = lenient(L, 1);
    double min_y = lenient(L, 2);
    double max_x = lenient(L, 3);
    double max_y = lenient(L, 4);
    const double float_max = static_cast<double>(std::numeric_limits<float>::max());
    if (!std::isfinite(min_x) || !std::isfinite(min_y) || !std::isfinite(max_x) || !std::isfinite(max_y)
        || std::abs(min_x) > float_max || std::abs(min_y) > float_max
        || std::abs(max_x) > float_max || std::abs(max_y) > float_max) {
        luaL_error(L, "Rect coordinates must be finite and representable as floats");
        return 0;
    }
    push_rect(L, static_cast<float>(min_x), static_cast<float>(min_y),
              static_cast<float>(max_x), static_cast<float>(max_y));
    return 1;
}

int rect_index(lua_State* L) {
    auto* rect = static_cast<RectValue*>(luaL_checkudata(L, 1, kRectMeta));
    const char* key = luaL_checkstring(L, 2);
    if (std::strcmp(key, "Min") == 0 || std::strcmp(key, "Max") == 0) {
        if (std::strcmp(key, "Min") == 0) push_vector2(L, rect->min_x, rect->min_y);
        else push_vector2(L, rect->max_x, rect->max_y);
    } else if (std::strcmp(key, "Width") == 0) lua_pushnumber(L, rect->max_x - rect->min_x);
    else if (std::strcmp(key, "Height") == 0) lua_pushnumber(L, rect->max_y - rect->min_y);
    else luaL_error(L, "%s is not a valid member of Rect", key);
    return 1;
}

int rect_equal(lua_State* L) {
    bool a_valid = has_metatable(L, 1, kRectMeta);
    bool b_valid = has_metatable(L, 2, kRectMeta);
    if (!a_valid || !b_valid) { lua_pushboolean(L, false); return 1; }
    auto* a = static_cast<RectValue*>(lua_touserdata(L, 1));
    auto* b = static_cast<RectValue*>(lua_touserdata(L, 2));
    lua_pushboolean(L, a->min_x == b->min_x && a->min_y == b->min_y
                       && a->max_x == b->max_x && a->max_y == b->max_y);
    return 1;
}

int rect_tostring(lua_State* L) {
    auto* value = static_cast<RectValue*>(luaL_checkudata(L, 1, kRectMeta));
    char buffer[192];
    int length = std::snprintf(buffer, sizeof(buffer), "%.9g, %.9g, %.9g, %.9g",
        value->min_x, value->min_y, value->max_x, value->max_y);
    lua_pushlstring(L, buffer, static_cast<size_t>(length));
    return 1;
}

void install_meta(lua_State* L, const char* name, lua_CFunction index,
                  lua_CFunction equal, lua_CFunction tostring, const char* type_name) {
    luaL_newmetatable(L, name);
    lua_pushcfunction(L, index, "datatype.__index"); lua_setfield(L, -2, "__index");
    lua_pushcfunction(L, equal, "datatype.__eq"); lua_setfield(L, -2, "__eq");
    lua_pushcfunction(L, tostring, "datatype.__tostring"); lua_setfield(L, -2, "__tostring");
    lua_pushcfunction(L, [](lua_State* S)->int {
        const char* type = "?";
        if (lua_getmetatable(S, 1)) { lua_getfield(S, -1, "__type"); type = lua_tostring(S, -1); }
        luaL_error(S, "%s member of %s is read-only and cannot be assigned to", luaL_checkstring(S, 2), type);
        return 0;
    }, "__newindex"); lua_setfield(L, -2, "__newindex");
    lua_pushstring(L, type_name); lua_setfield(L, -2, "__type");
    lua_pushliteral(L,"The metatable is locked");lua_setfield(L,-2,"__metatable");
    lua_pop(L, 1);
}

void install_constructor(lua_State* L, const char* global, lua_CFunction constructor) {
    lua_createtable(L, 0, 1);
    lua_pushcfunction(L, constructor, "new"); lua_setfield(L, -2, "new");
    lua_setreadonly(L, -1, true);
    lua_setglobal(L, global);
}
} // namespace

void install_range_bindings(lua_State* L) {
    install_meta(L, kNumberRangeMeta, number_range_index, number_range_equal,
                 number_range_tostring, "NumberRange");
    install_meta(L, kRectMeta, rect_index, rect_equal, rect_tostring, "Rect");
    install_constructor(L, "NumberRange", number_range_new);
    install_constructor(L, "Rect", rect_new);
}
