// Bounding-volume queries. Exact mesh/terrain contact is a different API.
constexpr const char* kOverlapParamsMeta="WorldSnapshot.OverlapParams";
struct OverlapParamsValue {
    World* world;
    WorldRayFilter filter;
    bool exclude_nil=true;
    size_t max_parts=0;
    double tolerance=0;
};
OverlapParamsValue* checked_overlap_params(lua_State* L,int index) {
    return static_cast<OverlapParamsValue*>(luaL_checkudata(L,index,kOverlapParamsMeta));
}
int overlap_params_new(lua_State* L) {
    if(lua_gettop(L)!=0)return luaL_error(L,"OverlapParams.new takes no arguments"),0;
    auto* w=static_cast<World*>(lua_touserdata(L,lua_upvalueindex(1)));
    auto* value=static_cast<OverlapParamsValue*>(lua_newuserdatadtor(L,sizeof(OverlapParamsValue),[](lua_State*,void* p){static_cast<OverlapParamsValue*>(p)->~OverlapParamsValue();}));
    new(value)OverlapParamsValue{w};luaL_getmetatable(L,kOverlapParamsMeta);lua_setmetatable(L,-2);return 1;
}
int overlap_params_add(lua_State* L) {
    auto* p=checked_overlap_params(L,1);
    try {
        auto list=raycast_filter_list(L,*p->world,2,true);
        if(p->filter.legacy.size()+list.size()>4096)throw std::runtime_error("spatial query filter limit exceeded");
        p->filter.legacy.insert(p->filter.legacy.end(),list.begin(),list.end());return 0;
    }catch(const std::exception& e){return luaL_error(L,"OverlapParams.AddToFilter: %s",e.what()),0;}
}
int overlap_params_index(lua_State* L) {
    auto* p=checked_overlap_params(L,1);const auto key=geometry_enum_key(L,2);
    if(spatial_params_index(L,p,key))return 1;
    if(key=="MaxParts")lua_pushnumber(L,double(p->max_parts));
    else if(key=="Tolerance")lua_pushnumber(L,p->tolerance);
    else if(key=="AddToFilter")lua_pushcfunction(L,overlap_params_add,"OverlapParams.AddToFilter");
    else return luaL_error(L,"unknown OverlapParams member: %s",key.c_str()),0;
    return 1;
}
int overlap_params_newindex(lua_State* L) {
    auto* p=checked_overlap_params(L,1);const auto key=geometry_enum_key(L,2);
    try {
        if(spatial_params_newindex(L,p,key))return 0;
        if(key=="MaxParts"||key=="Tolerance") {
            if(lua_type(L,3)!=LUA_TNUMBER)throw std::runtime_error("overlap limit requires a number");
            const double value=lua_tonumber(L,3);
            if(!std::isfinite(value))throw std::runtime_error("overlap limit must be finite");
            if(key=="Tolerance")p->tolerance=std::clamp(value,0.0,0.05);
            else {
                if(value<0||value>INT32_MAX||std::floor(value)!=value)throw std::runtime_error("MaxParts requires an integer from 0 to 2147483647");
                p->max_parts=size_t(value);
            }
        } else throw std::runtime_error("unknown OverlapParams member: "+key);
        return 0;
    }catch(const std::exception& e){return luaL_error(L,"OverlapParams: %s",e.what()),0;}
}
void overlap_finite_frame(const CFrameValue& frame) {
    query_rigid(frame);
    for(double x:frame.p)if(!std::isfinite(x)||std::abs(x)>std::numeric_limits<float>::max())
        throw std::runtime_error("overlap position must fit finite Vector3");
}
FrameVector overlap_vector(lua_State* L,int index) {
    if(!lua_isvector(L,index))throw std::runtime_error("overlap query requires Vector3");
    auto result=checked_frame_vector(L,index);
    for(double x:result)if(!std::isfinite(x))throw std::runtime_error("overlap query requires finite vectors");
    return result;
}
std::array<FrameVector,3> overlap_axes(const CFrameValue& frame) {
    return {{{frame.r[0],frame.r[3],frame.r[6]},
             {frame.r[1],frame.r[4],frame.r[7]},
             {frame.r[2],frame.r[5],frame.r[8]}}};
}
bool overlap_boxes(const CFrameValue& first,const FrameVector& first_half,const CFrameValue& second,const FrameVector& second_half) {
    const auto a=overlap_axes(first),b=overlap_axes(second);const auto delta=query_subtract(second.p,first.p);
    // Separating axis theorem: 6 face normals and 9 edge cross products.
    // Unnormalized cross axes avoid dividing by nearly parallel directions.
    auto separates=[&](const FrameVector& axis) {
        double radius=0;
        for(int i=0;i<3;++i)radius+=first_half[i]*std::abs(query_dot(axis,a[i]))+second_half[i]*std::abs(query_dot(axis,b[i]));
        return std::abs(query_dot(delta,axis))>radius;
    };
    for(int i=0;i<3;++i)if(separates(a[i])||separates(b[i]))return false;
    for(int i=0;i<3;++i)for(int j=0;j<3;++j)if(separates(query_cross(a[i],b[j])))return false;
    return true;
}
bool overlap_sphere_box(const FrameVector& center,double radius,const CFrameValue& box,const FrameVector& half) {
    const auto local=frame_rotate(query_inverse_rotation(box.r),query_subtract(center,box.p));
    FrameVector gap;for(int i=0;i<3;++i)gap[i]=std::max(0.0,std::abs(local[i])-half[i]);
    return std::hypot(gap[0],gap[1],gap[2])<=radius;
}
template<typename Intersects>
std::vector<Node*> query_world_bounds(World& w,Node& root,const WorldRayFilter& filter,
                                     size_t max_parts,Intersects intersects) {
    CollisionGroupTable groups;
    if(!filter.brute_force)groups=read_collision_groups(w,collision_query_root(w,root));
    size_t work=0;std::vector<Node*> result;
    for(const auto& id:w.order) {
        query_work(work);auto* node=find_node(w,id);
        // Terrain cells are not returned as one enormous Terrain bound.
        if(!node||node->class_name=="Terrain"||!spatial_query_candidate(w,*node,root,filter,groups,work))continue;
        auto pose=pivot_frame(w,*node,"CFrame");overlap_finite_frame(pose);
        auto half=query_size(w,*node);for(double& x:half)x/=2;
        if(!intersects(pose,half))continue;
        result.push_back(node);
        if(max_parts&&result.size()>=max_parts)break;
    }
    return result;
}
void push_bounds_results(lua_State* L,World& w,const std::vector<Node*>& result) {
    lua_createtable(L,int(result.size()),0);int index=1;
    for(auto* node:result){push_node(L,w,node);lua_rawseti(L,-2,index++);}
}
int world_root_overlap(lua_State* L) {
    auto* h=checked_handle(L,1);const std::string method=lua_tostring(L,lua_upvalueindex(1));
    try {
        if(h->node->destroyed||!collision_world_root(*h->node))throw std::runtime_error("overlap query requires a live WorldRoot");
        if(lua_gettop(L)<3||lua_gettop(L)>4)throw std::runtime_error("overlap query expects shape arguments and optional OverlapParams");
        const bool box=method=="GetPartBoundsInBox";CFrameValue shape;FrameVector half{};double radius=0;
        if(box) {
            shape=*checked_cframe(L,2);overlap_finite_frame(shape);half=overlap_vector(L,3);
            for(double& x:half){if(x<0)throw std::runtime_error("box size must be non-negative");x/=2;}
        } else {
            shape.p=overlap_vector(L,2);
            if(lua_type(L,3)!=LUA_TNUMBER)throw std::runtime_error("radius requires a number");
            radius=lua_tonumber(L,3);if(!std::isfinite(radius)||radius<0)throw std::runtime_error("radius must be finite and non-negative");
        }
        OverlapParamsValue defaults{h->world};const OverlapParamsValue* params=&defaults;
        if(!lua_isnoneornil(L,4)){params=checked_overlap_params(L,4);if(params->world!=h->world)throw std::runtime_error("OverlapParams belongs to another world");}
        if(box)for(double& x:half)x+=params->tolerance;else radius+=params->tolerance;
        auto& w=*h->world;
        const auto result=query_world_bounds(w,*h->node,params->filter,params->max_parts,
            [&](const CFrameValue& pose,const FrameVector& size){
                return box?overlap_boxes(shape,half,pose,size):overlap_sphere_box(shape.p,radius,pose,size);
            });
        push_bounds_results(L,w,result);return 1;
    }catch(const std::exception& e){return luaL_error(L,"%s: %s",method.c_str(),e.what()),0;}
}
void install_world_overlap(lua_State* L,World& w) {
    luaL_newmetatable(L,kOverlapParamsMeta);
    geometry_enum_method(L,"__index",overlap_params_index);geometry_enum_method(L,"__newindex",overlap_params_newindex);
    lua_pushliteral(L,"OverlapParams");lua_setfield(L,-2,"__type");
    lua_pushliteral(L,"The metatable is locked");lua_setfield(L,-2,"__metatable");lua_setreadonly(L,-1,true);lua_pop(L,1);
    lua_newtable(L);lua_pushlightuserdata(L,&w);lua_pushcclosure(L,overlap_params_new,"OverlapParams.new",1);lua_setfield(L,-2,"new");
    lua_setreadonly(L,-1,true);lua_setglobal(L,"OverlapParams");
}
