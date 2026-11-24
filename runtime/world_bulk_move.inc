// Prepare all poses and output records before publishing anything. The existing
// mutation bridge consumes ordinary transform records from this batch.
int bulk_array_length(lua_State* L,int index) {
    if(!lua_istable(L,index))throw std::runtime_error("BulkMoveTo requires sequential arrays");
    index=lua_absindex(L,index);const int length=lua_objlen(L,index);
    if(length>4096)throw std::runtime_error("BulkMoveTo array exceeds 4096 entries");
    int count=0;lua_pushnil(L);
    while(lua_next(L,index)) {
        if(++count>4096||lua_type(L,-2)!=LUA_TNUMBER||lua_tonumber(L,-2)<1||
                lua_tonumber(L,-2)>length||std::floor(lua_tonumber(L,-2))!=lua_tonumber(L,-2))
            throw std::runtime_error("BulkMoveTo requires dense sequential arrays");
        lua_pop(L,1);
    }
    if(count!=length)throw std::runtime_error("BulkMoveTo arrays cannot contain holes");
    return length;
}
int world_root_bulk_move(lua_State* L) {
    const auto* h=checked_handle(L,1);
    try {
        if(h->node->destroyed||!collision_world_root(*h->node))throw std::runtime_error("BulkMoveTo requires a live WorldRoot");
        if(lua_gettop(L)<3||lua_gettop(L)>4)throw std::runtime_error("BulkMoveTo expects parts, CFrames, and optional BulkMoveMode");
        const int count=bulk_array_length(L,2);
        if(bulk_array_length(L,3)!=count)throw std::runtime_error("BulkMoveTo arrays must have equal lengths");
        int mode=0;
        if(!lua_isnoneornil(L,4)) {
            Json value;
            if(!capture_ussi_export_enum(L,4,value)||value["$enum"]["type"]!="BulkMoveMode")
                throw std::runtime_error("BulkMoveTo eventMode requires Enum.BulkMoveMode");
            mode=value["$enum"]["value"].get<int>();
        }
        auto& w=*h->world;
        std::vector<std::pair<Node*,CFrameValue>> requests;requests.reserve(count);
        for(int i=1;i<=count;++i) {
            lua_rawgeti(L,2,i);
            if(!has_meta(L,-1,kInstanceMeta))throw std::runtime_error("BulkMoveTo partList requires BaseParts");
            const auto* part=static_cast<Handle*>(lua_touserdata(L,-1));
            if(part->world!=&w||part->node->destroyed||!pivot_part(w,*part->node)||part->node->class_name=="Terrain")
                throw std::runtime_error("BulkMoveTo requires live movable BaseParts in this runtime");
            Node* node=part->node;lua_pop(L,1);lua_rawgeti(L,3,i);
            if(!has_meta(L,-1,kCFrameMeta))throw std::runtime_error("BulkMoveTo cframeList requires CFrames");
            auto frame=*checked_cframe(L,-1);lua_pop(L,1);
            // Use the normal transform derivation to validate coordinates and
            // rotation before even considering a mutation to the current world.
            part_fields_from_frame(pivot_encode(frame));
            requests.emplace_back(node,std::move(frame));
        }
        if(requests.empty())return 0;

        struct Component {std::vector<Node*> parts;Node* anchor=nullptr;CFrameValue target;};
        std::vector<Component> components;
        std::unordered_map<std::string,size_t> membership;
        JointGraph graph(w);
        for(const auto& [part,target]:requests) {
            auto found=membership.find(part->id);size_t index;
            if(found==membership.end()) {
                index=components.size();Component component;
                component.parts=graph.connected(*part,true);component.parts.insert(component.parts.begin(),part);
                for(auto* member:component.parts)membership.emplace(member->id,index);
                components.push_back(std::move(component));
            } else index=found->second;
            // Absolute CFrame writes to one rigid component compose to the
            // last requested endpoint pose. Compute its delta once, avoiding
            // repeated traversal and roundoff when many listed parts are welded.
            components[index].anchor=part;components[index].target=target;
        }

        // A non-anchor part in a rigid component is moved by composing a delta
        // with its current pose. If its rotation metadata was never replicated,
        // fail the whole batch before any part is committed (Studio-verified).
        for(const auto& component:components)for(auto* part:component.parts)
            if(part!=component.anchor&&!pivot_frame(w,*part,"CFrame").rotation_known)
                throw std::runtime_error("connected part rotation is unavailable");

        std::vector<EnginePoseWrite> writes;std::vector<Json> entries;size_t bytes=0;
        for(const auto& component:components) {
            CFrameValue delta;
            if(component.parts.size()>1)
                delta=pivot_product(component.target,pivot_inverse(pivot_frame(w,*component.anchor,"CFrame")));
            for(auto* part:component.parts) {
                auto frame=part==component.anchor?component.target:
                    pivot_product(delta,pivot_frame(w,*part,"CFrame"));
                auto before=previous_part_transform(w,*part);
                auto after=part_fields_from_frame(pivot_encode(frame));
                if(before==after)continue;
                for(auto it=after.begin();it!=after.end();++it) {
                    Json entry{{"kind","set"},{"id",part->id},{"property",it.key()},{"value",it.value()}};
                    const size_t size=entry.dump().size();
                    if(entries.size()>=kMaxMutations-w.mutations.size()||
                            size>kMaxMutationBytes-w.mutation_bytes-bytes)
                        throw std::runtime_error("local mutation output limit exceeded");
                    bytes+=size;entries.push_back(std::move(entry));
                }
                writes.push_back({part,std::move(before),std::move(after)});
            }
        }
        check_mutation_budget(w,entries);
        for(const auto& write:writes)
            for(auto it=write.after.begin();it!=write.after.end();++it)w.local_properties[write.node->id][it.key()]=it.value();
        append_mutations(w,std::move(entries));
        for(const auto& write:writes) {
            if(mode==0)part_transform_events(w,*write.node,write.before,write.after);
            else if(!write.before.contains("CFrame")||write.before["CFrame"]!=write.after["CFrame"])
                property_events(w,*write.node,"CFrame");
        }
        return 0;
    }catch(const std::exception& e){return luaL_error(L,"BulkMoveTo: %s",e.what()),0;}
}
