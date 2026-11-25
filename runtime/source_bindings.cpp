#include "source_bindings.hpp"
#include "closure_bindings.hpp"
#include "script_thread_integrity.hpp"
#include "protected_script_load.hpp"
#include "sha256.hpp"
#include "local_source_trace.hpp"
#include <Luau/Compiler.h>
#include <Luau/Bytecode.h>
#include <Luau/BytecodeUtils.h>
#include <lualib.h>
#include <chrono>
#include <memory>
#include <string>
#include <vector>
#include <array>
#include <cstring>
#include <cstdio>
#include "platform_support.hpp"
#include <cstdlib>
#ifdef __APPLE__
#include <compression.h>
#else
#include <lz4.h>
#endif
#include <fstream>
#include "lapi.h"
#include "lstate.h"
#include "lgc.h"
#include "lmem.h"
#include "lfunc.h"
#include "ltable.h"
#include <algorithm>
#include "json.hpp"

namespace {
constexpr const char* kSourceBindingsRegistry="Headless.SourceBindings";
int device_tick(lua_State* L) {
    const auto now=std::chrono::system_clock::now().time_since_epoch();
    double seconds=std::chrono::duration<double>(now).count();
    // Roblox's legacy tick() returns epoch seconds in LOCAL time (os.time() plus
    // the host timezone offset), unlike os.time()/DateTime which are UTC.
    lua_pushnumber(L,seconds+static_cast<double>(local_timezone_offset_seconds()));return 1;
}
int collectgarbage_count(lua_State* L) {
    if(std::strcmp(luaL_checkstring(L,1),"count")!=0) {
        luaL_error(L,"collectgarbage only supports the count option");return 0;
    }
    lua_pushnumber(L,lua_gc(L,LUA_GCCOUNT,0)+lua_gc(L,LUA_GCCOUNTB,0)/1024.0);
    return 1;
}
int getgenv(lua_State* L) { lua_rawgetfield(L,LUA_REGISTRYINDEX,"Headless.ExecutorEnvironment"); return 1; }
int iscclosure(lua_State* L) { luaL_checktype(L,1,LUA_TFUNCTION); lua_pushboolean(L,lua_iscfunction(L,1)); return 1; }
int islclosure(lua_State* L) { luaL_checktype(L,1,LUA_TFUNCTION); lua_pushboolean(L,!lua_iscfunction(L,1)); return 1; }

// Env-gated diagnostic for the Luraph extraction route. Off by default.
static void trace_loadstring_diag(const char* chunk, const char* source, size_t length)
{
    static const bool enabled=[]{
        const char* v=std::getenv("ROVE_TRACE_LOADSTRING");
        return v && (v[0]=='1' || v[0]=='t' || v[0]=='T');
    }();
    if(!enabled)return;
    static unsigned seq=0;
    const char* dir=std::getenv("ROVE_TRACE_LOADSTRING_DIR");
    const std::string base=dir?dir:".";
    char path[512], manifest[512];
    std::snprintf(path,sizeof(path),"%s/loadstring_%03u.src",base.c_str(),++seq);
    std::snprintf(manifest,sizeof(manifest),"%s/manifest.txt",base.c_str());
    if(FILE* f=std::fopen(path,"wb")){
        std::fwrite(source,1,length,f);
        std::fclose(f);
    }
    char hex[160]; hex[0]=0;
    for(size_t i=0;i<length && i<64;++i)
        std::snprintf(hex+2*i,sizeof(hex)-2*i,"%02x",static_cast<unsigned char>(source[i]));
    if(FILE* m=std::fopen(manifest,"a")){
        const bool bytecode=length>=4 && static_cast<unsigned char>(source[0])==0x0e;
        std::fprintf(m,"%s\t%s\t%zu\t%s\t%s\n",path,chunk?chunk:"?",length,bytecode?"bytecode":"text",hex);
        std::fclose(m);
    }
}

int loadstring(lua_State* L) {
    size_t length=0;
    const char* source=luaL_checklstring(L,1,&length);
    const char* chunk=luaL_optstring(L,2,source);
    if(length>local_test_source_limit(100*1024*1024)) { luaL_error(L,"loadstring source exceeds configured input limit"); return 0; }
    trace_local_source(source,length);
    trace_loadstring_diag(chunk,source,length);
    auto* integrity=static_cast<ScriptThreadIntegrity*>(lua_touserdata(L,lua_upvalueindex(1)));
    if(integrity)integrity->check_load_thread();
    std::string code=Luau::compile(std::string(source,length));
    auto* store=static_cast<ProtectedScriptStore*>(lua_touserdata(L,lua_upvalueindex(2)));
    int status;
    if(store) {
        auto payload=store->make(std::string(source,length),code);
        status=load_protected_script(L,chunk,payload);
    } else status=luau_load(L,chunk,code.data(),code.size(),0);
    if(status!=0) {
        lua_pushnil(L); lua_insert(L,-2); return 2;
    }
    // Executor loadstring chunks run in the shared executor globals, so
    // getfenv(chunk) == getgenv() as in real executors.
    lua_getfield(L,LUA_REGISTRYINDEX,"Headless.ExecutorEnvironment");
    lua_setfenv(L,-2);
    mark_executor_closure(L,-1);
    return 1;
}
int codec(lua_State* L) {
    const auto* bindings=static_cast<const SourceBindings*>(lua_touserdata(L,lua_upvalueindex(1)));
    unsigned int operation=static_cast<unsigned int>(lua_tointeger(L,lua_upvalueindex(2)));
    size_t length=0;
    const auto* source=reinterpret_cast<const unsigned char*>(luaL_checklstring(L,1,&length));
    unsigned char* output=nullptr;
    size_t output_length=0;
    int status=bindings->codec(operation,source,length,&output,&output_length);
    if(status!=0) {
        const char* message=status==2
            ?(operation==1?"malformed Base64 input":"malformed or oversized zstd input")
            :"codec input exceeds limit";
        luaL_error(L,"%s",message);return 0;
    }
    // The scoped owner also frees Rust data if pushing to the VM raises OOM.
    auto release=[bindings,output_length](unsigned char* pointer){bindings->release(pointer,output_length);};
    std::unique_ptr<unsigned char,decltype(release)> owner(output,release);
    lua_pushlstring(L,reinterpret_cast<const char*>(output),output_length);
    return 1;
}
std::string crypt_string(lua_State* L,int index) {
    size_t length=0;const char* value=luaL_checklstring(L,index,&length);
    if(length>256*1024)throw std::runtime_error("crypt input exceeds 256 KiB");
    return std::string(value,length);
}
void check_sha256(lua_State* L,int index) {
    size_t length=0;const char* value=luaL_checklstring(L,index,&length);std::string algorithm(value,length);
    if(algorithm!="sha256"&&algorithm!="sha-256")luaL_error(L,"unsupported hash algorithm");
}
#include "extended_crypto.inc"
int crypt_hmac(lua_State* L) {
    try{check_sha256(L,3);auto result=source_crypto::hex(source_crypto::hmac_sha256(crypt_string(L,1),crypt_string(L,2)));lua_pushlstring(L,result.data(),result.size());return 1;}
    catch(const std::exception& e){luaL_error(L,"crypt.hmac failed: %s",e.what());return 0;}
}
void push_codec(lua_State* L, const SourceBindings* bindings, int operation) {
    const char* name=operation==0?"base64.encode":operation==1?"base64.decode"
        :operation==2?"zstdcompress":"zstddecompress";
    lua_pushlightuserdata(L,const_cast<SourceBindings*>(bindings));
    lua_pushinteger(L,operation);
    lua_pushcclosurek(L,codec,name,2,nullptr);
}
}

int source_encoding_codec(lua_State* L,EncodingCodec operation,int input_index,int parameter) {
    size_t length=0;
    const bool string_hash=operation==EncodingCodec::StringHash;
    if(string_hash)luaL_checktype(L,input_index,LUA_TSTRING);
    const void* input=string_hash?static_cast<const void*>(lua_tolstring(L,input_index,&length)):
        luaL_checkbuffer(L,input_index,&length);
    lua_getfield(L,LUA_REGISTRYINDEX,kSourceBindingsRegistry);
    const auto* bindings=static_cast<const SourceBindings*>(lua_touserdata(L,-1));
    lua_pop(L,1);
    if(!bindings)return luaL_error(L,"EncodingService codecs require the source host"),0;
    unsigned char* output=nullptr;
    size_t size=0;
    const int status=bindings->codec(static_cast<unsigned int>(operation),
        static_cast<const unsigned char*>(input),length,&output,&size,parameter);
    if(status==2&&operation==EncodingCodec::DecompressedSize){lua_pushnil(L);return 1;}
    if(status!=0) {
        const char* message=status==1?"input exceeds codec limit":status==3?"Zstandard library unavailable":
            operation==EncodingCodec::Base64Decode?"invalid Base64 input":
            string_hash||operation==EncodingCodec::BufferHash?"unknown hash algorithm":
            "invalid or oversized Zstandard data";
        return luaL_error(L,"EncodingService: %s",message),0;
    }
    auto release=[bindings,size](unsigned char* pointer){bindings->release(pointer,size);};
    std::unique_ptr<unsigned char,decltype(release)> owner(output,release);
    if(string_hash) {
        lua_pushlstring(L,reinterpret_cast<const char*>(output),size);
    }else if(operation==EncodingCodec::DecompressedSize) {
        const unsigned int decoded=unsigned(output[0])|(unsigned(output[1])<<8)|
            (unsigned(output[2])<<16)|(unsigned(output[3])<<24);
        lua_pushnumber(L,decoded);
    }else {
        void* buffer=lua_newbuffer(L,size);
        if(size)std::memcpy(buffer,output,size);
    }
    return 1;
}

#include "local_compat.inc"
#include "vm_debug_compat.inc"
#include "network_compat.inc"
#include "host_io_compat.inc"

void install_source_bindings(lua_State* L, const SourceBindings* bindings,
                             ScriptThreadIntegrity* thread_integrity,ProtectedScriptStore* protected_scripts) {
    lua_pushvalue(L,LUA_GLOBALSINDEX);lua_rawsetfield(L,LUA_REGISTRYINDEX,"Headless.ExecutorEnvironment");
    lua_pushlightuserdata(L,const_cast<SourceBindings*>(bindings));
    lua_setfield(L,LUA_REGISTRYINDEX,kSourceBindingsRegistry);
    lua_pushcfunction(L,device_tick,"tick");lua_setglobal(L,"tick");
    lua_pushcfunction(L,collectgarbage_count,"collectgarbage");lua_setglobal(L,"collectgarbage");
    lua_pushcfunction(L,getgenv,"getgenv"); lua_setglobal(L,"getgenv");
    lua_pushcfunction(L,iscclosure,"iscclosure"); lua_setglobal(L,"iscclosure");
    lua_pushcfunction(L,islclosure,"islclosure"); lua_setglobal(L,"islclosure");
    lua_pushlightuserdata(L,thread_integrity);
    lua_pushlightuserdata(L,protected_scripts);
    lua_pushcclosurek(L,loadstring,"loadstring",2,nullptr); lua_setglobal(L,"loadstring");
    lua_newtable(L); lua_setglobal(L,"shared");
    lua_newtable(L); lua_setglobal(L,"_G");
    lua_newtable(L);
    push_codec(L,bindings,0);lua_setfield(L,-2,"encode");
    push_codec(L,bindings,1);lua_setfield(L,-2,"decode");
    lua_setreadonly(L,-1,true);
    lua_pushvalue(L,-1);lua_setglobal(L,"base64");
    lua_newtable(L);
    lua_pushvalue(L,-2);lua_setfield(L,-2,"base64");
    for(const char* name:{"base64encode","base64_encode"}) {
        push_codec(L,bindings,0);lua_pushvalue(L,-1);lua_setglobal(L,name);lua_setfield(L,-2,name);
    }
    for(const char* name:{"base64decode","base64_decode"}) {
        push_codec(L,bindings,1);lua_pushvalue(L,-1);lua_setglobal(L,name);lua_setfield(L,-2,name);
    }
    push_codec(L,bindings,2);lua_pushvalue(L,-1);lua_setglobal(L,"zstdcompress");lua_setfield(L,-2,"zstdcompress");
    push_codec(L,bindings,3);lua_pushvalue(L,-1);lua_setglobal(L,"zstddecompress");lua_setfield(L,-2,"zstddecompress");
    lua_pushcfunction(L,crypt_hash,"crypt.hash");lua_setfield(L,-2,"hash");
    for(auto item:{std::pair<const char*,lua_CFunction>{"encrypt",crypt_encrypt},{"decrypt",crypt_decrypt},{"generatebytes",crypt_generatebytes},{"generatekey",crypt_generatekey}}){
        lua_pushlightuserdata(L,const_cast<SourceBindings*>(bindings));lua_pushcclosurek(L,item.second,item.first,1,nullptr);lua_setfield(L,-2,item.first);
    }
    lua_pushcfunction(L,crypt_hmac,"crypt.hmac");lua_pushvalue(L,-1);lua_setglobal(L,"hmac");lua_setfield(L,-2,"hmac");
    lua_setreadonly(L,-1,true);lua_setglobal(L,"crypt");lua_pop(L,1);
    install_local_compat(L);
    install_vm_debug(L);
    install_network_compat(L,bindings);
    install_host_io(L,bindings);
    lua_pushcfunction(L,lz4_compress,"lz4compress");lua_setglobal(L,"lz4compress");
    lua_pushcfunction(L,lz4_decompress,"lz4decompress");lua_setglobal(L,"lz4decompress");
    // Luraph env probes hash iscclosure across the executor surface, so every
    // function handed out must read as a native C closure. Wrap the remaining
    // Lua globals (host I/O, network, drawing) the same way real executors do.
    {
        const char* sweep=
            "local env=getfenv() "
            "local wrapped={} "
            "for k,v in pairs(env) do "
            "if type(v)==\"function\" and not iscclosure(v) then "
            "local w=wrapped[v]; if not w then w=newcclosure(v,k); wrapped[v]=w end; env[k]=w "
            "end end "
            "-- Library members must alias the same wrapped function object as "
            "-- their global names (real executors expose one closure per API). "
            "if type(env.http)=='table' and type(env.request)=='function' then "
            "pcall(function() env.http.request=env.request end) end";
        std::string bytecode=Luau::compile(sweep);
        if(luau_load(L,"=executor-c-sweep",bytecode.data(),bytecode.size(),0)!=0)lua_error(L);
        mark_executor_closure(L,-1);lua_call(L,0,0);
    }
    // These functions were installed by the executor; engine/library functions
    // inherited from the base environment keep their original classification.
    lua_pushnil(L);
    while(lua_next(L,LUA_GLOBALSINDEX)) {
        if(lua_isfunction(L,-1))mark_executor_closure(L,-1);
        lua_pop(L,1);
    }
    for(const char* library:{"debug","cache","crypt","base64","Drawing","WebSocket","http","fs","filesystem"}) {
        lua_getglobal(L,library);
        if(lua_istable(L,-1)) {
            lua_pushnil(L);
            while(lua_next(L,-2)) {
                bool engine_debug=std::strcmp(library,"debug")==0&&lua_type(L,-2)==LUA_TSTRING&&
                    (std::strcmp(lua_tostring(L,-2),"info")==0||std::strcmp(lua_tostring(L,-2),"traceback")==0);
                if(lua_isfunction(L,-1)&&!engine_debug)mark_executor_closure(L,-1);
                lua_pop(L,1);
            }
        }
        lua_pop(L,1);
    }
}
