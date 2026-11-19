// Script-facing spatial queries over the current native world.
constexpr const char* kRaycastParamsMeta="WorldSnapshot.RaycastParams";
constexpr const char* kRaycastResultMeta="WorldSnapshot.RaycastResult";
struct RaycastParamsValue {
    World* world;
    WorldRayFilter filter;
    bool exclude_nil=true;
    double margin=0,size_gradient=0;
};
struct RaycastResultValue {
    World* world;Node* instance;
    FrameVector position,normal;
    double distance;int material;
};
RaycastParamsValue* checked_raycast_params(lua_State* L,int index) {
    return static_cast<RaycastParamsValue*>(luaL_checkudata(L,index,kRaycastParamsMeta));
}
std::vector<std::string> raycast_filter_list(lua_State* L,World& w,int index,bool single=false) {
    std::vector<std::string> result;
    auto add=[&](int at) {
        if(!has_meta(L,at,kInstanceMeta))throw std::runtime_error("raycast filter requires Instances");
        auto* h=static_cast<Handle*>(lua_touserdata(L,at));
        if(h->world!=&w)throw std::runtime_error("raycast filter belongs to another world");
        result.push_back(h->node->id);
    };
    if(single&&has_meta(L,index,kInstanceMeta)){add(index);return result;}
    if(!lua_istable(L,index))throw std::runtime_error("raycast filter requires an array of Instances");
    index=lua_absindex(L,index);const int length=lua_objlen(L,index);
    if(length>4096)throw std::runtime_error("raycast filter limit exceeded");
    size_t count=0;lua_pushnil(L);
    while(lua_next(L,index)) {
        if(++count>4096||lua_type(L,-2)!=LUA_TNUMBER||lua_tonumber(L,-2)<1||lua_tonumber(L,-2)>length||std::floor(lua_tonumber(L,-2))!=lua_tonumber(L,-2))
            throw std::runtime_error("raycast filter requires a dense array");
        lua_pop(L,1);
    }
    for(int i=1;i<=length;++i){lua_rawgeti(L,index,i);add(-1);lua_pop(L,1);}
    return result;
}
void push_raycast_filter(lua_State* L,World& w,const std::vector<std::string>& list) {
    lua_createtable(L,int(list.size()),0);int i=1;
    for(const auto& id:list){auto* n=find_node(w,id);if(n)push_node(L,w,n);else lua_pushnil(L);lua_rawseti(L,-2,i++);}
}
int raycast_params_new(lua_State* L) {
    if(lua_gettop(L)!=0)return luaL_error(L,"RaycastParams.new takes no arguments"),0;
    auto* w=static_cast<World*>(lua_touserdata(L,lua_upvalueindex(1)));
    auto* value=static_cast<RaycastParamsValue*>(lua_newuserdatadtor(L,sizeof(RaycastParamsValue),[](lua_State*,void* p){static_cast<RaycastParamsValue*>(p)->~RaycastParamsValue();}));
    new(value)RaycastParamsValue{w};luaL_getmetatable(L,kRaycastParamsMeta);lua_setmetatable(L,-2);return 1;
}
int raycast_params_add(lua_State* L) {
    auto* p=checked_raycast_params(L,1);
    try {
        auto list=raycast_filter_list(L,*p->world,2,true);
        if(p->filter.legacy.size()+list.size()>4096)throw std::runtime_error("raycast filter limit exceeded");
        p->filter.legacy.insert(p->filter.legacy.end(),list.begin(),list.end());return 0;
    }catch(const std::exception& e){return luaL_error(L,"AddToFilter: %s",e.what()),0;}
}
template<typename Params>
bool spatial_params_index(lua_State* L,Params* p,const std::string& key) {
    auto& f=p->filter;
    if(key=="FilterDescendantsInstances")push_raycast_filter(L,*p->world,f.legacy);
    else if(key=="IncludeInstances"){if(f.include_active)push_raycast_filter(L,*p->world,f.include);else lua_pushnil(L);}
    else if(key=="ExcludeInstances"){if(p->exclude_nil)lua_pushnil(L);else push_raycast_filter(L,*p->world,f.exclude);}
    else if(key=="FilterType")push_geometry_item(L,kRaycastFilterType,f.legacy_include?1:0);
    else if(key=="RespectCanCollide")lua_pushboolean(L,f.respect_collide);
    else if(key=="BruteForceAllSlow")lua_pushboolean(L,f.brute_force);
    else if(key=="CollisionGroup")lua_pushlstring(L,f.collision_group.data(),f.collision_group.size());
    else return false;
    return true;
}
template<typename Params>
bool spatial_params_newindex(lua_State* L,Params* p,const std::string& key) {
    auto& f=p->filter;
    if(key=="FilterDescendantsInstances"||key=="IncludeInstances"||key=="ExcludeInstances") {
        const bool nil=lua_isnil(L,3);
        auto list=nil&&key!="FilterDescendantsInstances"?std::vector<std::string>{}:raycast_filter_list(L,*p->world,3);
        if(key=="FilterDescendantsInstances")f.legacy=std::move(list);
        else if(key=="IncludeInstances"){f.include=std::move(list);f.include_active=!nil;}
        else {f.exclude=std::move(list);p->exclude_nil=nil;}
    } else if(key=="FilterType")f.legacy_include=checked_geometry_value(L,3,kRaycastFilterType)==1;
    else if(key=="RespectCanCollide"||key=="BruteForceAllSlow") {
        if(lua_type(L,3)!=LUA_TBOOLEAN)throw std::runtime_error("spatial query flag requires a boolean");
        if(key=="RespectCanCollide")f.respect_collide=lua_toboolean(L,3);else f.brute_force=lua_toboolean(L,3);
    } else if(key=="CollisionGroup") {
        if(lua_type(L,3)!=LUA_TSTRING)throw std::runtime_error("CollisionGroup requires a string");
        size_t length;const char* value=lua_tolstring(L,3,&length);
        if(!length||length>100||std::memchr(value,0,length))throw std::runtime_error("invalid CollisionGroup name");
        f.collision_group.assign(value,length);
    } else return false;
    return true;
}
int raycast_params_index(lua_State* L) {
    auto* p=checked_raycast_params(L,1);const auto key=geometry_enum_key(L,2);
    if(spatial_params_index(L,p,key))return 1;
    if(key=="IgnoreWater")lua_pushboolean(L,p->filter.ignore_water);
    else if(key=="Margin")lua_pushnumber(L,p->margin);
    else if(key=="SizeGradient")lua_pushnumber(L,p->size_gradient);
    else if(key=="AddToFilter")lua_pushcfunction(L,raycast_params_add,"RaycastParams.AddToFilter");
    else return luaL_error(L,"unknown RaycastParams member: %s",key.c_str()),0;
    return 1;
}
int raycast_params_newindex(lua_State* L) {
    auto* p=checked_raycast_params(L,1);const auto key=geometry_enum_key(L,2);
    try {
        if(spatial_params_newindex(L,p,key))return 0;
        if(key=="IgnoreWater") {
            if(lua_type(L,3)!=LUA_TBOOLEAN)throw std::runtime_error("raycast flag requires a boolean");
            p->filter.ignore_water=lua_toboolean(L,3);
        } else if(key=="Margin"||key=="SizeGradient") {
            if(lua_type(L,3)!=LUA_TNUMBER)throw std::runtime_error("raycast size parameter requires a number");
            const double value=lua_tonumber(L,3),minimum=key=="Margin"?0:-1;
            if(!std::isfinite(value)||value<minimum)throw std::runtime_error("raycast size parameter is outside its finite range");
            if(key=="Margin")p->margin=value;else p->size_gradient=value;
        } else throw std::runtime_error("unknown RaycastParams member: "+key);
        return 0;
    }catch(const std::exception& e){return luaL_error(L,"RaycastParams: %s",e.what()),0;}
}
int raycast_result_index(lua_State* L) {
    auto* p=static_cast<RaycastResultValue*>(luaL_checkudata(L,1,kRaycastResultMeta));
    const auto key=geometry_enum_key(L,2);
    if(key=="Instance")push_node(L,*p->world,p->instance);
    else if(key=="Position")lua_pushvector(L,p->position[0],p->position[1],p->position[2]);
    else if(key=="Normal")lua_pushvector(L,p->normal[0],p->normal[1],p->normal[2]);
    else if(key=="Distance")lua_pushnumber(L,p->distance);
    else if(key=="Material")push_ussi_export_enum_json(L,Json{{"$enum",{{"type","Material"},{"value",p->material}}}});
    else return luaL_error(L,"unknown RaycastResult member: %s",key.c_str()),0;
    return 1;
}
int raycast_result_readonly(lua_State* L){return luaL_error(L,"RaycastResult is read-only"),0;}
bool capture_raycast_result(lua_State* L,World& w,int index,Json& out) {
    if(!has_meta(L,index,kRaycastResultMeta))return false;
    const auto* result=static_cast<RaycastResultValue*>(lua_touserdata(L,index));
    if(result->world!=&w)throw std::runtime_error("RaycastResult belongs to another world");
    out=Json{{"$raycast_result",{
        {"Instance",{{"$ref",result->instance->id}}},
        {"Position",{{"$vector3",result->position}}},
        {"Normal",{{"$vector3",result->normal}}},
        {"Distance",result->distance},
        {"Material",{{"$enum",{{"type","Material"},{"value",result->material}}}}}
    }}};
    return true;
}
FrameVector raycast_input_vector(lua_State* L,int index) {
    if(!lua_isvector(L,index))throw std::runtime_error("Raycast requires Vector3 origin and direction");
    const float* value=lua_tovector(L,index);FrameVector out;
    for(int i=0;i<3;++i){out[i]=value[i];if(!std::isfinite(out[i]))throw std::runtime_error("Raycast requires finite vectors");}
    return out;
}
int world_ray_hit_material(World& w,const WorldRayHit& hit) {
    int material=hit.material;
    if(material<0&&hit.node->class_name!="Terrain") {
        const auto* value=property_value(w,*hit.node,"Material");
        if(value)material=query_material(*value);
    }
    if(material<0)throw std::runtime_error("ray hit material is unavailable");
    return material;
}
FrameVector world_ray_position(const FrameVector& origin,const FrameVector& direction,double distance) {
    FrameVector position;
    for(int i=0;i<3;++i) {
        position[i]=origin[i]+direction[i]*distance;
        if(!std::isfinite(position[i])||std::abs(position[i])>std::numeric_limits<float>::max())
            throw std::runtime_error("ray position exceeds finite Vector3 range");
    }
    return position;
}
int world_root_raycast(lua_State* L) {
    auto* h=checked_handle(L,1);
    try {
        if(h->node->destroyed||(h->node->class_name!="Workspace"&&h->node->class_name!="WorldModel"))throw std::runtime_error("Raycast requires a live WorldRoot");
        if(lua_gettop(L)<3||lua_gettop(L)>4)throw std::runtime_error("Raycast expects origin, direction and optional RaycastParams");
        auto origin=raycast_input_vector(L,2),direction=raycast_input_vector(L,3);
        WorldRayFilter defaults;const WorldRayFilter* filter=&defaults;
        if(!lua_isnoneornil(L,4)) {
            auto* params=checked_raycast_params(L,4);
            if(params->world!=h->world)throw std::runtime_error("RaycastParams belongs to another world");
            if(params->margin!=0)throw std::runtime_error("Raycast Margin is unavailable; use Spherecast for explicit sphere casting");
            filter=&params->filter;
        }
        const double length=std::hypot(direction[0],direction[1],direction[2]);
        if(length>15000)throw std::runtime_error("Raycast direction exceeds 15000 studs");
        if(length==0){lua_pushnil(L);return 1;}
        for(double& value:direction)value/=length;
        auto hit=query_world_ray(*h->world,*h->node,origin,direction,length,*filter);
        if(!hit.node){lua_pushnil(L);return 1;}
        const int material=world_ray_hit_material(*h->world,hit);
        const auto position=world_ray_position(origin,direction,hit.distance);
        auto* result=static_cast<RaycastResultValue*>(lua_newuserdatatagged(L,sizeof(RaycastResultValue),0));
        *result={h->world,hit.node,position,hit.normal,hit.distance,material};
        luaL_getmetatable(L,kRaycastResultMeta);lua_setmetatable(L,-2);return 1;
    }catch(const std::exception& e){return luaL_error(L,"Raycast: %s",e.what()),0;}
}
void install_world_raycast(lua_State* L,World& w) {
    luaL_newmetatable(L,kRaycastParamsMeta);
    geometry_enum_method(L,"__index",raycast_params_index);geometry_enum_method(L,"__newindex",raycast_params_newindex);
    lua_pushliteral(L,"RaycastParams");lua_setfield(L,-2,"__type");
    lua_pushliteral(L,"The metatable is locked");lua_setfield(L,-2,"__metatable");lua_setreadonly(L,-1,true);lua_pop(L,1);
    luaL_newmetatable(L,kRaycastResultMeta);
    geometry_enum_method(L,"__index",raycast_result_index);geometry_enum_method(L,"__newindex",raycast_result_readonly);
    lua_pushliteral(L,"RaycastResult");lua_setfield(L,-2,"__type");
    lua_pushliteral(L,"RaycastResult");lua_setfield(L,-2,"__metatable");lua_setreadonly(L,-1,true);lua_pop(L,1);
    lua_newtable(L);lua_pushlightuserdata(L,&w);lua_pushcclosure(L,raycast_params_new,"RaycastParams.new",1);lua_setfield(L,-2,"new");
    lua_setreadonly(L,-1,true);lua_setglobal(L,"RaycastParams");
}
