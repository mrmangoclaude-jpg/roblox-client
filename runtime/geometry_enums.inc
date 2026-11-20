// Typed enums used by the public geometry API. Included after has_meta().
// Names and integer values follow Roblox creator-docs' Axis, NormalId and
// RotationOrder references. Items are canonical per VM, including table keys.
constexpr const char* kGeometryItemMeta="WorldSnapshot.Geometry.EnumItem";
constexpr const char* kGeometryEnumMeta="WorldSnapshot.Geometry.Enum";
constexpr const char* kGeometryEnumsRegistry="Headless.GeometryEnums";
constexpr const char* kGeometryItemsRegistry="Headless.GeometryEnumItems";
enum GeometryEnumKind { kGeometryAxis, kGeometryNormal, kGeometryRotationOrder,
                        kGuiSizeConstraint, kGuiAutomaticSize, kGuiAspectType, kGuiDominantAxis, kClientFont, kClientMessageType,
                        kGeometryTweenStyle, kGeometryEasingDirection, kTweenPlaybackState, kRenderPriority, kPartType, kActuatorRelativeTo, kVelocityConstraintMode, kForceLimitMode, kFontWeight, kFontStyle,
                        kGuiFillDirection, kGuiHorizontalAlignment, kGuiVerticalAlignment, kGuiSortOrder, kGuiFlexAlignment, kGuiItemLineAlignment,
                        kTextXAlignment, kTextYAlignment, kTextDirection,
                        kGuiScrollingDirection, kGuiScrollBarInset, kGuiVerticalScrollBarPosition, kGuiFlexMode, kGuiStartCorner, kRaycastFilterType, kTextTruncate,
                        kApplyStrokeMode, kStrokeSizingMode, kBorderStrokePosition, kLineJoinMode, kGradientTileMode, kGradientType,
                        kImageScaleType, kImageResamplerMode, kCompressionAlgorithm, kHashAlgorithm };
struct GeometryEnumSpec { const char* name; int count; std::array<const char*,64> names; std::array<int,64> values{}; bool mapped=false; };
constexpr GeometryEnumSpec kGeometryEnums[] = {
    {"Axis",3,{"X","Y","Z"}},
    {"NormalId",6,{"Right","Top","Back","Left","Bottom","Front"}},
    {"RotationOrder",6,{"XYZ","XZY","YZX","YXZ","ZXY","ZYX"}},
    {"SizeConstraint",3,{"RelativeXY","RelativeXX","RelativeYY"}},
    {"AutomaticSize",4,{"None","X","Y","XY"}},
    {"AspectType",2,{"FitWithinMaxSize","ScaleWithParentSize"}},
    {"DominantAxis",2,{"Width","Height"}},
    {"Font",53,{"Legacy","Arial","ArialBold","SourceSans","SourceSansBold","SourceSansLight","SourceSansItalic","Bodoni","Garamond","Cartoon","Code","Highway","SciFi","Arcade","Fantasy","Antique","SourceSansSemibold","Gotham","GothamMedium","GothamBold","GothamBlack","AmaticSC","Bangers","Creepster","DenkOne","Fondamento","FredokaOne","GrenzeGotisch","IndieFlower","JosefinSans","Jura","Kalam","LuckiestGuy","Merriweather","Michroma","Nunito","Oswald","PatrickHand","PermanentMarker","Roboto","RobotoCondensed","RobotoMono","Sarpanch","SpecialElite","TitilliumWeb","Ubuntu","BuilderSans","BuilderSansMedium","BuilderSansBold","BuilderSansExtraBold","Arimo","ArimoBold","Unknown"},{0,1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16,17,18,19,20,21,22,23,24,25,26,27,28,29,30,31,32,33,34,35,36,37,38,39,40,41,42,43,44,45,46,47,48,49,50,51,100},true},
    {"MessageType",4,{"MessageOutput","MessageInfo","MessageWarning","MessageError"},{0,1,2,3},true},
    {"EasingStyle",13,{"Linear","Sine","Back","Quad","Quart","Quint","Bounce","Elastic","Exponential","Circular","Cubic","Bezier","Spring"}},
    {"EasingDirection",3,{"In","Out","InOut"}},
    {"PlaybackState",6,{"Begin","Delayed","Playing","Paused","Completed","Cancelled"}},
    {"RenderPriority",5,{"First","Input","Camera","Character","Last"},{0,100,200,300,2000},true},
    {"PartType",6,{"Ball","Block","Cylinder","Wedge","CornerWedge","Capsule"}},
    {"ActuatorRelativeTo",3,{"Attachment0","Attachment1","World"}},
    {"VelocityConstraintMode",3,{"Line","Plane","Vector"}},
    {"ForceLimitMode",2,{"Magnitude","PerAxis"}},
    {"FontWeight",9,{"Thin","ExtraLight","Light","Regular","Medium","SemiBold","Bold","ExtraBold","Heavy"},{100,200,300,400,500,600,700,800,900},true},
    {"FontStyle",2,{"Normal","Italic"}},
    {"FillDirection",2,{"Horizontal","Vertical"}},
    {"HorizontalAlignment",3,{"Center","Left","Right"}},
    {"VerticalAlignment",3,{"Center","Top","Bottom"}},
    {"SortOrder",3,{"Name","Custom","LayoutOrder"}},
    {"UIFlexAlignment",5,{"None","Fill","SpaceAround","SpaceBetween","SpaceEvenly"}},
    {"ItemLineAlignment",5,{"Automatic","Start","Center","End","Stretch"}},
    {"TextXAlignment",3,{"Left","Right","Center"}},
    {"TextYAlignment",3,{"Top","Center","Bottom"}},
    {"TextDirection",3,{"Auto","LeftToRight","RightToLeft"}},
    {"ScrollingDirection",3,{"X","Y","XY"},{1,2,4},true},
    {"ScrollBarInset",3,{"None","ScrollBar","Always"}},
    {"VerticalScrollBarPosition",2,{"Right","Left"}},
    {"UIFlexMode",5,{"None","Grow","Shrink","Fill","Custom"}},
    {"StartCorner",4,{"TopLeft","TopRight","BottomLeft","BottomRight"}},
    {"RaycastFilterType",2,{"Exclude","Include"}},
    {"TextTruncate",3,{"None","AtEnd","SplitWord"}},
    {"ApplyStrokeMode",2,{"Contextual","Border"}},
    {"StrokeSizingMode",2,{"FixedSize","ScaledSize"}},
    {"BorderStrokePosition",3,{"Outer","Center","Inner"}},
    {"LineJoinMode",3,{"Round","Bevel","Miter"}},
    {"GradientTileMode",3,{"Clamp","Repeat","Mirror"}},
    {"GradientType",4,{"Linear","Radial","Conical","Elliptical"}},
    {"ScaleType",5,{"Stretch","Slice","Tile","Fit","Crop"}},
    {"ResamplerMode",2,{"Default","Pixelated"}},
    {"CompressionAlgorithm",1,{"Zstd"}},
    {"HashAlgorithm",5,{"Blake2b","Blake3","Md5","Sha1","Sha256"}},
};
int geometry_numeric(int kind,int index){return kGeometryEnums[kind].mapped?kGeometryEnums[kind].values[index]:index;}
struct GeometryEnumItem { int kind; int value; };

std::string geometry_enum_key(lua_State* L,int index) {
    size_t length;const char* s=luaL_checklstring(L,index,&length);
    return std::string(s,length);
}
void push_geometry_enum(lua_State* L,int kind) {
    lua_getfield(L,LUA_REGISTRYINDEX,kGeometryEnumsRegistry);
    lua_rawgeti(L,-1,kind+1);lua_remove(L,-2);
}
void push_geometry_item(lua_State* L,int kind,int value) {
    lua_getfield(L,LUA_REGISTRYINDEX,kGeometryItemsRegistry);
    lua_rawgeti(L,-1,kind*64+value+1);lua_remove(L,-2);
}
int checked_geometry_value(lua_State* L,int index,int kind) {
    if(lua_isnoneornil(L,index))luaL_error(L,"Argument %d missing or nil",index);
    if(!has_meta(L,index,kGeometryItemMeta)) {
        const char* cn=luaL_typename(L,index);
        if(lua_type(L,index)==LUA_TNUMBER)cn="double";
        else if(lua_type(L,index)==LUA_TBOOLEAN)cn="bool";
        luaL_error(L,"Unable to cast %s to %s",cn,kGeometryEnums[kind].name);
    }
    auto* item=static_cast<GeometryEnumItem*>(lua_touserdata(L,index));
    if(item->kind!=kind)luaL_error(L,"Unable to cast %s to %s",kGeometryEnums[item->kind].name,kGeometryEnums[kind].name);
    return item->value;
}
// Assigning to an Enum or EnumItem reads as a missing member in Roblox.
int geometry_enum_readonly(lua_State* L) { luaL_error(L,"%s is not a valid member of Enum",lua_tostring(L,2)?lua_tostring(L,2):"?");return 0; }
int geometry_item_readonly(lua_State* L) { luaL_error(L,"%s is not a valid member of EnumItem",lua_tostring(L,2)?lua_tostring(L,2):"?");return 0; }
// Receiver of an Enum member function: "invalid argument #1 to 'FromValue' (Enum expected, got number)".
int geometry_enum_kind(lua_State* L,int index) {
    if(!has_meta(L,index,kGeometryEnumMeta))luaL_typeerror(L,index,"Enum");
    return *static_cast<int*>(lua_touserdata(L,index));
}
int geometry_item_index(lua_State* L) {
    auto* item=static_cast<GeometryEnumItem*>(luaL_checkudata(L,1,kGeometryItemMeta));
    auto key=geometry_enum_key(L,2);
    if(key=="Name")lua_pushstring(L,kGeometryEnums[item->kind].names[item->value]);
    else if(key=="Value")lua_pushinteger(L,geometry_numeric(item->kind,item->value));
    else if(key=="EnumType")push_geometry_enum(L,item->kind);
    else if(key=="IsA")lua_pushcfunction(L,[](lua_State* S)->int{
        if(!has_meta(S,1,kGeometryItemMeta))luaL_typeerror(S,1,"EnumItem");
        luaL_checkstring(S,2);lua_pushboolean(S,0);return 1;},"IsA");
    else luaL_error(L,"%s is not a valid member of \"Enum.%s.%s\"",key.c_str(),kGeometryEnums[item->kind].name,kGeometryEnums[item->kind].names[item->value]);
    return 1;
}
int geometry_item_string(lua_State* L) {
    auto* item=static_cast<GeometryEnumItem*>(luaL_checkudata(L,1,kGeometryItemMeta));
    lua_pushfstring(L,"Enum.%s.%s",kGeometryEnums[item->kind].name,kGeometryEnums[item->kind].names[item->value]);
    return 1;
}
int geometry_item_equal(lua_State* L) {
    auto* a=static_cast<GeometryEnumItem*>(luaL_checkudata(L,1,kGeometryItemMeta));
    auto* b=has_meta(L,2,kGeometryItemMeta)?static_cast<GeometryEnumItem*>(lua_touserdata(L,2)):nullptr;
    lua_pushboolean(L,b&&a->kind==b->kind&&a->value==b->value);return 1;
}
int geometry_enum_items(lua_State* L) {
    int kind=geometry_enum_kind(L,1);
    lua_createtable(L,kGeometryEnums[kind].count,0);
    for(int i=0;i<kGeometryEnums[kind].count;++i){push_geometry_item(L,kind,i);lua_rawseti(L,-2,i+1);}
    return 1;
}
int geometry_enum_from_name(lua_State* L) {
    int kind=geometry_enum_kind(L,1);
    if(lua_type(L,2)!=LUA_TSTRING)luaL_typeerror(L,2,"string");
    auto name=geometry_enum_key(L,2);
    if(kind==kRaycastFilterType&&(name=="Blacklist"||name=="Whitelist")) {
        push_geometry_item(L,kind,name=="Whitelist"?1:0);return 1;
    }
    for(int i=0;i<kGeometryEnums[kind].count;++i)
        if(name==kGeometryEnums[kind].names[i]){push_geometry_item(L,kind,i);return 1;}
    lua_pushnil(L);return 1;
}
int geometry_enum_from_value(lua_State* L) {
    int kind=geometry_enum_kind(L,1);
    if(lua_type(L,2)!=LUA_TNUMBER)luaL_typeerror(L,2,"number");
    double value=std::trunc(lua_tonumber(L,2));
    for(int i=0;i<kGeometryEnums[kind].count;++i)if(value==geometry_numeric(kind,i)){push_geometry_item(L,kind,i);return 1;}
    lua_pushnil(L);
    return 1;
}
int geometry_enum_index(lua_State* L) {
    int kind=*static_cast<int*>(luaL_checkudata(L,1,kGeometryEnumMeta));
    auto name=geometry_enum_key(L,2);
    if(kind==kRaycastFilterType&&(name=="Blacklist"||name=="Whitelist")) {
        push_geometry_item(L,kind,name=="Whitelist"?1:0);return 1;
    }
    if(name=="GetEnumItems")lua_pushcfunction(L,geometry_enum_items,"GetEnumItems");
    else if(name=="FromName")lua_pushcfunction(L,geometry_enum_from_name,"FromName");
    else if(name=="FromValue")lua_pushcfunction(L,geometry_enum_from_value,"FromValue");
    else {
        for(int i=0;i<kGeometryEnums[kind].count;++i)
            if(name==kGeometryEnums[kind].names[i]){push_geometry_item(L,kind,i);return 1;}
        luaL_error(L,"%s is not a valid member of \"Enum.%s\"",name.c_str(),kGeometryEnums[kind].name);
    }
    return 1;
}
int geometry_enum_string(lua_State* L) {
    int kind=*static_cast<int*>(luaL_checkudata(L,1,kGeometryEnumMeta));
    lua_pushstring(L,kGeometryEnums[kind].name);return 1;
}
void geometry_enum_method(lua_State* L,const char* name,lua_CFunction f) {
    lua_pushcfunction(L,f,name);lua_setfield(L,-2,name);
}
void install_geometry_enums(lua_State* L) {
    int root=lua_gettop(L); // existing Enum table retains animation/chat enums
    lua_getfield(L,LUA_REGISTRYINDEX,kGeometryEnumsRegistry);
    const bool installed=lua_istable(L,-1);lua_pop(L,1);
    if(installed) {
        // Authored values also work without a World. Reuse their canonical
        // enums when world installation extends the root later in startup.
        for(int kind=0;kind<int(std::size(kGeometryEnums));++kind) {
            push_geometry_enum(L,kind);lua_setfield(L,root,kGeometryEnums[kind].name);
        }
        return;
    }
    luaL_newmetatable(L,kGeometryItemMeta);
    geometry_enum_method(L,"__index",geometry_item_index);
    geometry_enum_method(L,"__newindex",geometry_item_readonly);
    geometry_enum_method(L,"__tostring",geometry_item_string);
    geometry_enum_method(L,"__eq",geometry_item_equal);
    lua_pushliteral(L,"EnumItem");lua_setfield(L,-2,"__type");
    lua_pushliteral(L,"The metatable is locked");lua_setfield(L,-2,"__metatable");lua_pop(L,1);
    luaL_newmetatable(L,kGeometryEnumMeta);
    geometry_enum_method(L,"__index",geometry_enum_index);
    geometry_enum_method(L,"__newindex",geometry_enum_readonly);
    geometry_enum_method(L,"__tostring",geometry_enum_string);
    lua_pushliteral(L,"Enum");lua_setfield(L,-2,"__type");
    lua_pushliteral(L,"The metatable is locked");lua_setfield(L,-2,"__metatable");lua_pop(L,1);
    lua_newtable(L);int enums=lua_gettop(L);
    lua_newtable(L);int items=lua_gettop(L);
    for(int kind=0;kind<int(std::size(kGeometryEnums));++kind) {
        *static_cast<int*>(lua_newuserdatatagged(L,sizeof(int),0))=kind;
        luaL_getmetatable(L,kGeometryEnumMeta);lua_setmetatable(L,-2);
        lua_pushvalue(L,-1);lua_setfield(L,root,kGeometryEnums[kind].name);
        lua_rawseti(L,enums,kind+1);
        for(int value=0;value<kGeometryEnums[kind].count;++value) {
            auto* item=static_cast<GeometryEnumItem*>(lua_newuserdatatagged(L,sizeof(GeometryEnumItem),0));
            *item={kind,value};luaL_getmetatable(L,kGeometryItemMeta);lua_setmetatable(L,-2);
            lua_rawseti(L,items,kind*64+value+1);
        }
    }
    lua_setreadonly(L,enums,true);lua_setreadonly(L,items,true);
    lua_setfield(L,LUA_REGISTRYINDEX,kGeometryItemsRegistry);
    lua_setfield(L,LUA_REGISTRYINDEX,kGeometryEnumsRegistry);
}

bool push_geometry_enum_json(lua_State* L,const Json& value) {
    if(!value.is_object()||value.size()!=1||!value.contains("$enum"))return false;
    const auto& e=value["$enum"];
    if(!e.is_object()||!e.contains("type")||!e["type"].is_string())return false;
    for(int kind=0;kind<int(std::size(kGeometryEnums));++kind)if(e["type"]==kGeometryEnums[kind].name) {
        if(!e.contains("value")||!e["value"].is_number_integer())throw std::runtime_error("invalid geometry enum value");
        // Compare as JSON numbers before narrowing an externally supplied value.
        int v=-1;for(int i=0;i<kGeometryEnums[kind].count;++i)if(e["value"]==geometry_numeric(kind,i)){v=i;break;}
        if(v<0)throw std::runtime_error("unknown geometry enum value");
        if(e.contains("name")&&e["name"]!=kGeometryEnums[kind].names[v])throw std::runtime_error("geometry enum name/value mismatch");
        push_geometry_item(L,kind,v);return true;
    }
    return false;
}
bool capture_geometry_enum(lua_State* L,int index,Json& output) {
    if(!has_meta(L,index,kGeometryItemMeta))return false;
    auto* item=static_cast<GeometryEnumItem*>(lua_touserdata(L,index));
    output=Json{{"$enum",Json{{"type",kGeometryEnums[item->kind].name},
        {"name",kGeometryEnums[item->kind].names[item->value]},{"value",geometry_numeric(item->kind,item->value)}}}};
    return true;
}
int vector3_from_axis(lua_State* L) {
    int axis=checked_geometry_value(L,1,kGeometryAxis);
    lua_pushvector(L,axis==0,axis==1,axis==2);return 1;
}
int vector3_from_normal(lua_State* L) {
    int face=checked_geometry_value(L,1,kGeometryNormal);
    int axis=face%3,sign=face<3?1:-1;
    lua_pushvector(L,axis==0?sign:0,axis==1?sign:0,axis==2?sign:0);return 1;
}
void install_geometry_vector_constructors(lua_State* L) {
    geometry_enum_method(L,"FromAxis",vector3_from_axis);
    geometry_enum_method(L,"FromNormalId",vector3_from_normal);
    geometry_enum_method(L,"fromAxis",vector3_from_axis);
    geometry_enum_method(L,"fromNormalId",vector3_from_normal);
    lua_getglobal(L,"vector");
    lua_getfield(L,-1,"min"); lua_setfield(L,-3,"min");
    lua_getfield(L,-1,"max"); lua_setfield(L,-3,"max");
    lua_pop(L,1);
}
