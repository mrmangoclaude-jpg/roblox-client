// Local topology and rigid kinematics, not a contact/force solver. Redundant
// rigid edges are selected in stable world order; native tie order is unknown.
bool joint_part_endpoints(World& w,const Node& n){return n.class_name=="WeldConstraint"||class_is_a(w,n.class_name,"JointInstance");}
bool joint_rigid(const Node& n) {
    for(const char* name:{"Weld","Snap","ManualWeld","Motor","Motor6D","WeldConstraint"})if(n.class_name==name)return true;
    return false;
}
bool joint_node(World& w,const Node& n){return joint_part_endpoints(w,n)||class_is_a(w,n.class_name,"Constraint");}
std::string joint_container(World& w,const Node& n,bool allow_service=false) {
    const Node* current=&n;std::unordered_set<std::string> visited;
    while(current) {
        if(!visited.insert(current->id).second)throw std::runtime_error("joint ancestry contains a cycle");
        if(current->destroyed)return {};
        if(class_is_a(w,current->class_name,"WorldRoot"))return current->id;
        if(allow_service&&current->class_name=="JointsService")return "@JointsService";
        auto id=parent_id(w,*current);if(id.empty())return {};
        current=find_node(w,id);if(!current)throw std::runtime_error("joint ancestry is unresolved");
    }
    return {};
}
Node* joint_reference(World& w,const Node& n,const char* key,bool attachment) {
    const auto* v=property_value(w,n,key);
    if(!v)throw std::runtime_error(std::string(key)+" is unavailable");
    if(v->is_null())return nullptr;
    if(!v->is_object()||!v->contains("$ref")||!(*v)["$ref"].is_string())throw std::runtime_error("invalid joint endpoint reference");
    auto* node=find_node(w,(*v)["$ref"].get<std::string>());
    if(!node)throw std::runtime_error("joint endpoint is unresolved");
    if(node->destroyed)return nullptr;
    if(attachment?!attachment_node(w,*node):!pivot_part(w,*node))throw std::runtime_error("joint endpoint has incorrect class");
    if(!attachment)return node;
    std::unordered_set<std::string> visited;
    while(node) {
        if(!visited.insert(node->id).second)throw std::runtime_error("attachment endpoint ancestry contains a cycle");
        auto id=parent_id(w,*node);if(id.empty())return nullptr;
        node=find_node(w,id);if(!node)throw std::runtime_error("attachment endpoint ancestor is unresolved");
        if(node->destroyed)return nullptr;
        if(pivot_part(w,*node))return node;
        if(class_is_a(w,node->class_name,"WorldRoot"))return nullptr;
    }
    return nullptr;
}
struct JointEdge {Node* joint=nullptr;Node* a=nullptr;Node* b=nullptr;bool rigid=false;bool active=false;std::string unknown;};
struct JointGraph {
    World& w;std::vector<JointEdge> edges;
    std::unordered_map<std::string,std::vector<size_t>> incident;
    std::unordered_map<std::string,std::string> parent;
    std::unordered_map<std::string,bool> anchored;
    std::string root(std::string id) {
        if(!parent.count(id))parent[id]=id;
        std::string result=id;while(parent[result]!=result)result=parent[result];
        while(parent[id]!=id){auto next=parent[id];parent[id]=result;id=next;}return result;
    }
    explicit JointGraph(World& world,const std::vector<std::string>* selected=nullptr):w(world) {
        for(const auto& id:selected?*selected:get_joint_order(w)) {
            auto& node=w.nodes.at(id);if(node.destroyed||!joint_node(w,node))continue;
            JointEdge edge;edge.joint=&node;edge.rigid=joint_rigid(node);
            bool attachments=!joint_part_endpoints(w,node),inactive=false,single=false,mode_unknown=false;
            for(const char* name:{"VectorForce","Torque","LinearVelocity","AngularVelocity"})if(node.class_name==name)single=true;
            if(node.class_name=="LinearVelocity"||node.class_name=="VectorForce") {
                const Json* relative=property_value(w,node,"RelativeTo");
                if(relative&&relative->is_object()&&relative->contains("$enum")) {
                    const auto& item=(*relative)["$enum"];
                    relative=item.is_object()&&item.value("type","")=="ActuatorRelativeTo"&&item.contains("value")
                        ?&item.at("value"):nullptr;
                }
                if(!relative||!relative->is_number_integer()||relative->get<int>()<0||relative->get<int>()>2)mode_unknown=true;
                else single=relative->get<int>()!=1;
            }
            if(node.class_name=="AlignPosition"||node.class_name=="AlignOrientation") {
                auto* mode=property_value(w,node,"Mode");
                if(!mode||!mode->is_number_integer()||(mode->get<int>()!=0&&mode->get<int>()!=1))mode_unknown=true;
                else single=mode->get<int>()==0;
            }
            auto endpoint=[&](const char* key,Node*& out){try{out=joint_reference(w,node,key,attachments);if(!out)inactive=true;}catch(const std::exception& e){edge.unknown=e.what();}};
            endpoint(attachments?"Attachment0":"Part0",edge.a);
            if(!single&&!mode_unknown)endpoint(attachments?"Attachment1":"Part1",edge.b);
            if(mode_unknown)edge.unknown="constraint mode is unavailable";
            try {
                const auto* enabled=property_value(w,node,"Enabled");
                if(!enabled||!enabled->is_boolean())throw std::runtime_error("joint Enabled state is unavailable");
                if(!enabled->get<bool>())inactive=true;
                auto container=joint_container(w,node,joint_part_endpoints(w,node)&&node.class_name!="WeldConstraint");
                if(container.empty())inactive=true;
                if(single&&edge.a) {
                    auto first=joint_container(w,*edge.a);if(first.empty()||container!=first)inactive=true;
                }
                if(edge.a&&edge.b) {
                    auto first=joint_container(w,*edge.a),second=joint_container(w,*edge.b);
                    // VectorForce's second attachment supplies a direction
                    // frame, not a second body to couple. That frame may live
                    // on the same part as Attachment0.
                    if(first.empty()||first!=second||(edge.a==edge.b&&node.class_name!="VectorForce"))inactive=true;
                    if(container!="@JointsService"&&container!=first)inactive=true;
                    if(container=="@JointsService") {
                        auto* world_root=find_node(w,first);
                        if(!world_root||world_root->class_name!="Workspace")inactive=true;
                    }
                    if(edge.rigid&&!inactive)for(auto* part:{edge.a,edge.b}) {
                        auto* flag=property_value(w,*part,"Anchored");
                        if(!flag||!flag->is_boolean())throw std::runtime_error("joint endpoint Anchored state is unavailable");
                        auto representative=root(part->id);anchored[representative]=anchored[representative]||flag->get<bool>();
                    }
                }
            }catch(const std::exception& e){edge.unknown=e.what();}
            if(inactive)edge.unknown.clear();
            if(!inactive&&edge.unknown.empty()&&edge.a&&(edge.b||single)) {
                edge.active=true;
                if(edge.rigid) {
                    auto a=root(edge.a->id),b=root(edge.b->id);
                    if(a==b||(anchored[a]&&anchored[b]))edge.active=false;
                    else{parent[b]=a;anchored[a]=anchored[a]||anchored[b];}
                }
            }
            auto index=edges.size();edges.push_back(std::move(edge));
            if(edges.back().a)incident[edges.back().a->id].push_back(index);
            if(edges.back().b&&edges.back().b!=edges.back().a)incident[edges.back().b->id].push_back(index);
        }
    }
    std::vector<Node*> connected(Node& node,bool recursive) {
        std::vector<Node*> result;std::unordered_set<std::string> seen{node.id};std::deque<Node*> pending{&node};
        while(!pending.empty()) {
            auto* next=pending.front();pending.pop_front();
            for(auto index:incident[next->id]) {
                auto& edge=edges[index];if(!edge.rigid)continue;
                if(!edge.unknown.empty())throw std::runtime_error("connected parts unavailable: "+edge.unknown);
                if(!edge.active)continue;
                auto* other=edge.a==next?edge.b:edge.a;
                if(seen.insert(other->id).second){result.push_back(other);if(recursive)pending.push_back(other);}
            }
        }
        return result;
    }
    bool active(Node& node) {
        for(const auto& edge:edges)if(edge.joint==&node){if(!edge.unknown.empty())throw std::runtime_error(edge.unknown);return edge.active;}
        return false;
    }
};
int joint_query(lua_State* L) {
    auto* h=checked_handle(L,1);World& w=*h->world;Node& n=*h->node;
    if(!pivot_part(w,n)){luaL_error(L,"connection query requires BasePart");return 0;}
    const std::string method=lua_tostring(L,lua_upvalueindex(1));
    if(method=="GetConnectedParts"&&!lua_isnoneornil(L,2)&&lua_type(L,2)!=LUA_TBOOLEAN){luaL_error(L,"recursive must be a boolean");return 0;}
    try {
        JointGraph graph(w);std::vector<Node*> result;
        if(!n.destroyed) {
            if(method=="GetConnectedParts")result=graph.connected(n,lua_toboolean(L,2));
            else for(auto index:graph.incident[n.id]){auto& edge=graph.edges[index];if(!edge.unknown.empty())throw std::runtime_error("joint state unavailable: "+edge.unknown);if(edge.active)result.push_back(edge.joint);}
        }
        lua_newtable(L);int index=1;for(auto* node:result){push_node(L,w,node);lua_rawseti(L,-2,index++);}return 1;
    }catch(const std::exception& e){luaL_error(L,"connection query failed: %s",e.what());return 0;}
}
bool joint_index(lua_State* L,World& w,Node& n,const std::string& key) {
    if((key=="GetConnectedParts"||key=="GetJoints")&&pivot_part(w,n)) {
        lua_pushlstring(L,key.data(),key.size());lua_pushcclosurek(L,joint_query,key.c_str(),1,nullptr);return true;
    }
    if(key=="Active"&&joint_node(w,n)){JointGraph graph(w);lua_pushboolean(L,graph.active(n));return true;}
    return false;
}
std::string joint_origin(World& w,const Node& n,const std::string& key) {
    if(key!="Active"||!joint_node(w,n))return {};
    try{JointGraph graph(w);graph.active(const_cast<Node&>(n));return "local";}catch(const std::exception&){return "unavailable";}
}
void validate_joint_assignment(lua_State* L,World& w,Node& n,const std::string& key) {
    if(key!="Part0"&&key!="Part1"&&key!="Attachment0"&&key!="Attachment1")return;
    bool part=joint_part_endpoints(w,n)&&(key=="Part0"||key=="Part1");
    bool attachment=class_is_a(w,n.class_name,"Constraint")&&(key=="Attachment0"||key=="Attachment1");
    if((part||attachment)&&!lua_isnil(L,3)) {
        auto* target=checked_handle(L,3);
        if(target->world!=&w||(part?!pivot_part(w,*target->node):!attachment_node(w,*target->node)))throw std::runtime_error(part?"joint endpoint must be a BasePart":"constraint endpoint must be an Attachment");
    }
}
void watch_joint_property(World& w,Node& n,const std::string& key) {
    if(key!="Active"||!joint_node(w,n)||w.joint_active_watches.count(n.id))return;
    try{JointGraph graph(w);w.joint_active_watches[n.id]=graph.active(n);}catch(const std::exception&){w.joint_active_watches[n.id]=nullptr;}
}
void refresh_joint_events(World& w) {
    if(w.joint_active_watches.empty())return;JointGraph graph(w);
    for(auto it=w.joint_active_watches.begin();it!=w.joint_active_watches.end();) {
        auto* n=find_node(w,it->first);if(!n||n->destroyed){it=w.joint_active_watches.erase(it);continue;}
        Json value;try{value=graph.active(*n);}catch(const std::exception&){value=nullptr;}
        if(value!=it->second){it->second=value;property_events(w,*n,"Active");}++it;
    }
}
bool joint_part_write(lua_State* L,World& w,Node& n,const std::string& key) {
    if(!part_transform_key(key)||!pivot_part(w,n))return false;
    JointGraph graph(w);auto connected=graph.connected(n,true);
    if(connected.empty())return false;
    if(key=="CFrame"){if(!has_meta(L,3,kCFrameMeta))throw std::runtime_error("CFrame must be a CFrame");}
    else if(!lua_isvector(L,3))throw std::runtime_error("part transform must be a Vector3");
    auto before=part_transform_state(w,n);auto after=prepare_part_transform(w,n,Json{{key,convert_lua_value(L,w,3)}});
    auto old_frame=pivot_decode(before.at("CFrame")),new_frame=pivot_decode(after.at("CFrame"));
    std::vector<std::pair<Node*,Json>> changes{{&n,after}};
    if(key=="CFrame") {
        auto delta=pivot_product(new_frame,pivot_inverse(old_frame));
        for(auto* part:connected)changes.emplace_back(part,part_fields_from_frame(pivot_encode(pivot_product(delta,pivot_frame(w,*part,"CFrame")))));
    } else {
        // Rebase the moved endpoint's joint frame; other parts remain still.
        auto rebase=pivot_product(pivot_inverse(new_frame),old_frame);
        for(auto index:graph.incident[n.id]) {
            auto& edge=graph.edges[index];if(!edge.active||!edge.rigid||edge.joint->class_name=="WeldConstraint")continue;
            const char* offset=edge.a==&n?"C0":"C1";
            auto frame=pivot_product(rebase,pivot_frame(w,*edge.joint,offset));
            changes.emplace_back(edge.joint,Json{{offset,pivot_encode(frame)}});
        }
    }
    std::vector<Json> entries;std::vector<Json> previous;
    for(auto& [node,fields]:changes) {
        previous.push_back(pivot_part(w,*node)?part_transform_state(w,*node):Json::object());
        for(auto it=fields.begin();it!=fields.end();++it) {
            entries.push_back(Json{{"kind","set"},{"id",node->id},{"property",it.key()},{"value",it.value()}});
            if(!pivot_part(w,*node)){auto* old=property_value(w,*node,it.key());if(old)previous.back()[it.key()]=*old;}
        }
    }
    check_mutation_budget(w,entries);
    for(auto& [node,fields]:changes)for(auto it=fields.begin();it!=fields.end();++it)w.local_properties[node->id][it.key()]=it.value();
    append_mutations(w,std::move(entries));
    for(size_t i=0;i<changes.size();++i) {
        auto& [node,fields]=changes[i];if(pivot_part(w,*node))part_transform_events(w,*node,previous[i],fields);
        else for(auto it=fields.begin();it!=fields.end();++it)if(!previous[i].contains(it.key())||previous[i][it.key()]!=it.value())property_events(w,*node,it.key());
    }
    return true;
}
