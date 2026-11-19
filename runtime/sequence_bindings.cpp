#include "sequence_bindings.hpp"
#include "color3_bindings.hpp"

#include <lua.h>
#include <lualib.h>

#include <cmath>
#include <cstdio>
#include <cstring>
#include <new>
#include <string>
#include <vector>

namespace {
constexpr const char* kKeypointMeta = "HeadlessRuntime.NumberSequenceKeypoint";
constexpr const char* kSequenceMeta = "HeadlessRuntime.NumberSequence";
constexpr const char* kColorKeypointMeta = "HeadlessRuntime.ColorSequenceKeypoint";
constexpr const char* kColorSequenceMeta = "HeadlessRuntime.ColorSequence";

struct Keypoint {
    double time;
    double value;
    double envelope;
};
struct Sequence {
    std::vector<Keypoint> points;
};
struct Color { double r, g, b; };
struct ColorKeypoint { double time; Color value; double envelope; };
struct ColorSequence { std::vector<ColorKeypoint> points; };

double finite_number(lua_State* L, int index, const char* label) {
    double value = luaL_checknumber(L, index);
    if (!std::isfinite(value)) luaL_error(L, "%s must be finite", label);
    return value;
}
Keypoint* check_keypoint(lua_State* L, int index) {
    return static_cast<Keypoint*>(luaL_checkudata(L, index, kKeypointMeta));
}
Sequence* check_sequence(lua_State* L, int index) {
    return static_cast<Sequence*>(luaL_checkudata(L, index, kSequenceMeta));
}
ColorKeypoint* check_color_keypoint(lua_State* L, int index) {
    return static_cast<ColorKeypoint*>(luaL_checkudata(L, index, kColorKeypointMeta));
}
ColorSequence* check_color_sequence(lua_State* L, int index) {
    return static_cast<ColorSequence*>(luaL_checkudata(L, index, kColorSequenceMeta));
}
void destroy_sequence(lua_State*, void* data) {
    static_cast<Sequence*>(data)->~Sequence();
}
void destroy_color_sequence(lua_State*, void* data) {
    static_cast<ColorSequence*>(data)->~ColorSequence();
}
bool is_keypoint(lua_State* L, int index) {
    if (!lua_isuserdata(L, index) || !lua_getmetatable(L, index)) return false;
    luaL_getmetatable(L, kKeypointMeta);
    bool result = lua_rawequal(L, -1, -2) != 0;
    lua_pop(L, 2);
    return result;
}
bool is_sequence(lua_State* L, int index) {
    if (!lua_isuserdata(L, index) || !lua_getmetatable(L, index)) return false;
    luaL_getmetatable(L, kSequenceMeta);
    bool result = lua_rawequal(L, -1, -2) != 0;
    lua_pop(L, 2);
    return result;
}
bool is_color_keypoint(lua_State* L, int index) {
    if (!lua_isuserdata(L, index) || !lua_getmetatable(L, index)) return false;
    luaL_getmetatable(L, kColorKeypointMeta);
    bool result = lua_rawequal(L, -1, -2) != 0;
    lua_pop(L, 2);
    return result;
}
bool is_color_sequence(lua_State* L, int index) {
    if (!lua_isuserdata(L, index) || !lua_getmetatable(L, index)) return false;
    luaL_getmetatable(L, kColorSequenceMeta);
    bool result = lua_rawequal(L, -1, -2) != 0;
    lua_pop(L, 2);
    return result;
}
Color check_color3(lua_State* L, int index) {
    // Color3 is installed by the adjacent binding module before this one.
    Color color{};
    if (!read_color3(L, index, color.r, color.g, color.b)) {
        luaL_argerror(L, index, "Color3 expected");
    }
    return color;
}
int push_color3(lua_State* L, Color color) {
    return ::push_color3(L, color.r, color.g, color.b);
}
void validate_keypoint(lua_State* L, const Keypoint& value, int arg) {
    if (value.time < 0 || value.time > 1)
        luaL_argerror(L, arg, "time must be between 0 and 1");
    if (value.envelope < 0)
        luaL_argerror(L, arg, "envelope must be nonnegative");
}
int push_keypoint(lua_State* L, double time, double value, double envelope) {
    if (!std::isfinite(time) || !std::isfinite(value) || !std::isfinite(envelope)) {
        luaL_error(L, "NumberSequenceKeypoint components must be finite");
        return 0;
    }
    if (time < 0 || time > 1) {
        luaL_error(L, "NumberSequenceKeypoint time must be between 0 and 1");
        return 0;
    }
    if (envelope < 0) {
        luaL_error(L, "NumberSequenceKeypoint envelope must be nonnegative");
        return 0;
    }
    auto* point = static_cast<Keypoint*>(lua_newuserdatatagged(L, sizeof(Keypoint), 0));
    new (point) Keypoint{time, value, envelope};
    luaL_getmetatable(L, kKeypointMeta);
    lua_setmetatable(L, -2);
    return 1;
}
int keypoint_new(lua_State* L) {
    int count = lua_gettop(L);
    double time = finite_number(L, 1, "time");
    double value = finite_number(L, 2, "value");
    double envelope = count >= 3 ? finite_number(L, 3, "envelope") : 0;
    return push_keypoint(L, time, value, envelope);
}
int keypoint_index(lua_State* L) {
    Keypoint* point = check_keypoint(L, 1);
    const char* name = luaL_checkstring(L, 2);
    if (std::strcmp(name, "Time") == 0) lua_pushnumber(L, point->time);
    else if (std::strcmp(name, "Value") == 0) lua_pushnumber(L, point->value);
    else if (std::strcmp(name, "Envelope") == 0) lua_pushnumber(L, point->envelope);
    else {
        luaL_getmetatable(L, kKeypointMeta);
        lua_pushvalue(L, 2);
        lua_rawget(L, -2);
        lua_remove(L, -2);
    }
    return 1;
}
int immutable(lua_State* L) {
    luaL_error(L, "NumberSequence values are immutable");
    return 0;
}
int keypoint_tostring(lua_State* L) {
    Keypoint* p = check_keypoint(L, 1);
    char text[192];
    int n = std::snprintf(text, sizeof(text), "%g %g %g ",
                          p->time, p->value, p->envelope);
    lua_pushlstring(L, text, static_cast<size_t>(n));
    return 1;
}
int keypoint_equal(lua_State* L) {
    if (!is_keypoint(L, 1) || !is_keypoint(L, 2)) {
        lua_pushboolean(L, 0);
        return 1;
    }
    Keypoint* a = check_keypoint(L, 1);
    Keypoint* b = check_keypoint(L, 2);
    lua_pushboolean(L, a->time == b->time && a->value == b->value && a->envelope == b->envelope);
    return 1;
}
void append_point(lua_State* L, Sequence& sequence, const Keypoint& point, int arg) {
    validate_keypoint(L, point, arg);
    if (!sequence.points.empty() && point.time < sequence.points.back().time)
        luaL_argerror(L, arg, "keypoint times must be in nondecreasing order");
    sequence.points.push_back(point);
}
void validate_endpoints(lua_State* L, const Sequence& sequence) {
    if (sequence.points.size() < 2)
        luaL_error(L, "NumberSequence requires at least two keypoints");
    if (sequence.points.front().time != 0 || sequence.points.back().time != 1)
        luaL_error(L, "NumberSequence first and last keypoints must be at times 0 and 1");
}
int sequence_new(lua_State* L) {
    int count = lua_gettop(L);
    auto* sequence = static_cast<Sequence*>(lua_newuserdatadtor(L, sizeof(Sequence), destroy_sequence));
    new (sequence) Sequence{};
    luaL_getmetatable(L, kSequenceMeta);
    lua_setmetatable(L, -2);
    int result_index = lua_gettop(L);

    if (count == 1 && lua_istable(L, 1)) {
        size_t length = lua_objlen(L, 1);
        if (length > 1024) {
            luaL_error(L, "NumberSequence keypoint array exceeds 1024 entries");
            return 0;
        }
        for (size_t i = 1; i <= length; ++i) {
            lua_rawgeti(L, 1, static_cast<int>(i));
            Keypoint* point = static_cast<Keypoint*>(luaL_checkudata(L, -1, kKeypointMeta));
            append_point(L, *sequence, *point, 1);
            lua_pop(L, 1);
        }
        // Reject dictionary keys and sparse entries: the engine constructor
        // consumes an ordered keypoint array, never a lossy dense prefix.
        size_t actual = 0;
        lua_pushnil(L);
        while (lua_next(L, 1)) {
            ++actual;
            if (!lua_isnumber(L, -2) || lua_tointeger(L, -2) < 1
                || static_cast<size_t>(lua_tointeger(L, -2)) > length
                || lua_tonumber(L, -2) != static_cast<double>(lua_tointeger(L, -2))) {
                luaL_error(L, "NumberSequence keypoints must be a dense array");
                return 0;
            }
            lua_pop(L, 1);
        }
        if (actual != length) {
            luaL_error(L, "NumberSequence keypoints must be a dense array");
            return 0;
        }
    } else if (count == 1 || count == 2) {
        double first = finite_number(L, 1, "first value");
        double last = count == 2 ? finite_number(L, 2, "last value") : first;
        sequence->points.push_back(Keypoint{0, first, 0});
        sequence->points.push_back(Keypoint{1, last, 0});
    } else {
        luaL_error(L, "NumberSequence.new expects a value, value and envelope, or keypoint array");
        return 0;
    }
    validate_endpoints(L, *sequence);
    lua_pushvalue(L, result_index);
    return 1;
}
int sequence_index(lua_State* L) {
    Sequence* sequence = check_sequence(L, 1);
    const char* name = luaL_checkstring(L, 2);
    if (std::strcmp(name, "Keypoints") == 0) {
        lua_createtable(L, static_cast<int>(sequence->points.size()), 0);
        for (size_t i = 0; i < sequence->points.size(); ++i) {
            const auto& p = sequence->points[i];
            push_keypoint(L, p.time, p.value, p.envelope);
            lua_rawseti(L, -2, static_cast<int>(i + 1));
        }
    } else {
        luaL_getmetatable(L, kSequenceMeta);
        lua_pushvalue(L, 2);
        lua_rawget(L, -2);
        lua_remove(L, -2);
    }
    return 1;
}
int sequence_tostring(lua_State* L) {
    Sequence* sequence = check_sequence(L, 1);
    std::string text;
    char field[96];
    for (const auto& p : sequence->points) {
        int n = std::snprintf(field, sizeof(field), "%g %g %g ", p.time, p.value, p.envelope);
        text.append(field, static_cast<size_t>(n));
    }
    lua_pushlstring(L, text.data(), text.size());
    return 1;
}
int sequence_equal(lua_State* L) {
    if (!is_sequence(L, 1) || !is_sequence(L, 2)) {
        lua_pushboolean(L, 0);
        return 1;
    }
    const auto& a = check_sequence(L, 1)->points;
    const auto& b = check_sequence(L, 2)->points;
    bool equal = a.size() == b.size();
    for (size_t i = 0; equal && i < a.size(); ++i)
        equal = a[i].time == b[i].time && a[i].value == b[i].value && a[i].envelope == b[i].envelope;
    lua_pushboolean(L, equal);
    return 1;
}
void validate_color_time(lua_State* L, double time, int arg) {
    if (!std::isfinite(time) || time < 0 || time > 1)
        luaL_argerror(L, arg, "time must be finite and between 0 and 1");
}
int push_color_keypoint(lua_State* L, double time, Color color, double envelope) {
    validate_color_time(L, time, 1);
    auto* point = static_cast<ColorKeypoint*>(lua_newuserdatatagged(L, sizeof(ColorKeypoint), 0));
    new (point) ColorKeypoint{time, color, envelope};
    luaL_getmetatable(L, kColorKeypointMeta);
    lua_setmetatable(L, -2);
    return 1;
}
int color_keypoint_new(lua_State* L) {
    double time = finite_number(L, 1, "time");
    Color color{};
    if (!read_color3(L, 2, color.r, color.g, color.b)) {
        lua_pushliteral(L, "could not parse arg #2 to ColorSequenceKeypoint.new(), Color3 expected.");
        lua_error(L);
        return 0;
    }
    return push_color_keypoint(L, time, color, 0);
}
int color_keypoint_index(lua_State* L) {
    ColorKeypoint* point = check_color_keypoint(L, 1);
    const char* name = luaL_checkstring(L, 2);
    if (std::strcmp(name, "Time") == 0) lua_pushnumber(L, point->time);
    else if (std::strcmp(name, "Value") == 0) push_color3(L, point->value);
    else if (std::strcmp(name, "Envelope") == 0) lua_pushnumber(L, point->envelope);
    else {
        luaL_getmetatable(L, kColorKeypointMeta);
        lua_pushvalue(L, 2);
        lua_rawget(L, -2);
        lua_remove(L, -2);
    }
    return 1;
}
int color_keypoint_tostring(lua_State* L) {
    ColorKeypoint* point = check_color_keypoint(L, 1);
    char text[192];
    int n = std::snprintf(text, sizeof(text), "%g %g %g %g %g ", point->time,
                    point->value.r, point->value.g, point->value.b, point->envelope);
    lua_pushlstring(L, text, static_cast<size_t>(n));
    return 1;
}
int color_keypoint_equal(lua_State* L) {
    if (!is_color_keypoint(L, 1) || !is_color_keypoint(L, 2)) {
        lua_pushboolean(L, 0);
        return 1;
    }
    ColorKeypoint* a = check_color_keypoint(L, 1);
    ColorKeypoint* b = check_color_keypoint(L, 2);
    lua_pushboolean(L, a->time == b->time && a->value.r == b->value.r
        && a->value.g == b->value.g && a->value.b == b->value.b
        && a->envelope == b->envelope);
    return 1;
}
void append_color_point(lua_State* L, ColorSequence& sequence, const ColorKeypoint& point) {
    validate_color_time(L, point.time, 1);
    if (!sequence.points.empty() && point.time < sequence.points.back().time)
        luaL_argerror(L, 1, "keypoint times must be in nondecreasing order");
    sequence.points.push_back(point);
}
void validate_color_endpoints(lua_State* L, const ColorSequence& sequence) {
    if (sequence.points.size() < 2)
        luaL_error(L, "ColorSequence requires at least two keypoints");
    if (sequence.points.front().time != 0 || sequence.points.back().time != 1)
        luaL_error(L, "ColorSequence first and last keypoints must be at times 0 and 1");
}
int color_sequence_new(lua_State* L) {
    int count = lua_gettop(L);
    auto* sequence = static_cast<ColorSequence*>(lua_newuserdatadtor(L, sizeof(ColorSequence), destroy_color_sequence));
    new (sequence) ColorSequence{};
    luaL_getmetatable(L, kColorSequenceMeta);
    lua_setmetatable(L, -2);
    int result_index = lua_gettop(L);
    if (count == 1 && lua_istable(L, 1)) {
        size_t length = lua_objlen(L, 1);
        if (length > 1024) {
            luaL_error(L, "ColorSequence keypoint array exceeds 1024 entries");
            return 0;
        }
        for (size_t i = 1; i <= length; ++i) {
            lua_rawgeti(L, 1, static_cast<int>(i));
            ColorKeypoint* point = check_color_keypoint(L, -1);
            append_color_point(L, *sequence, *point);
            lua_pop(L, 1);
        }
        size_t actual = 0;
        lua_pushnil(L);
        while (lua_next(L, 1)) {
            ++actual;
            if (!lua_isnumber(L, -2) || lua_tointeger(L, -2) < 1
                || static_cast<size_t>(lua_tointeger(L, -2)) > length
                || lua_tonumber(L, -2) != static_cast<double>(lua_tointeger(L, -2))) {
                luaL_error(L, "ColorSequence keypoints must be a dense array");
                return 0;
            }
            lua_pop(L, 1);
        }
        if (actual != length) {
            luaL_error(L, "ColorSequence keypoints must be a dense array");
            return 0;
        }
    } else if (count == 1 || count == 2) {
        Color first = check_color3(L, 1);
        Color last = count == 2 ? check_color3(L, 2) : first;
        sequence->points.push_back(ColorKeypoint{0, first, 0});
        sequence->points.push_back(ColorKeypoint{1, last, 0});
    } else {
        luaL_error(L, "ColorSequence.new expects one color, two endpoint colors, or a keypoint array");
        return 0;
    }
    validate_color_endpoints(L, *sequence);
    lua_pushvalue(L, result_index);
    return 1;
}
int color_sequence_index(lua_State* L) {
    ColorSequence* sequence = check_color_sequence(L, 1);
    const char* name = luaL_checkstring(L, 2);
    if (std::strcmp(name, "Keypoints") == 0) {
        lua_createtable(L, static_cast<int>(sequence->points.size()), 0);
        for (size_t i = 0; i < sequence->points.size(); ++i) {
            const auto& point = sequence->points[i];
            push_color_keypoint(L, point.time, point.value, point.envelope);
            lua_rawseti(L, -2, static_cast<int>(i + 1));
        }
    } else {
        luaL_getmetatable(L, kColorSequenceMeta);
        lua_pushvalue(L, 2);
        lua_rawget(L, -2);
        lua_remove(L, -2);
    }
    return 1;
}
int color_sequence_tostring(lua_State* L) {
    ColorSequence* sequence = check_color_sequence(L, 1);
    std::string text;
    char field[192];
    for (const auto& p : sequence->points) {
        int n = std::snprintf(field, sizeof(field), "%g %g %g %g %g ", p.time,
                              p.value.r, p.value.g, p.value.b, p.envelope);
        text.append(field, static_cast<size_t>(n));
    }
    lua_pushlstring(L, text.data(), text.size());
    return 1;
}
int color_sequence_equal(lua_State* L) {
    if (!is_color_sequence(L, 1) || !is_color_sequence(L, 2)) {
        lua_pushboolean(L, 0);
        return 1;
    }
    const auto& a = check_color_sequence(L, 1)->points;
    const auto& b = check_color_sequence(L, 2)->points;
    bool equal = a.size() == b.size();
    for (size_t i = 0; equal && i < a.size(); ++i)
        equal = a[i].time == b[i].time && a[i].value.r == b[i].value.r
            && a[i].value.g == b[i].value.g && a[i].value.b == b[i].value.b
            && a[i].envelope == b[i].envelope;
    lua_pushboolean(L, equal);
    return 1;
}
void method(lua_State* L, const char* name, lua_CFunction callback) {
    lua_pushcfunction(L, callback, name);
    lua_setfield(L, -2, name);
}
} // namespace

void install_sequence_bindings(lua_State* L) {
    luaL_newmetatable(L, kKeypointMeta);
    method(L, "__index", keypoint_index);
    method(L, "__newindex", immutable);
    method(L, "__eq", keypoint_equal);
    method(L, "__tostring", keypoint_tostring);
    lua_pushliteral(L, "NumberSequenceKeypoint");
    lua_setfield(L, -2, "__type");
    lua_pushliteral(L,"The metatable is locked");lua_setfield(L,-2,"__metatable");
    lua_pop(L, 1);

    luaL_newmetatable(L, kSequenceMeta);
    method(L, "__index", sequence_index);
    method(L, "__newindex", immutable);
    method(L, "__eq", sequence_equal);
    method(L, "__tostring", sequence_tostring);
    lua_pushliteral(L, "NumberSequence");
    lua_setfield(L, -2, "__type");
    lua_pushliteral(L,"The metatable is locked");lua_setfield(L,-2,"__metatable");
    lua_pop(L, 1);

    lua_createtable(L, 0, 1);
    method(L, "new", keypoint_new);
    lua_setreadonly(L, -1, true);
    lua_setglobal(L, "NumberSequenceKeypoint");
    lua_createtable(L, 0, 1);
    method(L, "new", sequence_new);
    lua_setreadonly(L, -1, true);
    lua_setglobal(L, "NumberSequence");

    luaL_newmetatable(L, kColorKeypointMeta);
    method(L, "__index", color_keypoint_index);
    method(L, "__newindex", immutable);
    method(L, "__eq", color_keypoint_equal);
    method(L, "__tostring", color_keypoint_tostring);
    lua_pushliteral(L, "ColorSequenceKeypoint");
    lua_setfield(L, -2, "__type");
    lua_pushliteral(L,"The metatable is locked");lua_setfield(L,-2,"__metatable");
    lua_pop(L, 1);

    luaL_newmetatable(L, kColorSequenceMeta);
    method(L, "__index", color_sequence_index);
    method(L, "__newindex", immutable);
    method(L, "__eq", color_sequence_equal);
    method(L, "__tostring", color_sequence_tostring);
    lua_pushliteral(L, "ColorSequence");
    lua_setfield(L, -2, "__type");
    lua_pushliteral(L,"The metatable is locked");lua_setfield(L,-2,"__metatable");
    lua_pop(L, 1);

    lua_createtable(L, 0, 1);
    method(L, "new", color_keypoint_new);
    lua_setreadonly(L, -1, true);
    lua_setglobal(L, "ColorSequenceKeypoint");
    lua_createtable(L, 0, 1);
    method(L, "new", color_sequence_new);
    lua_setreadonly(L, -1, true);
    lua_setglobal(L, "ColorSequence");
}
