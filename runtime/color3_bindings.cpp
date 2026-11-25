#include "color3_bindings.hpp"

#include <lua.h>
#include <lualib.h>

#include <algorithm>
#include <array>
#include <cmath>
#include <cstdio>
#include <cstring>

namespace {
constexpr const char* kColorMeta = "LocalRuntime.Color3";
struct Color { double r, g, b; };

Color* check_color(lua_State* L, int index) {
    return static_cast<Color*>(luaL_checkudata(L, index, kColorMeta));
}

int color_lerp(lua_State* L);
int color_to_hsv(lua_State* L);
int color_to_hex(lua_State* L);

static double lenient_number(lua_State* L, int index) {
    int type = lua_type(L, index);
    if (type == LUA_TNUMBER) return lua_tonumber(L, index);
    if (type == LUA_TSTRING && lua_isnumber(L, index)) return lua_tonumber(L, index);
    return 0.0;
}
double finite_number(lua_State* L, int index, const char* label) {
    const double value = lenient_number(L, index);
    if (!std::isfinite(value)) {
        luaL_error(L, "%s must be finite", label);
        return 0;
    }
    return value;
}

int push_color_value(lua_State* L, double r, double g, double b) {
    if (!std::isfinite(r) || !std::isfinite(g) || !std::isfinite(b)) {
        luaL_error(L, "Color3 components must be finite");
        return 0;
    }
    auto* color = static_cast<Color*>(lua_newuserdatadtor(L, sizeof(Color), nullptr));
    // Roblox stores Color3 components as 32-bit floats: Color3.new(0.36002, 0, 0).R reads back 0.36002001166343689, not 0.36002.
    color->r = static_cast<double>(static_cast<float>(r));
    color->g = static_cast<double>(static_cast<float>(g));
    color->b = static_cast<double>(static_cast<float>(b));
    luaL_getmetatable(L, kColorMeta);
    lua_setmetatable(L, -2);
    return 1;
}

int color_new(lua_State* L) {
    const int count = lua_gettop(L);
    if (count > 3) {
        luaL_error(L, "Color3.new accepts up to red, green, and blue");
        return 0;
    }
    const double r = lua_isnoneornil(L, 1) ? 0.0 : finite_number(L, 1, "red");
    const double g = lua_isnoneornil(L, 2) ? 0.0 : finite_number(L, 2, "green");
    const double b = lua_isnoneornil(L, 3) ? 0.0 : finite_number(L, 3, "blue");
    return push_color_value(L, r, g, b);
}

int color_from_rgb(lua_State* L) {
    if (lua_gettop(L) != 3) {
        luaL_error(L, "Color3.fromRGB expects red, green, and blue");
        return 0;
    }
    return push_color_value(L, finite_number(L, 1, "red") / 255.0,
                            finite_number(L, 2, "green") / 255.0,
                            finite_number(L, 3, "blue") / 255.0);
}

Color hsv_to_rgb(double h, double s, double v) {
    h -= std::floor(h);
    const double chroma = v * s;
    const double sector = h * 6.0;
    const double x = chroma * (1.0 - std::abs(std::fmod(sector, 2.0) - 1.0));
    const double m = v - chroma;
    Color rgb{};
    if (sector < 1.0) rgb = {chroma, x, 0};
    else if (sector < 2.0) rgb = {x, chroma, 0};
    else if (sector < 3.0) rgb = {0, chroma, x};
    else if (sector < 4.0) rgb = {0, x, chroma};
    else if (sector < 5.0) rgb = {x, 0, chroma};
    else rgb = {chroma, 0, x};
    return {rgb.r + m, rgb.g + m, rgb.b + m};
}

int color_from_hsv(lua_State* L) {
    if (lua_gettop(L) != 3) {
        luaL_error(L, "Color3.fromHSV expects hue, saturation, and value");
        return 0;
    }
    const double h = finite_number(L, 1, "hue");
    const double s = finite_number(L, 2, "saturation");
    const double v = finite_number(L, 3, "value");
    const Color rgb = hsv_to_rgb(h, s, v);
    return push_color_value(L, rgb.r, rgb.g, rgb.b);
}

int hex_nibble(char c) {
    if (c >= '0' && c <= '9') return c - '0';
    if (c >= 'a' && c <= 'f') return c - 'a' + 10;
    if (c >= 'A' && c <= 'F') return c - 'A' + 10;
    return -1;
}

int color_from_hex(lua_State* L) {
    size_t length = 0;
    const char* text = luaL_checklstring(L, 1, &length);
    if (length && text[0] == '#') { ++text; --length; }
    std::array<int, 6> digits{};
    if (length == 3) {
        for (size_t i = 0; i < 3; ++i) {
            const int value = hex_nibble(text[i]);
            if (value < 0) { luaL_error(L, "Color3.fromHex expects hexadecimal digits"); return 0; }
            digits[i * 2] = digits[i * 2 + 1] = value;
        }
    } else if (length == 6) {
        for (size_t i = 0; i < 6; ++i) {
            digits[i] = hex_nibble(text[i]);
            if (digits[i] < 0) { luaL_error(L, "Color3.fromHex expects hexadecimal digits"); return 0; }
        }
    } else {
        luaL_error(L, "Color3.fromHex expects three or six hexadecimal digits");
        return 0;
    }
    return push_color_value(L, (digits[0] * 16 + digits[1]) / 255.0,
                            (digits[2] * 16 + digits[3]) / 255.0,
                            (digits[4] * 16 + digits[5]) / 255.0);
}

int color_index(lua_State* L) {
    const auto* color = check_color(L, 1);
    const char* key = luaL_checkstring(L, 2);
    if (std::strcmp(key, "R") == 0) lua_pushnumber(L, color->r);
    else if (std::strcmp(key, "G") == 0) lua_pushnumber(L, color->g);
    else if (std::strcmp(key, "B") == 0) lua_pushnumber(L, color->b);
    else if (std::strcmp(key, "Lerp") == 0) lua_pushcfunction(L, color_lerp, "Lerp");
    else if (std::strcmp(key, "ToHSV") == 0) lua_pushcfunction(L, color_to_hsv, "ToHSV");
    else if (std::strcmp(key, "ToHex") == 0) lua_pushcfunction(L, color_to_hex, "ToHex");
    else luaL_error(L, "%s is not a valid member of Color3", key);
    return 1;
}

int color_lerp(lua_State* L) {
    const auto* from = check_color(L, 1);
    const auto* to = check_color(L, 2);
    const double alpha = finite_number(L, 3, "alpha");
    return push_color_value(L, from->r + (to->r - from->r) * alpha,
                            from->g + (to->g - from->g) * alpha,
                            from->b + (to->b - from->b) * alpha);
}

int color_to_hsv(lua_State* L) {
    const auto* color = check_color(L, 1);
    // Roblox stores Color3 channels as float32 and runs the whole conversion in
    // float32; computing in double then rounding diverges in the last ULP.
    const float r = static_cast<float>(color->r);
    const float g = static_cast<float>(color->g);
    const float b = static_cast<float>(color->b);
    const float maximum = std::max({r, g, b});
    const float minimum = std::min({r, g, b});
    const float delta = maximum - minimum;
    float hue = 0.0f;
    if (delta != 0.0f) {
        if (maximum == r) hue = std::fmod((g - b) / delta, 6.0f);
        else if (maximum == g) hue = (b - r) / delta + 2.0f;
        else hue = (r - g) / delta + 4.0f;
        // Roblox wraps a negative sector in float32 BEFORE dividing by six.
        // Dividing first and adding one afterwards differs by one float32 ULP
        // for channels such as (123, 45, 67).
        if (hue < 0.0f) hue = std::fmod(hue + 6.0f, 6.0f);
        hue = hue / 6.0f;
        // Roblox represents fully saturated red as hue 1 in ToHSV.
        if (hue == 0.0f) hue = 1.0f;
    }
    const float saturation = maximum == 0.0f ? 0.0f : delta / maximum;
    lua_pushnumber(L, static_cast<double>(hue));
    lua_pushnumber(L, static_cast<double>(saturation));
    lua_pushnumber(L, static_cast<double>(maximum));
    return 3;
}

unsigned int channel_byte(double value) {
    value = std::max(0.0, std::min(1.0, value));
    return static_cast<unsigned int>(std::floor(value * 255.0 + 0.5));
}

int color_to_hex(lua_State* L) {
    const auto* color = check_color(L, 1);
    char text[7];
    std::snprintf(text, sizeof(text), "%02x%02x%02x", channel_byte(color->r),
                  channel_byte(color->g), channel_byte(color->b));
    lua_pushstring(L, text);
    return 1;
}

int color_equal(lua_State* L) {
    const auto* a = static_cast<const Color*>(lua_touserdata(L, 1));
    const auto* b = static_cast<const Color*>(lua_touserdata(L, 2));
    auto matches = [L](int index) {
        if (!lua_getmetatable(L, index)) return false;
        luaL_getmetatable(L, kColorMeta);
        const bool result = lua_rawequal(L, -1, -2) != 0;
        lua_pop(L, 2);
        return result;
    };
    const bool has_a = matches(1);
    const bool has_b = matches(2);
    lua_pushboolean(L, has_a && has_b && a && b && a->r == b->r && a->g == b->g && a->b == b->b);
    return 1;
}

int color_tostring(lua_State* L) {
    const auto* color = check_color(L, 1);
    lua_pushfstring(L, "%g, %g, %g", color->r, color->g, color->b);
    return 1;
}

void set_function(lua_State* L, const char* name, lua_CFunction function) {
    lua_pushcfunction(L, function, name);
    lua_setfield(L, -2, name);
}
} // namespace

bool read_color3(lua_State* L, int index, double& r, double& g, double& b) {
    if (!lua_getmetatable(L, index)) return false;
    luaL_getmetatable(L, kColorMeta);
    const bool matches = lua_rawequal(L, -1, -2) != 0;
    lua_pop(L, 2);
    if (!matches) return false;
    const auto* color = static_cast<const Color*>(lua_touserdata(L, index));
    if (!color) return false;
    r = color->r;
    g = color->g;
    b = color->b;
    return true;
}

int push_color3(lua_State* L, double r, double g, double b) {
    return push_color_value(L, r, g, b);
}

void install_color3_bindings(lua_State* L) {
    luaL_newmetatable(L, kColorMeta);
    lua_pushcfunction(L, color_index, "Color3.__index");
    lua_setfield(L, -2, "__index");
    lua_pushcfunction(L, color_equal, "Color3.__eq");
    lua_setfield(L, -2, "__eq");
    lua_pushcfunction(L, color_tostring, "Color3.__tostring");
    lua_setfield(L, -2, "__tostring");
    lua_pushcfunction(L, [](lua_State* S)->int {
        luaL_error(S, "%s member of Color3 is read-only and cannot be assigned to", luaL_checkstring(S, 2)); return 0;
    }, nullptr); lua_setfield(L, -2, "__newindex");
    lua_pushliteral(L, "Color3");
    lua_setfield(L, -2, "__type");
    lua_pushliteral(L,"The metatable is locked");lua_setfield(L,-2,"__metatable");
    lua_setreadonly(L, -1, true);
    lua_pop(L, 1);

    lua_createtable(L, 0, 4);
    set_function(L, "new", color_new);
    set_function(L, "fromRGB", color_from_rgb);
    set_function(L, "fromHSV", color_from_hsv);
    set_function(L, "fromHex", color_from_hex);
    set_function(L, "toHSV", color_to_hsv);
    lua_setreadonly(L, -1, true);
    lua_setglobal(L, "Color3");
}
