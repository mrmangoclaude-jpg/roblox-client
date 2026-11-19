#pragma once

#include <cstdint>

struct lua_State;

// Installs standalone UDim and UDim2 value constructors into a Luau state.
// Conversion into GuiObject properties is handled by the world binding layer.
void install_udim_bindings(lua_State* L);

// Raw UDim2 access for datatypes that embed UDim2 components (scales are stored as float32).
bool read_udim2_raw(lua_State* L, int index, double& xs, int32_t& xo, double& ys, int32_t& yo);
void push_udim2_raw(lua_State* L, double xs, int32_t xo, double ys, int32_t yo);
