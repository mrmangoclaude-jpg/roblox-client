// Constructor-default queries and resets. Keep ordinary getters/setters in
// charge of scriptability, typed values, transform coupling, and change events.
namespace property_defaults {
struct Value { std::string key; Json value; bool writable; };

Value read(lua_State* L,Node& node){
    if(lua_gettop(L)<2||lua_isnil(L,2)){luaL_error(L,"Argument 1 missing or nil");}
    luaL_checktype(L,2,LUA_TSTRING);size_t length=0;const char* raw=lua_tolstring(L,2,&length);
    if(!length||length>256||std::memchr(raw,0,length)){
        luaL_error(L,"property name must contain 1 through 256 bytes without NUL");
    }
    std::string key=canonical_instance_member(std::string(raw,length),&node);
    if(key=="archivable")key="Archivable";
    if(key=="ClassName")return {key,node.class_name,false};
    auto cls=constructors().find(node.class_name);
    if(key=="Name"&&cls!=constructors().end()&&cls->contains("name")&&(*cls)["name"].is_string())
        return {key,(*cls)["name"],true};
    if(key=="Parent"&&cls!=constructors().end()&&cls->value("creatable",false))
        return {key,nullptr,true};
    const Json* descriptor=property_descriptor(node,key);
    if(!descriptor||!descriptor->contains("value"))
        throw std::runtime_error("Invalid argument to IsPropertyModified(): Class "+node.class_name+" has no property named `"+key+"`");
    return {key,descriptor->at("value"),descriptor->value("writable",false)};
}

void key_argument(lua_State* L,const std::string& key){
    lua_pushlstring(L,key.data(),key.size());lua_replace(L,2);
}
}

int is_property_modified(lua_State* L){
    Handle* h=checked_handle(L,1);
    try{
        const auto reference=property_defaults::read(L,*h->node);
        property_defaults::key_argument(L,reference.key);
        // Read the real current property, including locally computed values.
        // Unreceived values still raise the normal unavailable-property error.
        instance_index(L);
        const Json current=convert_lua_value(L,*h->world,-1);lua_pop(L,1);
        // Normalize both sides through the native typed-value codec; script
        // replacements of globals such as Color3 cannot affect this path.
        push_json(L,*h->world,reference.value);
        const Json expected=convert_lua_value(L,*h->world,-1);lua_pop(L,1);
        lua_pushboolean(L,current!=expected);return 1;
    }catch(const std::runtime_error& error){luaL_error(L,"%s",error.what());return 0;}
}

int reset_property_to_default(lua_State* L){
    Handle* h=checked_handle(L,1);
    try{
        const auto reference=property_defaults::read(L,*h->node);
        if(!reference.writable)throw std::runtime_error("property is read-only");
        property_defaults::key_argument(L,reference.key);
        push_json(L,*h->world,reference.value);
        return instance_newindex(L);
    }catch(const std::exception& error){luaL_error(L,"ResetPropertyToDefault failed: %s",error.what());return 0;}
}
