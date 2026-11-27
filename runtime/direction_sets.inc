// Immutable public Axes/Faces values. Masks are a local value codec, not a
// claim about Roblox's wire representation.
namespace direction_sets {
constexpr const char* axes_meta="LocalLuau.Axes";
constexpr const char* faces_meta="LocalLuau.Faces";
constexpr const char* faces[]={"Right","Top","Back","Left","Bottom","Front"};
constexpr const char* axes[]={"X","Y","Z"};
struct Value { unsigned mask; bool is_axes; };

Value* read(lua_State* L,int index) {
    if(!lua_isuserdata(L,index)||!lua_getmetatable(L,index))return nullptr;
    for(const char* meta:{axes_meta,faces_meta}) {
        luaL_getmetatable(L,meta);const bool equal=lua_rawequal(L,-1,-2);lua_pop(L,1);
        if(equal){lua_pop(L,1);return static_cast<Value*>(lua_touserdata(L,index));}
    }
    lua_pop(L,1);return nullptr;
}
void push(lua_State* L,unsigned mask,bool is_axes) {
    auto* value=static_cast<Value*>(lua_newuserdata(L,sizeof(Value)));*value={mask,is_axes};
    luaL_getmetatable(L,is_axes?axes_meta:faces_meta);lua_setmetatable(L,-2);
}
int construct(lua_State* L) {
    const bool is_axes=lua_toboolean(L,lua_upvalueindex(1));
    const int count=lua_gettop(L);unsigned mask=0;
    for(int i=1;i<=count;++i) {
        nlohmann::json item;
        if(world_bindings::capture_geometry_enum_item(L,i,item)) {
            const auto& enumeration=item.at("$enum");
            const int value=enumeration.at("value").get<int>();
            if(enumeration.at("type")=="NormalId") {mask|=1u<<(is_axes?value%3:value);continue;}
            if(is_axes&&enumeration.at("type")=="Axis"){mask|=1u<<value;continue;}
        }
        // Both direction-set constructors ignore arguments that are not the
        // expected enum items (measured on a real client for Axes.new).
    }
    push(L,mask,is_axes);return 1;
}
int index(lua_State* L) {
    auto* value=read(L,1);size_t length=0;const char* raw=luaL_checklstring(L,2,&length);
    const std::string key(raw,length);
    if(value) {
        if(value->is_axes)for(unsigned i=0;i<3;++i)if(key==axes[i]){lua_pushboolean(L,value->mask&(1u<<i));return 1;}
        for(unsigned i=0;i<6;++i)if(key==faces[i]){lua_pushboolean(L,value->mask&(1u<<(value->is_axes?i%3:i)));return 1;}
    }
    luaL_error(L,"unknown direction-set member");return 0;
}
int readonly(lua_State* L){luaL_error(L,"Axes and Faces values are immutable");return 0;}
int equal(lua_State* L) {
    auto* a=read(L,1);auto* b=read(L,2);
    lua_pushboolean(L,a&&b&&a->is_axes==b->is_axes&&a->mask==b->mask);return 1;
}
int text(lua_State* L) {
    auto* value=read(L,1);if(!value){luaL_error(L,"Axes or Faces expected");return 0;}
    std::string result;
    for(unsigned i=0;i<(value->is_axes?3u:6u);++i)if(value->mask&(1u<<i)) {
        if(!result.empty())result+=", ";result+=value->is_axes?axes[i]:faces[i];
    }
    lua_pushlstring(L,result.data(),result.size());return 1;
}
void method(lua_State* L,const char* name,lua_CFunction fn){lua_pushcfunction(L,fn,name);lua_setfield(L,-2,name);}
void install(lua_State* L) {
    for(bool is_axes:{true,false}) {
        const char* name=is_axes?"Axes":"Faces";
        luaL_newmetatable(L,is_axes?axes_meta:faces_meta);
        method(L,"__index",index);method(L,"__newindex",readonly);method(L,"__eq",equal);method(L,"__tostring",text);
        lua_pushstring(L,name);lua_setfield(L,-2,"__type");lua_pushliteral(L,"The metatable is locked");lua_setfield(L,-2,"__metatable");
        lua_setreadonly(L,-1,true);lua_pop(L,1);
        lua_newtable(L);lua_pushboolean(L,is_axes);lua_pushcclosure(L,construct,"new",1);lua_setfield(L,-2,"new");
        lua_setreadonly(L,-1,true);lua_setglobal(L,name);
    }
}
}
