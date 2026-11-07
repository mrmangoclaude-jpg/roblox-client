// CollectionService and Instance tag compatibility surface.
// Included inside world_bindings' anonymous namespace after signal_for/emit.
// The snapshot adapter decodes server Tags SharedStrings. Unknown or invalid
// payloads remain unknown instead of being replaced with an empty tag list.
// The live corpus contains a valid 65,534-byte tag. Preserve that received
// value; the adapter separately bounds total payload bytes and tag count.
constexpr size_t kCollectionMaxTagBytes = 65536;
constexpr size_t kCollectionMaxTagsPerInstance = 256;

Node* collection_service(World& w) {
    auto it=w.services.find("CollectionService");
    if(it==w.services.end())return nullptr;
    Node* service=find_node(w,it->second);
    return !service||service->destroyed?nullptr:service;
}
bool collection_valid_tag(const std::string& tag) {
    return !tag.empty()&&tag.size()<=kCollectionMaxTagBytes&&tag.find('\0')==std::string::npos&&valid_utf8(tag.data(),tag.size());
}
std::string collection_read_tag(lua_State* L,int index) {
    size_t length=0;const char* raw=luaL_checklstring(L,index,&length);std::string tag(raw,length);
    if(!collection_valid_tag(tag))luaL_argerror(L,index,"tag must be non-empty UTF-8 without NUL and at most 65536 bytes");
    return tag;
}
Handle* collection_target(lua_State* L,int index,bool service_method) {
    Handle* receiver=checked_handle(L,1);
    if(service_method&&receiver->node->class_name!="CollectionService")luaL_error(L,"CollectionService method receiver required");
    Handle* target=service_method?checked_handle(L,index):receiver;
    if(target->world!=receiver->world)luaL_error(L,"tag target belongs to a different world");
    if(target->node->destroyed)luaL_error(L,"tag target is destroyed");
    return target;
}
std::vector<std::string> collection_tags(const Node& node) {
    if(!node.collection_tags_known)throw std::runtime_error("CollectionService tag state is unknown for this instance");
    return node.collection_tags;
}
bool collection_has(const Node& node,const std::string& tag) {
    auto tags=collection_tags(node);
    return std::find(tags.begin(),tags.end(),tag)!=tags.end();
}
bool collection_in_datamodel(World& w,const Node& node) {
    return node.id==w.game_id||is_descendant_of(w,node,w.game_id);
}
void collection_emit(World& w,Node& node,const std::string& tag,bool added) {
    Node* service=collection_service(w);if(!service)return;
    emit(w,*service,std::string(added?"tag-added:":"tag-removed:")+tag,Json::array({Json{{"$ref",node.id}}}));
}
void collection_read_state(Node& node,const Json& record) {
    const bool known=record.value("collection_tags_known",!node.server_owned||record.contains("collection_tags"));
    std::vector<std::string> tags;
    if(record.contains("collection_tags")) {
        const auto& values=record.at("collection_tags");
        if(!values.is_array()||values.size()>kCollectionMaxTagsPerInstance)throw std::runtime_error("invalid instance tag list");
        for(const auto& tag:values) {
            if(!tag.is_string()||!collection_valid_tag(tag.get_ref<const std::string&>()))throw std::runtime_error("invalid instance tag");
            tags.push_back(tag.get<std::string>());
        }
        std::sort(tags.begin(),tags.end());
        if(std::adjacent_find(tags.begin(),tags.end())!=tags.end())throw std::runtime_error("duplicate instance tag");
        if(!known&&!tags.empty())throw std::runtime_error("unknown tag list cannot contain values");
    }
    node.collection_tags=std::move(tags);node.collection_tags_known=known;
}
void collection_received_state(World& w,Node& node,const Json& record) {
    Node incoming;collection_read_state(incoming,record);
    auto previous=node.collection_tags;
    node.collection_tags=std::move(incoming.collection_tags);
    node.collection_tags_known=incoming.collection_tags_known;
    if(!node.collection_tags_known||!collection_in_datamodel(w,node))return;
    for(const auto& tag:previous)
        if(!std::binary_search(node.collection_tags.begin(),node.collection_tags.end(),tag))collection_emit(w,node,tag,false);
    for(const auto& tag:node.collection_tags)
        if(!std::binary_search(previous.begin(),previous.end(),tag))collection_emit(w,node,tag,true);
}
int collection_change_tag(lua_State* L,Handle* h,const std::string& tag,bool add) {
    Node& node=*h->node;
    try {
        auto tags=collection_tags(node);
        auto it=std::find(tags.begin(),tags.end(),tag);
        if(add&&it!=tags.end())return 0;
        if(!add&&it==tags.end())return 0;
        if(add){if(tags.size()>=kCollectionMaxTagsPerInstance)throw std::runtime_error("instance tag limit exceeded");tags.push_back(tag);std::sort(tags.begin(),tags.end());}
        else tags.erase(it);
        Json encoded=tags;std::vector<Json> mutations{Json{{"kind","set_tags"},{"id",node.id},{"tags",encoded}}};
        check_mutation_budget(*h->world,mutations);
        node.collection_tags=std::move(tags);node.collection_tags_known=true;append_mutations(*h->world,std::move(mutations));
        if(collection_in_datamodel(*h->world,node))collection_emit(*h->world,node,tag,add);
        return 0;
    } catch(const std::exception& e){luaL_error(L,"tag update failed: %s",e.what());return 0;}
}
int collection_add_tag(lua_State* L) {
    const bool service=checked_handle(L,1)->node->class_name=="CollectionService";
    Handle* h=collection_target(L,service?2:1,service);std::string tag=collection_read_tag(L,service?3:2);
    return collection_change_tag(L,h,tag,true);
}
int collection_remove_tag(lua_State* L) {
    const bool service=checked_handle(L,1)->node->class_name=="CollectionService";
    Handle* h=collection_target(L,service?2:1,service);std::string tag=collection_read_tag(L,service?3:2);
    return collection_change_tag(L,h,tag,false);
}
int collection_has_tag(lua_State* L) {
    const bool service=checked_handle(L,1)->node->class_name=="CollectionService";
    auto* h=collection_target(L,service?2:1,service);std::string tag=collection_read_tag(L,service?3:2);
    try{lua_pushboolean(L,collection_has(*h->node,tag));return 1;}
    catch(const std::exception& e){luaL_error(L,"HasTag failed: %s",e.what());return 0;}
}
int collection_get_tags(lua_State* L) {
    const bool service=checked_handle(L,1)->node->class_name=="CollectionService";
    auto* h=collection_target(L,service?2:1,service);
    try{auto tags=collection_tags(*h->node);lua_createtable(L,(int)tags.size(),0);int i=1;for(auto& tag:tags){lua_pushlstring(L,tag.data(),tag.size());lua_rawseti(L,-2,i++);}return 1;}
    catch(const std::exception& e){luaL_error(L,"GetTags failed: %s",e.what());return 0;}
}
int collection_get_tagged(lua_State* L) {
    auto* h=checked_handle(L,1);World& w=*h->world;std::string tag=luaL_checkstring(L,2);
    if(h->node->class_name!="CollectionService"){luaL_error(L,"GetTagged requires CollectionService");return 0;}
    tag=collection_read_tag(L,2);
    lua_newtable(L);int index=1;
    for(const auto& id:w.order){Node& node=w.nodes.at(id);if(node.destroyed||!node.collection_tags_known||!collection_in_datamodel(w,node))continue;
        if(std::find(node.collection_tags.begin(),node.collection_tags.end(),tag)!=node.collection_tags.end()){push_node(L,w,&node);lua_rawseti(L,-2,index++);}}
    return 1;
}
int collection_get_all_tags(lua_State* L) {
    auto* h=checked_handle(L,1);World& w=*h->world;if(h->node->class_name!="CollectionService"){luaL_error(L,"GetAllTags requires CollectionService");return 0;}std::set<std::string> tags;
    for(const auto& id:w.order){Node& node=w.nodes.at(id);if(node.destroyed||!node.collection_tags_known||!collection_in_datamodel(w,node))continue;tags.insert(node.collection_tags.begin(),node.collection_tags.end());}
    lua_createtable(L,(int)tags.size(),0);int i=1;for(const auto& tag:tags){lua_pushlstring(L,tag.data(),tag.size());lua_rawseti(L,-2,i++);}return 1;
}
int collection_service_add_tag(lua_State* L){return collection_add_tag(L);}
int collection_service_remove_tag(lua_State* L){return collection_remove_tag(L);}
int collection_service_has_tag(lua_State* L){return collection_has_tag(L);}
int collection_service_get_tags(lua_State* L){return collection_get_tags(L);}
int collection_get_added_signal(lua_State* L) {
    auto* h=checked_handle(L,1);std::string tag=luaL_checkstring(L,2);
    if(h->node->class_name!="CollectionService"){luaL_error(L,"GetInstanceAddedSignal requires CollectionService");return 0;}
    tag=collection_read_tag(L,2);
    try{push_signal(L,signal_for(*h->world,*h->node,"tag-added:"+tag));h->world->collection_events_observed=true;return 1;}
    catch(const std::exception& e){luaL_error(L,"GetInstanceAddedSignal failed: %s",e.what());return 0;}
}
int collection_get_removed_signal(lua_State* L) {
    auto* h=checked_handle(L,1);std::string tag=luaL_checkstring(L,2);
    if(h->node->class_name!="CollectionService"){luaL_error(L,"GetInstanceRemovedSignal requires CollectionService");return 0;}
    tag=collection_read_tag(L,2);
    try{push_signal(L,signal_for(*h->world,*h->node,"tag-removed:"+tag));h->world->collection_events_observed=true;return 1;}
    catch(const std::exception& e){luaL_error(L,"GetInstanceRemovedSignal failed: %s",e.what());return 0;}
}
bool collection_instance_index(lua_State* L,World& w,Node& n,const std::string& key) {
    if(n.class_name=="CollectionService"&&key=="AddTag")lua_pushcfunction(L,collection_service_add_tag,"AddTag");
    else if(n.class_name=="CollectionService"&&key=="RemoveTag")lua_pushcfunction(L,collection_service_remove_tag,"RemoveTag");
    else if(n.class_name=="CollectionService"&&key=="HasTag")lua_pushcfunction(L,collection_service_has_tag,"HasTag");
    else if(n.class_name=="CollectionService"&&key=="GetTags")lua_pushcfunction(L,collection_service_get_tags,"GetTags");
    else if(key=="AddTag")lua_pushcfunction(L,collection_add_tag,"AddTag");
    else if(key=="RemoveTag")lua_pushcfunction(L,collection_remove_tag,"RemoveTag");
    else if(key=="HasTag")lua_pushcfunction(L,collection_has_tag,"HasTag");
    else if(key=="GetTags")lua_pushcfunction(L,collection_get_tags,"GetTags");
    else if(n.class_name=="CollectionService"&&key=="GetTagged")lua_pushcfunction(L,collection_get_tagged,"GetTagged");
    else if(n.class_name=="CollectionService"&&key=="GetAllTags")lua_pushcfunction(L,collection_get_all_tags,"GetAllTags");
    else if(n.class_name=="CollectionService"&&key=="GetInstanceAddedSignal")lua_pushcfunction(L,collection_get_added_signal,"GetInstanceAddedSignal");
    else if(n.class_name=="CollectionService"&&key=="GetInstanceRemovedSignal")lua_pushcfunction(L,collection_get_removed_signal,"GetInstanceRemovedSignal");
    else return false;
    (void)w;return true;
}
void collection_parent_events(World& w,Node& root,const std::string& old_parent,const std::string& new_parent) {
    if(old_parent==new_parent||!w.collection_events_observed||!collection_service(w))return;
    auto in_tree=[&](const std::string& parent){
        if(parent.empty())return false;if(parent==w.game_id)return true;
        Node* p=find_node(w,parent);return p&&is_descendant_of(w,*p,w.game_id);
    };
    const bool was=in_tree(old_parent),now=in_tree(new_parent);if(was==now)return;
    std::vector<Node*> subtree{&root};
    subtree=descendant_nodes(w,root,true);
    for(Node* node:subtree){
        if(node->destroyed||!node->collection_tags_known)continue;
        for(const auto& tag:node->collection_tags)collection_emit(w,*node,tag,now);
    }
}
