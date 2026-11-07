// Small authored-source bindings for local Debris and replicated Players.
// This file is included inside world_bindings' anonymous namespace after
// destroy_roots() is defined. Call client_service_index() from instance_index
// and process_debris() from the persistent world pump.
constexpr size_t kMaxDebrisItems = 1000;

Json validated_session_stats(const Json& value) {
    if(!value.is_object()||value.size()>1)
        throw std::runtime_error("session statistics must be a bounded object");
    for(auto it=value.begin();it!=value.end();++it)
        if(it.key()!="network_rtt_ms"||!it.value().is_number()||
                !std::isfinite(it.value().get<double>())||it.value().get<double>()<0)
            throw std::runtime_error("invalid measured session RTT");
    return value;
}

Node* stats_child(World& world,Node& parent,const std::string& name) {
    for(const auto& id:world.order) {
        auto* node=find_node(world,id);
        if(node&&!node->destroyed&&!node->server_owned&&node->class_name=="StatsItem"&&
                parent_id(world,*node)==parent.id&&instance_name(world,*node)==name)return node;
    }
    if(world.nodes.size()>=kMaxNodes)throw std::runtime_error("world node limit exceeded");
    Node node;do{node.id="local:"+std::to_string(world.next_local_id++);}while(world.nodes.count(node.id));
    node.class_name="StatsItem";node.name=name;node.parent=parent.id;node.server_owned=false;
    node.attributes_known=true;node.collection_tags_known=true;
    node.origins={{"Name","local"},{"ClassName","local"},{"Parent","local"}};
    std::vector<Json> entries{Json{{"kind","create"},{"node",node_record(node)}}};
    check_mutation_budget(world,entries);
    auto& created=world.nodes.emplace(node.id,std::move(node)).first->second;
    world.order.push_back(created.id);append_mutations(world,std::move(entries));
    parent_events(world,created,"",parent.id);return &created;
}

int stats_item_value(lua_State* L) {
    auto* h=checked_handle(L,1);auto& world=*h->world;
    if(h->node->class_name!="StatsItem"||h->node->id!=world.stats_ping_item||
            !world.session_stats.contains("network_rtt_ms")) {
        luaL_error(L,"StatsItem has no measured value in this session");return 0;
    }
    const double value=world.session_stats.at("network_rtt_ms").get<double>();
    if(lua_toboolean(L,lua_upvalueindex(1))) {
        std::ostringstream text;text<<std::fixed<<std::setprecision(3)<<value<<" ms";
        const auto result=text.str();lua_pushlstring(L,result.data(),result.size());
    }else lua_pushnumber(L,value);
    return 1;
}

int test_service_message(lua_State* L) {
    auto* h=checked_handle(L,1);
    if(h->node->class_name!="TestService"){luaL_error(L,"TestService receiver required");return 0;}
    luaL_checktype(L,2,LUA_TSTRING);size_t size=0;const char* text=lua_tolstring(L,2,&size);
    if(!lua_isnoneornil(L,3)) {
        auto* source=checked_handle(L,3);
        if(source->world!=h->world){luaL_error(L,"source belongs to another world");return 0;}
    }
    if(!lua_isnoneornil(L,4))luaL_checkinteger(L,4);
    auto& world=*h->world;
    auto append=[&](const char* data,size_t length) {
        const auto room=world.output.size()<kMaxPrinted?kMaxPrinted-world.output.size():0;
        const auto take=std::min(room,length);world.output.append(data,take);
        if(take<length)world.output_truncated=true;
    };
    append("TestService: ",13);append(text,size);append("\n",1);
    return 0;
}

int player_get_mouse(lua_State* L) {
    auto* h=checked_handle(L,1);auto& world=*h->world;
    if(h->node->class_name!="Player"||h->node->id!=world.local_player||h->node->destroyed) {
        luaL_error(L,"GetMouse requires LocalPlayer");return 0;
    }
    auto found=world.client_services.player_mice.find(h->node->id);
    if(found!=world.client_services.player_mice.end()) {
        auto* mouse=find_node(world,found->second);
        if(mouse&&!mouse->destroyed){push_node(L,world,mouse);return 1;}
    }
    try {
        if(world.nodes.size()>=kMaxNodes)throw std::runtime_error("world node limit exceeded");
        Node node;do{node.id="local:"+std::to_string(world.next_local_id++);}while(world.nodes.count(node.id));
        node.class_name="PlayerMouse";node.name="Mouse";node.server_owned=false;
        node.properties["TargetFilter"]=nullptr;
        node.attributes_known=true;node.collection_tags_known=true;
        node.origins=Json{{"Name","local"},{"ClassName","local"},{"Parent","local"}};
        std::vector<Json> mutations{Json{{"kind","create"},{"node",node_record(node)}}};check_mutation_budget(world,mutations);
        auto inserted=world.nodes.emplace(node.id,std::move(node));auto& mouse=inserted.first->second;
        world.order.push_back(mouse.id);world.client_services.player_mice[h->node->id]=mouse.id;
        append_mutations(world,std::move(mutations));push_node(L,world,&mouse);return 1;
    }catch(const std::exception& e){luaL_error(L,"GetMouse: %s",e.what());return 0;}
}

int player_distance_from_character(lua_State* L) {
    auto* h=checked_handle(L,1);auto& world=*h->world;
    if(h->node->class_name!="Player"){luaL_error(L,"DistanceFromCharacter requires Player");return 0;}
    if(!lua_isvector(L,2)){luaL_argerror(L,2,"Vector3 expected");return 0;}
    const auto* input=lua_tovector(L,2);const double point[3]={input[0],input[1],input[2]};
    const Json* reference=property_value(world,*h->node,"Character");
    if(!reference){luaL_error(L,"Character is unavailable in snapshot");return 0;}
    if(reference->is_null()){lua_pushnumber(L,0);return 1;}
    Node* character=reference->is_object()&&reference->contains("$ref")?find_node(world,reference->at("$ref").get<std::string>()):nullptr;
    Node* root=nullptr;
    if(character) {
        for(const auto& id:direct_children(world,character->id)){auto* node=find_node(world,id);if(node&&!node->destroyed&&instance_name(world,*node)=="HumanoidRootPart"){root=node;break;}}
        if(!root){auto* primary=property_value(world,*character,"PrimaryPart");if(primary&&primary->is_object()&&primary->contains("$ref"))root=find_node(world,primary->at("$ref").get<std::string>());}
    }
    if(!root||!class_is_a(world,root->class_name,"BasePart")){lua_pushnumber(L,0);return 1;}
    lua_pushcfunction(L,instance_index,"Instance.__index");push_node(L,world,root);lua_pushliteral(L,"Position");lua_call(L,2,1);
    const auto* position=lua_tovector(L,-1);if(!position){luaL_error(L,"root Position is unavailable");return 0;}
    double squared=0;for(int i=0;i<3;++i){double d=double(point[i])-position[i];squared+=d*d;}
    lua_pushnumber(L,std::sqrt(squared));return 1;
}

int players_get_players(lua_State* L) {
    Handle* service = checked_handle(L, 1);
    if (service->node->class_name != "Players") {
        luaL_error(L, "GetPlayers requires Players");
        return 0;
    }
    World& world = *service->world;
    int count = 0;
    for (const auto& id : world.order) {
        const Node& node = world.nodes.at(id);
        if (!node.destroyed && node.class_name == "Player"
                && parent_id(world, node) == service->node->id) ++count;
    }
    lua_createtable(L, count, 0);
    int index = 1;
    for (const auto& id : world.order) {
        Node* node = find_node(world, id);
        if (node && !node->destroyed && node->class_name == "Player"
                && parent_id(world, *node) == service->node->id) {
            push_node(L, world, node);
            lua_rawseti(L, -2, index++);
        }
    }
    return 1;
}

int players_get_player_by_user_id(lua_State* L) {
    Handle* service = checked_handle(L, 1);
    if (service->node->class_name != "Players") {
        luaL_error(L, "GetPlayerByUserId requires Players");
        return 0;
    }
    if (!lua_isnumber(L, 2)) {
        luaL_argerror(L, 2, "number expected");
        return 0;
    }
    const double requested = lua_tonumber(L, 2);
    if (!std::isfinite(requested) || std::trunc(requested) != requested) {
        luaL_argerror(L, 2, "finite integer expected");
        return 0;
    }
    World& world = *service->world;
    for (const auto& id : world.order) {
        Node* player = find_node(world, id);
        if (!player || player->destroyed || player->class_name != "Player"
                || parent_id(world, *player) != service->node->id) continue;
        const Json* user_id = property_value(world, *player, "UserId");
        if (user_id && user_id->is_number() && user_id->get<double>() == requested) {
            push_node(L, world, player);
            return 1;
        }
    }
    lua_pushnil(L);
    return 1;
}

int players_get_player_from_character(lua_State* L) {
    Handle* service = checked_handle(L, 1);
    if (service->node->class_name != "Players") {
        luaL_error(L, "GetPlayerFromCharacter requires Players");
        return 0;
    }
    Handle* character = checked_handle(L, 2);
    if (character->world != service->world) {
        luaL_error(L, "character belongs to a different world");
        return 0;
    }
    World& world = *service->world;
    if (!class_is_a(world, character->node->class_name, "Model") || character->node->destroyed) {
        lua_pushnil(L);
        return 1;
    }
    for (const auto& id : world.order) {
        Node* player = find_node(world, id);
        if (!player || player->destroyed || player->class_name != "Player"
                || parent_id(world, *player) != service->node->id) continue;
        const Json* reference = property_value(world, *player, "Character");
        if (reference && reference->is_object() && reference->contains("$ref")
                && (*reference)["$ref"].is_string()
                && (*reference)["$ref"].get_ref<const std::string&>() == character->node->id) {
            push_node(L, world, player);
            return 1;
        }
    }
    lua_pushnil(L);
    return 1;
}

int debris_add_item(lua_State* L) {
    Handle* service = checked_handle(L, 1);
    if (service->node->class_name != "Debris") {
        luaL_error(L, "AddItem requires Debris");
        return 0;
    }
    Handle* item = checked_handle(L, 2);
    if (item->world != service->world) {
        luaL_error(L, "item belongs to a different world");
        return 0;
    }
    double seconds = 10.0;
    if (lua_gettop(L) >= 3) {
        if (!lua_isnumber(L, 3)) {
            luaL_argerror(L, 3, "number expected");
            return 0;
        }
        seconds = lua_tonumber(L, 3);
    }
    if (!std::isfinite(seconds)) {
        luaL_argerror(L, 3, "finite lifetime expected");
        return 0;
    }

    World& world = *service->world;
    if (!item->node->destroyed) {
        // Debris uses a hard queue bound. Adding the 1,001st entry immediately
        // destroys the oldest queued item, then retains the newly submitted one.
        if (world.client_services.debris.size() >= kMaxDebrisItems) {
            const std::string oldest = world.client_services.debris.front().instance_id;
            Node* node = find_node(world, oldest);
            try {
                if (node && !node->destroyed) destroy_roots(world, {oldest});
            } catch (const std::exception& error) {
                luaL_error(L, "Debris:AddItem could not destroy the oldest item: %s", error.what());
                return 0;
            }
            world.client_services.debris.erase(world.client_services.debris.begin());
        }
        const auto now = std::chrono::steady_clock::now();
        // Negative lifetimes expire on the next pump. Clamp finite values to
        // half the remaining clock range so time_point addition cannot wrap.
        const auto remaining = std::chrono::steady_clock::time_point::max() - now;
        const double max_seconds = std::chrono::duration<double>(remaining / 2).count();
        seconds = std::clamp(seconds, 0.0, max_seconds);
        const auto delay = std::chrono::duration_cast<std::chrono::steady_clock::duration>(
            std::chrono::duration<double>(seconds));
        world.client_services.debris.push_back(ScheduledDebrisItem{
            item->node->id, now + delay, world.client_services.next_debris_sequence++});
    }
    return 0;
}

// Call once per persistent world pump. Remove expired, already-destroyed nodes
// from the independent queue, and route live nodes through Instance:Destroy's
// normal event, tombstone and mutation path.
void process_debris(World& world, std::chrono::steady_clock::time_point now) {
    std::vector<std::string> due;
    std::vector<size_t> expired_indices, stale_indices;
    for (size_t i = 0; i < world.client_services.debris.size(); ++i) {
        const auto& entry = world.client_services.debris[i];
        Node* node = find_node(world, entry.instance_id);
        if (!node || node->destroyed) {
            stale_indices.push_back(i);
        } else if (entry.deadline <= now) {
            expired_indices.push_back(i);
            due.push_back(entry.instance_id);
        }
    }
    if (!due.empty()) {
        try {
            destroy_roots(world, due);
        } catch (const std::exception&) {
            // Drop only stale nodes. Keep live, due items queued so the shared
            // Destroy mutation can retry once another pump has budget.
            std::vector<ScheduledDebrisItem> retained;
            retained.reserve(world.client_services.debris.size() - stale_indices.size());
            size_t stale = 0;
            for (size_t i = 0; i < world.client_services.debris.size(); ++i) {
                if (stale < stale_indices.size() && stale_indices[stale] == i) {
                    ++stale;
                    continue;
                }
                retained.push_back(std::move(world.client_services.debris[i]));
            }
            world.client_services.debris = std::move(retained);
            return;
        }
    }
    if (!expired_indices.empty() || !stale_indices.empty()) {
        std::vector<bool> remove(world.client_services.debris.size(), false);
        for (const auto index : expired_indices) remove[index] = true;
        for (const auto index : stale_indices) remove[index] = true;
        std::vector<ScheduledDebrisItem> retained;
        retained.reserve(world.client_services.debris.size()
                         - expired_indices.size() - stale_indices.size());
        for (size_t i = 0; i < world.client_services.debris.size(); ++i) {
            if (remove[i]) continue;
            retained.push_back(std::move(world.client_services.debris[i]));
        }
        world.client_services.debris = std::move(retained);
    }
}

bool client_service_index(lua_State* L, World& world, Node& node, const std::string& key) {
    if(node.class_name=="Stats"&&key=="Network") {
        try {
            auto* network=stats_child(world,node,"Network");
            auto* server=stats_child(world,*network,"ServerStatsItem");
            world.stats_ping_item=stats_child(world,*server,"Data Ping")->id;
            push_node(L,world,network);return true;
        }catch(const std::exception& e){luaL_error(L,"Stats.Network: %s",e.what());return false;}
    }
    if(node.class_name=="StatsItem"&&(key=="GetValue"||key=="GetValueString")) {
        lua_pushboolean(L,key=="GetValueString");
        lua_pushcclosurek(L,stats_item_value,key.c_str(),1,nullptr);return true;
    }
    if(node.class_name=="TestService"&&key=="Message") {
        lua_pushcfunction(L,test_service_message,"Message");return true;
    }
    if(node.class_name=="Player") {
        if(key=="GetMouse"){lua_pushcfunction(L,player_get_mouse,"GetMouse");return true;}
        if(key=="DistanceFromCharacter"){lua_pushcfunction(L,player_distance_from_character,"DistanceFromCharacter");return true;}
    }
    if (node.class_name == "Players") {
        if (key == "GetPlayers" || key == "getPlayers" || key == "players") {
            lua_pushcfunction(L, players_get_players, "GetPlayers");
            return true;
        }
        if (key == "GetPlayerByUserId") {
            lua_pushcfunction(L, players_get_player_by_user_id, "GetPlayerByUserId");
            return true;
        }
        if (key == "GetPlayerFromCharacter" || key == "playerFromCharacter") {
            lua_pushcfunction(L, players_get_player_from_character, "GetPlayerFromCharacter");
            return true;
        }
    }
    if (node.class_name == "Debris" && key == "AddItem") {
        lua_pushcfunction(L, debris_add_item, "AddItem");
        return true;
    }
    (void)world;
    return false;
}
