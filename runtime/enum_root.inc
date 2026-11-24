// Enumerate supported canonical enum objects without consulting a replaceable
// global. The runtime implements a subset of the full engine enum catalog.
int enum_root_get_enums(lua_State* L) {
    bool receiver=false;
    if(lua_type(L,1)==LUA_TUSERDATA&&lua_getmetatable(L,1)){luaL_getmetatable(L,kEnumsMeta);receiver=lua_rawequal(L,-1,-2)!=0;lua_pop(L,2);}
    if(!receiver)luaL_typeerror(L,1,"Enums");
    std::vector<std::string> names;
    lua_pushnil(L);
    while(lua_next(L,lua_upvalueindex(1))) {
        if(lua_type(L,-2)==LUA_TSTRING&&lua_isuserdata(L,-1))names.emplace_back(lua_tostring(L,-2));
        lua_pop(L,1);
    }
    std::sort(names.begin(),names.end());
    lua_createtable(L,int(names.size()),0);int index=1;
    for(const auto& name:names){lua_getfield(L,lua_upvalueindex(1),name.c_str());lua_rawseti(L,-2,index++);}
    return 1;
}
static int enums_index(lua_State* L) {
    luaL_checkudata(L,1,kEnumsMeta);
    lua_getfield(L,LUA_REGISTRYINDEX,"Headless.EnumCatalog");
    lua_pushvalue(L,2);
    lua_rawget(L,-2);
    // An enum the catalog does not have is "not a valid member", as in Roblox, rather than nil.
    if(lua_isnil(L,-1)){const char* key=lua_tostring(L,2);luaL_error(L,"%s is not a valid member of \"Enum\"",key?key:"?");return 0;}
    return 1;
}
static int enums_tostring(lua_State* L) { lua_pushliteral(L,"Enums"); return 1; }
static int enums_readonly(lua_State* L) { luaL_error(L,"%s is not a valid member of Enums",lua_tostring(L,2)?lua_tostring(L,2):"?"); return 0; }
// Roblox's Enums userdata is iterable (`for name, enum in pairs(Enum) do`).
static int enums_next(lua_State* L) {
    lua_settop(L,2);
    return lua_next(L,1) ? 2 : 0;
}
static int enums_pairs(lua_State* L) {
    luaL_checkudata(L,1,kEnumsMeta);
    lua_getfield(L,LUA_REGISTRYINDEX,"Headless.EnumCatalog");
    lua_pushcfunction(L,enums_next,"next");
    lua_pushvalue(L,-2);
    lua_pushnil(L);
    return 3;
}
// The engine exposes Enum as opaque userdata (typeof "Enums"), not a table.
// Build the catalog as a table so the install_* helpers populate it unchanged,
// then hide it behind a userdata wrapper whose __index reads the catalog.
void install_enum_root(lua_State* L) {
    if(luaL_newmetatable(L,kEnumsMeta)) {
        lua_pushcfunction(L,enums_index,"__index");lua_setfield(L,-2,"__index");
        lua_pushcfunction(L,enums_pairs,"__pairs");lua_setfield(L,-2,"__pairs");
        lua_pushcfunction(L,enums_tostring,"__tostring");lua_setfield(L,-2,"__tostring");
        lua_pushcfunction(L,enums_readonly,"__newindex");lua_setfield(L,-2,"__newindex");
        lua_pushliteral(L,"Enums");lua_setfield(L,-2,"__type");
        lua_pushliteral(L,"The metatable is locked");lua_setfield(L,-2,"__metatable");
    }
    lua_pop(L,1);
    lua_pushvalue(L,-1);lua_pushcclosure(L,enum_root_get_enums,"GetEnums",1);
    lua_setfield(L,-2,"GetEnums");
    lua_setfield(L,LUA_REGISTRYINDEX,"Headless.EnumCatalog");
    lua_newuserdatatagged(L,1,0);
    luaL_getmetatable(L,kEnumsMeta);lua_setmetatable(L,-2);
}