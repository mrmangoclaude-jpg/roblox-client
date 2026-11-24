// Attachment geometry uses the ancestor reference pose. Bone animation offsets
// are included only in TransformedCFrame / TransformedWorldCFrame.
constexpr const char* kAttachmentLocal[]={"CFrame","Position","Orientation","Rotation","Axis","SecondaryAxis"};
constexpr const char* kAttachmentWorld[]={"WorldCFrame","WorldPosition","WorldOrientation","WorldRotation","WorldAxis","WorldSecondaryAxis"};
bool attachment_node(World& w,const Node& n){return class_is_a(w,n.class_name,"Attachment");}
bool attachment_local_key(const std::string& key){for(const char* s:kAttachmentLocal)if(key==s)return true;return false;}
bool attachment_world_key(const std::string& key){for(const char* s:kAttachmentWorld)if(key==s)return true;return false;}
bool bone_computed_key(const Node& n,const std::string& key){return n.class_name=="Bone"&&(key=="TransformedCFrame"||key=="TransformedWorldCFrame");}
Json attachment_local_fields(const Json& frame) {
    auto result=part_fields_from_frame(frame);
    if(result.contains("Orientation")) {
        auto cf=pivot_decode(frame);
        result["Axis"]=Json{{"$vector3",FrameVector{cf.r[0],cf.r[3],cf.r[6]}}};
        result["SecondaryAxis"]=Json{{"$vector3",FrameVector{cf.r[1],cf.r[4],cf.r[7]}}};
    }
    return result;
}
Json attachment_local_state(World& w,const Node& n) {
    const auto* frame=property_value(w,n,"CFrame");
    if(frame)return attachment_local_fields(*frame);
    Json state=Json::object();for(const char* key:kAttachmentLocal)if(auto* v=property_value(w,n,key))state[key]=*v;
    return state;
}
// Iterative traversal avoids recursive stack growth for deeply nested rigs.
// An unresolved parent is not equivalent to the world origin.
CFrameValue attachment_parent_frame(World& w,const Node& n,bool animated=false) {
    CFrameValue result;std::string id=parent_id(w,n);std::unordered_set<std::string> seen{n.id};
    while(!id.empty()) {
        if(!seen.insert(id).second)throw std::runtime_error("attachment ancestry contains a cycle");
        auto* parent=find_node(w,id);
        if(!parent||parent->destroyed)throw std::runtime_error("attachment ancestor is unavailable");
        if(class_is_a(w,parent->class_name,"WorldRoot"))return result;
        if(attachment_node(w,*parent)) {
            auto frame=pivot_frame(w,*parent,"CFrame");
            if(animated&&parent->class_name=="Bone")frame=pivot_product(frame,pivot_frame(w,*parent,"Transform"));
            result=pivot_product(frame,result);
        } else if(pivot_object(w,*parent)) {
            // BasePart attachments are relative to CFrame, not PivotOffset.
            auto frame=pivot_model(w,*parent)?object_pivot(w,*parent):pivot_frame(w,*parent,"CFrame");
            return pivot_product(frame,result);
        }
        id=parent_id(w,*parent);
    }
    return result;
}
Json attachment_value(World& w,Node& n,const std::string& key) {
    if(attachment_local_key(key)) {
        auto state=attachment_local_state(w,n);
        if(!state.contains(key))throw std::runtime_error("attachment local transform is unavailable");
        return state[key];
    }
    if(bone_computed_key(n,key)) {
        auto frame=pivot_product(pivot_frame(w,n,"CFrame"),pivot_frame(w,n,"Transform"));
        if(key=="TransformedWorldCFrame")frame=pivot_product(attachment_parent_frame(w,n,true),frame);
        return pivot_encode(frame);
    }
    auto parent=attachment_parent_frame(w,n);
    if(key=="WorldPosition") {
        auto local=part_vector(attachment_value(w,n,"Position"));auto p=frame_rotate(parent.r,local);
        for(int i=0;i<3;++i)p[i]+=parent.p[i];return Json{{"$vector3",p}};
    }
    auto local=pivot_frame(w,n,"CFrame");
    // A received rotation whose metadata was not replicated must stay unknown.
    // WorldPosition (handled above) only needs translation; every other computed
    // world pose needs the rotation, so never silently substitute identity.
    if(!local.rotation_known)throw std::runtime_error("attachment rotation is unavailable");
    auto frame=pivot_product(parent,local);
    auto fields=attachment_local_fields(pivot_encode(frame));return fields.at(key.substr(5));
}
std::string attachment_origin(World& w,const Node& n,const std::string& key) {
    if(!attachment_node(w,n)||key=="CFrame"||(!attachment_local_key(key)&&!attachment_world_key(key)&&!bone_computed_key(n,key)))return {};
    try {
        attachment_value(w,const_cast<Node&>(n),key);
        std::string tag=origin(w,n,"CFrame");
        auto merge=[&](const std::string& value){if(value=="local")tag="local";else if(tag!="local"&&(value=="received"||value=="derived_received"))tag="derived_received";};
        if(tag=="received")tag="derived_received";
        bool animated=bone_computed_key(n,key);
        if(animated)merge(origin(w,n,"Transform"));
        if(attachment_world_key(key)||key=="TransformedWorldCFrame") {
            merge(origin(w,n,"Parent"));
            std::unordered_set<std::string> seen;auto id=parent_id(w,n);
            while(!id.empty()&&seen.insert(id).second) {
                auto* p=find_node(w,id);if(!p)break;
                if(class_is_a(w,p->class_name,"WorldRoot"))break;
                if(attachment_node(w,*p)) {merge(origin(w,*p,"CFrame"));merge(origin(w,*p,"Parent"));if(animated&&p->class_name=="Bone")merge(origin(w,*p,"Transform"));}
                else if(pivot_object(w,*p)){merge(origin(w,*p,pivot_model(w,*p)?"WorldPivot":"CFrame"));break;}
                id=parent_id(w,*p);
            }
        }
        return tag;
    }catch(const std::exception&){return "unavailable";}
}
FrameVector attachment_unit(FrameVector v) {
    double length=std::hypot(v[0],v[1],v[2]);
    if(!std::isfinite(length)||length<1e-12)throw std::runtime_error("attachment axis must be finite and nonzero");
    for(auto& x:v)x/=length;return v;
}
Json attachment_prepare(World& w,Node& n,const Json& fields) {
    if(fields.contains("CFrame"))return attachment_local_fields(fields["CFrame"]);
    auto state=prepare_part_transform(w,n,fields);
    if(fields.contains("Axis")||fields.contains("SecondaryAxis")) {
        if(!state.contains("CFrame"))throw std::runtime_error("attachment pose is unavailable");
        auto frame=pivot_decode(state["CFrame"]);
        FrameVector x{frame.r[0],frame.r[3],frame.r[6]},y{frame.r[1],frame.r[4],frame.r[7]},z{frame.r[2],frame.r[5],frame.r[8]};
        if(fields.contains("Axis"))x=attachment_unit(part_vector(fields["Axis"]));else x=attachment_unit(x);
        if(fields.contains("SecondaryAxis"))y=attachment_unit(part_vector(fields["SecondaryAxis"]));
        double dot=frame_dot(x,y);for(int i=0;i<3;++i)y[i]-=dot*x[i];
        if(std::hypot(y[0],y[1],y[2])<1e-10) {
            if(fields.contains("SecondaryAxis"))throw std::runtime_error("attachment axes must not be parallel");
            y=frame_cross(z,x);
        }
        y=attachment_unit(y);z=attachment_unit(frame_cross(x,y));
        frame.r=frame_columns(x,y,z);state["CFrame"]=pivot_encode(frame);
    }
    return state.contains("CFrame")?attachment_local_fields(state["CFrame"]):state;
}
void attachment_commit_local(World& w,Node& n,const Json& after) {
    Json before;try{before=attachment_local_state(w,n);}catch(const std::exception&){before=Json::object();}
    std::vector<Json> entries;
    for(auto it=after.begin();it!=after.end();++it)entries.push_back(Json{{"kind","set"},{"id",n.id},{"property",it.key()},{"value",it.value()}});
    check_mutation_budget(w,entries);
    for(auto it=after.begin();it!=after.end();++it)w.local_properties[n.id][it.key()]=it.value();
    append_mutations(w,std::move(entries));
    for(const char* key:kAttachmentLocal)if(before.contains(key)!=after.contains(key)||(before.contains(key)&&before[key]!=after[key]))property_events(w,n,key);
}
void attachment_set(World& w,Node& n,const std::string& key,const Json& value) {
    if(key=="WorldRotation"||bone_computed_key(n,key))throw std::runtime_error("attachment property is read-only");
    if(key=="Transform"&&n.class_name=="Bone") {
        pivot_decode(value);auto* prior=property_value(w,n,key);bool changed=!prior||*prior!=value;
        std::vector<Json> entries{Json{{"kind","set"},{"id",n.id},{"property",key},{"value",value}}};
        check_mutation_budget(w,entries);w.local_properties[n.id][key]=value;append_mutations(w,std::move(entries));
        if(changed)property_events(w,n,key);return;
    }
    if(!attachment_world_key(key)){attachment_commit_local(w,n,attachment_prepare(w,n,Json{{key,value}}));return;}
    auto parent=attachment_parent_frame(w,n);auto inverse=pivot_inverse(parent);
    if(key=="WorldCFrame") {
        auto local=pivot_product(inverse,pivot_decode(value));attachment_commit_local(w,n,attachment_local_fields(pivot_encode(local)));return;
    }
    auto vector=part_vector(value);
    if(key=="WorldPosition") {
        for(int i=0;i<3;++i)vector[i]-=parent.p[i];vector=frame_rotate(inverse.r,vector);
        attachment_commit_local(w,n,attachment_prepare(w,n,Json{{"Position",Json{{"$vector3",vector}}}}));return;
    }
    if(key=="WorldAxis"||key=="WorldSecondaryAxis") {
        vector=frame_rotate(inverse.r,vector);
        attachment_commit_local(w,n,attachment_prepare(w,n,Json{{key.substr(5),Json{{"$vector3",vector}}}}));return;
    }
    // Explicit world angles provide rotation; only the existing world position
    // is needed, so this can also repair an unknown local rotation.
    Node target;target.properties["Position"]=attachment_value(w,n,"WorldPosition");
    auto world=prepare_part_transform(w,target,Json{{"Orientation",value}});
    auto local=pivot_product(inverse,pivot_decode(world.at("CFrame")));
    attachment_commit_local(w,n,attachment_local_fields(pivot_encode(local)));
}
bool attachment_write(lua_State* L,World& w,Node& n,const std::string& key) {
    if(!attachment_node(w,n)||(!attachment_local_key(key)&&!attachment_world_key(key)&&!bone_computed_key(n,key)&&!(n.class_name=="Bone"&&key=="Transform")))return false;
    if(key=="CFrame"||key=="WorldCFrame"||key=="Transform") {if(!has_meta(L,3,kCFrameMeta))throw std::runtime_error("attachment pose must be a CFrame");}
    else if(!bone_computed_key(n,key)&&!lua_isvector(L,3))throw std::runtime_error("attachment property must be a Vector3");
    attachment_set(w,n,key,convert_lua_value(L,w,3));return true;
}
int attachment_method(lua_State* L) {
    auto* h=checked_handle(L,1);World& w=*h->world;Node& n=*h->node;const std::string method=lua_tostring(L,lua_upvalueindex(1));
    if(!attachment_node(w,n)){luaL_error(L,"attachment method requires Attachment");return 0;}
    try {
        if(method=="GetConstraints") {
            lua_newtable(L);int index=1;
            for(const auto& id:w.order) {
                auto& constraint=w.nodes.at(id);if(constraint.destroyed||!class_is_a(w,constraint.class_name,"Constraint"))continue;
                for(const char* key:{"Attachment0","Attachment1"}) {
                    const auto* ref=property_value(w,constraint,key);
                    if(ref&&ref->is_object()&&ref->contains("$ref")&&(*ref)["$ref"]==n.id) {push_node(L,w,&constraint);lua_rawseti(L,-2,index++);break;}
                }
            }
            return 1;
        }
        std::string key=method.substr(3);
        if(method.rfind("Get",0)==0){push_json(L,w,attachment_value(w,n,key));return 1;}
        if(!lua_isvector(L,2))throw std::runtime_error("attachment axis must be a Vector3");
        attachment_set(w,n,key,convert_lua_value(L,w,2));return 0;
    }catch(const std::exception& e){luaL_error(L,"attachment method failed: %s",e.what());return 0;}
}
bool attachment_index(lua_State* L,World& w,Node& n,const std::string& key) {
    if(!attachment_node(w,n))return false;
    if(key=="GetAxis"||key=="GetSecondaryAxis"||key=="SetAxis"||key=="SetSecondaryAxis"||key=="GetConstraints") {
        lua_pushlstring(L,key.data(),key.size());lua_pushcclosurek(L,attachment_method,key.c_str(),1,nullptr);return true;
    }
    if(!attachment_local_key(key)&&!attachment_world_key(key)&&!bone_computed_key(n,key))return false;
    push_json(L,w,attachment_value(w,n,key));return true;
}
void watch_attachment_property(World& w,Node& n,const std::string& key) {
    if(!attachment_node(w,n)||(!attachment_world_key(key)&&!bone_computed_key(n,key)))return;
    auto& watched=w.attachment_watches[n.id];if(watched.contains(key))return;
    try{watched[key]=attachment_value(w,n,key);}catch(const std::exception&){watched[key]=nullptr;}
}
void refresh_attachment_events(World& w) {
    for(auto it=w.attachment_watches.begin();it!=w.attachment_watches.end();) {
        auto* n=find_node(w,it->first);if(!n||n->destroyed){it=w.attachment_watches.erase(it);continue;}
        for(auto p=it->second.begin();p!=it->second.end();++p) {
            Json value;try{value=attachment_value(w,*n,p.key());}catch(const std::exception&){value=nullptr;}
            if(value!=p.value()){p.value()=value;property_events(w,*n,p.key());}
        }
        ++it;
    }
}
bool apply_received_attachment_transform(World& w,Node& n,const Json& fields,uint64_t sequence) {
    if(!attachment_node(w,n))return false;
    Json inputs=Json::object();for(const char* key:kAttachmentLocal)if(fields.contains(key))inputs[key]=fields[key];
    if(inputs.empty())return false;
    auto after=attachment_prepare(w,n,inputs);Json before;
    try{before=attachment_local_state(w,n);}catch(const std::exception&){before=Json::object();}
    for(const char* key:kAttachmentLocal)if(after.contains("CFrame")||after.contains(key))clear_local_property(w,n.id,key);
    for(auto it=after.begin();it!=after.end();++it){n.properties[it.key()]=it.value();n.revisions[it.key()]=sequence;n.origins[it.key()]=inputs.contains(it.key())?"received":"derived_received";}
    for(const char* key:kAttachmentLocal)if(before.contains(key)!=after.contains(key)||(before.contains(key)&&before[key]!=after[key]))property_events(w,n,key);
    return true;
}
