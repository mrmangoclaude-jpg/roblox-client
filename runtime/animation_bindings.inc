// Included inside world_bindings' private namespace, after signal helpers.
// Implements local track clocks and events. Does not pose joints or transmit.
constexpr const char* kPriorityMeta="WorldSnapshot.AnimationPriority.Item";
constexpr const char* kPriorityEnumMeta="WorldSnapshot.AnimationPriority.Enum";
constexpr const char* kPriorityNames[]={"Idle","Movement","Action","Action2","Action3","Action4","Core"};
int priority_index(int v){return v==1000?6:(v>=0&&v<=5?v:-1);}
void push_priority(lua_State* L,int value){
    if(priority_index(value)<0)throw std::runtime_error("invalid AnimationPriority");
    *static_cast<int*>(lua_newuserdatatagged(L,sizeof(int),0))=value;
    luaL_getmetatable(L,kPriorityMeta);lua_setmetatable(L,-2);
}
int priority_readonly(lua_State* L){luaL_error(L,"AnimationPriority is read-only");return 0;}
int priority_item_index(lua_State* L){
    int v=*static_cast<int*>(luaL_checkudata(L,1,kPriorityMeta));const char* k=luaL_checkstring(L,2);
    if(!std::strcmp(k,"Name"))lua_pushstring(L,kPriorityNames[priority_index(v)]);
    else if(!std::strcmp(k,"Value"))lua_pushinteger(L,v);
    else if(!std::strcmp(k,"EnumType"))lua_getfield(L,LUA_REGISTRYINDEX,"Headless.AnimationPriorityEnum");
    else luaL_error(L,"unknown AnimationPriority member");return 1;
}
int priority_string(lua_State* L){int v=*static_cast<int*>(luaL_checkudata(L,1,kPriorityMeta));lua_pushfstring(L,"Enum.AnimationPriority.%s",kPriorityNames[priority_index(v)]);return 1;}
int priority_equal(lua_State* L){lua_pushboolean(L,has_meta(L,2,kPriorityMeta)&&*static_cast<int*>(lua_touserdata(L,1))==*static_cast<int*>(lua_touserdata(L,2)));return 1;}
int priority_items(lua_State* L){luaL_checkudata(L,1,kPriorityEnumMeta);lua_createtable(L,7,0);for(int i=0;i<7;i++){push_priority(L,i==6?1000:i);lua_rawseti(L,-2,i+1);}return 1;}
int priority_enum_index(lua_State* L){const char* k=luaL_checkstring(L,2);if(!std::strcmp(k,"GetEnumItems")){lua_pushcfunction(L,priority_items,"GetEnumItems");return 1;}for(int i=0;i<7;i++)if(!std::strcmp(k,kPriorityNames[i])){push_priority(L,i==6?1000:i);return 1;}luaL_error(L,"unknown AnimationPriority item");return 0;}
int priority_enum_string(lua_State* L){lua_pushliteral(L,"AnimationPriority");return 1;}
void install_animation_enum(lua_State* L){
    luaL_newmetatable(L,kPriorityMeta);
    lua_pushcfunction(L,priority_item_index,"__index");lua_setfield(L,-2,"__index");
    lua_pushcfunction(L,priority_string,"__tostring");lua_setfield(L,-2,"__tostring");
    lua_pushcfunction(L,priority_equal,"__eq");lua_setfield(L,-2,"__eq");
    lua_pushcfunction(L,priority_readonly,"__newindex");lua_setfield(L,-2,"__newindex");
    lua_pushliteral(L,"EnumItem");lua_setfield(L,-2,"__type");lua_pushliteral(L,"animation enum item");lua_setfield(L,-2,"__metatable");lua_pop(L,1);
    luaL_newmetatable(L,kPriorityEnumMeta);
    lua_pushcfunction(L,priority_enum_index,"__index");lua_setfield(L,-2,"__index");
    lua_pushcfunction(L,priority_enum_string,"__tostring");lua_setfield(L,-2,"__tostring");
    lua_pushcfunction(L,priority_readonly,"__newindex");lua_setfield(L,-2,"__newindex");
    lua_pushliteral(L,"Enum");lua_setfield(L,-2,"__type");lua_pushliteral(L,"animation enum");lua_setfield(L,-2,"__metatable");lua_pop(L,1);
    lua_newuserdatatagged(L,1,0);luaL_getmetatable(L,kPriorityEnumMeta);lua_setmetatable(L,-2);
    lua_pushvalue(L,-1);lua_setfield(L,LUA_REGISTRYINDEX,"Headless.AnimationPriorityEnum");
    lua_setfield(L,-2,"AnimationPriority");
}

Json node_record(const Node& n);
void check_mutation_budget(World& w,const std::vector<Json>& entries);
void append_mutations(World& w,std::vector<Json> entries);
Node* animation_node(World& w,const std::string& cls,const std::string& name,const std::string& parent=""){
    if(w.nodes.size()>=kMaxNodes+1000)throw std::runtime_error("local instance limit exceeded");
    Node node;do{node.id="local:"+std::to_string(w.next_local_id++);}while(w.nodes.count(node.id));
    node.class_name=cls;node.name=name;node.parent=parent;node.server_owned=false;node.attributes_known=true;
    node.properties["Archivable"]=true;node.origins=Json{{"Archivable","class_default"},{"Name","local"},{"Parent","local"}};
    std::vector<Json> entries{Json{{"kind","create"},{"node",node_record(node)}}};check_mutation_budget(w,entries);
    auto [it,ok]=w.nodes.emplace(node.id,std::move(node));w.order.push_back(it->first);
    append_mutations(w,std::move(entries));if(!parent.empty())parent_events(w,it->second,"",parent);return &it->second;
}
Node* animator_for(World& w,Node& n,bool create){
    if(n.destroyed)throw std::runtime_error("animation receiver is destroyed");
    if(n.class_name=="Animator")return &n;
    if(n.class_name!="Humanoid"&&n.class_name!="AnimationController")throw std::runtime_error("Animator, Humanoid or AnimationController required");
    for(const auto& id:direct_children(w,n.id)){auto& child=w.nodes.at(id);if(!child.destroyed&&child.class_name=="Animator")return &child;}
    return create?animation_node(w,"Animator","Animator",n.id):nullptr;
}
const Json* track_clip(World& w,const AnimationTrackState& track){auto it=w.animation.clips.find(track.reference);return it==w.animation.clips.end()?nullptr:&it->second;}
bool track_animator_is_local_character(World& w,const AnimationTrackState& track){
    auto* player=find_node(w,w.local_player);if(!player||player->destroyed)return false;
    const Json* character=property_value(w,*player,"Character");
    if(!character||!character->is_object()||!character->contains("$ref")||!(*character)["$ref"].is_string())return false;
    auto* animator=find_node(w,track.animator);if(!animator||animator->destroyed)return false;
    auto* model=find_node(w,(*character)["$ref"].get<std::string>());
    return model&&!model->destroyed&&model->class_name=="Model"&&is_descendant_of(w,*animator,model->id);
}
bool queue_animation_intent(World& w,const Node& track_node,const AnimationTrackState& track,const char* method,Json parameters=Json::object()){
    if(!track_animator_is_local_character(w,track))return true;
    if(w.animation.intents.size()>=AnimationState::intent_limit
       ||w.animation.next_intent_sequence==std::numeric_limits<uint64_t>::max())return false;
    Json state{{"playing",track.playing},{"priority",track.priority},{"looped",track.looped},
        {"time_position",track.position},{"speed",track.speed},{"weight_current",track.weight},
        {"weight_target",track.target}};
    if(parameters.contains("effective_state")&&parameters["effective_state"].is_object())
        for(auto it=parameters["effective_state"].begin();it!=parameters["effective_state"].end();++it)state[it.key()]=it.value();
    parameters.erase("effective_state");parameters["effective_state"]=std::move(state);
    w.animation.intents.push_back(Json{{"sequence",w.animation.next_intent_sequence++},
        {"track_id",track_node.id},{"animator_id",track.animator},
        {"animation_reference",track.reference},{"kind",method},{"parameters",std::move(parameters)}});
    return true;
}
void track_fade(AnimationTrackState& t,double target,double duration){t.fade_from=t.weight;t.target=target;t.fade_elapsed=0;t.fade_duration=duration;if(duration==0)t.weight=target;}
void track_stop(World& w,Node& node,AnimationTrackState& t,double fade,bool record_intent=true){
    if(!t.playing)return;
    if(record_intent)queue_animation_intent(w,node,t,"Stop",Json{{"fade_time",fade},{"effective_state",Json{
        {"playing",false},{"weight_current",fade==0?0.0:t.weight},{"weight_target",0.0}}}});
    t.playing=false;track_fade(t,0,fade);emit(w,node,"Stopped");property_events(w,node,"IsPlaying");
    if(fade==0){t.active=false;emit(w,node,"Ended");}
}
bool track_keyframes(World& w,Node& node,const Json& clip,double from,double to,bool forward,bool include_start,size_t& work){
    auto fire=[&](const Json& frame){
        double at=frame.at("time");bool crossed=forward?((at>from||(include_start&&at==from))&&at<=to):((at<from||(include_start&&at==from))&&at>=to);
        if(!crossed)return;
        const auto name=frame.at("name").get<std::string>();if(name!="Keyframe")emit(w,node,"KeyframeReached",Json::array({name}));
        for(const auto& marker:frame.at("markers"))emit(w,node,"marker:"+marker.at("name").get<std::string>(),Json::array({marker.at("value")}));
    };
    const auto& frames=clip.at("keyframes");
    if(forward){
        auto begin=std::lower_bound(frames.begin(),frames.end(),from,[](const Json& f,double at){return f.at("time").get<double>()<at;});
        for(auto it=begin;it!=frames.end()&&it->at("time").get<double>()<=to;++it){work+=1+it->at("markers").size();if(work>100000)return false;fire(*it);}
    }else{
        auto end=std::upper_bound(frames.begin(),frames.end(),from,[](double at,const Json& f){return at<f.at("time").get<double>();});
        while(end!=frames.begin()){--end;if(end->at("time").get<double>()<to)break;work+=1+end->at("markers").size();if(work>100000)return false;fire(*end);}
    }
    return true;
}
void advance_animations(World& w){
    for(auto it=w.animation.tracks.begin();it!=w.animation.tracks.end();){
        Node* node=find_node(w,it->first);
        if(!node||node->destroyed)it=w.animation.tracks.erase(it);else ++it;
    }
    auto now=std::chrono::steady_clock::now();size_t work=0;
    for(auto& [id,t]:w.animation.tracks){
        Node* node=find_node(w,id);Node* animator=find_node(w,t.animator);
        double dt=std::chrono::duration<double>(now-t.updated).count();t.updated=now;
        if(!node||node->destroyed){t.playing=t.active=false;continue;}
        if(!animator||animator->destroyed){track_stop(w,*node,t,0);t.active=false;continue;}
        if(!t.active)continue;
        if(t.fade_duration>0){t.fade_elapsed=std::min(t.fade_duration,t.fade_elapsed+dt);t.weight=t.fade_from+(t.target-t.fade_from)*(t.fade_elapsed/t.fade_duration);}
        if(!t.playing){if(t.fade_elapsed>=t.fade_duration){t.weight=0;t.active=false;emit(w,*node,"Ended");}continue;}
        const Json* clip=track_clip(w,t);if(!clip)continue;
        double length=clip->at("length");if(length<=0){track_stop(w,*node,t,0);continue;}
        if(t.speed==0)continue;
        double remaining=dt*std::abs(t.speed);bool forward=t.speed>0;
        // Bound pathological loop storms without silently dropping events.
        if(!std::isfinite(remaining)||remaining/length>256){track_stop(w,*node,t,0);if(w.output.size()<kMaxPrinted-80)w.output+="WARN: animation timeline step exceeds event limit\n";continue;}
        while(t.playing){
            double distance=forward?length-t.position:t.position;
            double step=std::min(remaining,std::max(0.0,distance));double end=t.position+(forward?step:-step);
            if(!track_keyframes(w,*node,*clip,t.position,end,forward,t.start_pending,work)){
                track_stop(w,*node,t,0);if(w.output.size()<kMaxPrinted-80)w.output+="WARN: animation timeline event budget exceeded\n";break;
            }
            t.start_pending=false;t.position=end;remaining-=step;
            if(step<distance)break;
            if(!t.looped){track_stop(w,*node,t,0);break;}
            emit(w,*node,"DidLoop");t.position=forward?0:length;t.start_pending=true;
            if(remaining<=0)break;
        }
    }
}
void complete_animations(World& w,const Json& responses){
    if(!responses.is_array()||responses.size()>32)throw std::runtime_error("invalid animation response batch");
    // Validate the complete batch before changing track state.
    size_t bytes=0;std::set<std::string> references;
    for(const auto& response:responses){
        const auto reference=response.at("reference").get<std::string>();
        if(!w.animation.requested.count(reference)||!references.insert(reference).second||w.animation.clips.count(reference)||w.animation.errors.count(reference))throw std::runtime_error("unexpected animation response");
        if(response.contains("error")){if(!response.at("error").is_string()||response.at("error").get_ref<const std::string&>().size()>128)throw std::runtime_error("invalid animation error");continue;}
        const auto& clip=response.at("clip");double length=clip.at("length");
        if(clip.value("version",0)!=1||clip.value("kind","")!="KeyframeSequence"||!std::isfinite(length)||length<0||length>86400||!clip.at("looped").is_boolean()||!clip.at("keyframes").is_array()||clip.at("keyframes").size()>20000)throw std::runtime_error("invalid animation timeline");
        if(!clip.at("priority").is_null()&&priority_index(clip.at("priority").get<int>())<0)throw std::runtime_error("invalid animation priority");
        double last=-1;size_t markers=0;
        for(const auto& frame:clip.at("keyframes")){
            double at=frame.at("time");if(!std::isfinite(at)||at<0||at<last||at>length||frame.at("name").get_ref<const std::string&>().size()>1024||!frame.at("markers").is_array())throw std::runtime_error("invalid animation keyframe");last=at;
            for(const auto& marker:frame.at("markers")){if(++markers>20000||marker.at("name").get_ref<const std::string&>().size()>1024||marker.at("value").get_ref<const std::string&>().size()>4096)throw std::runtime_error("invalid animation marker");}
        }
        bytes+=clip.dump().size();
    }
    if(bytes>16*1024*1024-w.animation.clip_bytes)throw std::runtime_error("animation timeline cache limit exceeded");
    for(const auto& response:responses){
        const auto reference=response.at("reference").get<std::string>();
        if(response.contains("error"))w.animation.errors[reference]="animation asset unavailable";
        else{w.animation.clips[reference]=response.at("clip");w.animation.clip_bytes+=response.at("clip").dump().size();}
        for(auto& [id,t]:w.animation.tracks)if(t.reference==reference){
            auto* node=find_node(w,id);if(!node||node->destroyed)continue;
            if(response.contains("error")){track_stop(w,*node,t,0);if(w.output.size()<kMaxPrinted-80)w.output+="WARN: animation asset failed to load\n";continue;}
            const auto& clip=response.at("clip");if(!t.loop_override)t.looped=clip.at("looped");if(!t.priority_override&&!clip.at("priority").is_null())t.priority=clip.at("priority");
            t.updated=std::chrono::steady_clock::now();t.position=std::min(t.position,clip.at("length").get<double>());property_events(w,*node,"Length");
        }
    }
}
int animator_method(lua_State* L){
    auto* h=checked_handle(L,1);auto& w=*h->world;const std::string method=lua_tostring(L,lua_upvalueindex(1));
    try{
        advance_animations(w);
        Node* animator=animator_for(w,*h->node,false);
        if(method=="LoadAnimation"){
            auto* animation=checked_handle(L,2);if(animation->world!=&w||animation->node->destroyed||animation->node->class_name!="Animation")throw std::runtime_error("LoadAnimation requires an Animation");
            auto ws=w.services.find("Workspace");if(ws==w.services.end()||!is_descendant_of(w,animator?*animator:*h->node,ws->second))throw std::runtime_error("Animator must be in Workspace");
            const Json* value=property_value(w,*animation->node,"AnimationId");
            if(!value||!value->is_string()||value->get_ref<const std::string&>().empty())value=property_value(w,*animation->node,"AnimationContent");
            if(!value||!value->is_string()||value->get_ref<const std::string&>().empty()||value->get_ref<const std::string&>().size()>512)throw std::runtime_error("Animation has no supported content reference");
            std::string reference=value->get<std::string>();
            if(w.animation.tracks.size()>=AnimationState::track_limit||(!w.animation.requested.count(reference)&&w.animation.requested.size()>=128))throw std::runtime_error("animation track or asset limit exceeded");
            if(!animator)animator=animator_for(w,*h->node,true);
            Node* node=animation_node(w,"AnimationTrack",instance_name(w,*animation->node));
            AnimationTrackState t;t.animator=animator->id;t.animation=animation->node->id;t.reference=reference;
            if(auto* clip=track_clip(w,t)){t.looped=clip->at("looped");if(!clip->at("priority").is_null())t.priority=clip->at("priority");}
            w.animation.tracks.emplace(node->id,std::move(t));
            if(w.animation.requested.insert(reference).second)w.animation.requests.push_back(Json{{"reference",reference}});
            push_node(L,w,node);return 1;
        }
        if(method=="GetPlayingAnimationTracks"){
            lua_newtable(L);int index=0;
            if(animator)for(const auto& id:w.order){auto it=w.animation.tracks.find(id);if(it!=w.animation.tracks.end()&&it->second.animator==animator->id&&it->second.active&&!w.nodes.at(id).destroyed){push_node(L,w,find_node(w,id));lua_rawseti(L,-2,++index);}}
            return 1;
        }
        std::string reference=luaL_checkstring(L,2);
        if(animator)for(const auto& id:w.order){auto it=w.animation.tracks.find(id);if(it!=w.animation.tracks.end()&&it->second.animator==animator->id&&it->second.reference==reference&&!w.nodes.at(id).destroyed){push_node(L,w,find_node(w,id));return 1;}}
        lua_pushnil(L);return 1;
    }catch(const std::exception& e){luaL_error(L,"animation method failed: %s",e.what());return 0;}
}
double animation_number(lua_State* L,int index,double fallback){double v=luaL_optnumber(L,index,fallback);if(!std::isfinite(v)||std::abs(v)>1e6)luaL_argerror(L,index,"finite animation number within supported range required");return v;}
int track_method(lua_State* L){
    auto* h=checked_handle(L,1);auto& w=*h->world;const std::string method=lua_tostring(L,lua_upvalueindex(1));
    try{
        if(h->node->destroyed||!w.animation.tracks.count(h->node->id))throw std::runtime_error("live AnimationTrack required");
        advance_animations(w);auto& t=w.animation.tracks.at(h->node->id);
        if(method=="Play"){
            double fade=animation_number(L,2,.1),weight=animation_number(L,3,1),speed=animation_number(L,4,1);
            if(fade<0||weight<0)throw std::runtime_error("fade and weight must be nonnegative");
            if(w.animation.errors.count(t.reference))throw std::runtime_error("animation asset failed to load");
            auto* owner=find_node(w,t.animator);if(!owner||owner->destroyed)throw std::runtime_error("Animator is destroyed");
            if(!queue_animation_intent(w,*h->node,t,"Play",Json{{"fade_time",fade},{"weight",weight},{"speed",speed},
                {"effective_state",Json{{"playing",true},{"time_position",0.0},{"speed",speed},
                    {"weight_current",fade==0?weight:0.0},{"weight_target",weight}}}}))throw std::runtime_error("animation intent limit exceeded");
            t.playing=t.active=true;t.position=0;t.speed=speed;t.weight=0;t.start_pending=true;track_fade(t,weight,fade);
            property_events(w,*h->node,"IsPlaying");if(auto* animator=find_node(w,t.animator)){emit(w,*animator,"AnimationPlayed",Json::array({Json{{"$ref",h->node->id}}}));if(auto* parent=find_node(w,parent_id(w,*animator)))emit(w,*parent,"AnimationPlayed",Json::array({Json{{"$ref",h->node->id}}}));}
        }else if(method=="Stop"){
            double fade=animation_number(L,2,.1);if(fade<0)throw std::runtime_error("fade must be nonnegative");
            if(t.playing&&!queue_animation_intent(w,*h->node,t,"Stop",Json{{"fade_time",fade},{"effective_state",Json{
                {"playing",false},{"weight_current",fade==0?0.0:t.weight},{"weight_target",0.0}}}}))throw std::runtime_error("animation intent limit exceeded");
            track_stop(w,*h->node,t,fade,false);
        }
        else if(method=="AdjustSpeed"){
            double speed=animation_number(L,2,1);
            if(!queue_animation_intent(w,*h->node,t,"AdjustSpeed",Json{{"speed",speed},
                {"effective_state",Json{{"speed",speed}}}}))throw std::runtime_error("animation intent limit exceeded");
            t.speed=speed;
        }
        else if(method=="AdjustWeight"){
            double weight=animation_number(L,2,1),fade=animation_number(L,3,.1);if(weight<0||fade<0)throw std::runtime_error("weight and fade must be nonnegative");
            if(t.playing&&!queue_animation_intent(w,*h->node,t,"AdjustWeight",Json{{"weight",weight},{"fade_time",fade},
                {"effective_state",Json{{"weight_current",fade==0?weight:t.weight},{"weight_target",weight}}}}))throw std::runtime_error("animation intent limit exceeded");
            if(t.playing)track_fade(t,weight,fade);
        }
        else if(method=="GetMarkerReachedSignal"){size_t n=0;const char* name=luaL_checklstring(L,2,&n);if(n>1024)throw std::runtime_error("marker name too long");push_signal(L,signal_for(w,*h->node,"marker:"+std::string(name,n)));return 1;}
        else if(method=="GetTimeOfKeyframe"){const auto* clip=track_clip(w,t);if(!clip)throw std::runtime_error("animation is not loaded");std::string name=luaL_checkstring(L,2);for(const auto& frame:clip->at("keyframes"))if(frame.at("name")==name){lua_pushnumber(L,frame.at("time"));return 1;}throw std::runtime_error("keyframe not found");}
        return 0;
    }catch(const std::exception& e){luaL_error(L,"AnimationTrack method failed: %s",e.what());return 0;}
}
bool animation_index(lua_State* L,World& w,Node& n,const std::string& key){
    // Received AnimationContent is the wire storage for the legacy AnimationId
    // string accessor. Prefer authored overrides, then the received alias.
    if(n.class_name=="Animation"&&key=="AnimationId"){
        const Json* value=local_value(w,n,"AnimationId");
        if(!value)value=property_value(w,n,"AnimationContent");
        if(!value)value=property_value(w,n,"AnimationId");
        if(value&&value->is_string()){push_json(L,w,*value);return true;}
    }
    if((n.class_name=="Animator"||n.class_name=="Humanoid"||n.class_name=="AnimationController")&&(key=="LoadAnimation"||key=="GetPlayingAnimationTracks"||key=="GetTrackByAnimationId")){
        lua_pushstring(L,key.c_str());lua_pushcclosurek(L,animator_method,key.c_str(),1,nullptr);return true;
    }
    if((n.class_name=="Animator"||n.class_name=="Humanoid"||n.class_name=="AnimationController")&&key=="AnimationPlayed"){push_signal(L,signal_for(w,n,key));return true;}
    if(n.class_name!="AnimationTrack"||!w.animation.tracks.count(n.id))return false;
    if(key=="Play"||key=="Stop"||key=="AdjustSpeed"||key=="AdjustWeight"||key=="GetMarkerReachedSignal"||key=="GetTimeOfKeyframe"){
        lua_pushstring(L,key.c_str());lua_pushcclosurek(L,track_method,key.c_str(),1,nullptr);return true;
    }
    if(key=="Stopped"||key=="Ended"||key=="DidLoop"||key=="KeyframeReached"){push_signal(L,signal_for(w,n,key));return true;}
    advance_animations(w);auto& t=w.animation.tracks.at(n.id);
    if(key=="Animation")push_node(L,w,find_node(w,t.animation));
    else if(key=="IsPlaying")lua_pushboolean(L,t.playing);
    else if(key=="Looped")lua_pushboolean(L,t.looped);
    else if(key=="Priority")push_priority(L,t.priority);
    else if(key=="Length"){auto* clip=track_clip(w,t);lua_pushnumber(L,clip?clip->at("length").get<double>():0);}
    else if(key=="TimePosition")lua_pushnumber(L,t.position);
    else if(key=="Speed")lua_pushnumber(L,t.speed);
    else if(key=="WeightCurrent")lua_pushnumber(L,t.weight);
    else if(key=="WeightTarget")lua_pushnumber(L,t.target);
    else return false;return true;
}
bool animation_newindex(lua_State* L,World& w,Node& n,const std::string& key){
    if(n.class_name=="Animation"&&key=="AnimationId"){
        size_t length=0;const char* text=luaL_checklstring(L,3,&length);
        if(lua_type(L,3)!=LUA_TSTRING||length>512)throw std::runtime_error("AnimationId requires a content string of at most 512 bytes");
        Json value=std::string(text,length);
        std::vector<Json> entries{Json{{"kind","set"},{"id",n.id},{"property","AnimationId"},{"value",value}}};
        check_mutation_budget(w,entries);w.local_properties[n.id]["AnimationId"]=value;append_mutations(w,std::move(entries));
        property_events(w,n,"AnimationId");return true;
    }
    if(n.class_name!="AnimationTrack"||!w.animation.tracks.count(n.id))return false;
    if(key=="Name"||key=="Parent"||key=="Archivable")return false;
    if(n.destroyed)throw std::runtime_error("AnimationTrack is destroyed");
    advance_animations(w);auto& t=w.animation.tracks.at(n.id);
    if(key=="Looped"){
        if(lua_type(L,3)!=LUA_TBOOLEAN)throw std::runtime_error("Looped requires boolean");
        bool looped=lua_toboolean(L,3);
        if(!queue_animation_intent(w,n,t,"Looped",Json{{"looped",looped},{"effective_state",Json{{"looped",looped}}}}))throw std::runtime_error("animation intent limit exceeded");
        t.looped=looped;t.loop_override=true;
    }
    else if(key=="Priority"){
        if(!has_meta(L,3,kPriorityMeta))throw std::runtime_error("Priority requires AnimationPriority");
        int priority=*static_cast<int*>(lua_touserdata(L,3));
        if(!queue_animation_intent(w,n,t,"Priority",Json{{"priority",priority},{"effective_state",Json{{"priority",priority}}}}))throw std::runtime_error("animation intent limit exceeded");
        t.priority=priority;t.priority_override=true;
    }
    else if(key=="TimePosition"){
        double at=animation_number(L,3,0);if(!t.playing)throw std::runtime_error("TimePosition requires a playing track");if(at<0)throw std::runtime_error("TimePosition must be nonnegative");
        const auto* clip=track_clip(w,t);double position=clip?std::min(at,clip->at("length").get<double>()):at;
        if(!queue_animation_intent(w,n,t,"TimePosition",Json{{"position",position},{"effective_state",Json{{"time_position",position}}}}))throw std::runtime_error("animation intent limit exceeded");
        t.position=position;t.start_pending=false;
    }
    else throw std::runtime_error("AnimationTrack property is read-only or unavailable");
    property_events(w,n,key);return true;
}
