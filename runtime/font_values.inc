// Public Font scripting values. Loading/rasterizing font assets is separate.
namespace font_values {
using Json=nlohmann::json;
constexpr const char* meta="LocalLuau.Font";
constexpr size_t family_limit=4096;
struct Value {std::string family;int weight;int style;};
struct Legacy {const char* family;int weight=400;int style=0;};
// Creator Docs Font datatype family table and Enum.Font replacement notes.
constexpr Legacy legacy[]={
    {"LegacyArial"},{"Arimo"},{"Arimo",700},{"SourceSansPro"},
    {"SourceSansPro",700},{"SourceSansPro",300},{"SourceSansPro",400,1},
    {"AccanthisADFStd"},{"Guru"},{"ComicNeueAngular"},{"Inconsolata"},
    {"HighwayGothic"},{"Zekton"},{"PressStart2P"},{"Balthazar"},{"RomanAntique"},
    {"SourceSansPro",600},{"Montserrat"},{"Montserrat",500},{"Montserrat",700},{"Montserrat",900},
    {"AmaticSC"},{"Bangers"},{"Creepster"},{"DenkOne"},{"Fondamento"},{"FredokaOne"},
    {"GrenzeGotisch"},{"IndieFlower"},{"JosefinSans"},{"Jura"},{"Kalam"},{"LuckiestGuy"},
    {"Merriweather"},{"Michroma"},{"Nunito"},{"Oswald"},{"PatrickHand"},{"PermanentMarker"},
    {"Roboto"},{"RobotoCondensed"},{"RobotoMono"},{"Sarpanch"},{"SpecialElite"},
    {"TitilliumWeb"},{"Ubuntu"},{"BuilderSans"},{"BuilderSans",500},{"BuilderSans",700},
    {"BuilderSans",800},{"Arimo"},{"Arimo",700}
};
std::string family_name(const char* name){return std::string("rbxasset://fonts/families/")+name+".json";}
bool valid_weight(int weight){return weight>=100&&weight<=900&&weight%100==0;}
bool valid_family(const std::string& family){return family.size()<=family_limit&&family.find('\0')==std::string::npos;}
Value* read(lua_State* L,int index) {
    if(!lua_isuserdata(L,index)||!lua_getmetatable(L,index))return nullptr;
    luaL_getmetatable(L,meta);const bool same=lua_rawequal(L,-1,-2);lua_pop(L,2);
    return same?static_cast<Value*>(lua_touserdata(L,index)):nullptr;
}
void destroy(lua_State*,void* raw){static_cast<Value*>(raw)->~Value();}
void push(lua_State* L,const Value& value) {
    auto* result=static_cast<Value*>(lua_newuserdatadtor(L,sizeof(Value),destroy));new(result)Value(value);
    luaL_getmetatable(L,meta);lua_setmetatable(L,-2);
}
int enum_number(lua_State* L,int index,const char* type,int fallback=-1) {
    if(lua_isnoneornil(L,index)&&fallback>=0)return fallback;
    int value=0;
    if(!world_bindings::read_geometry_enum_item(L,index,type,value)) {
        luaL_argerror(L,index,type);return 0;
    }
    return value;
}
std::string string_argument(lua_State* L,int index) {
    if(lua_type(L,index)!=LUA_TSTRING){luaL_argerror(L,index,lua_pushfstring(L,"string expected, got %s",luaL_typename(L,index)));return {};}
    size_t size=0;const char* raw=luaL_checklstring(L,index,&size);
    if(size>family_limit||std::memchr(raw,0,size)){luaL_argerror(L,index,"font string exceeds limit or contains NUL");return {};}
    return std::string(raw,size);
}
int construct(lua_State* L) {
    // Validate enum arguments before allocating the family string; Luau errors
    // use a longjmp and do not unwind C++ automatic objects.
    const int weight=enum_number(L,2,"FontWeight",400),style=enum_number(L,3,"FontStyle",0);
    auto family=string_argument(L,1);push(L,{std::move(family),weight,style});return 1;
}
int from_name(lua_State* L) {
    const int weight=enum_number(L,2,"FontWeight",400),style=enum_number(L,3,"FontStyle",0);
    size_t size=0;if(lua_type(L,1)!=LUA_TSTRING){luaL_argerror(L,1,"font name expected");return 0;}
    const char* raw=luaL_checklstring(L,1,&size);
    if(size==0||size>family_limit-40){luaL_argerror(L,1,"font name is empty or too long");return 0;}
    for(size_t i=0;i<size;++i)if(!((raw[i]>='A'&&raw[i]<='Z')||(raw[i]>='a'&&raw[i]<='z')||(raw[i]>='0'&&raw[i]<='9')||raw[i]=='_'||raw[i]=='-')){
        luaL_argerror(L,1,"font name may only contain letters, digits, underscores and hyphens");return 0;
    }
    push(L,{family_name(std::string(raw,size).c_str()),weight,style});return 1;
}
int from_id(lua_State* L) {
    const int weight=enum_number(L,2,"FontWeight",400),style=enum_number(L,3,"FontStyle",0);
    if(lua_type(L,1)!=LUA_TNUMBER){luaL_argerror(L,1,"numeric font asset ID expected");return 0;}
    const double id=lua_tonumber(L,1);
    if(!std::isfinite(id)||id<0||id>9007199254740991.0||id!=std::floor(id)){luaL_argerror(L,1,"font asset ID must be a nonnegative exact integer");return 0;}
    push(L,{"rbxassetid://"+std::to_string(static_cast<uint64_t>(id)),weight,style});return 1;
}
int from_enum(lua_State* L) {
    const int value=enum_number(L,1,"Font");
    if(value<0||value>=int(std::size(legacy))){luaL_argerror(L,1,"Enum.Font.Unknown cannot construct a Font");return 0;}
    const auto& font=legacy[value];push(L,{family_name(font.family),font.weight,font.style});return 1;
}
int index(lua_State* L) {
    auto* value=static_cast<Value*>(luaL_checkudata(L,1,meta));size_t size=0;const char* key=luaL_checklstring(L,2,&size);
    if(size==6&&std::memcmp(key,"Family",6)==0)lua_pushlstring(L,value->family.data(),value->family.size());
    else if(size==6&&std::memcmp(key,"Weight",6)==0)world_bindings::push_geometry_enum_item(L,"FontWeight",value->weight);
    else if(size==5&&std::memcmp(key,"Style",5)==0)world_bindings::push_geometry_enum_item(L,"FontStyle",value->style);
    else if(size==4&&std::memcmp(key,"Bold",4)==0)lua_pushboolean(L,value->weight>=600);
    else {luaL_error(L,"unknown Font member");return 0;}
    return 1;
}
int newindex(lua_State* L) {
    auto* value=static_cast<Value*>(luaL_checkudata(L,1,meta));size_t size=0;const char* key=luaL_checklstring(L,2,&size);
    if(size==6&&std::memcmp(key,"Family",6)==0)value->family=string_argument(L,3);
    else if(size==6&&std::memcmp(key,"Weight",6)==0)value->weight=enum_number(L,3,"FontWeight");
    else if(size==5&&std::memcmp(key,"Style",5)==0)value->style=enum_number(L,3,"FontStyle");
    else if(size==4&&std::memcmp(key,"Bold",4)==0){if(lua_type(L,3)!=LUA_TBOOLEAN){luaL_argerror(L,3,"boolean expected");return 0;}value->weight=lua_toboolean(L,3)?700:400;}
    else {luaL_error(L,"unknown Font member");return 0;}
    return 0;
}
int equal(lua_State* L) {
    auto* a=read(L,1);auto* b=read(L,2);
    lua_pushboolean(L,a&&b&&a->family==b->family&&a->weight==b->weight&&a->style==b->style);return 1;
}
int text(lua_State* L) {
    auto* value=static_cast<Value*>(luaL_checkudata(L,1,meta));
    lua_pushfstring(L,"Font { Family = %s, Weight = %d, Style = %d }",value->family.c_str(),value->weight,value->style);return 1;
}
void method(lua_State* L,const char* name,lua_CFunction fn){lua_pushcfunction(L,fn,name);lua_setfield(L,-2,name);}
void install(lua_State* L) {
    luaL_newmetatable(L,meta);method(L,"__index",index);method(L,"__newindex",newindex);method(L,"__eq",equal);method(L,"__tostring",text);
    lua_pushliteral(L,"Font");lua_setfield(L,-2,"__type");lua_pushliteral(L,"The metatable is locked");lua_setfield(L,-2,"__metatable");lua_setreadonly(L,-1,true);lua_pop(L,1);
    lua_newtable(L);method(L,"new",construct);method(L,"fromEnum",from_enum);method(L,"fromName",from_name);method(L,"fromId",from_id);
    lua_setreadonly(L,-1,true);lua_setglobal(L,"Font");
}
Json encode(const Value& value){return Json{{"$font",{{"family",value.family},{"weight",value.weight},{"style",value.style}}}};}
Value decode(const Json& data) {
    if(!data.is_object()||data.size()!=3||!data.contains("family")||!data["family"].is_string()||!data.contains("weight")||!data["weight"].is_number_integer()||!data.contains("style")||!data["style"].is_number_integer())throw std::runtime_error("invalid Font value");
    if(data["weight"]<100||data["weight"]>900||data["style"]<0||data["style"]>1)throw std::runtime_error("invalid Font enum components");
    Value value{data["family"].get<std::string>(),data["weight"].get<int>(),data["style"].get<int>()};
    if(!valid_family(value.family)||!valid_weight(value.weight))throw std::runtime_error("invalid Font components");return value;
}
}
