#include <cstdint>
#include <cstring>
#include <iterator>
#include <stdexcept>
#include <string>
#include <vector>
// Included after export_enums.inc declarations and installer in the runtime translation unit.
// SecurityCapabilities here is deliberately a serializable value container only.
// It never changes script identity, access checks, or engine permissions.
constexpr const char* kUsiSecurityCapabilitiesMeta="WorldSnapshot.USSI.SecurityCapabilities";
constexpr int kUsiSecurityCapabilityKind=0;
struct UsiSecurityCapabilitiesValue { uint64_t words[1]; };
static UsiExportItemRef* usi_check_security_capability(lua_State* L,int index) {
    auto* item=static_cast<UsiExportItemRef*>(luaL_checkudata(L,index,kUsiExportItemMeta));
    if(item->kind!=kUsiSecurityCapabilityKind) luaL_error(L,"Enum.SecurityCapability item required");
    return item;
}
static int usi_security_capabilities_readonly(lua_State* L) { luaL_error(L,"SecurityCapabilities values are immutable");return 0; }
static int usi_security_capabilities_new(lua_State* L) {
    const int argc=lua_gettop(L);
    auto* result=static_cast<UsiSecurityCapabilitiesValue*>(lua_newuserdatatagged(L,sizeof(UsiSecurityCapabilitiesValue),0));
    result->words[0]=0;
    for(int i=1;i<=argc;++i) { auto* item=usi_check_security_capability(L,i); result->words[0]|=(uint64_t(1)<<item->item); }
    luaL_getmetatable(L,kUsiSecurityCapabilitiesMeta);lua_setmetatable(L,-2);return 1;
}
static int usi_security_capabilities_tostring(lua_State* L) {
    auto* value=static_cast<UsiSecurityCapabilitiesValue*>(luaL_checkudata(L,1,kUsiSecurityCapabilitiesMeta));
    std::string out;
    const auto& caps=kUsiExportEnums[kUsiSecurityCapabilityKind];
    for(size_t i=0;i<caps.count;++i) if(value->words[0]&(uint64_t(1)<<i)) { if(!out.empty())out += " | "; out += caps.items[i].name; }
    lua_pushlstring(L,out.data(),out.size());return 1;
}
static int usi_security_capabilities_equal(lua_State* L) {
    auto* a=static_cast<UsiSecurityCapabilitiesValue*>(luaL_checkudata(L,1,kUsiSecurityCapabilitiesMeta));
    auto* b=has_meta(L,2,kUsiSecurityCapabilitiesMeta)?static_cast<UsiSecurityCapabilitiesValue*>(lua_touserdata(L,2)):nullptr;
    lua_pushboolean(L,b && a->words[0]==b->words[0]);return 1;
}
static void install_ussi_security_capabilities(lua_State* L,int globals) {
    globals=lua_absindex(L,globals);
    luaL_newmetatable(L,kUsiSecurityCapabilitiesMeta);lua_pushcfunction(L,usi_security_capabilities_tostring,"SecurityCapabilities.__tostring");lua_setfield(L,-2,"__tostring");lua_pushcfunction(L,usi_security_capabilities_equal,"SecurityCapabilities.__eq");lua_setfield(L,-2,"__eq");lua_pushcfunction(L,usi_security_capabilities_readonly,"SecurityCapabilities.__newindex");lua_setfield(L,-2,"__newindex");lua_pushliteral(L,"SecurityCapabilities");lua_setfield(L,-2,"__type");lua_pushliteral(L,"The metatable is locked");lua_setfield(L,-2,"__metatable");lua_pop(L,1);
    lua_createtable(L,0,1);lua_pushcfunction(L,usi_security_capabilities_new,"SecurityCapabilities.new");lua_setfield(L,-2,"new");lua_setreadonly(L,-1,true);lua_setfield(L,globals,"SecurityCapabilities");
}

static bool push_ussi_security_capabilities_json(lua_State* L,const Json& value) {
    if(!value.is_object()||value.size()!=1||!value.contains("$securityCapabilities"))return false;
    const auto& list=value["$securityCapabilities"];
    if(!list.is_array())throw std::runtime_error("invalid SecurityCapabilities payload");
    std::vector<int> indices;indices.reserve(list.size());
    const auto& caps=kUsiExportEnums[kUsiSecurityCapabilityKind];
    for(const auto& item:list) {
        if(!item.is_object()||!item.contains("name")||!item["name"].is_string()||!item.contains("value")||!item["value"].is_number_integer())throw std::runtime_error("invalid SecurityCapability item");
        int found=-1;for(size_t i=0;i<caps.count;++i)if(item["value"]==caps.items[i].value&&item["name"]==caps.items[i].name){found=(int)i;break;}
        if(found<0)throw std::runtime_error("unknown SecurityCapability name/value pair");
        indices.push_back(found);
    }
    auto* result=static_cast<UsiSecurityCapabilitiesValue*>(lua_newuserdatatagged(L,sizeof(UsiSecurityCapabilitiesValue),0));result->words[0]=0;
    for(int i:indices)result->words[0]|=(uint64_t(1)<<i);
    luaL_getmetatable(L,kUsiSecurityCapabilitiesMeta);lua_setmetatable(L,-2);return true;
}
static bool capture_ussi_security_capabilities(lua_State* L,int index,Json& out) {
    if(!has_meta(L,index,kUsiSecurityCapabilitiesMeta))return false;
    auto* value=static_cast<UsiSecurityCapabilitiesValue*>(lua_touserdata(L,index));Json list=Json::array();const auto& caps=kUsiExportEnums[kUsiSecurityCapabilityKind];
    for(size_t i=0;i<caps.count;++i)if(value->words[0]&(uint64_t(1)<<i))list.push_back(Json{{"name",caps.items[i].name},{"value",caps.items[i].value}});
    out=Json{{"$securityCapabilities",std::move(list)}};return true;
}
