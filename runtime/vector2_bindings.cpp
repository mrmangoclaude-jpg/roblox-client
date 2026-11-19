#include "vector2_bindings.hpp"
#include "vector_math_compat.hpp"

#include <lua.h>
#include <lualib.h>

#include <cmath>
#include <cstdio>
#include <cstring>
#include <limits>
#include <new>

namespace {
constexpr const char* kMeta = "HeadlessRuntime.Vector2";
struct Value { double x, y; };

Value* check(lua_State* L, int index) {
    return static_cast<Value*>(luaL_checkudata(L, index, kMeta));
}
bool is_vector(lua_State* L, int index) {
    if (!lua_isuserdata(L, index) || !lua_getmetatable(L, index)) return false;
    luaL_getmetatable(L, kMeta);
    bool result = lua_rawequal(L, -1, -2) != 0;
    lua_pop(L, 2);
    return result;
}
double finite_number(lua_State* L, int index, const char* label) {
    double value = luaL_checknumber(L, index);
    if (!std::isfinite(value)) luaL_error(L, "%s must be finite", label);
    return value;
}
int push_raw(lua_State* L, double x, double y) {
    x = static_cast<double>(static_cast<float>(x));
    y = static_cast<double>(static_cast<float>(y));
    auto* value = static_cast<Value*>(lua_newuserdatatagged(L, sizeof(Value), 0));
    new (value) Value{x, y};
    luaL_getmetatable(L, kMeta);
    lua_setmetatable(L, -2);
    return 1;
}
int push_value(lua_State* L, double x, double y) {
    if (!std::isfinite(x) || !std::isfinite(y)) {
        luaL_error(L, "Vector2 result must be finite");
        return 0;
    }
    return push_raw(L,x,y);
}
int construct(lua_State* L) {
    // The engine reads only the first two arguments and ignores any extras.
    // Infinity represents an unbounded UISizeConstraint maximum. Authored serialization preserves
    // infinity using explicit $number tags; property consumers validate allowed values.
    // The engine converts each component leniently: numbers and numeric strings convert, anything
    // else (nil, booleans, tables, other strings) reads as 0, and NaN passes through.
    auto component=[&](int index)->double {
        const int type=lua_type(L,index);
        return type==LUA_TNUMBER||(type==LUA_TSTRING&&lua_isnumber(L,index))?lua_tonumber(L,index):0.0;
    };
    const double x=component(1),y=component(2);
    return push_raw(L,x,y);
}
int index(lua_State* L) {
    Value* value = check(L, 1);
    const char* key = luaL_checkstring(L, 2);
    if (std::strcmp(key, "X") == 0) lua_pushnumber(L, value->x);
    else if (std::strcmp(key, "Y") == 0) lua_pushnumber(L, value->y);
    else if (std::strcmp(key, "Magnitude") == 0) lua_pushnumber(L, static_cast<double>(std::sqrt(static_cast<float>(value->x)*static_cast<float>(value->x) + static_cast<float>(value->y)*static_cast<float>(value->y))));
    else if (std::strcmp(key, "Unit") == 0) {
        float fx = static_cast<float>(value->x), fy = static_cast<float>(value->y);
        float magnitude = std::sqrt(fx*fx + fy*fy);
        if (magnitude == 0.0f) {
            const double nan=std::numeric_limits<double>::quiet_NaN();
            return push_raw(L,nan,nan);
        }
        return push_value(L, fx / magnitude, fy / magnitude);
    } else {
        luaL_getmetatable(L, kMeta);
        lua_pushvalue(L, 2);
        lua_rawget(L, -2);
        lua_remove(L, -2);
    }
    return 1;
}
int readonly(lua_State* L) {
    luaL_error(L, "Vector2 values are immutable");
    return 0;
}
int tostring_vector(lua_State* L) {
    Value* v = check(L, 1);
    char xb[32], yb[32];
    auto fmt = [](double d, char* out, size_t n) {
        if (std::isnan(d)) std::snprintf(out, n, "NAN");
        else if (std::isinf(d)) std::snprintf(out, n, d < 0 ? "-INF" : "INF");
        else std::snprintf(out, n, "%.9g", d);
    };
    fmt(v->x, xb, sizeof(xb));
    fmt(v->y, yb, sizeof(yb));
    char text[128];
    int size = std::snprintf(text, sizeof(text), "%s, %s", xb, yb);
    lua_pushlstring(L, text, static_cast<size_t>(size));
    return 1;
}
int equal(lua_State* L) {
    if (!is_vector(L, 1) || !is_vector(L, 2)) { lua_pushboolean(L, 0); return 1; }
    Value* a = check(L, 1); Value* b = check(L, 2);
    lua_pushboolean(L, a->x == b->x && a->y == b->y);
    return 1;
}
int add(lua_State* L) { Value* a=check(L,1); Value* b=check(L,2); return push_value(L,static_cast<float>(a->x)+static_cast<float>(b->x),static_cast<float>(a->y)+static_cast<float>(b->y)); }
int subtract(lua_State* L) { Value* a=check(L,1); Value* b=check(L,2); return push_value(L,static_cast<float>(a->x)-static_cast<float>(b->x),static_cast<float>(a->y)-static_cast<float>(b->y)); }
int multiply(lua_State* L) {
    if (is_vector(L,1) && is_vector(L,2)) { Value* a=check(L,1); Value* b=check(L,2); return push_value(L,static_cast<float>(a->x)*static_cast<float>(b->x),static_cast<float>(a->y)*static_cast<float>(b->y)); }
    if (is_vector(L,1)) { Value* a=check(L,1); float n=static_cast<float>(finite_number(L,2,"multiplier")); return push_value(L,static_cast<float>(a->x)*n,static_cast<float>(a->y)*n); }
    Value* b=check(L,2); float n=static_cast<float>(finite_number(L,1,"multiplier")); return push_value(L,n*static_cast<float>(b->x),n*static_cast<float>(b->y));
}
int divide(lua_State* L) {
    Value* a=check(L,1);
    if (is_vector(L,2)) { Value* b=check(L,2); float bx=static_cast<float>(b->x),by=static_cast<float>(b->y); if(bx==0||by==0){luaL_error(L,"Vector2 divisor components must be nonzero");return 0;}return push_value(L,static_cast<float>(a->x)/bx,static_cast<float>(a->y)/by); }
    float n=static_cast<float>(finite_number(L,2,"divisor")); if(n==0){luaL_error(L,"Vector2 divisor must be nonzero");return 0;}return push_value(L,static_cast<float>(a->x)/n,static_cast<float>(a->y)/n);
}
int negate(lua_State* L) { Value* a=check(L,1); return push_value(L,-static_cast<float>(a->x),-static_cast<float>(a->y)); }
int dot(lua_State* L) { Value* a=check(L,1); Value* b=check(L,2); lua_pushnumber(L,static_cast<double>(static_cast<float>(a->x)*static_cast<float>(b->x)+static_cast<float>(a->y)*static_cast<float>(b->y))); return 1; }
int cross(lua_State* L) { Value* a=check(L,1); Value* b=check(L,2); lua_pushnumber(L,static_cast<double>(static_cast<float>(a->x)*static_cast<float>(b->y)-static_cast<float>(a->y)*static_cast<float>(b->x))); return 1; }
int lerp(lua_State* L) { Value* a=check(L,1); Value* b=check(L,2); double t=finite_number(L,3,"alpha"); float ax=static_cast<float>(a->x),ay=static_cast<float>(a->y),bx=static_cast<float>(b->x),by=static_cast<float>(b->y),tf=static_cast<float>(t); return push_value(L,ax+(bx-ax)*tf,ay+(by-ay)*tf); }
int fuzzy_eq(lua_State* L) {
    Value* a=check(L,1);Value* b=check(L,2);
    double epsilon=luaL_optnumber(L,3,1e-5);
    if(!std::isfinite(epsilon)||std::fabs(epsilon)>.1)
        luaL_error(L,"The eps value provided to FuzzyEq should be a small positive value <= 0.1");
    lua_pushboolean(L,runtime_fuzzy_component(a->x,b->x,epsilon)&&runtime_fuzzy_component(a->y,b->y,epsilon));
    return 1;
}
int angle(lua_State* L) {
    Value* a=check(L,1);Value* b=check(L,2);
    bool signed_angle=false;
    if(!lua_isnoneornil(L,3)){luaL_checktype(L,3,LUA_TBOOLEAN);signed_angle=lua_toboolean(L,3);}
    const double radians=static_cast<double>(std::atan2f(static_cast<float>(a->x)*static_cast<float>(b->y)-static_cast<float>(a->y)*static_cast<float>(b->x),static_cast<float>(a->x)*static_cast<float>(b->x)+static_cast<float>(a->y)*static_cast<float>(b->y)));
    lua_pushnumber(L,static_cast<float>(signed_angle?radians:std::fabs(radians)));
    return 1;
}
int component(lua_State* L, double (*operation)(double)) { Value* a=check(L,1);return push_value(L,operation(a->x),operation(a->y)); }
int absolute(lua_State* L) { return component(L, std::fabs); }
int floor_values(lua_State* L) { return component(L, std::floor); }
int ceil_values(lua_State* L) { return component(L, std::ceil); }
double sign_value(double value) { return value>0?1.0:value<0?-1.0:0.0; }
int sign_values(lua_State* L) { return component(L,sign_value); }
int extrema(lua_State* L,bool maximum) {
    Value* a=check(L,1);double x=a->x,y=a->y;
    for(int i=2;i<=lua_gettop(L);++i){Value* b=check(L,i);x=maximum?std::fmax(x,b->x):std::fmin(x,b->x);y=maximum?std::fmax(y,b->y):std::fmin(y,b->y);}
    return push_raw(L,x,y);
}
int min_values(lua_State* L) { return extrema(L,false); }
int max_values(lua_State* L) { return extrema(L,true); }

void method(lua_State* L, const char* name, lua_CFunction callback) {
    lua_pushcfunction(L, callback, name); lua_setfield(L, -2, name);
}
void constant(lua_State* L, const char* name, double x, double y) {
    push_value(L,x,y); lua_setfield(L,-2,name);
}
} // namespace

void install_vector2_bindings(lua_State* L) {
    luaL_newmetatable(L, kMeta);
    method(L,"__index",index); method(L,"__newindex",readonly);
    method(L,"__tostring",tostring_vector); method(L,"__eq",equal);
    method(L,"__add",add); method(L,"__sub",subtract); method(L,"__mul",multiply);
    method(L,"__div",divide); method(L,"__unm",negate);
    method(L,"Dot",dot); method(L,"Cross",cross); method(L,"Lerp",lerp);
    method(L,"FuzzyEq",fuzzy_eq);method(L,"Angle",angle);
    method(L,"Abs",absolute); method(L,"Floor",floor_values); method(L,"Ceil",ceil_values);
    method(L,"Sign",sign_values); method(L,"Min",min_values); method(L,"Max",max_values);
    lua_pushliteral(L,"Vector2"); lua_setfield(L,-2,"__type");
    lua_pushliteral(L,"The metatable is locked"); lua_setfield(L,-2,"__metatable");
    lua_pop(L,1);

    lua_createtable(L,0,12);
    method(L,"new",construct);
    constant(L,"zero",0,0); constant(L,"one",1,1);
    constant(L,"xAxis",1,0); constant(L,"yAxis",0,1);
    method(L,"min",min_values); method(L,"max",max_values);
    lua_setreadonly(L,-1,true); lua_setglobal(L,"Vector2");
}

bool read_vector2(lua_State* L, int index, double& x, double& y) {
    if (!is_vector(L,index)) return false;
    Value* value=check(L,index); x=value->x; y=value->y; return true;
}
int push_vector2(lua_State* L, double x, double y) { return push_value(L,x,y); }

int push_engine_vector2(lua_State* L, double x, double y) { return push_raw(L,x,y); }
