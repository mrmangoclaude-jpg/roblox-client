// Local VM compatibility helpers. These do not access another process or
// elevate script permissions. File APIs below use a bounded per-VM workspace.
Closure* local_lclosure(lua_State* L,int index);
int debug_integer(lua_State* L,int index,int minimum);
int compat_getinfo(lua_State* L) {
    int level=lua_isfunction(L,1)?-lua_gettop(L):luaL_checkinteger(L,1);
    if(!lua_isfunction(L,1)&&level<0){luaL_error(L,"stack level must be nonnegative");return 0;}
    lua_Debug info{};
    if(!lua_getinfo(L,level,"slnuaf",&info)){lua_pushnil(L);return 1;}
    int function=lua_gettop(L);lua_newtable(L);
    auto text=[&](const char* key,const char* value){lua_pushstring(L,value?value:"");lua_setfield(L,-2,key);};
    auto number=[&](const char* key,int value){lua_pushinteger(L,value);lua_setfield(L,-2,key);};
    text("source",info.source);text("short_src",info.short_src);text("what",info.what);text("name",info.name);
    number("currentline",info.currentline);number("linedefined",info.linedefined);
    number("nups",info.nupvals);number("numparams",info.nparams);number("is_vararg",info.isvararg);
    lua_pushvalue(L,function);lua_setfield(L,-2,"func");return 1;
}
int compat_upvalue(lua_State* L) {
    auto* closure=local_lclosure(L,1);int index=debug_integer(L,2,1);
    TValue function;setclvalue(L,&function,closure);luaA_pushvalue(L,&function);
    if(!lua_getupvalue(L,-1,index))return luaL_error(L,"upvalue index out of range"),0;
    return 1;
}
int compat_upvalues(lua_State* L) {
    auto* closure=local_lclosure(L,1);TValue function;setclvalue(L,&function,closure);luaA_pushvalue(L,&function);
    int target=lua_gettop(L);lua_newtable(L);
    for(int i=1;lua_getupvalue(L,target,i);++i)lua_rawseti(L,-2,i);
    return 1;
}
int compat_setupvalue(lua_State* L) {
    auto* closure=local_lclosure(L,1);int index=debug_integer(L,2,1);luaL_checkany(L,3);
    TValue function;setclvalue(L,&function,closure);luaA_pushvalue(L,&function);
    lua_pushvalue(L,3);
    if(!lua_setupvalue(L,-2,index)){luaL_error(L,"upvalue index out of range");return 0;}
    lua_setsafeenv(L,LUA_GLOBALSINDEX,false);return 0;
}
int compat_rawmetatable(lua_State* L) {
    luaL_checkany(L,1);if(!lua_getmetatable(L,1))lua_pushnil(L);return 1;
}
int compat_setmetatable(lua_State* L) {
    luaL_checkany(L,1);
    if(!lua_isnil(L,2))luaL_checktype(L,2,LUA_TTABLE);
    lua_settop(L,2);lua_setmetatable(L,1);lua_pushvalue(L,1);return 1;
}
int compat_readonly(lua_State* L) {
    luaL_checktype(L,1,LUA_TTABLE);lua_pushboolean(L,lua_getreadonly(L,1));return 1;
}
int compat_setreadonly(lua_State* L) {
    luaL_checktype(L,1,LUA_TTABLE);luaL_checktype(L,2,LUA_TBOOLEAN);
    lua_setreadonly(L,1,lua_toboolean(L,2));lua_setsafeenv(L,1,false);lua_setsafeenv(L,LUA_GLOBALSINDEX,false);return 0;
}
int compat_registry(lua_State* L) {lua_pushvalue(L,LUA_REGISTRYINDEX);return 1;}
#include "memory_categories.inc"
#include "filesystem_compat.inc"
void install_local_compat(lua_State* L) {
    // Roblox locks the string metatable: getmetatable("") yields the protection
    // string while getrawmetatable still exposes the table. Luraph's env probe
    // fingerprints this, so the bare Luau string metatable must carry __metatable.
    lua_pushliteral(L,"");
    if(lua_getmetatable(L,-1)) {
        int was_readonly=lua_getreadonly(L,-1);
        if(was_readonly)lua_setreadonly(L,-1,false);
        lua_pushliteral(L,"The metatable is locked");
        lua_setfield(L,-2,"__metatable");
        if(was_readonly)lua_setreadonly(L,-1,true);
        lua_pop(L,1);
    }
    lua_pop(L,1);
    // Retain Luau's genuine info/traceback implementations when extending the
    // debug surface. A fresh table discarded them from every source VM.
    lua_newtable(L);int debug_table=lua_gettop(L);
    lua_getfield(L,LUA_REGISTRYINDEX,"_LOADED");lua_getfield(L,-1,"debug");
    for(const char* name:{"info","traceback"}) {
        lua_getfield(L,-1,name);luaL_checktype(L,-1,LUA_TFUNCTION);
        lua_setfield(L,debug_table,name);
    }
    lua_pop(L,2);
    for(auto binding:{std::pair<const char*,lua_CFunction>{"getinfo",compat_getinfo},{"getupvalue",compat_upvalue},{"getupvalues",compat_upvalues},{"setupvalue",compat_setupvalue}}) {
        lua_pushcfunction(L,binding.second,binding.first);lua_setfield(L,-2,binding.first);
    }
    lua_pushcfunction(L,compat_registry,"getregistry");
    lua_pushvalue(L,-1);lua_setglobal(L,"getreg");
    lua_pushvalue(L,-1);lua_setglobal(L,"getregistry");
    lua_setfield(L,-2,"getregistry");
    install_memory_category_bindings(L);
    lua_setglobal(L,"debug");
    for(auto binding:{std::pair<const char*,lua_CFunction>{"getrawmetatable",compat_rawmetatable},{"setrawmetatable",compat_setmetatable},{"isreadonly",compat_readonly},{"setreadonly",compat_setreadonly}}) {
        lua_pushcfunction(L,binding.second,binding.first);lua_setglobal(L,binding.first);
    }
    const char* source=
#include "local_workspace.inc"
    ;
    std::string bytecode=Luau::compile(source);
    if(luau_load(L,"=local-workspace",bytecode.data(),bytecode.size(),0)!=0)lua_error(L);
    mark_executor_closure(L,-1);lua_call(L,0,0);
    install_filesystem_compat(L);
    const char* drawing=
#include "drawing_compat.inc"
    ;
    bytecode=Luau::compile(drawing);
    if(luau_load(L,"=drawing-compat",bytecode.data(),bytecode.size(),0)!=0)lua_error(L);
    mark_executor_closure(L,-1);lua_call(L,0,0);
}
