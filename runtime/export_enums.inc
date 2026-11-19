#include <cstdint>
#include <cstring>
#include <iterator>
#include <stdexcept>
#include <string>
#include <vector>
// Verified Roblox Creator Docs enum metadata, pinned in outputs/ussi-analysis/creator-docs-provenance.json.
// Included in the runtime translation unit after Lua C API helpers are declared.
struct ExportEnumEntry { const char* name; int value; };
struct ExportEnumSpec { const char* name; const ExportEnumEntry* items; size_t count; };
static const ExportEnumEntry kUsiSecurityCapabilityItems[] = {
    {"RunClientScript", 0},
    {"RunServerScript", 1},
    {"AccessOutsideWrite", 2},
    {"AssetRequire", 3},
    {"LoadString", 4},
    {"ScriptGlobals", 5},
    {"CreateInstances", 6},
    {"Basic", 7},
    {"Audio", 8},
    {"DataStore", 9},
    {"Network", 10},
    {"Physics", 11},
    {"UI", 12},
    {"CSG", 13},
    {"Chat", 14},
    {"Animation", 15},
    {"Avatar", 16},
    {"Input", 17},
    {"Environment", 18},
    {"RemoteEvent", 19},
    {"LegacySound", 20},
    {"Players", 21},
    {"CapabilityControl", 22},
    {"Plugin", 23},
    {"LocalUser", 24},
    {"WritePlayer", 25},
    {"RobloxScript", 26},
    {"RobloxEngine", 27},
    {"Unassigned", 28},
    {"InternalTest", 29},
    {"PluginOrOpenCloud", 30},
    {"Assistant", 31},
    {"RemoteCommand", 32},
    {"AssetRead", 33},
    {"AssetManagement", 34},
    {"DynamicGeneration", 35},
    {"PlatformAvatarEditing", 36},
    {"AssetCreateUpdate", 37},
    {"Capture", 38},
    {"SensitiveInput", 39},
    {"Monetization", 40},
    {"LoadOwnedAsset", 41},
    {"Social", 42},
    {"ServerCommunication", 43},
    {"Logging", 44},
    {"PromptExternalPurchase", 45},
    {"Groups", 46},
    {"Teleport", 47},
    {"Consequences", 48},
    {"Material", 49},
    {"AvatarBehavior", 50},
    {"AvatarAppearance", 51},
    {"LoadUnownedAsset", 52},
};
static const ExportEnumEntry kUsiMaterialItems[] = {
    {"Plastic", 256},
    {"SmoothPlastic", 272},
    {"Neon", 288},
    {"Wood", 512},
    {"WoodPlanks", 528},
    {"Marble", 784},
    {"Basalt", 788},
    {"Slate", 800},
    {"CrackedLava", 804},
    {"Concrete", 816},
    {"Limestone", 820},
    {"Granite", 832},
    {"Pavement", 836},
    {"Brick", 848},
    {"Pebble", 864},
    {"Cobblestone", 880},
    {"Rock", 896},
    {"Sandstone", 912},
    {"CorrodedMetal", 1040},
    {"DiamondPlate", 1056},
    {"Foil", 1072},
    {"Metal", 1088},
    {"Grass", 1280},
    {"LeafyGrass", 1284},
    {"Sand", 1296},
    {"Fabric", 1312},
    {"Snow", 1328},
    {"Mud", 1344},
    {"Ground", 1360},
    {"Asphalt", 1376},
    {"Salt", 1392},
    {"Ice", 1536},
    {"Glacier", 1552},
    {"Glass", 1568},
    {"ForceField", 1584},
    {"Air", 1792},
    {"Water", 2048},
    {"Cardboard", 2304},
    {"Carpet", 2305},
    {"CeramicTiles", 2306},
    {"ClayRoofTiles", 2307},
    {"RoofShingles", 2308},
    {"Leather", 2309},
    {"Plaster", 2310},
    {"Rubber", 2311},
};
static const ExportEnumEntry kUsiCollisionFidelityItems[] = {
    {"Default", 0},
    {"Hull", 1},
    {"Box", 2},
    {"PreciseConvexDecomposition", 3},
    {"Tunable", 4},
};
#include "input_enum_data.inc"
#include "player_enum_data.inc"
// Roblox creator-docs/enums/BulkMoveMode.yaml, checked with BulkMoveTo.
static const ExportEnumEntry kBulkMoveModeItems[] = {
    {"FireAllEvents", 0}, {"FireCFrameChanged", 1},
};
static const ExportEnumEntry kMeshTypeItems[] = {
    {"Head",0},{"Torso",1},{"Wedge",2},{"Sphere",3},{"Cylinder",4},{"FileMesh",5},
    {"Brick",6},{"Prism",7},{"Pyramid",8},{"ParallelRamp",9},{"RightAngleRamp",10},{"CornerWedge",11},
};
constexpr int kExportEnumStride=512;
static_assert(std::size(kInputKeyCodeItems)<kExportEnumStride,"enum registry stride must fit KeyCode");
static const ExportEnumSpec kUsiExportEnums[] = {
#include "player_enum_specs.inc"
    {"SecurityCapability", kUsiSecurityCapabilityItems, std::size(kUsiSecurityCapabilityItems)},
    {"Material", kUsiMaterialItems, std::size(kUsiMaterialItems)},
    {"CollisionFidelity", kUsiCollisionFidelityItems, std::size(kUsiCollisionFidelityItems)},
    {"MouseBehavior", kInputMouseBehaviorItems, std::size(kInputMouseBehaviorItems)},
    {"UserInputState", kInputUserInputStateItems, std::size(kInputUserInputStateItems)},
    {"UserInputType", kInputUserInputTypeItems, std::size(kInputUserInputTypeItems)},
    {"KeyCode", kInputKeyCodeItems, std::size(kInputKeyCodeItems)},
    {"ContextActionPriority", kInputContextActionPriorityItems, std::size(kInputContextActionPriorityItems)},
    {"ContextActionResult", kInputContextActionResultItems, std::size(kInputContextActionResultItems)},
    {"PlayerActions", kInputPlayerActionsItems, std::size(kInputPlayerActionsItems)},
    {"BulkMoveMode", kBulkMoveModeItems, std::size(kBulkMoveModeItems)},
    {"MeshType", kMeshTypeItems, std::size(kMeshTypeItems)},


};
constexpr const char* kUsiExportEnumMeta = "WorldSnapshot.USSI.Enum";
constexpr const char* kUsiExportItemMeta = "WorldSnapshot.USSI.EnumItem";
constexpr const char* kUsiExportEnumsRegistry = "Headless.USSI.Enums";
constexpr const char* kUsiExportItemsRegistry = "Headless.USSI.EnumItems";
// Studio 0.745 exposes Unknown as a legacy alias of KeyCode.None.
static bool export_enum_name_matches(int kind,size_t item,const char* key,size_t n) {
    const char* name=kUsiExportEnums[kind].items[item].name;
    return (strlen(name)==n&&!memcmp(key,name,n)) ||
        (!strcmp(kUsiExportEnums[kind].name,"KeyCode")&&item==0&&n==7&&!memcmp(key,"Unknown",7));
}
struct UsiExportEnumRef { int kind; };
struct UsiExportItemRef { int kind; int item; };
static int usi_export_kind(lua_State* L, int i) {
    // Roblox words a wrong receiver as "invalid argument #1 to 'FromValue' (Enum expected, got number)".
    bool ok = false;
    if (lua_type(L, i) == LUA_TUSERDATA && lua_getmetatable(L, i)) {
        luaL_getmetatable(L, kUsiExportEnumMeta);
        ok = lua_rawequal(L, -1, -2) != 0;
        lua_pop(L, 2);
    }
    if (!ok) luaL_typeerror(L, i, "Enum");
    return static_cast<UsiExportEnumRef*>(lua_touserdata(L, i))->kind;
}
static int usi_export_item_index(lua_State* L) {
    auto* ref = static_cast<UsiExportItemRef*>(luaL_checkudata(L, 1, kUsiExportItemMeta));
    size_t n=0; const char* key=luaL_checklstring(L,2,&n);
    const auto& spec=kUsiExportEnums[ref->kind]; const auto& item=spec.items[ref->item];
    if(n==4 && !memcmp(key,"Name",4)) lua_pushstring(L,item.name);
    else if(n==5 && !memcmp(key,"Value",5)) lua_pushinteger(L,item.value);
    else if(n==8 && !memcmp(key,"EnumType",8)) {
        lua_getfield(L,LUA_REGISTRYINDEX,kUsiExportEnumsRegistry); lua_rawgeti(L,-1,ref->kind+1); lua_remove(L,-2);
    } else if(n==3 && !memcmp(key,"IsA",3)) {
        lua_pushcfunction(L,[](lua_State* S)->int{
            // IsA(EnumItem, className): the receiver and a class name are required; an enum item is never any class.
            bool receiver=false;
            if(lua_type(S,1)==LUA_TUSERDATA&&lua_getmetatable(S,1)){luaL_getmetatable(S,kUsiExportItemMeta);receiver=lua_rawequal(S,-1,-2)!=0;lua_pop(S,2);}
            if(!receiver)luaL_typeerror(S,1,"EnumItem");
            luaL_checkstring(S,2);
            lua_pushboolean(S,0); return 1; },"IsA");
    } else luaL_error(L,"%s is not a valid member of \"Enum.%s.%s\"",key,spec.name,item.name);
    return 1;
}
static int usi_export_item_tostring(lua_State* L) {
    auto* ref=static_cast<UsiExportItemRef*>(luaL_checkudata(L,1,kUsiExportItemMeta));
    lua_pushfstring(L,"Enum.%s.%s",kUsiExportEnums[ref->kind].name,kUsiExportEnums[ref->kind].items[ref->item].name); return 1;
}
static int usi_export_item_equal(lua_State* L) {
    auto* a=static_cast<UsiExportItemRef*>(luaL_checkudata(L,1,kUsiExportItemMeta));
    auto* b=has_meta(L,2,kUsiExportItemMeta)?static_cast<UsiExportItemRef*>(lua_touserdata(L,2)):nullptr;
    lua_pushboolean(L,b && a->kind==b->kind && a->item==b->item); return 1;
}
static int usi_export_enum_index(lua_State* L) {
    int kind=usi_export_kind(L,1); size_t n=0; const char* key=luaL_checklstring(L,2,&n);
    if(n==12 && !memcmp(key,"GetEnumItems",12)) { lua_pushcfunction(L,[](lua_State* S)->int {
        int k=usi_export_kind(S,1); lua_createtable(S,kUsiExportEnums[k].count,0);
        for(size_t i=0;i<kUsiExportEnums[k].count;++i) { lua_getfield(S,LUA_REGISTRYINDEX,kUsiExportItemsRegistry); lua_rawgeti(S,-1,k*kExportEnumStride+(int)i+1); lua_remove(S,-2); lua_rawseti(S,-2,(int)i+1); } return 1;
    },"GetEnumItems"); return 1; }
    if(n==8 && !memcmp(key,"FromName",8)) { lua_pushcfunction(L,[](lua_State* S)->int { int k=usi_export_kind(S,1); size_t z=0;if(lua_type(S,2)!=LUA_TSTRING)luaL_typeerror(S,2,"string");const char* q=lua_tolstring(S,2,&z);for(size_t i=0;i<kUsiExportEnums[k].count;++i)if(export_enum_name_matches(k,i,q,z)){lua_getfield(S,LUA_REGISTRYINDEX,kUsiExportItemsRegistry);lua_rawgeti(S,-1,k*kExportEnumStride+(int)i+1);lua_remove(S,-2);return 1;}lua_pushnil(S);return 1; },"FromName"); return 1; }
    if(n==9 && !memcmp(key,"FromValue",9)) { lua_pushcfunction(L,[](lua_State* S)->int { int k=usi_export_kind(S,1); if(lua_type(S,2)!=LUA_TNUMBER)luaL_typeerror(S,2,"number");double v=std::trunc(lua_tonumber(S,2));for(size_t i=0;i<kUsiExportEnums[k].count;++i)if(v==kUsiExportEnums[k].items[i].value){lua_getfield(S,LUA_REGISTRYINDEX,kUsiExportItemsRegistry);lua_rawgeti(S,-1,k*kExportEnumStride+(int)i+1);lua_remove(S,-2);return 1;}lua_pushnil(S);return 1; },"FromValue"); return 1; }
    for(size_t i=0;i<kUsiExportEnums[kind].count;++i) {if(export_enum_name_matches(kind,i,key,n)){lua_getfield(L,LUA_REGISTRYINDEX,kUsiExportItemsRegistry);lua_rawgeti(L,-1,kind*kExportEnumStride+(int)i+1);lua_remove(L,-2);return 1;}}
    luaL_error(L,"%s is not a valid member of \"Enum.%s\"",key,kUsiExportEnums[kind].name);return 0;
}
static int usi_export_enum_tostring(lua_State* L) { lua_pushstring(L,kUsiExportEnums[usi_export_kind(L,1)].name);return 1; }
// Assigning to an Enum or EnumItem reads as a missing member in Roblox.
static int usi_export_enum_readonly(lua_State* L) { luaL_error(L,"%s is not a valid member of Enum",lua_tostring(L,2)?lua_tostring(L,2):"?");return 0; }
static int usi_export_item_readonly(lua_State* L) { luaL_error(L,"%s is not a valid member of EnumItem",lua_tostring(L,2)?lua_tostring(L,2):"?");return 0; }
static void install_ussi_export_enums(lua_State* L, int enumTable) {
    enumTable=lua_absindex(L,enumTable);
    luaL_newmetatable(L,kUsiExportItemMeta); lua_pushcfunction(L,usi_export_item_index,"EnumItem.__index");lua_setfield(L,-2,"__index"); lua_pushcfunction(L,usi_export_item_tostring,"EnumItem.__tostring");lua_setfield(L,-2,"__tostring");lua_pushcfunction(L,usi_export_item_equal,"EnumItem.__eq");lua_setfield(L,-2,"__eq");lua_pushcfunction(L,usi_export_item_readonly,"EnumItem.__newindex");lua_setfield(L,-2,"__newindex");lua_pushliteral(L,"EnumItem");lua_setfield(L,-2,"__type");lua_pushliteral(L,"The metatable is locked");lua_setfield(L,-2,"__metatable");lua_pop(L,1);
    luaL_newmetatable(L,kUsiExportEnumMeta);lua_pushcfunction(L,usi_export_enum_index,"Enum.__index");lua_setfield(L,-2,"__index");lua_pushcfunction(L,usi_export_enum_tostring,"Enum.__tostring");lua_setfield(L,-2,"__tostring");lua_pushcfunction(L,usi_export_enum_readonly,"Enum.__newindex");lua_setfield(L,-2,"__newindex");lua_pushliteral(L,"Enum");lua_setfield(L,-2,"__type");lua_pushliteral(L,"The metatable is locked");lua_setfield(L,-2,"__metatable");lua_pop(L,1);
    lua_createtable(L,(int)std::size(kUsiExportEnums),0); int enums=lua_gettop(L); lua_createtable(L,(int)std::size(kUsiExportEnums)*kExportEnumStride,0);int items=lua_gettop(L);
    for(int k=0;k<(int)std::size(kUsiExportEnums);++k){
        auto* e=(UsiExportEnumRef*)lua_newuserdatatagged(L,sizeof(UsiExportEnumRef),0);e->kind=k;luaL_getmetatable(L,kUsiExportEnumMeta);lua_setmetatable(L,-2);
        lua_pushvalue(L,-1);lua_rawseti(L,enums,k+1);lua_setfield(L,enumTable,kUsiExportEnums[k].name);
        for(size_t i=0;i<kUsiExportEnums[k].count;++i){
            auto* v=(UsiExportItemRef*)lua_newuserdatatagged(L,sizeof(UsiExportItemRef),0);v->kind=k;v->item=(int)i;luaL_getmetatable(L,kUsiExportItemMeta);lua_setmetatable(L,-2);
            lua_pushvalue(L,-1);lua_rawseti(L,items,k*kExportEnumStride+(int)i+1);
            // Enum userdata resolve names through __index and the item registry;
            // assigning fields here invokes their immutable __newindex handler.
            lua_pop(L,1);
        }
    }
    lua_setreadonly(L,enums,true);lua_pushvalue(L,enums);lua_setfield(L,LUA_REGISTRYINDEX,kUsiExportEnumsRegistry);
    lua_setreadonly(L,items,true);lua_setfield(L,LUA_REGISTRYINDEX,kUsiExportItemsRegistry);
    lua_pop(L,1);
}


// Snapshot transport helpers: these preserve both the verified name and numeric ID.
static bool push_ussi_export_enum_json(lua_State* L,const Json& value) {
    if(!value.is_object()||value.size()!=1||!value.contains("$enum"))return false;
    const auto& e=value["$enum"];
    if(!e.is_object()||!e.contains("type")||!e["type"].is_string())return false;
    for(int k=0;k<(int)std::size(kUsiExportEnums);++k)if(e["type"]==kUsiExportEnums[k].name) {
        if(!e.contains("value")||!e["value"].is_number_integer())throw std::runtime_error("invalid USSI enum value");
        int found=-1;for(size_t i=0;i<kUsiExportEnums[k].count;++i)if(e["value"]==kUsiExportEnums[k].items[i].value){found=(int)i;break;}
        if(found<0)throw std::runtime_error("unknown USSI enum value");
        if(e.contains("name")&&(!e["name"].is_string()||!export_enum_name_matches(k,found,e["name"].get_ref<const std::string&>().data(),e["name"].get_ref<const std::string&>().size())))throw std::runtime_error("USSI enum name/value mismatch");
        lua_getfield(L,LUA_REGISTRYINDEX,kUsiExportItemsRegistry);lua_rawgeti(L,-1,k*kExportEnumStride+found+1);lua_remove(L,-2);return true;
    }
    return false;
}
static bool capture_ussi_export_enum(lua_State* L,int index,Json& out) {
    if(!has_meta(L,index,kUsiExportItemMeta))return false;
    auto* ref=static_cast<UsiExportItemRef*>(lua_touserdata(L,index));const auto& e=kUsiExportEnums[ref->kind];const auto& item=e.items[ref->item];
    out=Json{{"$enum",Json{{"type",e.name},{"name",item.name},{"value",item.value}}}};return true;
}
