// Collision definitions are received state in this client runtime. Saved-place
// v1 layout: version/count bytes, then id, mask width, LE mask, name length/name.
// See tests/fixtures/references/collision-groups-public.json for provenance.
struct CollisionGroupEntry { unsigned id;uint32_t mask;std::string name; };
struct CollisionGroupTable {
    std::vector<CollisionGroupEntry> entries{{0,UINT32_MAX,"Default"}};
    bool complete=false;
    const CollisionGroupEntry* find(const std::string& name) const {
        for(const auto& entry:entries)if(entry.name==name)return &entry;
        return nullptr;
    }
};
bool collision_world_root(const Node& node){return node.class_name=="Workspace"||node.class_name=="WorldModel";}
void validate_collision_name(const std::string& name) {
    if(name.empty()||name.size()>100||name.find('\0')!=std::string::npos||!valid_utf8(name.data(),name.size()))
        throw std::runtime_error("collision group name must be valid UTF-8 with 1 to 100 bytes");
}
void validate_collision_table(CollisionGroupTable& table) {
    if(table.entries.empty()||table.entries.size()>32)throw std::runtime_error("invalid collision group count");
    uint32_t used=0;std::unordered_set<std::string> names;
    for(const auto& entry:table.entries) {
        validate_collision_name(entry.name);
        if(entry.id>=32||(used&(uint32_t{1}<<entry.id))||!names.insert(entry.name).second)
            throw std::runtime_error("duplicate or out-of-range collision group ID/name");
        if((entry.id==0)!=(entry.name=="Default"))throw std::runtime_error("Default collision group must use ID zero");
        used|=uint32_t{1}<<entry.id;
    }
    if(!(used&1))throw std::runtime_error("collision group data lacks Default");
    std::sort(table.entries.begin(),table.entries.end(),[](const auto& a,const auto& b){return a.id<b.id;});
    table.complete=true;
}
std::string collision_data_bytes(const Json& value) {
    if(value.is_string()) {
        const auto& bytes=value.get_ref<const std::string&>();
        if(bytes.size()>4096)throw std::runtime_error("collision group data exceeds limit");
        return bytes;
    }
    if(value.is_object()&&value.size()==1&&value.contains("$bytes_hex")&&value.at("$bytes_hex").is_string()) {
        const auto& hex=value.at("$bytes_hex").get_ref<const std::string&>();
        if(hex.size()>8192||hex.size()%2)throw std::runtime_error("invalid collision group hex length");
        auto nibble=[](char c)->int{if(c>='0'&&c<='9')return c-'0';if(c>='a'&&c<='f')return c-'a'+10;if(c>='A'&&c<='F')return c-'A'+10;return -1;};
        std::string bytes;bytes.reserve(hex.size()/2);
        for(size_t i=0;i<hex.size();i+=2){int a=nibble(hex[i]),b=nibble(hex[i+1]);if(a<0||b<0)throw std::runtime_error("invalid collision group hex digit");bytes.push_back(char((a<<4)|b));}
        return bytes;
    }
    throw std::runtime_error("CollisionGroupData requires bytes or a tagged byte-string");
}
CollisionGroupTable decode_collision_data(const Json& value) {
    const auto bytes=collision_data_bytes(value);CollisionGroupTable table;
    // An explicitly empty definition is the constructor's Default-only state.
    if(bytes.empty()){table.complete=true;return table;}
    size_t cursor=0;
    auto byte=[&]()->unsigned{if(cursor>=bytes.size())throw std::runtime_error("truncated CollisionGroupData");return static_cast<unsigned char>(bytes[cursor++]);};
    if(byte()!=1)throw std::runtime_error("unsupported CollisionGroupData version");
    const unsigned count=byte();if(count==0||count>32)throw std::runtime_error("invalid collision group count");
    table.entries.clear();
    for(unsigned n=0;n<count;++n) {
        const unsigned id=byte();if(byte()!=4)throw std::runtime_error("unsupported collision mask width");
        uint32_t mask=0;for(unsigned shift=0;shift<32;shift+=8)mask|=uint32_t(byte())<<shift;
        const unsigned length=byte();if(length>bytes.size()-cursor)throw std::runtime_error("truncated collision group name");
        table.entries.push_back({id,mask,bytes.substr(cursor,length)});cursor+=length;
    }
    if(cursor!=bytes.size())throw std::runtime_error("trailing CollisionGroupData bytes");
    validate_collision_table(table);return table;
}
int64_t collision_decimal(const std::string& text) {
    if(text.empty()||text.size()>11)throw std::runtime_error("invalid legacy collision group integer");
    size_t i=text[0]=='-'?1:0;if(i==text.size())throw std::runtime_error("invalid legacy collision group integer");
    int64_t number=0;for(;i<text.size();++i){if(text[i]<'0'||text[i]>'9')throw std::runtime_error("invalid legacy collision group integer");number=number*10+(text[i]-'0');}
    return text[0]=='-'?-number:number;
}
CollisionGroupTable decode_legacy_collision_groups(const Json& value) {
    if(!value.is_string()||value.get_ref<const std::string&>().size()>4096)throw std::runtime_error("invalid legacy CollisionGroups string");
    const auto& text=value.get_ref<const std::string&>();CollisionGroupTable table;
    if(text.empty()){table.complete=true;return table;}
    table.entries.clear();size_t start=0;
    while(start<text.size()) {
        if(table.entries.size()>=32)throw std::runtime_error("invalid collision group count");
        size_t end=text.find('\\',start);if(end==std::string::npos)end=text.size();
        const auto row=text.substr(start,end-start);const size_t a=row.find('^'),b=a==std::string::npos?a:row.find('^',a+1);
        if(a==std::string::npos||b==std::string::npos||row.find('^',b+1)!=std::string::npos)throw std::runtime_error("malformed legacy collision group record");
        const auto id=collision_decimal(row.substr(a+1,b-a-1)),mask=collision_decimal(row.substr(b+1));
        if(id<0||id>31||mask<INT32_MIN||mask>UINT32_MAX)throw std::runtime_error("legacy collision group integer out of range");
        table.entries.push_back({unsigned(id),uint32_t(mask),row.substr(0,a)});start=end+1;
        if(start==text.size())throw std::runtime_error("trailing legacy collision group separator");
    }
    validate_collision_table(table);return table;
}
Node& collision_workspace(World& w) {
    const auto service=w.services.find("Workspace");
    Node* node=service==w.services.end()?nullptr:find_node(w,service->second);
    if(!node||node->destroyed||node->class_name!="Workspace")throw std::runtime_error("Workspace collision state is unavailable");
    return *node;
}
CollisionGroupTable read_collision_groups(World& w,Node& root) {
    if(root.destroyed||!collision_world_root(root))throw std::runtime_error("collision groups require a live WorldRoot");
    if(const auto* value=property_value(w,root,"CollisionGroupData"))return decode_collision_data(*value);
    if(const auto* value=property_value(w,root,"CollisionGroups"))return decode_legacy_collision_groups(*value);
    if(root.class_name=="Workspace") {
        const auto service=w.services.find("PhysicsService");
        if(service!=w.services.end())if(auto* node=find_node(w,service->second);node&&!node->destroyed)
            if(const auto* value=property_value(w,*node,"CollisionGroups"))return decode_legacy_collision_groups(*value);
    }
    CollisionGroupTable table;table.complete=!root.server_owned;return table;
}
Node& collision_query_root(World& w,Node& root) {
    if(root.class_name=="WorldModel")if(const auto* value=property_value(w,root,"UseWorkspaceCollisionGroups")) {
        if(!value->is_boolean())throw std::runtime_error("invalid UseWorkspaceCollisionGroups");
        if(value->get<bool>())return collision_workspace(w);
    }
    return root;
}
bool collision_pair(const CollisionGroupTable& table,const std::string& first,const std::string& second,bool query=false) {
    if(!table.complete&&(first!="Default"||second!="Default"))throw std::runtime_error("collision group matrix is unavailable");
    const auto* a=table.find(first);const auto* b=table.find(second);
    if(!a||!b) {
        if(!query)return true; // Public CollisionGroupsAreCollidable contract.
        // Query compatibility policy: an unregistered name uses Default's mask.
        if(!a)a=table.find("Default");if(!b)b=table.find("Default");
    }
    return (a->mask&(uint32_t{1}<<b->id))&&(b->mask&(uint32_t{1}<<a->id));
}
std::string part_collision_group(World& w,Node& node) {
    if(const auto* value=property_value(w,node,"CollisionGroup")) {
        if(!value->is_string())throw std::runtime_error("part collision group name is unavailable");
        return value->get<std::string>();
    }
    return "Default";
}
Node* part_collision_world(World& w,Node& node) {
    auto* cursor=&node;
    for(size_t depth=0;cursor&&depth<=w.nodes.size();++depth) {
        if(collision_world_root(*cursor))return cursor;
        cursor=find_node(w,parent_id(w,*cursor));
    }
    if(cursor)throw std::runtime_error("collision hierarchy contains a cycle");return nullptr;
}
CollisionGroupTable part_collision_table(World& w,Node& node) {
    Node* root=part_collision_world(w,node);
    if(!root)root=&collision_workspace(w);
    return read_collision_groups(w,collision_query_root(w,*root));
}
int part_collision_id(World& w,Node& node) {
    const auto name=part_collision_group(w,node);
    // The reserved Default ID does not require a received custom matrix.
    if(name=="Default")return 0;
    auto table=part_collision_table(w,node);
    if(!table.complete)throw std::runtime_error("collision group definitions are unavailable");
    const auto* entry=table.find(name);return entry?int(entry->id):-1;
}
int instance_newindex(lua_State* L);
bool collision_group_write(lua_State* L,World& w,Node& node,const std::string& key) {
    if(!pivot_part(w,node))return false;
    if(key=="CollisionGroup") {
        if(lua_type(L,3)!=LUA_TSTRING)throw std::runtime_error("collision group name requires a string");
        size_t size;const char* value=lua_tolstring(L,3,&size);validate_collision_name(std::string(value,size));
        return false; // Use the normal property mutation and notification path.
    }
    if(key!="CollisionGroupId")return false;
    if(node.destroyed)throw std::runtime_error("collision group requires a live BasePart");
    if(lua_type(L,3)!=LUA_TNUMBER)throw std::runtime_error("collision group ID requires a number");
    const double id=lua_tonumber(L,3);
    if(!std::isfinite(id)||id<0||id>31||std::floor(id)!=id)
        throw std::runtime_error("deprecated CollisionGroupId clamping/unregistered-ID assignment is not implemented; set CollisionGroup by name");
    std::string name="Default";
    if(id!=0) {
        auto table=part_collision_table(w,node);
        if(!table.complete)throw std::runtime_error("collision group definitions are unavailable");
        const CollisionGroupEntry* entry=nullptr;
        for(const auto& candidate:table.entries)if(candidate.id==id)entry=&candidate;
        if(!entry)throw std::runtime_error("deprecated unregistered CollisionGroupId assignment is not implemented; set CollisionGroup by name");
        name=entry->name;
    }
    lua_pushcfunction(L,instance_newindex,"BasePart.CollisionGroup");push_node(L,w,&node);
    lua_pushliteral(L,"CollisionGroup");lua_pushlstring(L,name.data(),name.size());lua_call(L,3,0);
    return true;
}
int collision_group_method(lua_State* L) {
    auto* h=checked_handle(L,1);auto& w=*h->world;
    const std::string method=lua_tostring(L,lua_upvalueindex(1));
    try {
        const bool service=h->node->class_name=="PhysicsService";
        if(h->node->destroyed||(!service&&!collision_world_root(*h->node)))throw std::runtime_error("collision group method requires a live WorldRoot or PhysicsService");
        Node& root=service?collision_workspace(w):*h->node;
        if(method=="RegisterCollisionGroup"||method=="CreateCollisionGroup"||method=="UnregisterCollisionGroup"||method=="RemoveCollisionGroup"||method=="RenameCollisionGroup"||method=="CollisionGroupSetCollidable")
            throw std::runtime_error("collision group definitions can only be changed by the server");
        if(method=="GetMaxCollisionGroups"){lua_pushinteger(L,32);return 1;}
        auto table=read_collision_groups(w,root);
        auto name=[&](int at){if(lua_type(L,at)!=LUA_TSTRING)throw std::runtime_error("collision group name requires a string");size_t length;const char* raw=lua_tolstring(L,at,&length);if(length>100)throw std::runtime_error("collision group name exceeds 100 bytes");return std::string(raw,length);};
        auto require_complete=[&](){if(!table.complete)throw std::runtime_error("collision group definitions are unavailable");};
        if(method=="GetRegisteredCollisionGroups"||method=="GetCollisionGroups") {
            require_complete();lua_createtable(L,int(table.entries.size()),0);int i=1;
            for(const auto& entry:table.entries) {
                lua_createtable(L,0,3);lua_pushlstring(L,entry.name.data(),entry.name.size());lua_setfield(L,-2,"name");
                const int64_t mask=entry.mask&0x80000000u?int64_t(entry.mask)-0x100000000LL:int64_t(entry.mask);
                lua_pushnumber(L,double(mask));lua_setfield(L,-2,"mask");
                if(method=="GetCollisionGroups"){lua_pushinteger(L,entry.id);lua_setfield(L,-2,"id");}
                lua_rawseti(L,-2,i++);
            }
        } else if(method=="CollisionGroupsAreCollidable")lua_pushboolean(L,collision_pair(table,name(2),name(3)));
        else if(method=="IsCollisionGroupRegistered"||method=="GetCollisionGroupId") {
            auto key=name(2);if(key!="Default")require_complete();const auto* entry=table.find(key);
            if(method=="IsCollisionGroupRegistered")lua_pushboolean(L,entry!=nullptr);
            else {if(!entry)throw std::runtime_error("collision group is not registered");lua_pushinteger(L,entry->id);}
        } else if(method=="GetCollisionGroupName") {
            if(lua_type(L,2)!=LUA_TNUMBER)throw std::runtime_error("collision group ID requires an integer");
            const double id=lua_tonumber(L,2);if(!std::isfinite(id)||id<0||id>31||std::floor(id)!=id)throw std::runtime_error("collision group ID must be from 0 to 31");
            if(id!=0)require_complete();const CollisionGroupEntry* found=nullptr;
            for(const auto& entry:table.entries)if(entry.id==id)found=&entry;
            if(found)lua_pushlstring(L,found->name.data(),found->name.size());else lua_pushliteral(L,"");
        } else if(method=="CollisionGroupContainsPart"||method=="SetPartCollisionGroup") {
            const bool setter=method=="SetPartCollisionGroup";auto group=name(setter?3:2);
            if(group!="Default")require_complete();if(!table.find(group))throw std::runtime_error("collision group is not registered");
            auto* part=checked_handle(L,setter?2:3);
            if(part->world!=&w||part->node->destroyed||!pivot_part(w,*part->node))throw std::runtime_error("collision membership requires a live BasePart");
            if(!setter)lua_pushboolean(L,part_collision_group(w,*part->node)==group);
            else {
                lua_pushcfunction(L,instance_newindex,"BasePart.CollisionGroup");push_node(L,w,part->node);lua_pushliteral(L,"CollisionGroup");lua_pushlstring(L,group.data(),group.size());lua_call(L,3,0);return 0;
            }
        } else throw std::runtime_error("unknown collision group method");
        return 1;
    }catch(const std::exception& e){return luaL_error(L,"%s: %s",method.c_str(),e.what()),0;}
}
int part_can_collide_with(lua_State* L) {
    auto* a=checked_handle(L,1);auto* b=checked_handle(L,2);auto& w=*a->world;
    try {
        if(a->world!=b->world||a->node->destroyed||b->node->destroyed||!pivot_part(w,*a->node)||!pivot_part(w,*b->node))throw std::runtime_error("CanCollideWith requires two live BaseParts");
        Node* root=part_collision_world(w,*a->node);
        if(!root||root!=part_collision_world(w,*b->node))throw std::runtime_error("CanCollideWith requires parts in the same WorldRoot");
        for(auto* node:{a->node,b->node}) {
            const auto* collide=property_value(w,*node,"CanCollide");
            if(!collide||!collide->is_boolean())throw std::runtime_error("part CanCollide is unavailable");
            if(!collide->get<bool>()){lua_pushboolean(L,false);return 1;}
        }
        auto table=read_collision_groups(w,collision_query_root(w,*root));
        lua_pushboolean(L,collision_pair(table,part_collision_group(w,*a->node),part_collision_group(w,*b->node),true));return 1;
    }catch(const std::exception& e){return luaL_error(L,"CanCollideWith: %s",e.what()),0;}
}
bool collision_groups_index(lua_State* L,World& w,Node& n,const std::string& key) {
    if(pivot_part(w,n)&&key=="CanCollideWith"){lua_pushcfunction(L,part_can_collide_with,"CanCollideWith");return true;}
    if(pivot_part(w,n)&&key=="CollisionGroupId"){lua_pushinteger(L,part_collision_id(w,n));return true;}
    const bool service=n.class_name=="PhysicsService";
    if(!service&&!collision_world_root(n))return false;
    bool supported=false;
    for(const char* method:{"GetMaxCollisionGroups","GetRegisteredCollisionGroups","IsCollisionGroupRegistered","CollisionGroupsAreCollidable","RegisterCollisionGroup","UnregisterCollisionGroup","RenameCollisionGroup","CollisionGroupSetCollidable"})if(key==method)supported=true;
    if(service)for(const char* method:{"GetCollisionGroups","GetCollisionGroupId","GetCollisionGroupName","CollisionGroupContainsPart","SetPartCollisionGroup","CreateCollisionGroup","RemoveCollisionGroup"})if(key==method)supported=true;
    if(!supported)return false;
    lua_pushlstring(L,key.data(),key.size());lua_pushcclosure(L,collision_group_method,key.c_str(),1);return true;
}
