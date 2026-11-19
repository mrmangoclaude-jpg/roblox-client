constexpr const char* kInstanceExtendedThreadStore = "Headless.InstanceExtended.CallbackThreads";
constexpr int kInstanceExtendedMaxCallbackThreads = 2048;

Handle* instance_extended_callback_handle(lua_State* L) {
    auto* handle=checked_handle(L,1);
    size_t size=0;const char* name=luaL_checklstring(L,2,&size);
    if(!((handle->node->class_name=="BindableFunction"&&size==8&&std::memcmp(name,"OnInvoke",8)==0)||
         (handle->node->class_name=="RemoteFunction"&&size==14&&std::memcmp(name,"OnClientInvoke",14)==0))) {
        luaL_error(L,"unsupported callback property");return nullptr;
    }
    return handle;
}

int instance_extended_set_callback(lua_State* L) {
    auto* handle=instance_extended_callback_handle(L);
    luaL_checktype(L,3,LUA_TFUNCTION);
    try{set_bindable_callback(L,*handle->world,*handle->node);}
    catch(const std::exception& error){luaL_error(L,"callback write failed: %s",error.what());}
    return 0;
}

int instance_extended_get_callback(lua_State* L) {
    auto* handle=instance_extended_callback_handle(L);
    auto callback=handle->world->bindable_callbacks.find(handle->node->id);
    if(callback==handle->world->bindable_callbacks.end())lua_pushnil(L);
    else lua_getref(L,callback->second.reference);
    return 1;
}

void instance_extended_push_thread_store(lua_State* L,World& world) {
    lua_getfield(L,LUA_REGISTRYINDEX,kInstanceExtendedThreadStore);
    lua_pushlightuserdata(L,&world);lua_rawget(L,-2);
    if(!lua_istable(L,-1)) {
        lua_pop(L,1);lua_newtable(L);
        lua_pushlightuserdata(L,&world);lua_pushvalue(L,-2);lua_rawset(L,-4);
    }
    lua_remove(L,-2);
}

int instance_extended_set_callback_thread(lua_State* L) {
    auto* handle=instance_extended_callback_handle(L);
    luaL_checktype(L,3,LUA_TTHREAD);
    instance_extended_push_thread_store(L,*handle->world);
    int store=lua_gettop(L);
    lua_pushlightuserdata(L,handle->node);lua_rawget(L,store);
    bool exists=!lua_isnil(L,-1);lua_pop(L,1);
    if(!exists) {
        lua_getfield(L,store,"count");int count=lua_tointeger(L,-1);lua_pop(L,1);
        if(count>=kInstanceExtendedMaxCallbackThreads){luaL_error(L,"callback thread limit exceeded");return 0;}
        lua_pushinteger(L,count+1);lua_setfield(L,store,"count");
    }
    lua_pushlightuserdata(L,handle->node);lua_pushvalue(L,3);lua_rawset(L,store);
    return 0;
}

int instance_extended_get_callback_thread(lua_State* L) {
    auto* handle=instance_extended_callback_handle(L);
    instance_extended_push_thread_store(L,*handle->world);
    lua_pushlightuserdata(L,handle->node);lua_rawget(L,-2);
    if(!lua_isthread(L,-1)){lua_pop(L,1);lua_pushnil(L);}
    return 1;
}

int instance_extended_fire_proximity_prompt(lua_State* L) {
    auto* handle=checked_handle(L,1);
    if(handle->node->class_name!="ProximityPrompt"||handle->node->destroyed) {
        luaL_error(L,"live ProximityPrompt required");return 0;
    }
    Json player=handle->world->local_player.empty()?Json(nullptr):Json{{"$ref",handle->world->local_player}};
    if(handle->node->server_owned&&handle->world->persistent) {
        try {enqueue_reflected_signal(*handle->world,*handle->node,"TriggeredActionReplicated",Json::array({player}));}
        catch(const std::exception& error){return luaL_error(L,"fireproximityprompt failed: %s",error.what()),0;}
    }
    emit(*handle->world,*handle->node,"Triggered",Json::array({player}));
    return 0;
}

int instance_extended_fire_touch(lua_State* L) {
    auto* part=checked_handle(L,1);auto* other=checked_handle(L,2);
    if(!class_is_a(*part->world,part->node->class_name,"BasePart")||part->node->destroyed) {
        luaL_error(L,"first argument must be a live BasePart");return 0;
    }
    if(part->world!=other->world) {
        luaL_error(L,"touch participants must belong to the same world");return 0;
    }
    if(!class_is_a(*other->world,other->node->class_name,"BasePart")||other->node->destroyed) {
        luaL_error(L,"second argument must be a live BasePart");return 0;
    }
    int state=0;
    if(lua_type(L,3)==LUA_TBOOLEAN)state=lua_toboolean(L,3)?0:1;
    else {
        double value=luaL_checknumber(L,3);
        if(!std::isfinite(value)||(value!=0&&value!=1)) {
            luaL_error(L,"touch state must be 0, 1, or a boolean");return 0;
        }
        state=static_cast<int>(value);
    }
    const char* event=state==0?"Touched":"TouchEnded";
    auto& w=*part->world;
    if(part->node==other->node)return 0;
    if(w.persistent&&part->node->server_owned&&other->node->server_owned) {
        // Explicit API request, distinct from contacts observed by the local
        // solver. The session adapter verifies current received ownership.
        Json request{{"touch",{{"first",part->node->id},{"second",other->node->id},{"began",state==0}}}};
        auto size=request.dump().size();
        if(w.remote_server_events.size()>=64||w.remote_server_event_bytes+size>256*1024)
            return luaL_error(L,"touch replication queue limit exceeded"),0;
        w.remote_server_events.push_back(std::move(request));w.remote_server_event_bytes+=size;
    }
    emit(*part->world,*part->node,event,Json::array({Json{{"$ref",other->node->id}}}));
    if(part->node!=other->node)
        emit(*other->world,*other->node,event,Json::array({Json{{"$ref",part->node->id}}}));
    return 0;
}

int instance_extended_is_hidden_property(lua_State* L) {
    auto* handle=checked_handle(L,1);
    size_t size=0;const char* raw=luaL_checklstring(L,2,&size);std::string key(raw,size);
    std::string canonical=hidden_property_name(*handle->node,key);
    const Json* descriptor=property_descriptor(*handle->node,canonical);
    if(canonical!="Tags"&&canonical!="Name"&&canonical!="Parent"&&canonical!="ClassName"&&!descriptor&&
       !handle->node->properties.contains(canonical)) {
        luaL_error(L,"unknown property");return 0;
    }
    bool hidden=reflected_hidden_property(*handle->world,*handle->node,key);
    if(descriptor) {
        const std::string type=descriptor->value("engine_type","");
        hidden=hidden||type=="BinaryString"||type=="SharedString"||type=="SystemAddress";
    }
    lua_pushboolean(L,hidden);return 1;
}

int instance_extended_instance_cache(lua_State* L) {
    auto* world=static_cast<World*>(lua_touserdata(L,lua_upvalueindex(1)));
    lua_newtable(L);int count=0;
    for(const auto& id:world->order) {
        Node& node=world->nodes.at(id);
        push_instance_cache(L);lua_pushlightuserdata(L,&node);lua_rawget(L,-2);lua_remove(L,-2);
        if(!lua_isnil(L,-1))lua_rawseti(L,-2,++count);else lua_pop(L,1);
    }
    return 1;
}

int instance_extended_hidden_gui(lua_State* L) {
    auto* world=static_cast<World*>(lua_touserdata(L,lua_upvalueindex(1)));
    lua_getfield(L,LUA_REGISTRYINDEX,"Headless.OverlayRoot");
    if(has_meta(L,-1,kInstanceMeta)&&!checked_handle(L,-1)->node->destroyed)return 1;
    lua_pop(L,1);auto* core=ensure_client_service(*world,"CoreGui");
    lua_pushlightuserdata(L,world);lua_pushcclosurek(L,instance_new,"new",1,nullptr);
    lua_pushliteral(L,"ScreenGui");push_node(L,*world,core);lua_call(L,2,1);
    lua_pushvalue(L,-1);lua_setfield(L,LUA_REGISTRYINDEX,"Headless.OverlayRoot");
    return 1;
}

int instance_extended_network_owner(lua_State* L) {
    auto* handle=checked_handle(L,1);
    if(!class_is_a(*handle->world,handle->node->class_name,"BasePart")||handle->node->destroyed) {
        luaL_error(L,"live BasePart required");return 0;
    }
    auto value=handle->node->properties.find("NetworkOwnerV3");
    if(value==handle->node->properties.end()) {
        luaL_error(L,"NetworkOwnerV3 is unavailable in this snapshot");return 0;
    }
    try {
        double peer=json_number(*value);
        if(!std::isfinite(peer)||std::floor(peer)!=peer)throw std::runtime_error("invalid NetworkOwnerV3 value");
        lua_pushboolean(L,peer>=4);return 1;
    }catch(const std::exception& error){luaL_error(L,"network owner unavailable: %s",error.what());return 0;}
}

int instance_extended_simulation_radius(lua_State* L) {
    auto* world=static_cast<World*>(lua_touserdata(L,lua_upvalueindex(1)));
    Node* player=find_node(*world,world->local_player);
    if(!player){luaL_error(L,"LocalPlayer is unavailable in this snapshot");return 0;}
    auto value=player->properties.find("SimulationRadius");
    if(value==player->properties.end()) {
        luaL_error(L,"SimulationRadius is unavailable in this snapshot");return 0;
    }
    try {
        double radius=json_number(*value);
        if(!std::isfinite(radius))throw std::runtime_error("invalid SimulationRadius value");
        lua_pushnumber(L,radius);return 1;
    }catch(const std::exception& error){luaL_error(L,"simulation radius unavailable: %s",error.what());return 0;}
}

int instance_extended_clone_reference(lua_State* L) {
    auto* original=checked_handle(L,1);
    auto* copy=static_cast<Handle*>(lua_newuserdatatagged(L,sizeof(Handle),0));*copy=*original;
    luaL_getmetatable(L,kInstanceMeta);lua_setmetatable(L,-2);return 1;
}

void install_instance_extended(lua_State* L,World& world) {
    lua_getfield(L,LUA_REGISTRYINDEX,kInstanceExtendedThreadStore);
    if(!lua_istable(L,-1)) {
        lua_pop(L,1);lua_newtable(L);lua_pushvalue(L,-1);
        lua_setfield(L,LUA_REGISTRYINDEX,kInstanceExtendedThreadStore);
    }
    lua_pop(L,1);
    for(auto item:std::initializer_list<std::pair<const char*,lua_CFunction>>{
        {"setcallbackvalue",instance_extended_set_callback},
        {"setcallbackfunction",instance_extended_set_callback},
        {"setcallbackmember",instance_extended_set_callback},
        {"setcallbackthread",instance_extended_set_callback_thread},
        {"getcallbackthread",instance_extended_get_callback_thread},
        {"getcallbackfunction",instance_extended_get_callback},
        {"getcallbackmember",instance_extended_get_callback},
        {"fireproximityprompt",instance_extended_fire_proximity_prompt},
        {"firetouchinterest",instance_extended_fire_touch},
        {"firetouchtransmitter",instance_extended_fire_touch},
        {"ishiddenproperty",instance_extended_is_hidden_property},
        {"getnetworkowner",instance_extended_network_owner},
        {"isnetworkowner",instance_extended_network_owner},
        {"clonereference",instance_extended_clone_reference}}) {
        lua_pushcfunction(L,item.second,item.first);lua_setglobal(L,item.first);
    }
    for(auto item:std::initializer_list<std::pair<const char*,lua_CFunction>>{
        {"getinstancelist",instance_extended_instance_cache},
        {"getinstancecache",instance_extended_instance_cache},
        {"get_hidden_gui",instance_extended_hidden_gui},
        {"getsimulationradius",instance_extended_simulation_radius},
        {"getsimradius",instance_extended_simulation_radius}}) {
        lua_pushlightuserdata(L,&world);lua_pushcclosurek(L,item.second,item.first,1,nullptr);
        lua_setglobal(L,item.first);
    }
}
