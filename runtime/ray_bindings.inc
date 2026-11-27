// Ordinary authored Ray values. The public projection contract requires a unit
// direction; callers can obtain one with ray.Unit. No world intersection here.
namespace {
constexpr const char* kRayMeta = "LocalRuntime.Ray";
struct RayValue { float origin[3]; float direction[3]; };

RayValue* checked_ray(lua_State* L, int index) {
    return static_cast<RayValue*>(luaL_checkudata(L, index, kRayMeta));
}
void push_ray(lua_State* L, const float* origin, const float* direction) {
    auto* ray = static_cast<RayValue*>(lua_newuserdatatagged(L, sizeof(RayValue), 0));
    for (int i = 0; i < 3; ++i) { ray->origin[i] = origin[i]; ray->direction[i] = direction[i]; }
    luaL_getmetatable(L, kRayMeta); lua_setmetatable(L, -2);
}
int ray_new(lua_State* L) {
    // Studio defaults an *absent* component to a zero vector, while an
    // explicitly supplied non-Vector3 value is a normal argument error.
    const float zero[3] = {0, 0, 0};
    const float* origin = zero;
    const float* direction = zero;
    if (lua_gettop(L) >= 1) {
        if (!lua_isvector(L, 1)) { luaL_argerror(L, 1, lua_pushfstring(L, "Vector3 expected, got %s", luaL_typename(L, 1))); return 0; }
        origin = lua_tovector(L, 1);
    }
    if (lua_gettop(L) >= 2) {
        if (!lua_isvector(L, 2)) { luaL_argerror(L, 2, lua_pushfstring(L, "Vector3 expected, got %s", luaL_typename(L, 2))); return 0; }
        direction = lua_tovector(L, 2);
    }
    push_ray(L, origin, direction); return 1;
}
void ray_projection(const RayValue& ray, const float* point, double* closest) {
    double t = 0;
    for (int i = 0; i < 3; ++i) t += (double(point[i]) - ray.origin[i]) * ray.direction[i];
    if (t < 0) t = 0;
    for (int i = 0; i < 3; ++i) closest[i] = ray.origin[i] + t * ray.direction[i];
}
int ray_closest_point(lua_State* L) {
    auto* ray = checked_ray(L, 1); const float* point = luaL_checkvector(L, 2);
    double closest[3]; ray_projection(*ray, point, closest);
    lua_pushvector(L, float(closest[0]), float(closest[1]), float(closest[2])); return 1;
}
int ray_distance(lua_State* L) {
    auto* ray = checked_ray(L, 1); const float* point = luaL_checkvector(L, 2);
    double closest[3]; ray_projection(*ray, point, closest);
    lua_pushnumber(L, std::hypot(double(point[0]) - closest[0], double(point[1]) - closest[1], double(point[2]) - closest[2])); return 1;
}
int ray_index(lua_State* L) {
    auto* ray = checked_ray(L, 1); size_t length = 0;
    const char* raw = luaL_checklstring(L, 2, &length); const std::string key(raw, length);
    if (key == "Origin") lua_pushvector(L, ray->origin[0], ray->origin[1], ray->origin[2]);
    else if (key == "Direction") lua_pushvector(L, ray->direction[0], ray->direction[1], ray->direction[2]);
    else if (key == "Unit") {
        double length = std::hypot(double(ray->direction[0]), double(ray->direction[1]), double(ray->direction[2]));
        float direction[3]; for (int i = 0; i < 3; ++i) direction[i] = float(ray->direction[i] / length);
        push_ray(L, ray->origin, direction);
    } else if (key == "ClosestPoint") lua_pushcfunction(L, ray_closest_point, "ClosestPoint");
    else if (key == "Distance") lua_pushcfunction(L, ray_distance, "Distance");
    else luaL_error(L, "unknown Ray member");
    return 1;
}
int ray_equal(lua_State* L) {
    auto* a = checked_ray(L, 1); auto* b = checked_ray(L, 2); bool equal = true;
    for (int i = 0; i < 3; ++i) equal = equal && a->origin[i] == b->origin[i] && a->direction[i] == b->direction[i];
    lua_pushboolean(L, equal); return 1;
}
int ray_readonly(lua_State* L) { luaL_error(L, "Ray values are immutable"); return 0; }
int ray_string(lua_State* L) {
    auto* ray = checked_ray(L, 1);
    // Studio renders a Ray as "{origin}, {direction}" with each component at
    // %.9g (the PhysicalProperties convention), not Vector3's full-precision form.
    char text[160];
    std::snprintf(text, sizeof(text), "{%.9g, %.9g, %.9g}, {%.9g, %.9g, %.9g}",
        double(ray->origin[0]), double(ray->origin[1]), double(ray->origin[2]),
        double(ray->direction[0]), double(ray->direction[1]), double(ray->direction[2]));
    lua_pushstring(L, text); return 1;
}
void ray_method(lua_State* L, const char* name, lua_CFunction fn) {
    lua_pushcfunction(L, fn, name); lua_setfield(L, -2, name);
}
void install_ray_bindings(lua_State* L) {
    luaL_newmetatable(L, kRayMeta);
    ray_method(L, "__index", ray_index); ray_method(L, "__newindex", ray_readonly);
    ray_method(L, "__eq", ray_equal); ray_method(L, "__tostring", ray_string);
    lua_pushliteral(L, "Ray"); lua_setfield(L, -2, "__type");
    lua_pushliteral(L,"The metatable is locked");lua_setfield(L,-2,"__metatable");
    lua_setreadonly(L, -1, true); lua_pop(L, 1);
    lua_newtable(L); ray_method(L, "new", ray_new);
    lua_setreadonly(L, -1, true); lua_setglobal(L, "Ray");
}
}
