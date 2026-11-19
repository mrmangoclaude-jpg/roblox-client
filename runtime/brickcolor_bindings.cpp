#include "brickcolor_bindings.hpp"
#include "color3_bindings.hpp"
#include "platform_support.hpp"

#include <lua.h>
#include <lualib.h>

#include <cmath>
#include <cstdint>
#include <cstring>
#include <limits>

namespace {
constexpr const char* kMeta = "LocalRuntime.BrickColor";
struct Entry { int number; const char* name; unsigned char r,g,b; };
// IDs, names, and RGB channels measured in the 0.745 native palette initializer.
constexpr Entry kEntries[] = {
    {1, "White", 242,243,243},
    {2, "Grey", 161,165,162},
    {3, "Light yellow", 249,233,153},
    {5, "Brick yellow", 215,197,154},
    {6, "Light green (Mint)", 194,218,184},
    {9, "Light reddish violet", 232,186,200},
    {11, "Pastel Blue", 128,187,219},
    {12, "Light orange brown", 203,132,66},
    {18, "Nougat", 204,142,105},
    {21, "Bright red", 196,40,28},
    {22, "Med. reddish violet", 196,112,160},
    {23, "Bright blue", 13,105,172},
    {24, "Bright yellow", 245,205,48},
    {25, "Earth orange", 98,71,50},
    {26, "Black", 27,42,53},
    {27, "Dark grey", 109,110,108},
    {28, "Dark green", 40,127,71},
    {29, "Medium green", 161,196,140},
    {36, "Lig. Yellowich orange", 243,207,155},
    {37, "Bright green", 75,151,75},
    {38, "Dark orange", 160,95,53},
    {39, "Light bluish violet", 193,202,222},
    {40, "Transparent", 236,236,236},
    {41, "Tr. Red", 205,84,75},
    {42, "Tr. Lg blue", 193,223,240},
    {43, "Tr. Blue", 123,182,232},
    {44, "Tr. Yellow", 247,241,141},
    {45, "Light blue", 180,210,228},
    {47, "Tr. Flu. Reddish orange", 217,133,108},
    {48, "Tr. Green", 132,182,141},
    {49, "Tr. Flu. Green", 248,241,132},
    {50, "Phosph. White", 236,232,222},
    {100, "Light red", 238,196,182},
    {101, "Medium red", 218,134,122},
    {102, "Medium blue", 110,153,202},
    {103, "Light grey", 199,193,183},
    {104, "Bright violet", 107,50,124},
    {105, "Br. yellowish orange", 226,155,64},
    {106, "Bright orange", 218,133,65},
    {107, "Bright bluish green", 0,143,156},
    {108, "Earth yellow", 104,92,67},
    {110, "Bright bluish violet", 67,84,147},
    {111, "Tr. Brown", 191,183,177},
    {112, "Medium bluish violet", 104,116,172},
    {113, "Tr. Medi. reddish violet", 229,173,200},
    {115, "Med. yellowish green", 199,210,60},
    {116, "Med. bluish green", 85,165,175},
    {118, "Light bluish green", 183,215,213},
    {119, "Br. yellowish green", 164,189,71},
    {120, "Lig. yellowish green", 217,228,167},
    {121, "Med. yellowish orange", 231,172,88},
    {123, "Br. reddish orange", 211,111,76},
    {124, "Bright reddish violet", 146,57,120},
    {125, "Light orange", 234,184,146},
    {126, "Tr. Bright bluish violet", 165,165,203},
    {127, "Gold", 220,188,129},
    {128, "Dark nougat", 174,122,89},
    {131, "Silver", 156,163,168},
    {133, "Neon orange", 213,115,61},
    {134, "Neon green", 216,221,86},
    {135, "Sand blue", 116,134,157},
    {136, "Sand violet", 135,124,144},
    {137, "Medium orange", 224,152,100},
    {138, "Sand yellow", 149,138,115},
    {140, "Earth blue", 32,58,86},
    {141, "Earth green", 39,70,45},
    {143, "Tr. Flu. Blue", 207,226,247},
    {145, "Sand blue metallic", 121,136,161},
    {146, "Sand violet metallic", 149,142,163},
    {147, "Sand yellow metallic", 147,135,103},
    {148, "Dark grey metallic", 87,88,87},
    {149, "Black metallic", 22,29,50},
    {150, "Light grey metallic", 171,173,172},
    {151, "Sand green", 120,144,130},
    {153, "Sand red", 149,121,119},
    {154, "Dark red", 123,46,47},
    {157, "Tr. Flu. Yellow", 255,246,123},
    {158, "Tr. Flu. Red", 225,164,194},
    {168, "Gun metallic", 117,108,98},
    {176, "Red flip/flop", 151,105,91},
    {178, "Yellow flip/flop", 180,132,85},
    {179, "Silver flip/flop", 137,135,136},
    {180, "Curry", 215,169,75},
    {190, "Fire Yellow", 249,214,46},
    {191, "Flame yellowish orange", 232,171,45},
    {192, "Reddish brown", 105,64,40},
    {193, "Flame reddish orange", 207,96,36},
    {194, "Medium stone grey", 163,162,165},
    {195, "Royal blue", 70,103,164},
    {196, "Dark Royal blue", 35,71,139},
    {198, "Bright reddish lilac", 142,66,133},
    {199, "Dark stone grey", 99,95,98},
    {200, "Lemon metalic", 130,138,93},
    {208, "Light stone grey", 229,228,223},
    {209, "Dark Curry", 176,142,68},
    {210, "Faded green", 112,149,120},
    {211, "Turquoise", 121,181,181},
    {212, "Light Royal blue", 159,195,233},
    {213, "Medium Royal blue", 108,129,183},
    {216, "Rust", 144,76,42},
    {217, "Brown", 124,92,70},
    {218, "Reddish lilac", 150,112,159},
    {219, "Lilac", 107,98,155},
    {220, "Light lilac", 167,169,206},
    {221, "Bright purple", 205,98,152},
    {222, "Light purple", 228,173,200},
    {223, "Light pink", 220,144,149},
    {224, "Light brick yellow", 240,213,160},
    {225, "Warm yellowish orange", 235,184,127},
    {226, "Cool yellow", 253,234,141},
    {232, "Dove blue", 125,187,221},
    {268, "Medium lilac", 52,43,117},
    {301, "Slime green", 80,109,84},
    {302, "Smoky grey", 91,93,105},
    {303, "Dark blue", 0,16,176},
    {304, "Parsley green", 44,101,29},
    {305, "Steel blue", 82,124,174},
    {306, "Storm blue", 51,88,130},
    {307, "Lapis", 16,42,220},
    {308, "Dark indigo", 61,21,133},
    {309, "Sea green", 52,142,64},
    {310, "Shamrock", 91,154,76},
    {311, "Fossil", 159,161,172},
    {312, "Mulberry", 89,34,89},
    {313, "Forest green", 31,128,29},
    {314, "Cadet blue", 159,173,192},
    {315, "Electric blue", 9,137,207},
    {316, "Eggplant", 123,0,123},
    {317, "Moss", 124,156,107},
    {318, "Artichoke", 138,171,133},
    {319, "Sage green", 185,196,177},
    {320, "Ghost grey", 202,203,209},
    {321, "Lilac", 167,94,155},
    {322, "Plum", 123,47,123},
    {323, "Olivine", 148,190,129},
    {324, "Laurel green", 168,189,153},
    {325, "Quill grey", 223,223,222},
    {327, "Crimson", 151,0,0},
    {328, "Mint", 177,229,166},
    {329, "Baby blue", 152,194,219},
    {330, "Carnation pink", 255,152,220},
    {331, "Persimmon", 255,89,89},
    {332, "Maroon", 117,0,0},
    {333, "Gold", 239,184,56},
    {334, "Daisy orange", 248,217,109},
    {335, "Pearl", 231,231,236},
    {336, "Fog", 199,212,228},
    {337, "Salmon", 255,148,148},
    {338, "Terra Cotta", 190,104,98},
    {339, "Cocoa", 86,36,36},
    {340, "Wheat", 241,231,199},
    {341, "Buttermilk", 254,243,187},
    {342, "Mauve", 224,178,208},
    {343, "Sunrise", 212,144,189},
    {344, "Tawny", 150,85,85},
    {345, "Rust", 143,76,42},
    {346, "Cashmere", 211,190,150},
    {347, "Khaki", 226,220,188},
    {348, "Lily white", 237,234,234},
    {349, "Seashell", 233,218,218},
    {350, "Burgundy", 136,62,62},
    {351, "Cork", 188,155,93},
    {352, "Burlap", 199,172,120},
    {353, "Beige", 202,191,163},
    {354, "Oyster", 187,179,178},
    {355, "Pine Cone", 108,88,75},
    {356, "Fawn brown", 160,132,79},
    {357, "Hurricane grey", 149,137,136},
    {358, "Cloudy grey", 171,168,158},
    {359, "Linen", 175,148,131},
    {360, "Copper", 150,103,102},
    {361, "Medium brown", 86,66,54},
    {362, "Bronze", 126,104,63},
    {363, "Flint", 105,102,92},
    {364, "Dark taupe", 90,76,66},
    {365, "Burnt Sienna", 106,57,9},
    {1001, "Institutional white", 248,248,248},
    {1002, "Mid gray", 205,205,205},
    {1003, "Really black", 17,17,17},
    {1004, "Really red", 255,0,0},
    {1005, "Deep orange", 255,176,0},
    {1006, "Alder", 180,128,255},
    {1007, "Dusty Rose", 163,75,75},
    {1008, "Olive", 193,190,66},
    {1009, "New Yeller", 255,255,0},
    {1010, "Really blue", 0,0,255},
    {1011, "Navy blue", 0,32,96},
    {1012, "Deep blue", 33,84,185},
    {1013, "Cyan", 4,175,236},
    {1014, "CGA brown", 170,85,0},
    {1015, "Magenta", 170,0,170},
    {1016, "Pink", 255,102,204},
    {1017, "Deep orange", 255,175,0},
    {1018, "Teal", 18,238,212},
    {1019, "Toothpaste", 0,255,255},
    {1020, "Lime green", 0,255,0},
    {1021, "Camo", 58,125,21},
    {1022, "Grime", 127,142,100},
    {1023, "Lavender", 140,91,159},
    {1024, "Pastel light blue", 175,221,255},
    {1025, "Pastel orange", 255,201,201},
    {1026, "Pastel violet", 177,167,255},
    {1027, "Pastel blue-green", 159,243,233},
    {1028, "Pastel green", 204,255,204},
    {1029, "Pastel yellow", 255,255,204},
    {1030, "Pastel brown", 255,204,153},
    {1031, "Royal purple", 98,37,209},
    {1032, "Hot pink", 255,0,191},
};
struct Value { int number; };
#include "brickcolor_palette.inc"

const Entry* by_number(int number) {
    for (const auto& entry : kEntries) if (entry.number == number) return &entry;
    return nullptr;
}
const Entry* by_name(const char* name, size_t length) {
    for (const auto& entry : kEntries)
        if (std::strlen(entry.name) == length && std::memcmp(entry.name,name,length)==0) return &entry;
    return nullptr;
}
const Entry* closest_color(double r,double g,double b) {
    const Entry* closest=nullptr;
    double minimum=std::numeric_limits<double>::infinity();
    for (const auto& entry:kEntries) {
        // The documented match uses total absolute channel distance, not
        // Euclidean distance. Preserve catalog order for equal distances.
        double distance=std::abs(r-entry.r/255.0)+std::abs(g-entry.g/255.0)+std::abs(b-entry.b/255.0);
        if(distance<minimum){minimum=distance;closest=&entry;}
    }
    return closest;
}
void push_value(lua_State* L,const Entry* entry) {
    auto* value=static_cast<Value*>(lua_newuserdatatagged(L,sizeof(Value),0));
    value->number=entry->number;
    luaL_getmetatable(L,kMeta);lua_setmetatable(L,-2);
}
const Entry* check_entry(lua_State* L,int index) {
    auto* value=static_cast<Value*>(luaL_checkudata(L,index,kMeta));
    const Entry* entry=by_number(value->number);
    if(!entry){luaL_error(L,"invalid BrickColor value");return nullptr;}
    return entry;
}
int create(lua_State* L) {
    int count=lua_gettop(L);const Entry* entry=nullptr;
    if(count==1&&lua_type(L,1)==LUA_TNUMBER) {
        double number=lua_tonumber(L,1);
        // Roblox floors the value to a palette id; ids without a palette entry
        // (including non-finite input) fall back to Medium stone grey below.
        if(std::isfinite(number)) {
            double id=std::floor(number);
            if(id>=0&&id<=65535)entry=by_number(static_cast<int>(id));
        }
    } else if(count==1&&lua_type(L,1)==LUA_TSTRING) {
        size_t size=0;const char* name=lua_tolstring(L,1,&size);entry=by_name(name,size);
    } else if(count==1&&lua_type(L,1)==LUA_TUSERDATA) {
        // Read the documented Color3 components without depending on the
        // Color3 module's private userdata layout.
        if(!lua_getmetatable(L,1)){luaL_error(L,"BrickColor.new expects Color3 userdata");return 0;}
        lua_getfield(L,-1,"__type");bool color3=lua_isstring(L,-1)&&std::strcmp(lua_tostring(L,-1),"Color3")==0;
        lua_pop(L,2);if(!color3){luaL_error(L,"BrickColor.new expects Color3 userdata");return 0;}
        const char* fields[]={"R","G","B"};double channels[3];
        for(int i=0;i<3;i++){
            lua_getfield(L,1,fields[i]);channels[i]=lua_tonumber(L,-1);lua_pop(L,1);
            if(!std::isfinite(channels[i])){luaL_error(L,"Color3 channels must be finite");return 0;}
        }
        entry=closest_color(channels[0],channels[1],channels[2]);
    } else if(count==3) {
        double rgb[3];for(int i=0;i<3;i++){rgb[i]=luaL_checknumber(L,i+1);if(!std::isfinite(rgb[i])||rgb[i]<0||rgb[i]>1){luaL_error(L,"BrickColor channels must be normalized finite values");return 0;}}
        entry=closest_color(rgb[0],rgb[1],rgb[2]);
    } else if(count==1){luaL_argerror(L,1,lua_pushfstring(L,"Color3 expected, got %s",luaL_typename(L,1)));return 0;}
    else {luaL_error(L,"BrickColor.new expects a palette id, name, Color3, or three RGB numbers");return 0;}
    if(!entry)entry=by_number(194);
    push_value(L,entry);return 1;
}
int palette(lua_State* L) {
    if(lua_gettop(L)<1){luaL_error(L,"Argument 1 missing or nil");return 0;}
    const double value=luaL_checknumber(L,1);
    // Roblox rounds the index half away from zero, converts to int32 (non-finite
    // input saturates to INT_MIN), then bounds-checks against the 128-entry palette.
    int index;
    if(std::isfinite(value)){
        const double rounded=std::round(value);
        if(rounded>2147483647.0)index=2147483647;
        else if(rounded<-2147483648.0)index=-2147483648;
        else index=static_cast<int>(rounded);
    }else index=-2147483648;
    if(index<0||index>=128){luaL_error(L,"palette index out of bounds (%d)",index);return 0;}
    push_value(L,by_number(kPalette[index]));return 1;
}
int random_color(lua_State* L) {
    if(lua_gettop(L)!=0){luaL_error(L,"BrickColor.random expects no arguments");return 0;}
    uint32_t value;
    if(!host_entropy(&value,sizeof(value))){luaL_error(L,"BrickColor.random entropy unavailable");return 0;}
    // 128 divides the uint32 range exactly, so these seven bits are unbiased.
    push_value(L,by_number(kPalette[value&127]));return 1;
}
int index(lua_State* L) {
    const Entry* entry=check_entry(L,1);const char* key=luaL_checkstring(L,2);
    if(std::strcmp(key,"Number")==0)lua_pushinteger(L,entry->number);
    else if(std::strcmp(key,"Name")==0)lua_pushstring(L,entry->name);
    else if(std::strcmp(key,"r")==0)lua_pushnumber(L,entry->r/255.0);
    else if(std::strcmp(key,"g")==0)lua_pushnumber(L,entry->g/255.0);
    else if(std::strcmp(key,"b")==0)lua_pushnumber(L,entry->b/255.0);
    else if(std::strcmp(key,"Color")==0) {
        push_color3(L,entry->r/255.0,entry->g/255.0,entry->b/255.0);
    } else lua_pushnil(L);
    return 1;
}
int tostring_value(lua_State* L) {lua_pushstring(L,check_entry(L,1)->name);return 1;}
int equal(lua_State* L) {
    auto* a=static_cast<Value*>(luaL_checkudata(L,1,kMeta));auto* b=static_cast<Value*>(luaL_checkudata(L,2,kMeta));
    lua_pushboolean(L,a->number==b->number);return 1;
}
int static_entry(lua_State* L) {
    int number=static_cast<int>(lua_tointeger(L,lua_upvalueindex(1)));
    const Entry* entry=by_number(number);if(!entry){luaL_error(L,"unsupported BrickColor constant");return 0;}
    push_value(L,entry);return 1;
}
void set_constant(lua_State* L,const char* name,int number) {
    lua_pushinteger(L,number);lua_pushcclosurek(L,static_entry,name,1,nullptr);lua_setfield(L,-2,name);
}
}

void install_brickcolor_bindings(lua_State* L) {
    luaL_newmetatable(L,kMeta);
    lua_pushcfunction(L,index,"__index");lua_setfield(L,-2,"__index");
    lua_pushcfunction(L,tostring_value,"__tostring");lua_setfield(L,-2,"__tostring");
    lua_pushcfunction(L,equal,"__eq");lua_setfield(L,-2,"__eq");
    lua_pushliteral(L,"BrickColor");lua_setfield(L,-2,"__type");
    lua_pushliteral(L,"The metatable is locked");lua_setfield(L,-2,"__metatable");lua_pop(L,1);
    lua_createtable(L,0,13);
    lua_pushcfunction(L,create,"new");lua_setfield(L,-2,"new");
    lua_pushcfunction(L,palette,"palette");lua_setfield(L,-2,"palette");
    lua_pushcfunction(L,random_color,"random");lua_setfield(L,-2,"random");
    lua_pushcfunction(L,create,"New");lua_setfield(L,-2,"New");
    lua_pushcfunction(L,random_color,"Random");lua_setfield(L,-2,"Random");
    set_constant(L,"White",1);set_constant(L,"Black",26);
    set_constant(L,"Gray",194);set_constant(L,"DarkGray",199);
    set_constant(L,"Red",21);set_constant(L,"Yellow",24);
    set_constant(L,"Green",28);set_constant(L,"Blue",23);
    lua_setreadonly(L,-1,true);lua_setglobal(L,"BrickColor");
}
