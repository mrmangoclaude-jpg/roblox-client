#include "physical_properties.hpp"

#include <lualib.h>
#include <algorithm>
#include <cmath>
#include <cstring>
#include <new>
#include <stdexcept>

namespace {
constexpr const char* kPhysicalPropertiesMeta = "LocalLuau.PhysicalProperties";
struct PhysicalPropertiesValue {
    float density;
    float friction;
    float elasticity;
    float friction_weight;
    float elasticity_weight;
    float acoustic_absorption;
};

bool has_physical_properties_meta(lua_State* L, int index) {
    if (!lua_getmetatable(L, index)) return false;
    luaL_getmetatable(L, kPhysicalPropertiesMeta);
    const bool matches = lua_rawequal(L, -1, -2) != 0;
    lua_pop(L, 2);
    return matches;
}

PhysicalPropertiesValue* checked(lua_State* L, int index) {
    return static_cast<PhysicalPropertiesValue*>(luaL_checkudata(L, index, kPhysicalPropertiesMeta));
}

float checked_clamped_number(lua_State* L, int index, const char* field,
                             double minimum, double maximum) {
    double value = luaL_checknumber(L, index);
    if (!std::isfinite(value)) {
        luaL_error(L, "PhysicalProperties.%s must be finite", field);
        return 0.0f;
    }
    return static_cast<float>(std::clamp(value, minimum, maximum));
}

void push_value(lua_State* L, const PhysicalPropertiesValue& fields) {
    auto* value = static_cast<PhysicalPropertiesValue*>(
        lua_newuserdatatagged(L, sizeof(PhysicalPropertiesValue), 0));
    new (value) PhysicalPropertiesValue(fields);
    luaL_getmetatable(L, kPhysicalPropertiesMeta);
    lua_setmetatable(L, -2);
}

struct MaterialDefault {
    const char* name;
    float density, friction, elasticity, friction_weight, elasticity_weight, acoustic_absorption;
};
constexpr MaterialDefault kMaterialDefaults[] = {
    {"Plastic", 0.7f, 0.3f, 0.5f, 1, 1, 0.3f},
    {"SmoothPlastic", 0.7f, 0.2f, 0.5f, 1, 1, 0.2f},
    {"Neon", 0.7f, 0.3f, 0.2f, 1, 1, 0.3f},
    {"Wood", 0.35f, 0.48f, 0.2f, 1, 1, 0.25f},
    {"WoodPlanks", 0.35f, 0.48f, 0.2f, 1, 1, 0.25f},
    {"Marble", 2.563f, 0.2f, 0.17f, 1, 1, 0.01f},
    {"Basalt", 2.691f, 0.7f, 0.15f, 0.3f, 1, 0.2f},
    {"Slate", 2.691f, 0.4f, 0.2f, 1, 1, 0.03f},
    {"CrackedLava", 2.691f, 0.65f, 0.15f, 1, 1, 0.35f},
    {"Concrete", 2.403f, 0.7f, 0.2f, 0.3f, 1, 0.05f},
    {"Limestone", 2.691f, 0.5f, 0.15f, 1, 1, 0.15f},
    {"Granite", 2.691f, 0.4f, 0.2f, 1, 1, 0.2f},
    {"Pavement", 2.691f, 0.5f, 0.17f, 0.3f, 1, 0.6f},
    {"Brick", 1.922f, 0.8f, 0.15f, 0.3f, 1, 0.35f},
    {"Pebble", 2.403f, 0.4f, 0.17f, 1, 1.5f, 0.4f},
    {"Cobblestone", 2.691f, 0.5f, 0.17f, 1, 1, 0.45f},
    {"Rock", 2.691f, 0.5f, 0.17f, 1, 1, 0.15f},
    {"Sandstone", 2.691f, 0.5f, 0.15f, 5, 1, 0.2f},
    {"CorrodedMetal", 7.85f, 0.7f, 0.2f, 1, 1, 0.15f},
    {"DiamondPlate", 7.85f, 0.35f, 0.25f, 1, 1, 0.05f},
    {"Foil", 2.7f, 0.4f, 0.25f, 1, 1, 0.1f},
    {"Metal", 7.85f, 0.4f, 0.25f, 1, 1, 0.1f},
    {"Grass", 0.9f, 0.4f, 0.1f, 1, 1.5f, 0.7f},
    {"LeafyGrass", 0.9f, 0.4f, 0.1f, 2, 2, 0.75f},
    {"Sand", 1.602f, 0.5f, 0.05f, 5, 2.5f, 0.55f},
    {"Fabric", 0.7f, 0.35f, 0.05f, 1, 1, 0.65f},
    {"Snow", 0.9f, 0.3f, 0.03f, 3, 4, 0.8f},
    {"Mud", 0.9f, 0.3f, 0.07f, 3, 4, 0.65f},
    {"Ground", 0.9f, 0.45f, 0.1f, 1, 1, 0.6f},
    {"Asphalt", 2.36f, 0.8f, 0.2f, 0.3f, 1, 0.4f},
    {"Salt", 2.165f, 0.5f, 0.05f, 1, 1, 0.15f},
    {"Ice", 0.919f, 0.02f, 0.15f, 3, 1, 0.2f},
    {"Glacier", 0.919f, 0.05f, 0.15f, 2, 1, 0.7f},
    {"Glass", 2.403f, 0.25f, 0.2f, 1, 1, 0.1f},
    {"ForceField", 2.403f, 0.25f, 0.2f, 1, 1, 0},
    {"Air", 0.01f, 0.01f, 0.01f, 1, 1, 0.01f},
    {"Water", 1, 0.005f, 0.01f, 1, 1, 0.01f},
    {"Cardboard", 0.7f, 0.5f, 0.05f, 1, 2, 0.55f},
    {"Carpet", 1.1f, 0.4f, 0.25f, 1, 2, 0.65f},
    {"CeramicTiles", 2.4f, 0.51f, 0.2f, 1, 1, 0.04f},
    {"ClayRoofTiles", 2, 0.51f, 0.2f, 1, 1, 0.3f},
    {"RoofShingles", 2.36f, 0.8f, 0.2f, 0.3f, 1, 0.3f},
    {"Leather", 0.86f, 0.35f, 0.25f, 1, 1, 0.65f},
    {"Plaster", 0.75f, 0.6f, 0.2f, 0.3f, 1, 0.3f},
    {"Rubber", 1.3f, 1.5f, 0.95f, 3, 2, 0.5f},
};

int physical_properties_new(lua_State* L) {
    const int count = lua_gettop(L);
    if (count == 1) {
        if (!lua_isuserdata(L, 1))
            luaL_error(L, "PhysicalProperties.new with 1 argument expects Enum.Material inputs");
        lua_getfield(L, 1, "Name");
        const char* name = lua_tostring(L, -1);
        const MaterialDefault* found = nullptr;
        if (name)
            for (const auto& m : kMaterialDefaults)
                if (std::strcmp(m.name, name) == 0) { found = &m; break; }
        lua_pop(L, 1);
        if (!found)
            luaL_error(L, "PhysicalProperties.new with 1 argument expects Enum.Material inputs");
        push_value(L, PhysicalPropertiesValue{found->density, found->friction, found->elasticity,
            found->friction_weight, found->elasticity_weight, found->acoustic_absorption});
        return 1;
    }
    if (count != 3 && count != 5 && count != 6) {
        luaL_error(L, "Invalid number of arguments: %d. Four ways to call PhysicalProperties.new:\n"
            "\t\t\t\t\t1. new(material: Material)  -- returns default properties for the given material\n"
            "\t\t\t\t\t2. new(density: number, friction: number, elasticity: number)\n"
            "\t\t\t\t\t3. new(density: number, friction: number, elasticity: number, frictionWeight: number, elasticityWeight: number)\n"
            "\t\t\t\t\t4. new(density: number, friction: number, elasticity: number, frictionWeight: number, elasticityWeight: number, acousticAbsorption: number)\n",
            count);
        return 0;
    }
    PhysicalPropertiesValue value{};
    value.density = checked_clamped_number(L, 1, "Density", 0.0001, 100.0);
    value.friction = checked_clamped_number(L, 2, "Friction", 0.0, 2.0);
    value.elasticity = checked_clamped_number(L, 3, "Elasticity", 0.0, 1.0);
    value.friction_weight = count >= 5
        ? checked_clamped_number(L, 4, "FrictionWeight", 0.0, 100.0) : 1.0f;
    value.elasticity_weight = count >= 5
        ? checked_clamped_number(L, 5, "ElasticityWeight", 0.0, 100.0) : 1.0f;
    value.acoustic_absorption = count == 6
        ? checked_clamped_number(L, 6, "AcousticAbsorption", 0.0, 1.0) : 1.0f;
    push_value(L, value);
    return 1;
}

int physical_properties_tostring(lua_State* L) {
    auto* value = checked(L, 1);
    char text[160];
    std::snprintf(text, sizeof(text), "%.9g, %.9g, %.9g, %.9g, %.9g, %.9g",
        double(value->density), double(value->friction), double(value->elasticity),
        double(value->friction_weight), double(value->elasticity_weight), double(value->acoustic_absorption));
    lua_pushstring(L, text);
    return 1;
}

int physical_properties_index(lua_State* L) {
    auto* value = checked(L, 1);
    const char* key = luaL_checkstring(L, 2);
    if (std::strcmp(key, "Density") == 0) lua_pushnumber(L, value->density);
    else if (std::strcmp(key, "Friction") == 0) lua_pushnumber(L, value->friction);
    else if (std::strcmp(key, "Elasticity") == 0) lua_pushnumber(L, value->elasticity);
    else if (std::strcmp(key, "FrictionWeight") == 0) lua_pushnumber(L, value->friction_weight);
    else if (std::strcmp(key, "ElasticityWeight") == 0) lua_pushnumber(L, value->elasticity_weight);
    else if (std::strcmp(key, "AcousticAbsorption") == 0) lua_pushnumber(L, value->acoustic_absorption);
    else lua_pushnil(L);
    return 1;
}

int physical_properties_newindex(lua_State* L) {
    luaL_error(L, "PhysicalProperties values are immutable");
    return 0;
}

int physical_properties_equal(lua_State* L) {
    if (!has_physical_properties_meta(L, 1) || !has_physical_properties_meta(L, 2)) {
        lua_pushboolean(L, false);
        return 1;
    }
    auto* a = static_cast<PhysicalPropertiesValue*>(lua_touserdata(L, 1));
    auto* b = static_cast<PhysicalPropertiesValue*>(lua_touserdata(L, 2));
    lua_pushboolean(L,
        a->density == b->density && a->friction == b->friction
        && a->elasticity == b->elasticity && a->friction_weight == b->friction_weight
        && a->elasticity_weight == b->elasticity_weight
        && a->acoustic_absorption == b->acoustic_absorption);
    return 1;
}

void install_constructor(lua_State* L) {
    lua_createtable(L, 0, 1);
    lua_pushcfunction(L, physical_properties_new, "new");
    lua_setfield(L, -2, "new");
    lua_setreadonly(L, -1, true);
    lua_setglobal(L, "PhysicalProperties");
}
}  // namespace

void install_physical_properties(lua_State* L) {
    luaL_newmetatable(L, kPhysicalPropertiesMeta);
    lua_pushcfunction(L, physical_properties_index, "PhysicalProperties.__index");
    lua_setfield(L, -2, "__index");
    lua_pushcfunction(L, physical_properties_newindex, "PhysicalProperties.__newindex");
    lua_setfield(L, -2, "__newindex");
    lua_pushcfunction(L, physical_properties_equal, "PhysicalProperties.__eq");
    lua_setfield(L, -2, "__eq");
    lua_pushcfunction(L, physical_properties_tostring, "PhysicalProperties.__tostring");
    lua_setfield(L, -2, "__tostring");
    lua_pushstring(L, "PhysicalProperties");
    lua_setfield(L, -2, "__type");
    lua_pushstring(L, "PhysicalProperties");
    lua_setfield(L, -2, "__metatable");
    lua_pop(L, 1);
    install_constructor(L);
}

bool is_physical_properties(lua_State* L, int index) {
    return has_physical_properties_meta(L, index);
}

bool capture_physical_properties(lua_State* L, int index, nlohmann::json& value) {
    if (!is_physical_properties(L, index)) return false;
    const auto* fields = static_cast<const PhysicalPropertiesValue*>(lua_touserdata(L, index));
    value = nlohmann::json{{"$physical_properties", nlohmann::json::array({
        fields->density, fields->friction, fields->elasticity, fields->friction_weight,
        fields->elasticity_weight, fields->acoustic_absorption})}};
    return true;
}

bool push_physical_properties_json(lua_State* L, const nlohmann::json& value) {
    if (!value.is_object() || value.size() != 1 || !value.contains("$physical_properties")) return false;
    const auto& fields = value.at("$physical_properties");
    if (!fields.is_array() || fields.size() != 6) throw std::runtime_error("invalid PhysicalProperties components");
    float numbers[6];
    const double minima[] = {0.0001, 0.0, 0.0, 0.0, 0.0, 0.0};
    const double maxima[] = {100.0, 2.0, 1.0, 100.0, 100.0, 1.0};
    for (size_t i = 0; i < 6; ++i) {
        if (!fields[i].is_number()) throw std::runtime_error("invalid PhysicalProperties scalar");
        double number = fields[i].get<double>();
        if (!std::isfinite(number)) throw std::runtime_error("non-finite PhysicalProperties scalar");
        numbers[i] = static_cast<float>(std::clamp(number, minima[i], maxima[i]));
    }
    push_value(L, PhysicalPropertiesValue{numbers[0], numbers[1], numbers[2],
        numbers[3], numbers[4], numbers[5]});
    return true;
}
