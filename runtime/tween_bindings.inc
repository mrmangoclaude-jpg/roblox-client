// Bounded TweenInfo and TweenService:GetValue subset.
// Included after geometry_enums.inc in world_bindings.cpp.
namespace {
constexpr const char* kTweenInfoMeta = "LocalRuntime.TweenInfo";
constexpr double kTweenPi = 3.141592653589793238462643383279502884;
struct TweenInfoValue {
    double time = 1.0;
    int style = 3;       // Quad
    int direction = 1;   // Out
    lua_Integer repeat_count = 0;
    bool reverses = false;
    double delay_time = 0.0;
};

TweenInfoValue* checked_tween_info(lua_State* L, int index) {
    return static_cast<TweenInfoValue*>(luaL_checkudata(L, index, kTweenInfoMeta));
}

void push_tween_info(lua_State* L, const TweenInfoValue& value) {
    auto* out = static_cast<TweenInfoValue*>(lua_newuserdatatagged(L, sizeof(TweenInfoValue), 0));
    new(out) TweenInfoValue(value);
    luaL_getmetatable(L, kTweenInfoMeta);
    lua_setmetatable(L, -2);
}

bool tween_info_is_value(lua_State* L, int index) {
    return has_meta(L, index, kTweenInfoMeta);
}

int tween_info_readonly(lua_State* L) {
    luaL_error(L, "%s member of TweenInfo is read-only and cannot be assigned to", luaL_checkstring(L, 2));
    return 0;
}

int tween_info_index(lua_State* L) {
    auto* value = checked_tween_info(L, 1);
    const std::string key = geometry_enum_key(L, 2);
    if (key == "Time") lua_pushnumber(L, value->time);
    else if (key == "EasingStyle") push_geometry_item(L, kGeometryTweenStyle, value->style);
    else if (key == "EasingDirection") push_geometry_item(L, kGeometryEasingDirection, value->direction);
    else if (key == "RepeatCount") lua_pushinteger(L, value->repeat_count);
    else if (key == "Reverses") lua_pushboolean(L, value->reverses);
    else if (key == "DelayTime") lua_pushnumber(L, value->delay_time);
    else luaL_error(L, "%s is not a valid member of TweenInfo", key.c_str());
    return 1;
}

int tween_info_tostring(lua_State* L) {
    auto* value = checked_tween_info(L, 1);
    // Studio renders the full descriptor, with numbers via the VM's own
    // shortest-round-trip formatter and capitalized Reverses.
    auto numstr = [&](double n) -> std::string {
        lua_pushnumber(L, n);
        size_t len = 0; const char* s = luaL_tolstring(L, -1, &len);
        std::string r(s, len); lua_pop(L, 2); return r;
    };
    std::string time = numstr(value->time), delay = numstr(value->delay_time);
    lua_pushinteger(L, value->repeat_count);
    size_t rl = 0; const char* rs = luaL_tolstring(L, -1, &rl);
    std::string repeat(rs, rl); lua_pop(L, 2);
    lua_pushfstring(L, "Time:%s DelayTime:%s RepeatCount:%s Reverses:%s EasingDirection:%s EasingStyle:%s",
                    time.c_str(), delay.c_str(), repeat.c_str(), value->reverses ? "True" : "False",
                    kGeometryEnums[kGeometryEasingDirection].names[value->direction],
                    kGeometryEnums[kGeometryTweenStyle].names[value->style]);
    return 1;
}

int tween_info_equal(lua_State* L) {
    auto* a = tween_info_is_value(L, 1) ? static_cast<TweenInfoValue*>(lua_touserdata(L, 1)) : nullptr;
    auto* b = tween_info_is_value(L, 2) ? static_cast<TweenInfoValue*>(lua_touserdata(L, 2)) : nullptr;
    lua_pushboolean(L, a && b && a->time == b->time && a->style == b->style
                    && a->direction == b->direction && a->repeat_count == b->repeat_count
                    && a->reverses == b->reverses && a->delay_time == b->delay_time);
    return 1;
}

double tween_finite_number(lua_State* L, int index, const char* name, double fallback,
                           const char* type_error) {
    if (lua_isnoneornil(L, index)) return fallback;
    if (lua_type(L, index) != LUA_TNUMBER) {
        luaL_error(L, "%s", type_error);
        return 0;
    }
    double value = lua_tonumber(L, index);
    // Studio accepts negative Time and DelayTime values.
    if (!std::isfinite(value)) {
        luaL_error(L, "TweenInfo.%s must be finite", name);
        return 0;
    }
    return value;
}

int tween_enum_option(lua_State* L, int index, int kind, int fallback,
                      const char* ordinal, const char* enum_name) {
    if (lua_isnone(L, index)) return fallback;
    if (lua_type(L, index) == LUA_TNUMBER) {
        // Studio truncates raw numbers toward zero into an enum value, then
        // clamps into range (0.5 -> Linear, 2.9 -> Back, -0.5 -> Linear).
        double number = lua_tonumber(L, index);
        int value = static_cast<int>(number);
        if (std::isfinite(number) && value >= 0 && value < kGeometryEnums[kind].count) {
            if (kind == kGeometryTweenStyle && value >= 11)
                luaL_error(L, "TweenInfo.new does not support Enum.EasingStyle.Spring or Enum.EasingStyle.Bezier");
            return value;
        }
        luaL_error(L, "TweenInfo.new %s argument expects Enum.%s input", ordinal, enum_name);
        return 0;
    }
    if (!has_meta(L, index, kGeometryItemMeta)) {
        luaL_error(L, "TweenInfo.new %s argument expects Enum.%s input", ordinal, enum_name);
        return 0;
    }
    int value = checked_geometry_value(L, index, kind);
    if (kind == kGeometryTweenStyle && value >= 11)
        luaL_error(L, "TweenInfo.new does not support Enum.EasingStyle.Spring or Enum.EasingStyle.Bezier");
    return value;
}

lua_Integer tween_repeat_option(lua_State* L, int index) {
    if (lua_isnoneornil(L, index)) return 0;
    if (!lua_isnumber(L, index)) {
        luaL_error(L, "TweenInfo.new fourth arg should be a number for RepeatCount.");
        return 0;
    }
    double value = lua_tonumber(L, index);
    if (!std::isfinite(value) || std::floor(value) != value
        || value < -2147483648.0 || value > 2147483647.0) {
        luaL_error(L, "TweenInfo.RepeatCount must be a 32-bit integer");
        return 0;
    }
    return static_cast<lua_Integer>(value);
}

int tween_boolean_option(lua_State* L, int index) {
    if (lua_isnoneornil(L, index)) return 0;
    if (lua_type(L, index) != LUA_TBOOLEAN) {
        luaL_error(L, "TweenInfo.new fifth arg should be a boolean for Reverses.");
        return 0;
    }
    return lua_toboolean(L, index);
}

int tween_info_constructor(lua_State* L) {
    if (lua_gettop(L) > 6) {
        luaL_error(L, "TweenInfo.new accepts at most 6 arguments");
        return 0;
    }
    TweenInfoValue value;
    value.time = tween_finite_number(L, 1, "Time", 1.0,
        "TweenInfo.new first argument expects a number for time.");
    value.style = tween_enum_option(L, 2, kGeometryTweenStyle, 3, "second", "EasingStyle");
    value.direction = tween_enum_option(L, 3, kGeometryEasingDirection, 1, "third", "EasingDirection");
    value.repeat_count = tween_repeat_option(L, 4);
    value.reverses = tween_boolean_option(L, 5) != 0;
    value.delay_time = tween_finite_number(L, 6, "DelayTime", 0.0,
        "TweenInfo.new sixth arg should be a number for DelayTime.");
    push_tween_info(L, value);
    return 1;
}

// Easing as the engine evaluates it, fitted against values measured in a live client: the alpha is a 32-bit float and every result
// is rounded to float, but which steps run in double differs per style (the rounding path decides the last digits).
// TweenService:GetValue(0.6, Linear, Out) is 0.6000000238418579, not the all-double result 0.5999999940395355.
float tween_ease_in(int style, float x) {
    const double xd = x;
    switch (style) {
        case 0: return x; // Linear
        case 1: return static_cast<float>(1.0 - std::cos(xd * kTweenPi / 2.0)); // Sine
        case 2: { // Back
            const float overshoot = 1.70158f;
            return x * x * ((overshoot + 1.0f) * x - overshoot);
        }
        case 3: return x * x; // Quad
        case 4: return static_cast<float>(std::pow(xd, 4.0)); // Quart
        case 5: return static_cast<float>(std::pow(xd, 5.0)); // Quint
        case 6: { // Bounce: float 1 - x, double out-polynomial
            double t = 1.0f - x;
            double value;
            if (t < 1.0 / 2.75) value = 7.5625 * t * t;
            else if (t < 2.0 / 2.75) { t -= 1.5 / 2.75; value = 7.5625 * t * t + 0.75; }
            else if (t < 2.5 / 2.75) { t -= 2.25 / 2.75; value = 7.5625 * t * t + 0.9375; }
            else { t -= 2.625 / 2.75; value = 7.5625 * t * t + 0.984375; }
            return static_cast<float>(1.0 - value);
        }
        case 7: { // Elastic: exponent rounded to float, double pow and sin
            if (x == 0.0f || x == 1.0f) return x;
            const float exponent = static_cast<float>(10.0 * xd - 10.0); // double product, then rounded to float
            return static_cast<float>(std::pow(2.0, static_cast<double>(exponent)) * std::sin(xd * kTweenPi * 6.5));
        }
        case 8: { // Exponential
            if (x == 0.0f) return 0.0f;
            const float exponent = static_cast<float>(10.0 * xd - 10.0); // double product, then rounded to float
            return static_cast<float>(std::pow(2.0, static_cast<double>(exponent)));
        }
        case 9: { // Circular
            const float square = x * x;
            const float remaining = 1.0f - square;
            return 1.0f - std::sqrt(remaining);
        }
        case 10: return static_cast<float>(std::pow(xd, 3.0)); // Cubic
        default: return x;
    }
}

// Out is 1 - In(1 - x) for every style, with float arithmetic around the In curve (Bounce and Exponential have no special out curve).
float tween_ease_out(int style, float x) {
    return 1.0f - tween_ease_in(style, 1.0f - x);
}

double tween_ease(int style, int direction, double alpha) {
    if (std::isnan(alpha)) return alpha;
    const float x = static_cast<float>(std::clamp(alpha, 0.0, 1.0));
    if (x == 0.0f || x == 1.0f) return x;
    if (direction == 0) return tween_ease_in(style, x);
    if (direction == 1) return tween_ease_out(style, x);
    if (x < 0.5f) return tween_ease_in(style, x * 2.0f) * 0.5f;
    return 1.0f - tween_ease_in(style, (1.0f - x) * 2.0f) * 0.5f;
}

int tween_service_get_value(lua_State* L) {
    auto* receiver = checked_handle(L, 1);
    if (receiver->node->class_name != "TweenService") {
        luaL_error(L, "TweenService:GetValue receiver must be TweenService");
        return 0;
    }
    double alpha = luaL_checknumber(L, 2);
    int style = checked_geometry_value(L, 3, kGeometryTweenStyle);
    int direction = checked_geometry_value(L, 4, kGeometryEasingDirection);
    lua_pushnumber(L, tween_ease(style, direction, alpha));
    return 1;
}

// These helpers let root's authored-value serializer add TweenInfo without
// exposing its userdata layout or allowing untrusted tables to impersonate it.
bool tween_info_capture_fields(lua_State* L, int index, double& time, int& style,
                               int& direction, lua_Integer& repeats, bool& reverses,
                               double& delay) {
    if (!tween_info_is_value(L, index)) return false;
    auto* value = static_cast<TweenInfoValue*>(lua_touserdata(L, index));
    time = value->time; style = value->style; direction = value->direction;
    repeats = value->repeat_count; reverses = value->reverses; delay = value->delay_time;
    return true;
}

void tween_info_push_fields(lua_State* L, double time, int style, int direction,
                            lua_Integer repeats, bool reverses, double delay) {
    if (!std::isfinite(time) || time < 0 || style < 0 || style > 12
        || direction < 0 || direction > 2 || repeats < -2147483648LL || repeats > 2147483647LL
        || !std::isfinite(delay) || delay < 0) {
        luaL_error(L, "invalid serialized TweenInfo");
        return;
    }
    push_tween_info(L, TweenInfoValue{time, style, direction, repeats, reverses, delay});
}

void install_tween_bindings(lua_State* L) {
    luaL_newmetatable(L, kTweenInfoMeta);
    lua_pushcfunction(L, tween_info_index, "__index"); lua_setfield(L, -2, "__index");
    lua_pushcfunction(L, tween_info_readonly, "__newindex"); lua_setfield(L, -2, "__newindex");
    lua_pushcfunction(L, tween_info_tostring, "__tostring"); lua_setfield(L, -2, "__tostring");
    lua_pushcfunction(L, tween_info_equal, "__eq"); lua_setfield(L, -2, "__eq");
    lua_pushliteral(L, "TweenInfo"); lua_setfield(L, -2, "__type");
    lua_pushliteral(L,"The metatable is locked");lua_setfield(L,-2,"__metatable");
    lua_pop(L, 1);

    lua_newtable(L);
    lua_pushcfunction(L, tween_info_constructor, "new");
    lua_setfield(L, -2, "new");
    lua_setglobal(L, "TweenInfo");
}
} // namespace
