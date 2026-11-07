// Pure geometry and batched local transforms. Does not simulate joints or send
// replication. Include after CFrame helpers, property_events and budget declarations.
bool pivot_model(World& w,const Node& n){return class_is_a(w,n.class_name,"Model");}
bool pivot_part(World& w,const Node& n){return class_is_a(w,n.class_name,"BasePart");}
bool pivot_object(World& w,const Node& n){return pivot_model(w,n)||pivot_part(w,n)||n.class_name=="Camera";}
CFrameValue pivot_decode(const Json& value) {
    if(!value.is_object()||!value.contains("$cframe"))throw std::runtime_error("pivot requires a CFrame");
    const auto& v=value["$cframe"];CFrameValue cf;
    if(!v.is_object()||!v.contains("position")||!v["position"].is_array()||v["position"].size()!=3||
        !v.contains("rotation")||!v["rotation"].is_array()||v["rotation"].size()!=9)
        throw std::runtime_error("pivot CFrame rotation/position is unavailable");
    for(int i=0;i<3;++i){cf.p[i]=json_number(v["position"][i]);if(!std::isfinite(cf.p[i]))throw std::runtime_error("nonfinite pivot position");}
    for(int i=0;i<9;++i){cf.r[i]=json_number(v["rotation"][i]);if(!std::isfinite(cf.r[i]))throw std::runtime_error("nonfinite pivot rotation");}
    return cf;
}
Json pivot_encode(const CFrameValue& cf){return Json{{"$cframe",Json{{"position",cf.p},{"rotation",cf.r}}}};}
Json pivot_angles(lua_State* L,const CFrameValue& cf,bool yxz) {
    auto values=frame_euler_angles(cf.r,yxz);for(auto& value:values)value*=180/std::acos(-1.0);
    return Json{{"$vector3",values}};
}
CFrameValue pivot_frame(World& w,const Node& n,const char* key) {
    const auto* value=property_value(w,n,key);
    if(!value)throw std::runtime_error(std::string(key)+" is unavailable for "+n.class_name);
    return pivot_decode(*value);
}
CFrameValue pivot_product(const CFrameValue& a,const CFrameValue& b) {
    CFrameValue result;result.r=frame_product(a.r,b.r);result.p=frame_rotate(a.r,b.p);
    for(int i=0;i<3;++i)result.p[i]+=a.p[i];return result;
}
CFrameValue pivot_inverse(const CFrameValue& cf){CFrameValue result;frame_inverse_parts(cf,result.p,result.r);return result;}
std::vector<Node*> pivot_descendants(World& w,Node& n,bool include_self=false) {
    std::vector<Node*> result;
    if(include_self)result.push_back(&n);
    for(Node* child:descendant_nodes(w,n,false))if(!child->destroyed)result.push_back(child);
    return result;
}
std::pair<CFrameValue,FrameVector> pivot_bounds(World& w,Node& n,const CFrameValue& axes) {
    FrameVector low{},high{};bool any=false;auto inverse=pivot_inverse(axes);
    for(auto* child:pivot_descendants(w,n))if(pivot_part(w,*child)) {
        auto frame=pivot_product(inverse,pivot_frame(w,*child,"CFrame"));
        const auto* size=property_value(w,*child,"Size");
        if(!size||!size->is_object()||!size->contains("$vector3")||!(*size)["$vector3"].is_array()||(*size)["$vector3"].size()!=3)
            throw std::runtime_error("bounding-box part Size is unavailable");
        FrameVector half{};for(int i=0;i<3;++i){half[i]=json_number((*size)["$vector3"][i])/2;if(!std::isfinite(half[i])||half[i]<0)throw std::runtime_error("invalid bounding-box size");}
        for(int row=0;row<3;++row) {
            double extent=0;for(int col=0;col<3;++col)extent+=std::abs(frame.r[row*3+col])*half[col];
            double lo=frame.p[row]-extent,hi=frame.p[row]+extent;
            if(!any){low[row]=lo;high[row]=hi;}else{low[row]=std::min(low[row],lo);high[row]=std::max(high[row],hi);}
        }
        any=true;
    }
    if(!any)return {axes,FrameVector{0,0,0}};
    CFrameValue center;FrameVector size;
    for(int i=0;i<3;++i){center.p[i]=(low[i]+high[i])/2;size[i]=high[i]-low[i];}
    return {pivot_product(axes,center),size};
}
CFrameValue model_world_pivot(World& w,Node& n) {
    if(const auto* local=local_value(w,n,"WorldPivot"))return pivot_decode(*local);
    const auto* saved=property_value(w,n,"WorldPivot");
    if(saved&&origin(w,n,"WorldPivot")!="class_default")return pivot_decode(*saved);
    // An untouched model follows the world-aligned bounds until WorldPivot is set.
    return pivot_bounds(w,n,CFrameValue{}).first;
}
Node* model_primary(World& w,Node& n) {
    const auto* value=property_value(w,n,"PrimaryPart");
    if(!value)throw std::runtime_error("model PrimaryPart state is unavailable");
    if(value->is_null())return nullptr;
    if(!value->is_object()||!value->contains("$ref")||!(*value)["$ref"].is_string())throw std::runtime_error("invalid PrimaryPart reference");
    auto* part=find_node(w,(*value)["$ref"].get<std::string>());
    if(!part)throw std::runtime_error("PrimaryPart reference is unresolved");
    if(part->destroyed)return nullptr;
    if(!pivot_part(w,*part))throw std::runtime_error("PrimaryPart must be a BasePart");
    return part;
}
CFrameValue object_pivot(World& w,Node& n) {
    if(pivot_model(w,n)) {
        if(auto* primary=model_primary(w,n))return pivot_product(pivot_frame(w,*primary,"CFrame"),pivot_frame(w,*primary,"PivotOffset"));
        return model_world_pivot(w,n);
    }
    auto cf=pivot_frame(w,n,"CFrame");
    return pivot_part(w,n)?pivot_product(cf,pivot_frame(w,n,"PivotOffset")):cf;
}
Handle* checked_pivot_object(lua_State* L,bool model_only=false) {
    auto* h=checked_handle(L,1);
    if(h->node->destroyed||!pivot_object(*h->world,*h->node)||(model_only&&!pivot_model(*h->world,*h->node)))
        luaL_error(L,"pivot method has an invalid receiver");
    return h;
}
int object_get_pivot(lua_State* L) {
    auto* h=checked_pivot_object(L);
    try{auto cf=object_pivot(*h->world,*h->node);return push_frame_value(L,cf.p,cf.r);}
    catch(const std::exception& e){luaL_error(L,"GetPivot: %s",e.what());return 0;}
}
int model_get_bounds(lua_State* L) {
    auto* h=checked_pivot_object(L,true);
    try{auto result=pivot_bounds(*h->world,*h->node,object_pivot(*h->world,*h->node));
        bool size_only=lua_toboolean(L,lua_upvalueindex(1));
        if(!size_only)push_frame_value(L,result.first.p,result.first.r);
        lua_pushvector(L,result.second[0],result.second[1],result.second[2]);return size_only?1:2;
    }catch(const std::exception& e){luaL_error(L,"model bounds: %s",e.what());return 0;}
}
Json pivot_fingerprint(World& w,const std::vector<Node*>& nodes) {
    Json result=Json::array();
    for(auto* n:nodes) {
        Json row{{"id",n->id},{"parent",parent_id(w,*n)}};
        for(const char* key:{"CFrame","PivotOffset","WorldPivot","PrimaryPart","Size"})
            if(const auto* value=property_value(w,*n,key))row[key]=*value;
        result.push_back(std::move(row));
    }
    return result;
}
int object_pivot_to(lua_State* L) {
    auto* h=checked_pivot_object(L);auto* requested=checked_cframe(L,2);World& w=*h->world;
    try {
        CFrameValue target=pivot_decode(pivot_encode(*requested));
        auto nodes=pivot_descendants(w,*h->node,true);
        nodes.erase(std::remove_if(nodes.begin(),nodes.end(),[&](Node* n){return !pivot_object(w,*n);}),nodes.end());
        auto before=pivot_fingerprint(w,nodes);auto source=object_pivot(w,*h->node);
        if(pivot_model(w,*h->node))if(auto* primary=model_primary(w,*h->node);primary&&!is_descendant_of(w,*primary,h->node->id))
            throw std::runtime_error("PivotTo requires the PrimaryPart to be inside the model");
        // Include the pivot itself, since external primary parts can affect it.
        before.push_back(pivot_encode(source));
        Json offsets=Json::array();auto cached=w.pivot_caches.find(h->node->id);
        if(cached!=w.pivot_caches.end()&&cached->second["fingerprint"]==before)offsets=cached->second["offsets"];
        else {
            auto inverse=pivot_inverse(source);
            for(auto* n:nodes)offsets.push_back(pivot_encode(pivot_product(inverse,pivot_model(w,*n)?model_world_pivot(w,*n):pivot_frame(w,*n,"CFrame"))));
        }
        size_t cached_count=nodes.size();for(const auto& [id,cache]:w.pivot_caches)if(id!=h->node->id)cached_count+=cache["offsets"].size();
        if(cached_count>20000)throw std::runtime_error("local pivot cache limit exceeded");
        std::vector<Json> entries;std::vector<std::pair<Node*,std::pair<std::string,Json>>> writes;
        auto add=[&](Node* n,const std::string& key,Json value){entries.push_back(Json{{"kind","set"},{"id",n->id},{"property",key},{"value",value}});writes.push_back({n,{key,std::move(value)}});};
        for(size_t i=0;i<nodes.size();++i) {
            auto* n=nodes[i];auto transformed=pivot_product(target,pivot_decode(offsets[i]));
            // Revalidate computed output before committing any local property.
            auto value=pivot_encode(transformed);pivot_decode(value);
            if(pivot_model(w,*n))add(n,"WorldPivot",value);
            else {add(n,"CFrame",value);if(pivot_part(w,*n)) {
                    add(n,"Position",Json{{"$vector3",transformed.p}});
                    add(n,"Orientation",pivot_angles(L,transformed,true));add(n,"Rotation",pivot_angles(L,transformed,false));
                }
                if(n->class_name=="Camera")add(n,"CoordinateFrame",value);}
        }
        check_mutation_budget(w,entries);
        std::vector<std::pair<Node*,std::string>> changed;
        for(auto& [n,field]:writes){auto* old=property_value(w,*n,field.first);if(!old||*old!=field.second)changed.push_back({n,field.first});w.local_properties[n->id][field.first]=field.second;}
        append_mutations(w,std::move(entries));
        auto after=pivot_fingerprint(w,nodes);after.push_back(pivot_encode(object_pivot(w,*h->node)));
        w.pivot_caches[h->node->id]=Json{{"fingerprint",std::move(after)},{"offsets",std::move(offsets)}};
        // PivotTo changes CFrame but deliberately suppresses Position events.
        for(auto& [n,key]:changed)if(key!="Position"&&key!="Orientation"&&key!="Rotation")property_events(w,*n,key);
        return 0;
    }catch(const std::exception& e){luaL_error(L,"PivotTo: %s",e.what());return 0;}
}
int model_get_primary_frame(lua_State* L);
int model_move_legacy(lua_State* L);
int model_get_scale(lua_State* L);
int model_scale_to(lua_State* L);
bool model_pivot_index(lua_State* L,World& w,Node& n,const std::string& key) {
    if(!pivot_object(w,n))return false;
    if(key=="GetPivot"){lua_pushcfunction(L,object_get_pivot,"GetPivot");return true;}
    if(key=="PivotTo"){lua_pushcfunction(L,object_pivot_to,"PivotTo");return true;}
    if(pivot_model(w,n)) {
        if(key=="GetScale"){lua_pushcfunction(L,model_get_scale,"GetScale");return true;}
        if(key=="ScaleTo"){lua_pushcfunction(L,model_scale_to,"ScaleTo");return true;}
        if(key=="Scale")throw std::runtime_error("Scale is not scriptable; use GetScale and ScaleTo");
        if(key=="GetPrimaryPartCFrame"){lua_pushcfunction(L,model_get_primary_frame,"GetPrimaryPartCFrame");return true;}
        if(key=="TranslateBy"||key=="SetPrimaryPartCFrame") {
            lua_pushboolean(L,key=="SetPrimaryPartCFrame");lua_pushcclosure(L,model_move_legacy,key.c_str(),1);return true;
        }
        if(key=="WorldPivot"){auto cf=model_world_pivot(w,n);push_frame_value(L,cf.p,cf.r);return true;}
        if(key=="GetBoundingBox"||key=="GetExtentsSize") {
            lua_pushboolean(L,key=="GetExtentsSize");lua_pushcclosure(L,model_get_bounds,key.c_str(),1);return true;
        }
    }
    return false;
}
