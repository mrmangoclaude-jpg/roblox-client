// Roblox's Vector3 surface over the VM's native vector values. Capture the
// pinned Luau library functions before user code runs; no global lookup occurs
// when a method/property is used. Arithmetic and snapshot encoding stay native.
// Reference: creator-docs/content/en-us/reference/engine/datatypes/Vector3.yaml
int vector3_fuzzy_eq(lua_State* L) {
    const auto* a=luaL_checkvector(L,1);
    const auto* b=luaL_checkvector(L,2);
    const double epsilon=luaL_optnumber(L,3,1e-5);
    lua_pushboolean(L,runtime_fuzzy_component(a[0],b[0],epsilon)&&
        runtime_fuzzy_component(a[1],b[1],epsilon)&&runtime_fuzzy_component(a[2],b[2],epsilon));
    return 1;
}

int vector3_index(lua_State* L) {
    const auto* value = luaL_checkvector(L, 1);
    size_t length = 0;
    // Roblox's Vector3.__index is an unnamed C function: argument errors omit
    // the "to 'Vector3.__index'" fragment that luaL_checklstring would add.
    if (lua_type(L, 2) != LUA_TSTRING)
        luaL_error(L, "invalid argument #2 (string expected, got %s)", luaL_typename(L, 2));
    const char* key = lua_tolstring(L, 2, &length);
    if (length == 1) {
        const unsigned component = unsigned((key[0] | ' ') - 'x');
        if (component < 3) {
            lua_pushnumber(L, value[component]);
            return 1;
        }
    }
    int property = 0;
    if (!std::strcmp(key, "Magnitude") || !std::strcmp(key, "magnitude")) property = 2;
    if (!std::strcmp(key, "Unit") || !std::strcmp(key, "unit")) property = 3;
    if (property) {
        lua_settop(L, 1);
        lua_pushvalue(L, lua_upvalueindex(property));
        lua_insert(L, 1);
        lua_call(L, 1, 1);
        return 1;
    }
    lua_pushvalue(L, 2);
    lua_rawget(L, lua_upvalueindex(1));
    if (lua_isnil(L, -1)) luaL_error(L, "%s is not a valid member of Vector3", key);
    return 1;
}

// The engine's Vector3 methods are native functions named in PascalCase (debug.info(v.Abs, "n") == "Abs"), while the pinned Luau
// vector library names them in lowercase. Forward the PascalCase entries so the names match and share the pinned behavior.
int vector3_forward(lua_State* L) {
    const int count = lua_gettop(L);
    lua_pushvalue(L, lua_upvalueindex(1));
    lua_insert(L, 1);
    lua_call(L, count, LUA_MULTRET);
    return lua_gettop(L);
}
// Vector3:Angle returns a single-precision number in the engine; the pinned library returns the double it computed.
int vector3_angle_forward(lua_State* L) {
    const int count = lua_gettop(L);
    lua_pushvalue(L, lua_upvalueindex(1));
    lua_insert(L, 1);
    lua_call(L, count, 1);
    lua_pushnumber(L, static_cast<double>(static_cast<float>(luaL_checknumber(L, -1))));
    return 1;
}

void install_vector3_methods(lua_State* L) {
    const int base = lua_gettop(L);
    lua_getglobal(L, "vector");
    const int library = lua_gettop(L);
    lua_newtable(L);
    const int methods = lua_gettop(L);
    const char* pairs[][2] = {
        {"Dot", "dot"}, {"Cross", "cross"}, {"Lerp", "lerp"}, {"Angle", "angle"},
        {"Abs", "abs"}, {"Floor", "floor"}, {"Ceil", "ceil"}, {"Sign", "sign"},
        {"Min", "min"}, {"Max", "max"},
        {"dot", "dot"}, {"cross", "cross"}, {"lerp", "lerp"},
    };
    for (const auto& pair : pairs) {
        lua_getfield(L, library, pair[1]);
        if (!lua_isfunction(L, -1)) luaL_error(L, "missing pinned vector function %s", pair[1]);
        if (pair[0][0] >= 'A' && pair[0][0] <= 'Z') {
            lua_pushcclosurek(L, std::strcmp(pair[0], "Angle") ? vector3_forward : vector3_angle_forward, pair[0], 1, nullptr);
        }
        lua_setfield(L, methods, pair[0]);
    }
    lua_pushcfunction(L,vector3_fuzzy_eq,"FuzzyEq");
    lua_setfield(L,methods,"FuzzyEq");
    lua_setreadonly(L, methods, true);
    lua_newtable(L);
    const int metatable = lua_gettop(L);
    lua_pushvalue(L, methods);
    lua_getfield(L, library, "magnitude");
    lua_getfield(L, library, "normalize");
    lua_pushcclosure(L, vector3_index, "Vector3.__index", 3);
    lua_setfield(L, metatable, "__index");
    lua_pushcfunction(L, [](lua_State* S)->int {
        luaL_error(S, "%s cannot be assigned to", luaL_checkstring(S, 2)); return 0;
    }, nullptr); lua_setfield(L, metatable, "__newindex");
    lua_pushliteral(L, "Vector3"); lua_setfield(L, metatable, "__type");
    lua_pushliteral(L, "The metatable is locked"); lua_setfield(L, metatable, "__metatable");
    lua_setreadonly(L, metatable, true);
    lua_pushvector(L, 0, 0, 0);
    lua_pushvalue(L, metatable);
    lua_setmetatable(L, -2);
    lua_settop(L, base);
}
