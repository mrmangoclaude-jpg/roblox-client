std::string hidden_property_name(const Node& n,const std::string& key) {
    if(n.class_name=="Fire"&&key=="size_xml")return "Size";
    if(n.class_name=="Humanoid"&&key=="Health_XML")return "Health";
    return key;
}
bool reflected_hidden_property(World& w,const Node& n,const std::string& key) {
    // Protected script text is transported as a shared string, but Source is
    // a reflected script property. Its transport type is not a hidden flag.
    if(key=="Source"&&(n.class_name=="Script"||n.class_name=="LocalScript"||n.class_name=="ModuleScript"))return false;
    if((key=="formFactorRaw"||key=="isPlayerScript")&&property_descriptor(n,key))return true;
    if(hidden_property_name(n,key)!=key||key=="Tags"||key=="NetworkOwnerV3"||key=="DefinesCapabilities")return true;
    if(const Json* descriptor=property_descriptor(n,key)) {
        const auto type=descriptor->value("engine_type","");
        if(type=="BinaryString"||type=="SharedString"||type=="SystemAddress")return true;
    }
    auto cls=w.class_property_types.find(n.class_name);
    if(cls!=w.class_property_types.end()&&cls->is_object()) {
        auto type=cls->find(key);
        if(type!=cls->end()&&type->is_number_integer()) {
            int id=type->get<int>();return id==8||id==46||id==47;
        }
    }
    return false;
}
void enforce_scriptability(lua_State* L,World& w,Node& n,std::string& key) {
    bool readable=!reflected_hidden_property(w,n,key);
    auto node=w.scriptability.find(n.id);if(node!=w.scriptability.end()){auto field=node->second.find(key);if(field!=node->second.end())readable=field->second;}
    if(!readable)luaL_error(L,"property is not scriptable");
    key=hidden_property_name(n,key);
}
int compat_property(lua_State* L) {
    auto* h=checked_handle(L,1);std::string key=luaL_checkstring(L,2);int operation=lua_tointeger(L,lua_upvalueindex(1));
    bool hidden=reflected_hidden_property(*h->world,*h->node,key);std::string canonical=hidden_property_name(*h->node,key);
    if(canonical!="Tags"&&canonical!="Name"&&canonical!="Parent"&&canonical!="ClassName"&&!property_descriptor(*h->node,canonical)&&!h->node->properties.contains(canonical)){
        if(operation==2||operation==3){if(operation==3)luaL_checktype(L,3,LUA_TBOOLEAN);lua_pushnil(L);return 1;}
        luaL_error(L,"unknown property");return 0;
    }
    auto& fields=h->world->scriptability[h->node->id];auto field=fields.find(key);bool previous=field==fields.end()?!hidden:field->second;
    if(operation==2){lua_pushboolean(L,previous);return 1;}
    if(operation==3){luaL_checktype(L,3,LUA_TBOOLEAN);fields[key]=lua_toboolean(L,3);lua_pushboolean(L,previous);return 1;}
    // A separate native accessor path leaves per-instance scriptability intact.
    lua_pushboolean(L,true);lua_pushcclosurek(L,operation==0?instance_index:instance_newindex,"property access",1,nullptr);lua_pushvalue(L,1);lua_pushlstring(L,canonical.data(),canonical.size());if(operation==1)lua_pushvalue(L,3);
    int result=lua_pcall(L,operation==0?2:3,operation==0?1:0,0);
    if(result!=LUA_OK){lua_error(L);return 0;}
    lua_pushboolean(L,hidden);return operation==0?2:1;
}
int compat_fps(lua_State* L) {
    auto* w=static_cast<World*>(lua_touserdata(L,lua_upvalueindex(1)));double value=luaL_checknumber(L,1);
    if(!std::isfinite(value)||value<0||value>1000){luaL_error(L,"frame cap must be 0..1000");return 0;}w->render_cap=value;return 0;
}
int compat_scriptbytes(lua_State* L) {
    auto* h=checked_handle(L,1);if(h->node->class_name!="ModuleScript"&&h->node->class_name!="LocalScript"&&h->node->class_name!="Script"){luaL_error(L,"script Instance required");return 0;}
    try {
        const Json* code=&h->node->script_code;
        if(!code->is_object()&&!h->node->script_origin.empty()){auto* origin=find_node(*h->world,h->node->script_origin);if(origin)code=&origin->script_code;}
        if(!code->is_object())throw std::runtime_error("script code is unavailable");
        std::string bytes;
        if(code->contains("source"))bytes=Luau::compile(code->at("source").get<std::string>());
        else if(code->contains("bytecode_hex")){
            const auto& hex=code->at("bytecode_hex").get_ref<const std::string&>();
            auto nib=[](char c){return c>='0'&&c<='9'?c-'0':c>='a'&&c<='f'?c-'a'+10:c>='A'&&c<='F'?c-'A'+10:-1;};
            if(hex.size()%2)throw std::runtime_error("invalid bytecode encoding");
            for(size_t i=0;i<hex.size();i+=2){int a=nib(hex[i]),b=nib(hex[i+1]);if(a<0||b<0)throw std::runtime_error("invalid bytecode encoding");bytes+=char(a*16+b);}
        }else throw std::runtime_error("script code is unavailable");
        if(lua_toboolean(L,lua_upvalueindex(1)))bytes=source_crypto::hex(source_crypto::sha256(bytes));
        lua_pushlstring(L,bytes.data(),bytes.size());return 1;
    }catch(const std::exception& e){luaL_error(L,"script code: %s",e.what());return 0;}
}
int compat_namecall_continue(lua_State* L,int status){if(status!=LUA_OK){lua_error(L);return 0;}return lua_gettop(L);}
int compat_namecall(lua_State* L) {
    const char* method=lua_namecallatom(L,nullptr);if(!method){luaL_error(L,"missing namecall method");return 0;}
    int arguments=lua_gettop(L);lua_pushcfunction(L,instance_index,"Instance.__index");lua_pushvalue(L,1);lua_pushstring(L,method);lua_call(L,2,1);
    if(!lua_isfunction(L,-1)){luaL_error(L,"Instance member is not callable");return 0;}
    lua_insert(L,1);return lua_callyieldable(L,arguments,LUA_MULTRET);
}
int compat_checkcaller(lua_State* L){auto* w=static_cast<World*>(lua_touserdata(L,lua_upvalueindex(1)));lua_pushboolean(L,!w->scheduler||w->scheduler->owner(L).empty());return 1;}
int compat_push_thread_script(lua_State* L,World* w,lua_State* thread) {
    const auto owner=w->scheduler?w->scheduler->owner(thread):std::string();
    const bool script=owner.compare(0,7,"script:")==0,module=owner.compare(0,7,"module:")==0;
    auto* node=(script||module)?find_node(*w,owner.substr(7)):nullptr;
    // Destroy removes hierarchy membership; it does not collect a script
    // whose userdata is still alive. The owner identifier holds no Lua ref.
    if(node&&(node->class_name=="Script"||node->class_name=="LocalScript"||node->class_name=="ModuleScript"))
        push_node(L,*w,node);
    else lua_pushnil(L);
    return 1;
}
int compat_callingscript(lua_State* L) {
    return compat_push_thread_script(L,static_cast<World*>(lua_touserdata(L,lua_upvalueindex(1))),L);
}
int compat_scriptfromthread(lua_State* L) {
    luaL_checktype(L,1,LUA_TTHREAD);
    return compat_push_thread_script(L,static_cast<World*>(lua_touserdata(L,lua_upvalueindex(1))),lua_tothread(L,1));
}
int compat_active(lua_State* L){lua_pushboolean(L,true);return 1;} // An attached session is active; env probes hash isrbxactive()==true.
int compat_hui(lua_State* L) {
    auto* w=static_cast<World*>(lua_touserdata(L,lua_upvalueindex(1)));
    lua_getfield(L,LUA_REGISTRYINDEX,"Headless.OverlayRoot");
    if(has_meta(L,-1,kInstanceMeta)&&!checked_handle(L,-1)->node->destroyed)return 1;
    lua_pop(L,1);
    // A separate local display surface. It is not a descendant of game.CoreGui
    // and never changes that tree's membership signals.
    lua_pushlightuserdata(L,w);lua_pushcclosurek(L,instance_new,"Instance.new",1,nullptr);lua_pushliteral(L,"Folder");lua_call(L,1,1);
    auto* root=checked_handle(L,-1)->node;w->overlay_root=root->id;root->name="RuntimeOverlay";
    lua_pushvalue(L,-1);lua_setfield(L,LUA_REGISTRYINDEX,"Headless.OverlayRoot");return 1;
}
int compat_connection_toggle(lua_State* L) {
    auto* c=static_cast<ConnectionHandle*>(luaL_checkudata(L,1,kConnectionMeta))->connection;
    bool enable=lua_toboolean(L,lua_upvalueindex(1));
    if(!c->auto_disconnected&&!c->manually_disconnected)c->connected=enable;return 0;
}
int compat_connection_fire(lua_State* L) {
    auto* c=static_cast<ConnectionHandle*>(luaL_checkudata(L,1,kConnectionMeta))->connection;
    if(!c->connected||c->signal->node->destroyed)return 0;
    auto* scheduler=c->signal->world->scheduler;if(!scheduler){luaL_error(L,"connection dispatch requires a scheduler");return 0;}
    int count=lua_gettop(L)-1;
    auto arguments=[&](lua_State* target){for(int i=0;i<count;++i)lua_pushvalue(L,i+2);if(target!=L)lua_xmove(L,target,count);return count;};
    if(lua_toboolean(L,lua_upvalueindex(1)))
        scheduler->callback(L,c->callback,arguments,[c](){return c->connected&&!c->signal->node->destroyed;},c->owner,c->identity);
    else {scheduler->callback_now(L,c->callback,arguments,c->owner,c->identity);lua_pop(L,1);}
    return 0;
}
int compat_firesignal(lua_State* L) {
    auto* signal=static_cast<SignalHandle*>(luaL_checkudata(L,1,kSignalMeta))->signal;
    if(signal->node->destroyed)return 0;
    auto& w=*signal->world;auto* scheduler=w.scheduler;
    if(!scheduler)return luaL_error(L,"signal dispatch requires a scheduler"),0;
    const int count=lua_gettop(L)-1;
    auto arguments=[&](lua_State* target){for(int i=0;i<count;++i)lua_pushvalue(L,i+2);if(target!=L)lua_xmove(L,target,count);return count;};
    // Callbacks may connect/disconnect/reenter; iterate the initial membership.
    std::vector<Connection*> callbacks;
    for(auto& c:w.connections)if(c->signal==signal&&c->connected&&(!c->once||!c->once_pending))callbacks.push_back(c.get());
    auto waiting=std::move(w.waiters[signal]);w.waiters[signal].clear();
    for(auto* c:callbacks) {
        if(!c->connected||signal->node->destroyed||(c->once&&c->once_pending))continue;
        if(c->once){c->once_pending=true;c->connected=false;c->auto_disconnected=true;}
        scheduler->callback_now(L,c->callback,arguments,c->owner,c->identity);lua_pop(L,1);
    }
    for(auto waiter:waiting){scheduler->wake_signal(waiter.thread,arguments);lua_unref(L,waiter.reference);}
    return 0;
}
bool reflected_argument_matches(const Json& value,int type) {
    if(type==0||type==3)return value.is_null();
    if(type==2||type==8||type==33)return value.is_string()||(value.is_object()&&value.contains("$bytes_hex"));
    if(type==9)return value.is_boolean();
    if(type==7)return value.is_object()&&value.contains("$enum");
    if(type==10||type==11||type==12) {
        if(!value.is_number()||!std::isfinite(value.get<double>()))return false;
        double number=value.get<double>();
        if(type==10)return number==std::trunc(number)&&number>=INT32_MIN&&number<=INT32_MAX;
        return type==12||std::abs(number)<=std::numeric_limits<float>::max();
    }
    if(type==28||type==69)return value.is_null()||(value.is_object()&&value.contains("$ref"));
    const char* tag=nullptr;
    switch(type) {
        case 13:tag="$udim";break;case 14:tag="$udim2";break;case 18:tag="$brickcolor";break;
        case 19:tag="$color3";break;case 21:tag="$vector2";break;case 22:tag="$vector3";break;
        case 27:tag="$cframe";break;case 29:case 30:tag="$remote_array";break;
        case 31:case 32:tag="$remote_map";break;case 37:tag="$number_range";break;
        case 40:tag="$rect";break;case 48:tag="$datetime";break;case 56:tag="$buffer_hex";break;
        default:return false;
    }
    return value.is_object()&&value.contains(tag);
}
void enqueue_reflected_signal(World& w,Node& node,const std::string& name,Json values) {
    if(!w.persistent||node.destroyed||!node.server_owned)
        throw std::runtime_error("received signal in a persistent session required");
    auto cls=w.class_event_signatures.find(node.class_name);
    if(cls==w.class_event_signatures.end()||!cls->contains(name))
        throw std::runtime_error("signal has no received replication signature");
    const auto& types=cls->at(name);
    if(values.size()!=types.size())throw std::runtime_error("signal argument count does not match received signature");
    for(size_t i=0;i<types.size();++i) {
        int type=types[i].get<int>();
        if(!reflected_argument_matches(values[i],type))
            throw std::runtime_error("signal argument datatype does not match received signature");
        if((type==28||type==69)&&values[i].is_null())values[i]=Json{{"$ref",nullptr}};
    }
    Json event{{"node",node.id},{"event",name},{"argument_types",types},{"arguments",std::move(values)}};
    const auto size=event.dump().size();
    if(w.remote_server_events.size()>=64||size>128*1024||w.remote_server_event_bytes+size>256*1024)
        throw std::runtime_error("signal replication queue limit exceeded");
    w.remote_server_events.push_back(std::move(event));w.remote_server_event_bytes+=size;
}
int compat_replicatesignal(lua_State* L) {
    auto* signal=static_cast<SignalHandle*>(luaL_checkudata(L,1,kSignalMeta))->signal;
    auto& w=*signal->world;
    try {
        Json values=Json::array();size_t bytes=65536,items=10000;std::unordered_set<const void*> path;
        if(lua_gettop(L)>257)throw std::runtime_error("signal argument count exceeds limit");
        for(int i=2;i<=lua_gettop(L);++i) {
            Json value;
            auto cls=w.class_event_signatures.find(signal->node->class_name);
            if(cls!=w.class_event_signatures.end()&&cls->contains(signal->key)) {
                const auto& signature=cls->at(signal->key);
                if(size_t(i-2)<signature.size()&&signature[i-2]==10&&lua_type(L,i)==LUA_TNUMBER) {
                    // Reflection reads an engine int through Luau's numeric
                    // conversion; wire serialization still receives int32.
                    values.push_back(lua_tointeger(L,i));continue;
                }
            }
            if(capture_ussi_export_enum(L,i,value)||capture_geometry_enum(L,i,value))values.push_back(std::move(value));
            else values.push_back(capture_remote_value(L,w,i,bytes,items,path));
        }
        enqueue_reflected_signal(w,*signal->node,signal->key,std::move(values));
    }catch(const std::exception& error){luaL_error(L,"replicatesignal failed: %s",error.what());}
    return 0;
}
bool connection_compat_index(lua_State* L,Connection& c,const char* key) {
    if(std::strcmp(key,"Enabled")==0)lua_pushboolean(L,c.connected);
    else if(std::strcmp(key,"ForeignState")==0)lua_pushboolean(L,false);
    else if(std::strcmp(key,"LuaConnection")==0){lua_getref(L,c.callback);lua_pushboolean(L,lua_isLfunction(L,-1));}
    else if(std::strcmp(key,"Function")==0)lua_getref(L,c.callback);
    else if(std::strcmp(key,"Thread")==0)lua_getref(L,c.creator_ref);
    else if(std::strcmp(key,"Enable")==0||std::strcmp(key,"Disable")==0){lua_pushboolean(L,std::strcmp(key,"Enable")==0);lua_pushcclosurek(L,compat_connection_toggle,key,1,nullptr);}
    else if(std::strcmp(key,"Fire")==0||std::strcmp(key,"Defer")==0){lua_pushboolean(L,std::strcmp(key,"Defer")==0);lua_pushcclosurek(L,compat_connection_fire,key,1,nullptr);}
    else return false;return true;
}
int compat_connections(lua_State* L) {
    auto* signal=static_cast<SignalHandle*>(luaL_checkudata(L,1,kSignalMeta))->signal;
    // Native signal subscriptions are linked at the head. Enumeration must
    // retain newest-first order, including the actual creating coroutine.
    lua_newtable(L);int count=0;for(auto it=signal->world->connections.rbegin();it!=signal->world->connections.rend();++it){auto& c=*it;if(c->signal!=signal||c->auto_disconnected||c->manually_disconnected)continue;
        auto* value=static_cast<ConnectionHandle*>(lua_newuserdatatagged(L,sizeof(ConnectionHandle),0));value->connection=c.get();luaL_getmetatable(L,kConnectionMeta);lua_setmetatable(L,-2);lua_rawseti(L,-2,++count);
    }return 1;
}
int compat_cloneref(lua_State* L) {
    auto* original=checked_handle(L,1);
    auto* copy=static_cast<Handle*>(lua_newuserdatatagged(L,sizeof(Handle),0));*copy=*original;
    luaL_getmetatable(L,kInstanceMeta);lua_setmetatable(L,-2);return 1;
}
int compat_compareinstances(lua_State* L) {
    auto* a=checked_handle(L,1);auto* b=checked_handle(L,2);
    lua_pushboolean(L,a->world==b->world&&a->node==b->node);return 1;
}
int compat_cache_invalidate(lua_State* L) {
    auto* h=checked_handle(L,1);push_instance_cache(L);lua_pushlightuserdata(L,h->node);lua_pushnil(L);lua_rawset(L,-3);return 0;
}
int compat_cache_iscached(lua_State* L) {
    auto* h=checked_handle(L,1);push_instance_cache(L);lua_pushlightuserdata(L,h->node);lua_rawget(L,-2);lua_pushboolean(L,!lua_isnil(L,-1));return 1;
}
int compat_cache_replace(lua_State* L) {
    auto* h=checked_handle(L,1);auto* replacement=checked_handle(L,2);
    if(h->world!=replacement->world){luaL_error(L,"replacement must belong to the same world");return 0;}
    push_instance_cache(L);lua_pushlightuserdata(L,h->node);lua_pushvalue(L,2);lua_rawset(L,-3);return 0;
}
int compat_instances(lua_State* L) {
    auto* w=static_cast<World*>(lua_touserdata(L,lua_upvalueindex(1)));int mode=lua_tointeger(L,lua_upvalueindex(2));
    lua_newtable(L);int count=0;
    for(const auto& id:w->order){auto& n=w->nodes.at(id);if(n.destroyed)continue;
        if(mode==1&&!parent_id(*w,n).empty())continue;
        if(mode==2&&n.class_name!="ModuleScript"&&n.class_name!="LocalScript"&&n.class_name!="Script")continue;
        push_node(L,*w,&n);lua_rawseti(L,-2,++count);
    }return 1;
}
int compat_callback(lua_State* L) {
    auto* h=checked_handle(L,1);std::string name=luaL_checkstring(L,2);
    if(!((h->node->class_name=="BindableFunction"&&name=="OnInvoke")||
         (h->node->class_name=="RemoteFunction"&&name=="OnClientInvoke"))){luaL_error(L,"unsupported callback property");return 0;}
    auto it=h->world->bindable_callbacks.find(h->node->id);
    if(it==h->world->bindable_callbacks.end())lua_pushnil(L);else lua_getref(L,it->second.reference);return 1;
}
int compat_fireclick(lua_State* L) {
    auto* h=checked_handle(L,1);if(h->node->class_name!="ClickDetector"||h->node->destroyed){luaL_error(L,"live ClickDetector required");return 0;}
    double distance=luaL_optnumber(L,2,0);if(!std::isfinite(distance)||distance<0){luaL_error(L,"distance must be finite and nonnegative");return 0;}
    std::string event=luaL_optstring(L,3,"MouseClick");
    if(event!="MouseClick"&&event!="RightMouseClick"&&event!="MouseHoverEnter"&&event!="MouseHoverLeave"){luaL_error(L,"invalid ClickDetector event");return 0;}
    Json player=h->world->local_player.empty()?Json(nullptr):Json{{"$ref",h->world->local_player}};
    if(h->node->server_owned&&h->world->persistent) {
        // Documented reflected left-click action; other action numbers have
        // not been established for this client revision.
        if(event!="MouseClick")return luaL_error(L,"server ClickDetector action is not implemented for this event"),0;
        try {enqueue_reflected_signal(*h->world,*h->node,"MouseActionReplicated",Json::array({player,0}));}
        catch(const std::exception& error){return luaL_error(L,"fireclickdetector failed: %s",error.what()),0;}
    }
    emit(*h->world,*h->node,event,Json::array({player}));return 0;
}
void install_instance_compat(lua_State* L,World& w) {
    lua_pushcfunction(L,compat_replicatesignal,"replicatesignal");lua_setglobal(L,"replicatesignal");
    for(auto item:{std::pair<const char*,lua_CFunction>{"cloneref",compat_cloneref},{"compareinstances",compat_compareinstances},{"getcallbackvalue",compat_callback},{"fireclickdetector",compat_fireclick},{"firesignal",compat_firesignal},{"getconnections",compat_connections},{"isrbxactive",compat_active},{"isgameactive",compat_active}}){lua_pushcfunction(L,item.second,item.first);lua_setglobal(L,item.first);}
    for(auto item:{std::pair<const char*,lua_CFunction>{"checkcaller",compat_checkcaller},{"gethui",compat_hui},{"setfpscap",compat_fps}}){lua_pushlightuserdata(L,&w);lua_pushcclosurek(L,item.second,item.first,1,nullptr);lua_setglobal(L,item.first);}
    lua_pushlightuserdata(L,&w);lua_pushcclosurek(L,compat_callingscript,"getcallingscript",1,nullptr);
    lua_pushvalue(L,-1);lua_setglobal(L,"getcallingscript");lua_setglobal(L,"getcaller");
    lua_pushlightuserdata(L,&w);lua_pushcclosurek(L,compat_scriptfromthread,"getscriptfromthread",1,nullptr);
    lua_pushvalue(L,-1);lua_setglobal(L,"getscriptfromthread");
    lua_setfield(L,LUA_REGISTRYINDEX,"Headless.ScriptFromThread");
    const char* properties[]={"gethiddenproperty","sethiddenproperty","isscriptable","setscriptable"};
    for(int i=0;i<4;++i){lua_pushinteger(L,i);lua_pushcclosurek(L,compat_property,properties[i],1,nullptr);lua_setglobal(L,properties[i]);}
    for(auto name:{"getscriptbytecode","dumpstring","getscripthash"}){lua_pushboolean(L,std::strcmp(name,"getscripthash")==0);lua_pushcclosurek(L,compat_scriptbytes,name,1,nullptr);lua_setglobal(L,name);}
    lua_newtable(L);for(auto item:{std::pair<const char*,lua_CFunction>{"invalidate",compat_cache_invalidate},{"iscached",compat_cache_iscached},{"replace",compat_cache_replace}}){lua_pushcfunction(L,item.second,item.first);lua_setfield(L,-2,item.first);}lua_setglobal(L,"cache");
    const char* names[]={"getinstances","getnilinstances","getscripts"};
    for(int mode=0;mode<3;++mode){lua_pushlightuserdata(L,&w);lua_pushinteger(L,mode);lua_pushcclosurek(L,compat_instances,names[mode],2,nullptr);lua_setglobal(L,names[mode]);}
}
