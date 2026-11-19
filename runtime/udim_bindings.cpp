#include "udim_bindings.hpp"
#include <lua.h>
#include <lualib.h>
#include <cmath>
#include <cstdint>
#include <limits>
#include <new>
#include <sstream>
#include <iomanip>
#include <string>

namespace {
constexpr const char* kUDim = "LocalLuau.UDim";
constexpr const char* kUDim2 = "LocalLuau.UDim2";
struct UDimValue { double scale; int32_t offset; };
struct UDim2Value { UDimValue x, y; };
int udim2_lerp(lua_State* L);

bool valid_number(lua_State* L, int index, double* out) {
    if (!lua_isnumber(L,index)) return false;
    double value=lua_tonumber(L,index);
    if (!std::isfinite(value) || std::abs(value)>1.0e9) return false;
    *out=value;return true;
}
bool valid_offset(double value) {
    return std::isfinite(value) && std::abs(value)<=static_cast<double>(std::numeric_limits<int32_t>::max());
}
bool has_metatable(lua_State* L,int index,const char* name) {
    if(!lua_getmetatable(L,index))return false;
    luaL_getmetatable(L,name);bool same=lua_rawequal(L,-1,-2)!=0;lua_pop(L,2);return same;
}
bool read_udim(lua_State* L,int index,UDimValue* out) {
    if(!has_metatable(L,index,kUDim))return false;
    auto* value=static_cast<UDimValue*>(lua_touserdata(L,index));
    *out=*value;return true;
}
bool read_udim2(lua_State* L,int index,UDim2Value* out) {
    if(!has_metatable(L,index,kUDim2))return false;
    auto* value=static_cast<UDim2Value*>(lua_touserdata(L,index));
    *out=*value;return true;
}
void push_udim(lua_State* L,UDimValue value) {
    // Roblox stores UDim scale as float32; round once on storage.
    value.scale=static_cast<double>(static_cast<float>(value.scale));
    auto* out=static_cast<UDimValue*>(lua_newuserdatadtor(L,sizeof(UDimValue),nullptr));
    new(out) UDimValue(value);
    luaL_getmetatable(L,kUDim);lua_setmetatable(L,-2);
}
void push_udim2(lua_State* L,UDim2Value value) {
    value.x.scale=static_cast<double>(static_cast<float>(value.x.scale));
    value.y.scale=static_cast<double>(static_cast<float>(value.y.scale));
    auto* out=static_cast<UDim2Value*>(lua_newuserdatadtor(L,sizeof(UDim2Value),nullptr));
    new(out) UDim2Value(value);
    luaL_getmetatable(L,kUDim2);lua_setmetatable(L,-2);
}
int udim_new(lua_State* L) {
    int n=lua_gettop(L);if(n>2){luaL_error(L,"UDim.new accepts at most two numbers");return 0;}
    double scale=0,offset=0;
    if(n>=1&&!lua_isnil(L,1)&&!valid_number(L,1,&scale)){luaL_error(L,"UDim scale must be a finite bounded number");return 0;}
    if(n>=2&&!lua_isnil(L,2)&&!valid_number(L,2,&offset)){luaL_error(L,"UDim offset must be a finite bounded number");return 0;}
    if(!valid_offset(offset)){luaL_error(L,"UDim offset exceeds the supported integer range");return 0;}
    // UDim stores pixel offsets as signed integers. Match native integer conversion.
    push_udim(L,{scale,static_cast<int32_t>(std::trunc(offset))});return 1;
}
int udim_index(lua_State* L) {
    auto* v=static_cast<UDimValue*>(luaL_checkudata(L,1,kUDim));
    const char* key=luaL_checkstring(L,2);
    if(std::string(key)=="Scale")lua_pushnumber(L,v->scale);
    else if(std::string(key)=="Offset")lua_pushinteger(L,v->offset);
    else lua_pushnil(L);
    return 1;
}
int udim_add(lua_State* L) {
    UDimValue a,b;if(!read_udim(L,1,&a))luaL_typeerror(L,1,"UDim");if(!read_udim(L,2,&b))luaL_typeerror(L,2,"UDim");
    int64_t offset=static_cast<int64_t>(a.offset)+b.offset;
    double scale=a.scale+b.scale;
    if(offset<std::numeric_limits<int32_t>::min()||offset>std::numeric_limits<int32_t>::max()||!std::isfinite(scale)){luaL_error(L,"UDim sum is out of range");return 0;}
    push_udim(L,{scale,static_cast<int32_t>(offset)});return 1;
}
int udim_sub(lua_State* L) {
    UDimValue a,b;if(!read_udim(L,1,&a))luaL_typeerror(L,1,"UDim");if(!read_udim(L,2,&b))luaL_typeerror(L,2,"UDim");
    int64_t offset=static_cast<int64_t>(a.offset)-b.offset;
    double scale=a.scale-b.scale;
    if(offset<std::numeric_limits<int32_t>::min()||offset>std::numeric_limits<int32_t>::max()||!std::isfinite(scale)){luaL_error(L,"UDim difference is out of range");return 0;}
    push_udim(L,{scale,static_cast<int32_t>(offset)});return 1;
}
int udim_equal(lua_State* L) {
    UDimValue a,b;lua_pushboolean(L,read_udim(L,1,&a)&&read_udim(L,2,&b)&&a.scale==b.scale&&a.offset==b.offset);return 1;
}
int udim_tostring(lua_State* L) {
    auto* v=static_cast<UDimValue*>(luaL_checkudata(L,1,kUDim));
    std::ostringstream out;out<<std::setprecision(9)<<v->scale<<", "<<v->offset;
    auto text=out.str();lua_pushlstring(L,text.data(),text.size());return 1;
}
int udim2_new(lua_State* L) {
    int n=lua_gettop(L);
    if(n==0){push_udim2(L,{{0,0},{0,0}});return 1;}
    if(n==2) {
        UDimValue x,y;
        if(read_udim(L,1,&x)&&read_udim(L,2,&y)){push_udim2(L,{x,y});return 1;}
    }
    if(n>4){luaL_error(L,"UDim2.new accepts zero, two UDim values, or up to four numbers");return 0;}
    double c[4]={0,0,0,0};for(int i=0;i<n;i++)if(!lua_isnil(L,i+1)&&!valid_number(L,i+1,&c[i])){luaL_error(L,"UDim2 components must be finite bounded numbers");return 0;}
    if(!valid_offset(c[1])||!valid_offset(c[3])){luaL_error(L,"UDim2 offset exceeds the supported integer range");return 0;}
    push_udim2(L,{{c[0],static_cast<int32_t>(std::trunc(c[1]))},{c[2],static_cast<int32_t>(std::trunc(c[3]))}});return 1;
}
int udim2_from_scale(lua_State* L) {
    double x=0,y=0;if(lua_gettop(L)!=2||!valid_number(L,1,&x)||!valid_number(L,2,&y)){luaL_error(L,"UDim2.fromScale expects two finite numbers");return 0;}
    push_udim2(L,{{x,0},{y,0}});return 1;
}
int udim2_from_offset(lua_State* L) {
    double x=0,y=0;if(lua_gettop(L)!=2||!valid_number(L,1,&x)||!valid_number(L,2,&y)||!valid_offset(x)||!valid_offset(y)){luaL_error(L,"UDim2.fromOffset expects two bounded numbers");return 0;}
    push_udim2(L,{{0,static_cast<int32_t>(std::trunc(x))},{0,static_cast<int32_t>(std::trunc(y))}});return 1;
}
int udim2_index(lua_State* L) {
    auto* v=static_cast<UDim2Value*>(luaL_checkudata(L,1,kUDim2));const char* key=luaL_checkstring(L,2);
    if(std::string(key)=="X"||std::string(key)=="Width")push_udim(L,v->x);
    else if(std::string(key)=="Y"||std::string(key)=="Height")push_udim(L,v->y);
    else if(std::string(key)=="Lerp")lua_pushcfunction(L,udim2_lerp,"UDim2:Lerp");
    else lua_pushnil(L);return 1;
}
int udim2_add(lua_State* L) {
    UDim2Value a,b;if(!read_udim2(L,1,&a))luaL_typeerror(L,1,"UDim2");if(!read_udim2(L,2,&b))luaL_typeerror(L,2,"UDim2");
    int64_t xo=static_cast<int64_t>(a.x.offset)+b.x.offset,yo=static_cast<int64_t>(a.y.offset)+b.y.offset;
    double xs=a.x.scale+b.x.scale,ys=a.y.scale+b.y.scale;
    if(xo<std::numeric_limits<int32_t>::min()||xo>std::numeric_limits<int32_t>::max()||yo<std::numeric_limits<int32_t>::min()||yo>std::numeric_limits<int32_t>::max()||!std::isfinite(xs)||!std::isfinite(ys)){luaL_error(L,"UDim2 sum is out of range");return 0;}
    push_udim2(L,{{xs,static_cast<int32_t>(xo)},{ys,static_cast<int32_t>(yo)}});return 1;
}
int udim2_sub(lua_State* L) {
    UDim2Value a,b;if(!read_udim2(L,1,&a))luaL_typeerror(L,1,"UDim2");if(!read_udim2(L,2,&b))luaL_typeerror(L,2,"UDim2");
    int64_t xo=static_cast<int64_t>(a.x.offset)-b.x.offset,yo=static_cast<int64_t>(a.y.offset)-b.y.offset;
    double xs=a.x.scale-b.x.scale,ys=a.y.scale-b.y.scale;
    if(xo<std::numeric_limits<int32_t>::min()||xo>std::numeric_limits<int32_t>::max()||yo<std::numeric_limits<int32_t>::min()||yo>std::numeric_limits<int32_t>::max()||!std::isfinite(xs)||!std::isfinite(ys)){luaL_error(L,"UDim2 difference is out of range");return 0;}
    push_udim2(L,{{xs,static_cast<int32_t>(xo)},{ys,static_cast<int32_t>(yo)}});return 1;
}
int udim2_lerp(lua_State* L) {
    UDim2Value a,b;double alpha=0;if(!read_udim2(L,1,&a)||!read_udim2(L,2,&b)||!valid_number(L,3,&alpha)){luaL_error(L,"UDim2:Lerp expects a goal UDim2 and finite alpha");return 0;}
    double xo=a.x.offset+(b.x.offset-a.x.offset)*alpha,yo=a.y.offset+(b.y.offset-a.y.offset)*alpha;
    // Roblox lerps UDim2 scale in float32: the difference, product and sum each
    // round to float32, which breaks midpoint ties differently than double math.
    float xf=static_cast<float>(alpha);
    float xs=static_cast<float>(a.x.scale)+(static_cast<float>(b.x.scale)-static_cast<float>(a.x.scale))*xf;
    float ys=static_cast<float>(a.y.scale)+(static_cast<float>(b.y.scale)-static_cast<float>(a.y.scale))*xf;
    if(!std::isfinite(xs)||!std::isfinite(ys)||!valid_offset(xo)||!valid_offset(yo)){luaL_error(L,"UDim2:Lerp result is out of range");return 0;}
    push_udim2(L,{{xs,static_cast<int32_t>(std::round(xo))},{ys,static_cast<int32_t>(std::round(yo))}});return 1;
}
int udim2_equal(lua_State* L) {
    UDim2Value a,b;bool same=read_udim2(L,1,&a)&&read_udim2(L,2,&b)&&a.x.scale==b.x.scale&&a.x.offset==b.x.offset&&a.y.scale==b.y.scale&&a.y.offset==b.y.offset;
    lua_pushboolean(L,same);return 1;
}
int udim2_tostring(lua_State* L) {
    auto* v=static_cast<UDim2Value*>(luaL_checkudata(L,1,kUDim2));
    std::ostringstream out;out<<"{"<<std::setprecision(9)<<v->x.scale<<", "<<v->x.offset<<"}, {"<<v->y.scale<<", "<<v->y.offset<<"}";
    auto text=out.str();lua_pushlstring(L,text.data(),text.size());return 1;
}
int udim_negate(lua_State* L) {
    UDimValue a;if(!read_udim(L,1,&a))luaL_typeerror(L,1,"UDim");
    push_udim(L,{-a.scale,static_cast<int32_t>(-static_cast<int64_t>(a.offset))});return 1;
}
int udim2_negate(lua_State* L) {
    UDim2Value a;if(!read_udim2(L,1,&a))luaL_typeerror(L,1,"UDim2");
    push_udim2(L,{{-a.x.scale,static_cast<int32_t>(-static_cast<int64_t>(a.x.offset))},{-a.y.scale,static_cast<int32_t>(-static_cast<int64_t>(a.y.offset))}});return 1;
}
void set_metamethod(lua_State* L,const char* key,lua_CFunction function) {lua_pushcfunction(L,function,key);lua_setfield(L,-2,key);}
// Operator metamethods carry no function name, so argument errors read "invalid argument #2 (UDim expected, got number)" as in Roblox.
void set_operator(lua_State* L,const char* key,lua_CFunction function) {lua_pushcfunction(L,function,nullptr);lua_setfield(L,-2,key);}
void make_library(lua_State* L,const char* name,lua_CFunction constructor,lua_CFunction from_scale=nullptr,lua_CFunction from_offset=nullptr) {
    lua_createtable(L,0,3);lua_pushcfunction(L,constructor,"new");lua_setfield(L,-2,"new");
    if(from_scale){lua_pushcfunction(L,from_scale,"fromScale");lua_setfield(L,-2,"fromScale");}
    if(from_offset){lua_pushcfunction(L,from_offset,"fromOffset");lua_setfield(L,-2,"fromOffset");}
    lua_setreadonly(L,-1,true);lua_setglobal(L,name);
}
}

void install_udim_bindings(lua_State* L) {
    luaL_newmetatable(L,kUDim);
    set_metamethod(L,"__index",udim_index);set_operator(L,"__add",udim_add);set_operator(L,"__sub",udim_sub);set_operator(L,"__unm",udim_negate);
    set_metamethod(L,"__eq",udim_equal);set_metamethod(L,"__tostring",udim_tostring);
    lua_pushliteral(L,"UDim");lua_setfield(L,-2,"__type");lua_pushliteral(L,"The metatable is locked");lua_setfield(L,-2,"__metatable");lua_pop(L,1);
    luaL_newmetatable(L,kUDim2);
    set_metamethod(L,"__index",udim2_index);set_operator(L,"__add",udim2_add);set_operator(L,"__sub",udim2_sub);set_operator(L,"__unm",udim2_negate);
    set_metamethod(L,"__eq",udim2_equal);set_metamethod(L,"__tostring",udim2_tostring);set_metamethod(L,"Lerp",udim2_lerp);
    lua_pushliteral(L,"UDim2");lua_setfield(L,-2,"__type");lua_pushliteral(L,"The metatable is locked");lua_setfield(L,-2,"__metatable");lua_pop(L,1);
    make_library(L,"UDim",udim_new);make_library(L,"UDim2",udim2_new,udim2_from_scale,udim2_from_offset);
}

bool read_udim2_raw(lua_State* L, int index, double& xs, int32_t& xo, double& ys, int32_t& yo) {
    UDim2Value v{};
    if (!read_udim2(L, index, &v)) return false;
    xs = v.x.scale; xo = v.x.offset; ys = v.y.scale; yo = v.y.offset;
    return true;
}
void push_udim2_raw(lua_State* L, double xs, int32_t xo, double ys, int32_t yo) {
    push_udim2(L, {{xs, xo}, {ys, yo}});
}
