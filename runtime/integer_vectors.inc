// Immutable signed-16-bit scripting values, measured in Studio 0.745.
namespace integer_values {
constexpr const char* meta2="LocalLuau.Vector2int16";
constexpr const char* meta3="LocalLuau.Vector3int16";
constexpr const char* metaRegion="LocalLuau.Region3int16";
struct Vector {int dimension;int values[3];};
struct Region {Vector minimum,maximum;};

int narrow(double number) {
    // Explicit conversion avoids undefined floating-to-integer overflow. These
    // non-finite/saturation results match the arm64 Studio constructor probes.
    if(std::isnan(number)||number<=-9223372036854775808.0)return 0;
    if(number>=18446744073709551616.0)return -1;
    double wrapped=std::fmod(std::trunc(number),65536.0);
    if(wrapped<0)wrapped+=65536;
    const int result=static_cast<int>(wrapped);
    return result>=32768?result-65536:result;
}
Vector* read(lua_State* L,int index) {
    if(!lua_isuserdata(L,index)||!lua_getmetatable(L,index))return nullptr;
    for(const char* meta:{meta2,meta3}){
        luaL_getmetatable(L,meta);bool same=lua_rawequal(L,-1,-2);lua_pop(L,1);
        if(same){lua_pop(L,1);return static_cast<Vector*>(lua_touserdata(L,index));}
    }
    lua_pop(L,1);return nullptr;
}
void push(lua_State* L,const Vector& value) {
    auto* data=static_cast<Vector*>(lua_newuserdata(L,sizeof(Vector)));*data=value;
    luaL_getmetatable(L,value.dimension==2?meta2:meta3);lua_setmetatable(L,-2);
}
int construct(lua_State* L) {
    const int dimension=lua_tointeger(L,lua_upvalueindex(1));
    Vector result{dimension,{0,0,0}};
    for(int i=0;i<dimension;++i)result.values[i]=narrow(lua_tonumber(L,i+1));
    push(L,result);return 1;
}
int index(lua_State* L) {
    auto* value=read(L,1);const char* key=luaL_checkstring(L,2);
    if(value&&key[0]&&key[1]=='\0'){
        const int component=(key[0]=='X'||key[0]=='x')?0:(key[0]=='Y'||key[0]=='y')?1:(key[0]=='Z'||key[0]=='z')?2:-1;
        if(component>=0&&component<value->dimension){lua_pushinteger(L,value->values[component]);return 1;}
    }
    luaL_error(L,"'%s' is not a valid member of Vector%dint16",key,value?value->dimension:0);return 0;
}
int readonly(lua_State* L){luaL_error(L,"integer vector and region values are immutable");return 0;}
int equal(lua_State* L) {
    auto* a=read(L,1);auto* b=read(L,2);bool same=a&&b&&a->dimension==b->dimension;
    if(same)for(int i=0;i<a->dimension;++i)same=same&&a->values[i]==b->values[i];
    lua_pushboolean(L,same);return 1;
}
int text(lua_State* L) {
    auto* value=read(L,1);if(!value){luaL_error(L,"integer vector expected");return 0;}
    std::string result;
    for(int i=0;i<value->dimension;++i){if(i)result+=", ";result+=std::to_string(value->values[i]);}
    lua_pushlstring(L,result.data(),result.size());return 1;
}
int negate(lua_State* L) {
    auto* value=read(L,1);if(!value){luaL_error(L,"integer vector expected");return 0;}
    Vector out=*value;for(int i=0;i<out.dimension;++i)out.values[i]=narrow(-out.values[i]);push(L,out);return 1;
}
int arithmetic(lua_State* L) {
    const int op=lua_tointeger(L,lua_upvalueindex(1));
    auto* a=read(L,1);auto* b=read(L,2);
    const Vector* vector=a?a:b;
    const char* typeName=vector&&vector->dimension==2?"Vector2int16":"Vector3int16";
    // Roblox reports a wrong operand as "invalid argument #2 (Vector3int16 expected, got number)"; only * and / take a number.
    if(!vector){luaL_typeerror(L,1,typeName);return 0;}
    if(a&&b&&a->dimension!=b->dimension){luaL_typeerror(L,2,typeName);return 0;}
    if((op==0||op==1)&&!(a&&b)){luaL_typeerror(L,a?2:1,typeName);return 0;}
    Vector out=*vector;
    double scalar=0;
    if(!(a&&b)){
        scalar=static_cast<float>(luaL_checknumber(L,a?2:1));
        if(op==2&&vector->dimension==3)scalar=narrow(scalar);
    }
    for(int i=0;i<vector->dimension;++i){
        const double left=a?a->values[i]:scalar,right=b?b->values[i]:scalar;
        if(op==3&&right==0&&vector->dimension==2){luaL_error(L,"Vector2int16 division by zero");return 0;}
        out.values[i]=narrow(op==0?left+right:op==1?left-right:op==2?left*right:left/right);
    }
    push(L,out);return 1;
}
int region_new(lua_State* L) {
    Region result{{3,{0,0,0}},{3,{0,0,0}}};
    for(int i=1;i<=2;++i)if(!lua_isnoneornil(L,i)){
        auto* vector=read(L,i);
        if(!vector||vector->dimension!=3){luaL_argerror(L,i,"Vector3int16 expected");return 0;}
        (i==1?result.minimum:result.maximum)=*vector;
    }
    auto* value=static_cast<Region*>(lua_newuserdata(L,sizeof(Region)));*value=result;
    luaL_getmetatable(L,metaRegion);lua_setmetatable(L,-2);return 1;
}
int region_index(lua_State* L) {
    auto* value=static_cast<Region*>(luaL_checkudata(L,1,metaRegion));std::string key=luaL_checkstring(L,2);
    if(key=="Min")push(L,value->minimum);
    else if(key=="Max")push(L,value->maximum);
    else {luaL_error(L,"'%s' is not a valid member of Region3int16",key.c_str());return 0;}
    return 1;
}
int region_equal(lua_State* L) {
    auto* a=static_cast<Region*>(luaL_checkudata(L,1,metaRegion));auto* b=static_cast<Region*>(luaL_checkudata(L,2,metaRegion));
    bool same=true;for(int i=0;i<3;++i)same=same&&a->minimum.values[i]==b->minimum.values[i]&&a->maximum.values[i]==b->maximum.values[i];
    lua_pushboolean(L,same);return 1;
}
int region_text(lua_State* L) {
    auto* value=static_cast<Region*>(luaL_checkudata(L,1,metaRegion));std::string result;
    for(const auto* v:{&value->minimum,&value->maximum}){
        if(!result.empty())result+="; ";
        for(int i=0;i<3;++i){if(i)result+=", ";result+=std::to_string(v->values[i]);}
    }
    lua_pushlstring(L,result.data(),result.size());return 1;
}
void install(lua_State* L) {
    for(int dimension:{2,3}){
        const char* name=dimension==2?"Vector2int16":"Vector3int16";
        luaL_newmetatable(L,dimension==2?meta2:meta3);
        for(const auto& pair:std::initializer_list<std::pair<const char*,lua_CFunction>>{
            {"__index",index},{"__newindex",readonly},{"__eq",equal},{"__tostring",text},{"__unm",negate}}){
            lua_pushcfunction(L,pair.second,pair.first);lua_setfield(L,-2,pair.first);
        }
        int op=0;for(const char* field:{"__add","__sub","__mul","__div"}){
            lua_pushinteger(L,op++);lua_pushcclosure(L,arithmetic,nullptr,1);lua_setfield(L,-2,field);
        }
        lua_pushstring(L,name);lua_setfield(L,-2,"__type");lua_pushliteral(L,"The metatable is locked");lua_setfield(L,-2,"__metatable");lua_pop(L,1);
        lua_newtable(L);lua_pushinteger(L,dimension);lua_pushcclosure(L,construct,"new",1);lua_setfield(L,-2,"new");
        lua_setreadonly(L,-1,true);lua_setglobal(L,name);
    }
    luaL_newmetatable(L,metaRegion);
    for(const auto& pair:std::initializer_list<std::pair<const char*,lua_CFunction>>{
        {"__index",region_index},{"__newindex",readonly},{"__eq",region_equal},{"__tostring",region_text}}){
        lua_pushcfunction(L,pair.second,pair.first);lua_setfield(L,-2,pair.first);
    }
    lua_pushliteral(L,"Region3int16");lua_setfield(L,-2,"__type");lua_pushliteral(L,"The metatable is locked");lua_setfield(L,-2,"__metatable");lua_pop(L,1);
    lua_newtable(L);lua_pushcfunction(L,region_new,"new");lua_setfield(L,-2,"new");lua_setreadonly(L,-1,true);lua_setglobal(L,"Region3int16");
}
} // namespace integer_values
