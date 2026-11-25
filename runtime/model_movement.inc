// Model movement with the legacy raw-primary/world-axis contracts. These are
// hierarchy operations: each descendant BasePart is transformed exactly once.
// https://create.roblox.com/docs/reference/engine/classes/Model
Node& required_model_primary(World& w,Node& model,bool for_write) {
    auto* part=model_primary(w,model);
    if(!part)throw std::runtime_error("model has no PrimaryPart");
    if(for_write&&!is_descendant_of(w,*part,model.id))
        throw std::runtime_error("PrimaryPart must be inside the model");
    return *part;
}
int model_get_primary_frame(lua_State* L) {
    auto* h=checked_pivot_object(L,true);
    try {
        if(lua_gettop(L)!=1)throw std::runtime_error("expected no arguments");
        auto frame=pivot_frame(*h->world,required_model_primary(*h->world,*h->node,false),"CFrame");
        return push_frame_value(L,frame.p,frame.r);
    }catch(const std::exception& e){return luaL_error(L,"GetPrimaryPartCFrame: %s",e.what()),0;}
}
int model_move_legacy(lua_State* L) {
    auto* h=checked_pivot_object(L,true);
    const bool primary_mode=lua_toboolean(L,lua_upvalueindex(1));
    const char* method=primary_mode?"SetPrimaryPartCFrame":"TranslateBy";
    try {
        if(lua_gettop(L)!=2)throw std::runtime_error("expected one argument");
        auto& w=*h->world;Node* primary=nullptr;CFrameValue delta,target;
        if(primary_mode) {
            if(!has_meta(L,2,kCFrameMeta))throw std::runtime_error("expected a CFrame");
            target=pivot_decode(pivot_encode(*checked_cframe(L,2)));
            primary=&required_model_primary(w,*h->node,true);
            delta=pivot_product(target,pivot_inverse(pivot_frame(w,*primary,"CFrame")));
        } else {
            if(!lua_isvector(L,2))throw std::runtime_error("expected a Vector3");
            const auto* v=lua_tovector(L,2);
            for(int i=0;i<3;++i) {
                if(!std::isfinite(v[i]))throw std::runtime_error("translation must be finite");
                delta.p[i]=v[i];
            }
        }
        auto moved=[&](const CFrameValue& old) {
            if(primary_mode)return pivot_product(delta,old);
            auto result=old;
            for(int i=0;i<3;++i)result.p[i]+=delta.p[i];
            return result;
        };
        std::vector<EnginePoseWrite> writes;std::vector<Json> entries;size_t bytes=0;
        auto stage=[&](Node& n,Json before,Json after) {
            if(before==after)return;
            for(auto it=after.begin();it!=after.end();++it) {
                Json entry{{"kind","set"},{"id",n.id},{"property",it.key()},{"value",it.value()}};
                const size_t size=entry.dump().size();
                if(entries.size()>=kMaxMutations-w.mutations.size()||size>kMaxMutationBytes-w.mutation_bytes-bytes)
                    throw std::runtime_error("local mutation output limit exceeded");
                bytes+=size;entries.push_back(std::move(entry));
            }
            writes.push_back({&n,std::move(before),std::move(after)});
        };
        auto nodes=pivot_descendants(w,*h->node,true);
        // Every descendant must have a complete pose before any write is staged;
        // otherwise a part whose rotation was not replicated would silently be
        // moved with an assumed identity rotation. Fail the whole batch so it
        // stays atomic and retryable once the received state is complete.
        for(auto* node:nodes)if(pivot_part(w,*node)&&node!=primary) {
            auto frame=pivot_frame(w,*node,"CFrame");
            if(!frame.rotation_known)throw std::runtime_error("part rotation is unavailable");
        }
        if(primary) {
            auto frame=pivot_frame(w,*primary,"CFrame");
            if(!frame.rotation_known)throw std::runtime_error("primary part rotation is unavailable");
        }
        for(auto* node:nodes) {
            if(pivot_part(w,*node)) {
                auto frame=node==primary?target:moved(pivot_frame(w,*node,"CFrame"));
                stage(*node,previous_part_transform(w,*node),part_fields_from_frame(pivot_encode(frame)));
            } else if(pivot_model(w,*node)) {
                // Preserve explicit pivots without forcing a bounds calculation.
                // Untouched models continue deriving their pivot from their parts.
                const auto* saved=property_value(w,*node,"WorldPivot");
                if(saved&&(local_value(w,*node,"WorldPivot")||origin(w,*node,"WorldPivot")!="class_default")) {
                    auto frame=pivot_encode(moved(pivot_decode(*saved)));pivot_decode(frame);
                    stage(*node,Json{{"WorldPivot",*saved}},Json{{"WorldPivot",std::move(frame)}});
                }
            }
        }
        check_mutation_budget(w,entries);
        for(const auto& write:writes)
            for(auto it=write.after.begin();it!=write.after.end();++it)w.local_properties[write.node->id][it.key()]=it.value();
        append_mutations(w,std::move(entries));
        for(auto* node:nodes)if(pivot_model(w,*node))w.pivot_caches.erase(node->id);
        for(const auto& write:writes) {
            if(pivot_part(w,*write.node))part_transform_events(w,*write.node,write.before,write.after);
            else property_events(w,*write.node,"WorldPivot");
        }
        return 0;
    }catch(const std::exception& e){return luaL_error(L,"%s: %s",method,e.what()),0;}
}
