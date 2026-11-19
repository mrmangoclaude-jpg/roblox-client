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
    luaL_error(L, "TweenInfo values are immutable");
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
    else luaL_error(L, "unknown TweenInfo member");
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

double tween_finite_number(lua_State* L, int index, const char* name, double fallback) {
    if (lua_isnoneornil(L, index)) return fallback;
    double value = luaL_checknumber(L, index);
    if (!std::isfinite(value) || value < 0.0) {
        luaL_error(L, "TweenInfo.%s must be finite and nonnegative", name);
        return 0;
    }
    return value;
}

int tween_enum_option(lua_State* L, int index, int kind, int fallback) {
    if (lua_isnoneornil(L, index)) return fallback;
    return checked_geometry_value(L, index, kind);
}

lua_Integer tween_repeat_option(lua_State* L, int index) {
    if (lua_isnoneornil(L, index)) return 0;
    if (!lua_isnumber(L, index)) {
        luaL_error(L, "TweenInfo.RepeatCount must be an integer");
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
        luaL_error(L, "TweenInfo.Reverses must be a boolean");
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
    value.time = tween_finite_number(L, 1, "Time", 1.0);
    value.style = tween_enum_option(L, 2, kGeometryTweenStyle, 3);
    value.direction = tween_enum_option(L, 3, kGeometryEasingDirection, 1);
    value.repeat_count = tween_repeat_option(L, 4);
    value.reverses = tween_boolean_option(L, 5) != 0;
    value.delay_time = tween_finite_number(L, 6, "DelayTime", 0.0);
    push_tween_info(L, value);
    return 1;
}

double tween_ease_in(int style, double x) {
    switch (style) {
        case 0: return x; // Linear
        case 1: return 1.0 - std::cos(x * kTweenPi / 2.0); // Sine
        case 2: { // Back
            const double overshoot = static_cast<double>(static_cast<float>(1.70158));
            return x * x * ((overshoot + 1.0) * x - overshoot);
        }
        case 3: return x * x; // Quad
        case 4: return x * x * x * x; // Quart
        case 5: return x * x * x * x * x; // Quint
        case 6: { // Bounce-in is the inverse of the legacy out polynomial.
            double inverse = 1.0 - x;
            double value;
            if (inverse < 1.0 / 2.75) value = 7.5625 * inverse * inverse;
            else if (inverse < 2.0 / 2.75) {
                inverse -= 1.5 / 2.75; value = 7.5625 * inverse * inverse + 0.75;
            } else if (inverse < 2.5 / 2.75) {
                inverse -= 2.25 / 2.75; value = 7.5625 * inverse * inverse + 0.9375;
            } else {
                inverse -= 2.625 / 2.75; value = 7.5625 * inverse * inverse + 0.984375;
            }
            return 1.0 - value;
        }
        case 7: { // Elastic
            if (x == 0.0 || x == 1.0) return x;
            return std::pow(2.0, 10.0 * x - 10.0) * std::sin(x * kTweenPi * 6.5);
        }
        case 8: { // Exponential
            if (x == 0.0) return 0.0;
            return std::pow(2.0, 10.0 * x - 10.0);
        }
        case 9: { // Circular; preserve the legacy float32 intermediate steps.
            const float xf = static_cast<float>(x);
            const float square = static_cast<float>(xf * xf);
            const float remaining = static_cast<float>(1.0f - square);
            const float root = static_cast<float>(std::sqrt(remaining));
            return static_cast<float>(1.0f - root);
        }
        case 10: return x * x * x; // Cubic
        default: return x;
    }
}

double tween_ease_out(int style, double x) {
    if (style == 6) { // Bounce has a separately-defined out curve.
        constexpr double n1 = 7.5625;
        constexpr double d1 = 2.75;
        if (x < 1.0 / d1) return n1 * x * x;
        if (x < 2.0 / d1) { x -= 1.5 / d1; return n1 * x * x + 0.75; }
        if (x < 2.5 / d1) { x -= 2.25 / d1; return n1 * x * x + 0.9375; }
        x -= 2.625 / d1;
        return n1 * x * x + 0.984375;
    }
    if (style == 2 || style == 7) return 1.0 - tween_ease_in(style, 1.0 - x);
    if (style == 8) {
        if (x == 1.0) return 1.0;
        return 1.0 - std::pow(2.0, -10.0 * x);
    }
    return 1.0 - tween_ease_in(style, 1.0 - x);
}

double tween_ease(int style, int direction, double alpha) {
    const double x = std::clamp(alpha, 0.0, 1.0);
    if (std::isnan(alpha)) return alpha;
    if (x == 0.0 || x == 1.0) return x;
    if (direction == 0) return static_cast<float>(tween_ease_in(style, x));
    if (direction == 1) return 1.0 - static_cast<float>(tween_ease_in(style, 1.0 - x));
    if (x == 0.0 || x == 1.0) return x;
    if (x < 0.5)
        return static_cast<float>(tween_ease_in(style, x * 2.0)) * 0.5;
    return 1.0 - static_cast<float>(tween_ease_in(style, (1.0 - x) * 2.0)) * 0.5;
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
    if (!std::isfinite(time) || time < 0 || style < 0 || style > 10
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
    lua_pushliteral(L, "immutable TweenInfo"); lua_setfield(L, -2, "__metatable");
    lua_pop(L, 1);

    lua_newtable(L);
    lua_pushcfunction(L, tween_info_constructor, "TweenInfo.new");
    lua_setfield(L, -2, "new");
    lua_setglobal(L, "TweenInfo");
}
} // namespace
