#include "closure_bindings.hpp"

#include <lualib.h>
#include <Luau/Bytecode.h>
#include "lapi.h"
#include "lstate.h"
#include "lfunc.h"
#include "lgc.h"
#include "lmem.h"
#include <utility>
#include <string>

namespace {
char executor_prototype;
constexpr const char* kOwned="Headless.ExecutorClosures";
constexpr const char* kHooks="Headless.ClosureHooks";
constexpr const char* kRoutes="Headless.ClosureRoutes";
constexpr const char* kWrapped="Headless.WrappedClosures";

void registry_table(lua_State* L,const char* name) {
    lua_rawgetfield(L,LUA_REGISTRYINDEX,name);
    if(lua_istable(L,-1))return;
    lua_pop(L,1);lua_newtable(L);lua_newtable(L);
    lua_pushliteral(L,"k");lua_setfield(L,-2,"__mode");lua_setmetatable(L,-2);
    lua_pushvalue(L,-1);lua_rawsetfield(L,LUA_REGISTRYINDEX,name);
}
void mark_prototype(Proto* p) {
    p->userdata=&executor_prototype;
    for(int i=0;i<p->sizep;++i)mark_prototype(p->p[i]);
}
void copy_entry(lua_State* L,const char* name,int from,int to) {
    from=lua_absindex(L,from);to=lua_absindex(L,to);registry_table(L,name);
    lua_pushvalue(L,to);lua_pushvalue(L,from);lua_rawget(L,-3);lua_rawset(L,-3);lua_pop(L,1);
}

// Forward arguments and return all values through Luau's public yieldable-call
// API. The continuation is required even when the wrapped function returns
// synchronously; it also resumes a yielded Luau function without losing values.
int call_continuation(lua_State* L, int status) {
    if (status != LUA_OK) {
        // This path is reached when a wrapped function errors after yielding.
        // Preserve its error object so the caller's pcall sees the failure.
        if (lua_gettop(L) == 0) lua_pushliteral(L, "wrapped function failed after yielding");
        lua_error(L);
        return 0;
    }
    return lua_gettop(L);
}

int call_wrapped_function(lua_State* L) {
    const int argument_count = lua_gettop(L);
    registry_table(L,kWrapped);luaA_pushvalue(L,L->ci->func);lua_rawget(L,-2);lua_remove(L,-2);
    if(!lua_isfunction(L,-1))return luaL_error(L,"wrapped function is unavailable"),0;
    lua_insert(L, 1);
    return lua_pcallyieldable(L, argument_count, LUA_MULTRET,0);
}
int wrapped_continuation(lua_State* L,int status) {
    if(status!=LUA_OK&&lua_type(L,-1)==LUA_TSTRING) {
        size_t length;const char* raw=lua_tolstring(L,-1,&length);std::string error(raw,length);
        for(size_t colon=error.find(':');colon!=std::string::npos;colon=error.find(':',colon+1)) {
            size_t end=colon+1;while(end<error.size()&&error[end]>='0'&&error[end]<='9')++end;
            if(end>colon+1&&end+1<error.size()&&error[end]==':'&&error[end+1]==' ') {
                lua_pop(L,1);lua_pushlstring(L,error.data()+end+2,error.size()-end-2);break;
            }
        }
    }
    return call_continuation(L,status);
}

int clonefunction(lua_State* L) {
    luaL_checktype(L, 1, LUA_TFUNCTION);
    // Public clone cannot reproduce an executor C closure that carries its
    // own private state (upvalues). Plain native functions and newcclosure
    // trampolines have no private state and remain cloneable.
    auto* fn = clvalue(luaA_toobject(L, 1));
    if (fn->isC && fn->nupvalues > 0)
        return luaL_error(L, "clonefunction: cannot clone a C closure"), 0;
    push_closure_clone(L,1);
    return 1;
}

int call_hook(lua_State* L) {
    const int arguments=lua_gettop(L);
    registry_table(L,kRoutes);
    luaA_pushvalue(L,L->ci->func);lua_rawget(L,-2);lua_remove(L,-2);
    if(!lua_isfunction(L,-1))return luaL_error(L,"hook target is unavailable"),0;
    lua_insert(L,1);return lua_callyieldable(L,arguments,LUA_MULTRET);
}

// A zero-capture Lua forwarding prototype keeps the target's allocation kind
// and capacity intact when its replacement is native. It uses a real function
// constant, so it neither depends on mutable globals nor leaks a helper name.
Proto* forwarding_prototype(lua_State* L,int replacement,Proto* original) {
    auto* p=luaF_newproto(L);
    p->is_vararg=1;p->maxstacksize=2;
    p->code=luaM_newarray(L,5,Instruction,p->memcat);p->sizecode=5;
    p->code[0]=LOP_PREPVARARGS;
    p->code[1]=LOP_LOADK;
    p->code[2]=LOP_GETVARARGS|(1u<<8);
    p->code[3]=LOP_CALL;
    p->code[4]=LOP_RETURN;
    p->codeentry=p->code;
    p->k=luaM_newarray(L,1,TValue,p->memcat);p->sizek=1;
    setobj(L,&p->k[0],luaA_toobject(L,replacement));
    p->source=original->source;p->debugname=original->debugname;
    p->linedefined=original->linedefined;p->userdata=original->userdata;
    return p;
}

void copy_body(lua_State* L,Closure* to,Closure* from) {
    to->inactive=from->inactive;
    to->env=from->env;to->stacksize=from->stacksize;to->preload=from->preload;
    luaC_objbarrier(L,to,to->env);
    if(to->isC) {
        to->c.f=from->c.f;to->c.cont=from->c.cont;to->c.debugname=from->c.debugname;
        if(to->c.debugname)luaC_objbarrier(L,to,to->c.debugname);
    }else {to->l.p=from->l.p;luaC_objbarrier(L,to,to->l.p);}
    auto* dst=to->isC?to->c.upvals:to->l.uprefs;
    auto* src=from->isC?from->c.upvals:from->l.uprefs;
    for(int i=0;i<from->nupvalues;++i){setobj(L,&dst[i],&src[i]);luaC_barrier(L,to,&dst[i]);}
    for(int i=from->nupvalues;i<to->nupvalues;++i)setnilvalue(&dst[i]);
}

int hookfunction(lua_State* L) {
    luaL_checktype(L,1,LUA_TFUNCTION);luaL_checktype(L,2,LUA_TFUNCTION);
    auto* target=clvalue(luaA_toobject(L,1));auto* replacement=clvalue(luaA_toobject(L,2));
    if(target->inactive||replacement->inactive)return luaL_error(L,"inactive prototypes cannot be hooked"),0;
    if(!target->isC&&!replacement->isC&&replacement->nupvalues>target->nupvalues)
        return luaL_error(L,"replacement needs more captured slots than the target closure"),0;
    push_closure_clone(L,1);const int previous=lua_gettop(L);
    registry_table(L,kHooks);lua_pushvalue(L,1);lua_rawget(L,-2);
    const bool first=lua_isnil(L,-1);lua_pop(L,1);
    if(first){lua_pushvalue(L,1);push_closure_clone(L,previous);lua_rawset(L,-3);}
    lua_pop(L,1);
    if(target->isC) {
        // Snapshot the replacement so later hooks on it cannot rewrite this
        // target or the original returned from an earlier hook.
        push_closure_clone(L,2);const int route=lua_gettop(L);
        registry_table(L,kRoutes);lua_pushvalue(L,1);lua_pushvalue(L,route);lua_rawset(L,-3);lua_pop(L,2);
        target->c.f=call_hook;target->c.cont=call_continuation;
    }else if(!replacement->isC)copy_body(L,target,replacement);
    else {
        push_closure_clone(L,2);
        target->l.p=forwarding_prototype(L,-1,target->l.p);
        target->stacksize=target->l.p->maxstacksize;target->preload=0;
        luaC_objbarrier(L,target,target->l.p);lua_pop(L,1);
        for(int i=0;i<target->nupvalues;++i)setnilvalue(&target->l.uprefs[i]);
    }
    // Imported fastcalls are disabled in the caller's environment so a hook
    // of a standard library function is observed by ordinary Luau calls.
    lua_setsafeenv(L,LUA_GLOBALSINDEX,false);
    lua_pushvalue(L,previous);return 1;
}

int restorefunction(lua_State* L) {
    luaL_checktype(L,1,LUA_TFUNCTION);registry_table(L,kHooks);
    lua_pushvalue(L,1);lua_rawget(L,-2);
    if(!lua_isfunction(L,-1))return luaL_error(L,"function has not been hooked"),0;
    auto* target=clvalue(luaA_toobject(L,1));auto* original=clvalue(luaA_toobject(L,-1));
    copy_body(L,target,original);copy_entry(L,kRoutes,-1,1);
    lua_pop(L,1);lua_pushvalue(L,1);lua_pushnil(L);lua_rawset(L,-3);
    return 0;
}

int newcclosure(lua_State* L) {
    luaL_checktype(L, 1, LUA_TFUNCTION);
    const char* name = luaL_optstring(L, 2, "newcclosure");

    // Wrapping an existing native function would add a redundant trampoline
    // and alter its debug name, so preserve its identity as native executors do.
    if (lua_iscfunction(L, 1)) {
        lua_pushvalue(L, 1);
        return 1;
    }

    lua_pushcclosurek(L, call_wrapped_function, name, 0, wrapped_continuation);
    registry_table(L,kWrapped);lua_pushvalue(L,-2);lua_pushvalue(L,1);lua_rawset(L,-3);lua_pop(L,1);

    // Keep the visible environment consistent with the wrapped closure.
    lua_getfenv(L, 1);
    lua_setfenv(L, -2);
    mark_executor_closure(L,-1);
    return 1;
}

int isnewcclosure(lua_State* L) {
    luaL_checktype(L, 1, LUA_TFUNCTION);
    const bool result = lua_iscfunction(L, 1) && lua_tocfunction(L, 1) == call_wrapped_function;
    lua_pushboolean(L, result);
    return 1;
}

int getupvalue(lua_State* L) {
    luaL_checktype(L, 1, LUA_TFUNCTION);
    const int index = luaL_checkinteger(L, 2);
    // Executor getupvalue exposes the function behind a newcclosure wrapper
    // even though the native trampoline itself reports zero real upvalues.
    if (lua_iscfunction(L, 1) && lua_tocfunction(L, 1) == call_wrapped_function && index == 1) {
        registry_table(L, kWrapped);
        lua_pushvalue(L, 1); lua_rawget(L, -2); lua_remove(L, -2);
        if (lua_isfunction(L, -1)) return 1;
        lua_pop(L, 1);
    }
    if (!lua_getupvalue(L, 1, index))
        lua_pushnil(L);
    return 1;
}

int isfunctionhooked(lua_State* L) {
    luaL_checktype(L,1,LUA_TFUNCTION);registry_table(L,kHooks);
    lua_pushvalue(L,1);lua_rawget(L,-2);
    const bool hooked=lua_isfunction(L,-1);lua_pop(L,2);lua_pushboolean(L,hooked);return 1;
}

} // namespace

void mark_executor_closure(lua_State* L,int index) {
    index=lua_absindex(L,index);auto* closure=clvalue(luaA_toobject(L,index));
    if(!closure->isC){mark_prototype(closure->l.p);return;}
    registry_table(L,kOwned);lua_pushvalue(L,index);lua_pushboolean(L,true);lua_rawset(L,-3);lua_pop(L,1);
}
bool is_executor_closure(lua_State* L,int index) {
    index=lua_absindex(L,index);auto* closure=clvalue(luaA_toobject(L,index));
    if(!closure->isC)return closure->l.p->userdata==&executor_prototype;
    registry_table(L,kOwned);lua_pushvalue(L,index);lua_rawget(L,-2);
    const bool result=lua_toboolean(L,-1);lua_pop(L,2);return result;
}
void push_closure_clone(lua_State* L,int index) {
    index=lua_absindex(L,index);auto* original=clvalue(luaA_toobject(L,index));
    if(!original->isC) {
        lua_clonefunction(L,index);lua_getfenv(L,index);lua_setfenv(L,-2);
    }else {
        auto* clone=luaF_newCclosure(L,original->nupvalues,original->env);
        copy_body(L,clone,original);
        TValue value;setclvalue(L,&value,clone);luaA_pushvalue(L,&value);
        copy_entry(L,kRoutes,index,-1);copy_entry(L,kWrapped,index,-1);copy_entry(L,kOwned,index,-1);
    }
}

void install_closure_bindings(lua_State* L) {
    for(auto item:{std::pair<const char*,lua_CFunction>{"hookfunction",hookfunction},{"replaceclosure",hookfunction},{"restorefunction",restorefunction},{"isfunctionhooked",isfunctionhooked},{"ishooked",isfunctionhooked}}) {
        lua_pushcfunction(L,item.second,item.first);mark_executor_closure(L,-1);lua_setglobal(L,item.first);
    }
    lua_pushcfunction(L, clonefunction, "clonefunction");
    lua_setglobal(L, "clonefunction");
    lua_pushcfunction(L, clonefunction, "clonefunc");
    lua_setglobal(L, "clonefunc");
    lua_pushcfunction(L, newcclosure, "newcclosure");
    lua_setglobal(L, "newcclosure");
    lua_pushcfunction(L, isnewcclosure, "isnewcclosure");
    lua_setglobal(L, "isnewcclosure");
    lua_pushcfunction(L, getupvalue, "getupvalue");
    lua_setglobal(L, "getupvalue");
    for(const char* name:{"clonefunction","clonefunc","newcclosure","isnewcclosure","getupvalue"}) {
        lua_getglobal(L,name);mark_executor_closure(L,-1);lua_pop(L,1);
    }
}
