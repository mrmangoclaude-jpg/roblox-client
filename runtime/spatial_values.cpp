#include "spatial_values.hpp"
#include "world_bindings.hpp"

#include <lualib.h>

#include <algorithm>
#include <array>
#include <cmath>
#include <cstdio>
#include <limits>
#include <new>
#include <stdexcept>
#include <string>

namespace spatial_values {
namespace {

constexpr const char* kRegionMeta = "LocalRuntime.Region3";
struct Region { std::array<float, 3> minimum, maximum; };

Region* checked_region(lua_State* L, int index) {
    return static_cast<Region*>(luaL_checkudata(L, index, kRegionMeta));
}

bool is_region(lua_State* L, int index) {
    if (!lua_isuserdata(L, index) || !lua_getmetatable(L, index)) return false;
    luaL_getmetatable(L, kRegionMeta);
    const bool result = lua_rawequal(L, -1, -2) != 0;
    lua_pop(L, 2);
    return result;
}

float checked_finite_float(lua_State* L, int index, const char* label) {
    if (lua_type(L, index) != LUA_TNUMBER) {
        luaL_argerror(L, index, label);
        return 0;
    }
    const double input = luaL_checknumber(L, index);
    if (!std::isfinite(input) || std::fabs(input) > std::numeric_limits<float>::max()) {
        luaL_error(L, "%s must be a finite float", label);
        return 0;
    }
    return static_cast<float>(input);
}

std::array<float, 3> checked_vector(lua_State* L, int index) {
    if (!lua_isvector(L, index)) {
        luaL_argerror(L, index, lua_pushfstring(L, "Vector3 expected, got %s", luaL_typename(L, index)));
        return {};
    }
    const float* input = lua_tovector(L, index);
    std::array<float, 3> result{input[0], input[1], input[2]};
    for (float item : result) {
        if (!std::isfinite(item)) {
            luaL_argerror(L, index, "finite Vector3 expected");
            return {};
        }
    }
    return result;
}

void push_region(lua_State* L, const std::array<float, 3>& minimum,
                 const std::array<float, 3>& maximum) {
    auto* result = static_cast<Region*>(lua_newuserdatatagged(L, sizeof(Region), 0));
    new (result) Region{minimum, maximum};
    luaL_getmetatable(L, kRegionMeta);
    lua_setmetatable(L, -2);
}

int region_new(lua_State* L) {
    const std::array<float, 3> zero{0, 0, 0};
    const auto minimum = lua_isnone(L, 1) ? zero : checked_vector(L, 1);
    const auto maximum = lua_isnone(L, 2) ? zero : checked_vector(L, 2);
    push_region(L, minimum, maximum);
    return 1;
}

int region_expand_to_grid(lua_State* L) {
    const Region& original = *checked_region(L, 1);
    const float resolution = checked_finite_float(L, 2, "resolution");
    if (resolution <= 0) {
        luaL_argerror(L, 2, "positive resolution expected");
        return 0;
    }
    std::array<float, 3> minimum{}, maximum{};
    for (int axis = 0; axis < 3; ++axis) {
        const double low = original.minimum[axis];
        const double high = original.maximum[axis];
        if (low > high) {
            luaL_error(L, "ExpandToGrid requires nonnegative Region3 size components; reversed bounds are not verified");
            return 0;
        }
        const double expanded_low = std::floor(low / resolution) * resolution;
        const double expanded_high = std::ceil(high / resolution) * resolution;
        if (!std::isfinite(expanded_low) || !std::isfinite(expanded_high)
                || std::fabs(expanded_low) > std::numeric_limits<float>::max()
                || std::fabs(expanded_high) > std::numeric_limits<float>::max()) {
            luaL_error(L, "expanded Region3 bounds exceed finite Vector3 range");
            return 0;
        }
        minimum[axis] = static_cast<float>(expanded_low);
        maximum[axis] = static_cast<float>(expanded_high);
    }
    push_region(L, minimum, maximum);
    return 1;
}

int region_index(lua_State* L) {
    const Region& region = *checked_region(L, 1);
    const std::string key = luaL_checkstring(L, 2);
    if (key == "Size") {
        lua_pushvector(L, region.maximum[0] - region.minimum[0],
                       region.maximum[1] - region.minimum[1],
                       region.maximum[2] - region.minimum[2]);
    } else if (key == "CFrame") {
        const double x = (double(region.minimum[0]) + region.maximum[0]) * 0.5;
        const double y = (double(region.minimum[1]) + region.maximum[1]) * 0.5;
        const double z = (double(region.minimum[2]) + region.maximum[2]) * 0.5;
        // Preserve the native CFrame userdata even if the script replaced its
        // global constructor table after startup.
        return world_bindings::push_translation_cframe(L, x, y, z);
    } else if (key == "ExpandToGrid") {
        lua_pushcfunction(L, region_expand_to_grid, "ExpandToGrid");
    } else {
        luaL_error(L, "unknown Region3 member");
        return 0;
    }
    return 1;
}

int region_readonly(lua_State* L) {
    luaL_error(L, "Region3 values are immutable");
    return 0;
}

int region_equal(lua_State* L) {
    if (!is_region(L, 1) || !is_region(L, 2)) {
        lua_pushboolean(L, 0);
        return 1;
    }
    const Region& a = *checked_region(L, 1);
    const Region& b = *checked_region(L, 2);
    lua_pushboolean(L, a.minimum == b.minimum && a.maximum == b.maximum);
    return 1;
}

int region_string(lua_State* L) {
    const Region& value = *checked_region(L, 1);
    float center[3], size[3];
    for (int axis = 0; axis < 3; ++axis) {
        center[axis] = (value.minimum[axis] + value.maximum[axis]) * 0.5f;
        size[axis] = value.maximum[axis] - value.minimum[axis];
    }
    char buffer[256];
    int n = std::snprintf(buffer, sizeof(buffer),
        "%.9g, %.9g, %.9g, 1, 0, 0, 0, 1, 0, 0, 0, 1; %.9g, %.9g, %.9g",
        double(center[0]), double(center[1]), double(center[2]),
        double(size[0]), double(size[1]), double(size[2]));
    lua_pushlstring(L, buffer, static_cast<size_t>(n));
    return 1;
}

void set_function(lua_State* L, const char* name, lua_CFunction function) {
    lua_pushcfunction(L, function, name);
    lua_setfield(L, -2, name);
}

bool read_vector_json(const nlohmann::json& value, std::array<float, 3>& out) {
    if (!value.is_array() || value.size() != 3) return false;
    for (int axis = 0; axis < 3; ++axis) {
        if (!value[axis].is_number()) return false;
        const double component = value[axis].get<double>();
        if (!std::isfinite(component) || std::fabs(component) > std::numeric_limits<float>::max()) return false;
        out[axis] = static_cast<float>(component);
    }
    return true;
}

}  // namespace

void install_spatial_values(lua_State* L) {
    luaL_newmetatable(L, kRegionMeta);
    set_function(L, "__index", region_index);
    set_function(L, "__newindex", region_readonly);
    set_function(L, "__eq", region_equal);
    set_function(L, "__tostring", region_string);
    lua_pushliteral(L, "Region3");
    lua_setfield(L, -2, "__type");
    lua_pushliteral(L,"The metatable is locked");lua_setfield(L,-2,"__metatable");
    lua_setreadonly(L, -1, true);
    lua_pop(L, 1);

    lua_newtable(L);
    set_function(L, "new", region_new);
    lua_setreadonly(L, -1, true);
    lua_setglobal(L, "Region3");
}

bool is_spatial_value(lua_State* L, int index) {
    return is_region(L, index);
}

bool read_region_bounds(lua_State* L, int index, std::array<double, 3>& minimum,
                        std::array<double, 3>& maximum) {
    if (!is_region(L, index)) return false;
    const auto& region = *checked_region(L, index);
    for (int axis = 0; axis < 3; ++axis) {
        minimum[axis] = region.minimum[axis];
        maximum[axis] = region.maximum[axis];
    }
    return true;
}

bool capture_spatial_value(lua_State* L, int index, nlohmann::json& value) {
    if (!is_region(L, index)) return false;
    const Region& region = *checked_region(L, index);
    value = nlohmann::json{{"$region3", nlohmann::json::array({
        nlohmann::json::array({region.minimum[0], region.minimum[1], region.minimum[2]}),
        nlohmann::json::array({region.maximum[0], region.maximum[1], region.maximum[2]})})}};
    return true;
}

bool push_spatial_value(lua_State* L, const nlohmann::json& value) {
    if (!value.is_object() || value.size() != 1 || !value.contains("$region3")) return false;
    const auto& data = value.at("$region3");
    if (!data.is_array() || data.size() != 2) throw std::runtime_error("invalid Region3 component count");
    std::array<float, 3> minimum{}, maximum{};
    if (!read_vector_json(data[0], minimum) || !read_vector_json(data[1], maximum))
        throw std::runtime_error("invalid Region3 vector components");
    luaL_getmetatable(L, kRegionMeta);
    if (lua_isnil(L, -1)) {
        lua_pop(L, 1);
        throw std::runtime_error("Region3 is not installed in this Luau state");
    }
    lua_pop(L, 1);
    push_region(L, minimum, maximum);
    return true;
}

}  // namespace spatial_values
