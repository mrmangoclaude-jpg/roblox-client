#include <cstring>
// Named tags backed by Luau's actual per-thread allocation categories.
// Registry storage belongs to this VM; no process-global category state.
namespace {
char memory_category_registry_key;
char memory_category_current_key;
// The active tag of each thread, kept in a weak-keyed registry table. A thread that never set one reports the
// chunk name of its caller, which is what Roblox shows for a script.
void memory_category_push_current(lua_State* L) {
    lua_pushlightuserdata(L,&memory_category_current_key);lua_rawget(L,LUA_REGISTRYINDEX);
    if(lua_istable(L,-1)) {
        lua_pushthread(L);lua_rawget(L,-2);
        if(lua_isstring(L,-1)){lua_remove(L,-2);return;}
        lua_pop(L,1);
    }
    lua_pop(L,1);
    // A thread that never set one reports the name of the script it runs in ("ReplicatedFirst.Guard" -> "Guard").
    lua_Debug frame{};
    if(lua_getinfo(L,1,"s",&frame)&&frame.source) {
        const char* name=frame.source+(frame.source[0]=='='?1:0);
        const char* dot=std::strrchr(name,'.');
        lua_pushstring(L,dot?dot+1:name);
    } else lua_pushstring(L,"");
}
// Stores the value at `index` as the running thread's tag.
void memory_category_store_current(lua_State* L,int index) {
    index=lua_absindex(L,index);
    lua_pushlightuserdata(L,&memory_category_current_key);lua_rawget(L,LUA_REGISTRYINDEX);
    if(lua_isnil(L,-1)) {
        lua_pop(L,1);lua_newtable(L);
        lua_newtable(L);lua_pushstring(L,"k");lua_setfield(L,-2,"__mode");lua_setmetatable(L,-2);
        lua_pushlightuserdata(L,&memory_category_current_key);lua_pushvalue(L,-2);lua_rawset(L,LUA_REGISTRYINDEX);
    }
    lua_pushthread(L);lua_pushvalue(L,index);lua_rawset(L,-3);lua_pop(L,1);
}
int memory_category_set(lua_State* L) {
    size_t length=0;luaL_checklstring(L,1,&length);
    if(length>256)return luaL_error(L,"memory category name exceeds 256 bytes"),0;
    lua_pushlightuserdata(L,&memory_category_registry_key);lua_rawget(L,LUA_REGISTRYINDEX);
    if(lua_isnil(L,-1)) {
        lua_pop(L,1);lua_newtable(L);
        lua_pushlightuserdata(L,&memory_category_registry_key);lua_pushvalue(L,-2);lua_rawset(L,LUA_REGISTRYINDEX);
    }
    if(!lua_istable(L,-1))return luaL_error(L,"invalid VM memory category registry"),0;
    const int categories=lua_gettop(L);
    lua_pushvalue(L,1);lua_rawget(L,categories);
    int category=lua_isnumber(L,-1)?lua_tointeger(L,-1):0;lua_pop(L,1);
    if(!category) {
        category=lua_objlen(L,categories)+1;
        if(category>=LUA_MEMORY_CATEGORIES)return luaL_error(L,"local VM memory category limit exceeded"),0;
        lua_pushvalue(L,1);lua_pushinteger(L,category);lua_rawset(L,categories);
        lua_pushvalue(L,1);lua_rawseti(L,categories,category);
    }
    if(category<1||category>=LUA_MEMORY_CATEGORIES)return luaL_error(L,"invalid VM memory category"),0;
    memory_category_push_current(L);
    lua_setmemcat(L,category);
    memory_category_store_current(L,1);
    return 1;
}
int memory_category_reset(lua_State* L){
    lua_setmemcat(L,0);
    lua_pushstring(L,"1");memory_category_store_current(L,lua_gettop(L));lua_pop(L,1);
    return 0;
}
int memory_category_get(lua_State* L){memory_category_push_current(L);return 1;}
// The label is ignored. A missing or nil label raises Roblox's own message; other wrong types get the usual type error.
int profile_begin(lua_State* L) {
    if(lua_isnoneornil(L,1))
        luaL_error(L,"debug.profilebegin(string) parameter must be string, got an unexpected type. Not opening profile block.");
    luaL_checkstring(L,1);
    return 0;
}
int profile_end(lua_State*){return 0;}
// Members the engine's debug library has but game scripts cannot use; they raise the engine's own messages.
int debug_dump_code_size(lua_State* L){return luaL_error(L,"dumpcodesize can only be called from CommandBar"),0;}
int debug_not_enabled(lua_State* L){
    lua_Debug frame{};const char* name=lua_getinfo(L,0,"n",&frame)&&frame.name?frame.name:"?";
    return luaL_error(L,"debug.%s is not enabled.",name),0;
}
void install_memory_category_bindings(lua_State* L) {
    lua_pushcfunction(L,profile_begin,"profilebegin");lua_setfield(L,-2,"profilebegin");
    lua_pushcfunction(L,profile_end,"profileend");lua_setfield(L,-2,"profileend");
    lua_pushcfunction(L,debug_dump_code_size,"dumpcodesize");lua_setfield(L,-2,"dumpcodesize");
    for(const char* name:{"dumpheap","dumprefs","tracerefs","loadmodule"}){lua_pushcfunction(L,debug_not_enabled,name);lua_setfield(L,-2,name);}
    lua_pushcfunction(L,memory_category_get,"getmemorycategory");lua_setfield(L,-2,"getmemorycategory");
    lua_pushcfunction(L,memory_category_set,"setmemorycategory");lua_setfield(L,-2,"setmemorycategory");
    lua_pushcfunction(L,memory_category_reset,"resetmemorycategory");lua_setfield(L,-2,"resetmemorycategory");
}
}
