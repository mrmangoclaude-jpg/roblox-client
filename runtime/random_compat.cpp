#include "platform_support.hpp"
// Ordinary standalone Random compatibility port.
// Provenance: user-supplied native-overrides/src/runtime_v2.cpp lines 6371-6504
// from the user's Env Logger 2.0 workspace. The source uses a PCG XSH-RR stream
// (multiplier 6364136223846793005, increment 105), a two-step seed initializer,
// and the measured extra draw for the two widest int32 intervals.
//
// Historical scope: the old runtime/release-729 source and independent recorded
// Studio 0.742.0.7421053 fixtures. Roblox build 0.745 compatibility is UNVERIFIED.
// Official Random documentation says fractional seeds round down; those 0.742
// controls and the supplied source instead truncate toward zero. Preserve that
// measured behavior here. Bounds likewise truncate toward zero before sampling.
//
// Deliberate standalone constraints: exact argument counts, finite arguments,
// signed-int32 integer bounds, and no simulated game/service/environment APIs.
// An omitted/nil seed uses actual host /dev/urandom entropy, replacing the old
// runtime's deterministic context seed/sequence. No authentication code is used.
#include "random_compat.hpp"

#include "lua.h"
#include "lualib.h"

#include <algorithm>
#include <cmath>
#include <cstdint>
#include <cstring>
#include <fstream>
#include <limits>

namespace
{
constexpr uint64_t kMultiplier = UINT64_C(6364136223846793005);
constexpr uint64_t kIncrement = UINT64_C(105);
constexpr uint64_t kMaximumExactSeed = UINT64_C(9007199254740991);
constexpr const char* kMetatable = "RobloxClientResearch.RandomCompatibility.v1";
constexpr double kPi = 3.141592653589793238462643383279502884;
constexpr int kMaximumShuffleEntries = 1000000;

struct RandomState
{
    uint64_t state;
};

// Argument errors read like the engine for these methods: no function name ("missing argument #2 (number expected)").
double numberArgument(lua_State* L, int index)
{
    const int type = lua_type(L, index);
    if (type == LUA_TNONE)
        luaL_error(L, "missing argument #%d (number expected)", index);
    if (type == LUA_TNUMBER || (type == LUA_TSTRING && lua_isnumber(L, index)))
        return lua_tonumber(L, index);
    luaL_error(L, "invalid argument #%d (number expected, got %s)", index, luaL_typename(L, index));
    return 0;
}

// Double to int64 the way the hardware converts: truncate, and NaN or anything out of range becomes INT64_MIN.
int64_t toInt64(double value)
{
    if (!(value == value) || value >= 9223372036854775808.0 || value < -9223372036854775808.0)
        return std::numeric_limits<int64_t>::min();
    return static_cast<int64_t>(value);
}

uint64_t mulHigh64(uint64_t a, uint64_t b)
{
    const uint64_t aLow = a & 0xFFFFFFFFu, aHigh = a >> 32, bLow = b & 0xFFFFFFFFu, bHigh = b >> 32;
    const uint64_t p0 = aLow * bLow, p1 = aLow * bHigh, p2 = aHigh * bLow, p3 = aHigh * bHigh;
    const uint64_t middle = (p0 >> 32) + (p1 & 0xFFFFFFFFu) + (p2 & 0xFFFFFFFFu);
    return p3 + (p1 >> 32) + (p2 >> 32) + (middle >> 32);
}

RandomState* stateFor(lua_State* L)
{
    bool receiver = false;
    if (lua_type(L, 1) == LUA_TUSERDATA && lua_getmetatable(L, 1))
    {
        luaL_getmetatable(L, kMetatable);
        receiver = lua_rawequal(L, -1, -2) != 0;
        lua_pop(L, 2);
    }
    if (!receiver)
        luaL_typeerror(L, 1, "Random");
    return static_cast<RandomState*>(lua_touserdata(L, 1));
}

RandomState* pushRandom(lua_State* L, uint64_t state)
{
    auto* result = static_cast<RandomState*>(lua_newuserdata(L, sizeof(RandomState)));
    result->state = state;
    luaL_getmetatable(L, kMetatable);
    lua_setmetatable(L, -2);
    return result;
}

uint64_t normalizedSeed(lua_State*, double seed)
{
    constexpr double limit = static_cast<double>(kMaximumExactSeed);
    int64_t integer = 0;
    if (!(seed == seed))
        integer = std::numeric_limits<int64_t>::min();
    else if (seed >= -limit && seed <= limit)
        integer = static_cast<int64_t>(std::trunc(seed));
    uint64_t state = kIncrement; // Advance from zero once.
    state += static_cast<uint64_t>(integer);
    return state * kMultiplier + kIncrement;
}

bool readHostSeed(double& seed)
{
    // Do not substitute wall time or a deterministic fallback if entropy fails.
    // No Luau error is raised while this C++ stream object is alive.
    uint64_t bits = 0;
    if (!host_entropy(&bits, sizeof(bits)))
        return false;
    seed = static_cast<double>(bits & kMaximumExactSeed);
    return true;
}

uint32_t nextUint32(RandomState& random)
{
    const uint64_t previous = random.state;
    random.state = previous * kMultiplier + kIncrement;
    const uint32_t shifted = static_cast<uint32_t>(((previous >> 18u) ^ previous) >> 27u);
    const uint32_t rotation = static_cast<uint32_t>(previous >> 59u);
    return (shifted >> rotation) | (shifted << ((0u - rotation) & 31u));
}

float randomFloatMul(float left, float right)
{
    volatile float result = left * right;
    return result;
}

float randomFloatSub(float left, float right)
{
    volatile float result = left - right;
    return result;
}

double nextFraction(RandomState& random)
{
    const uint32_t low = nextUint32(random);
    const uint32_t high = nextUint32(random);
    const uint64_t bits = static_cast<uint64_t>(low) | (static_cast<uint64_t>(high) << 32u);
    return std::ldexp(static_cast<double>(bits), -64);
}

int randomNew(lua_State* L)
{
    double seed = 0;
    if (lua_isnoneornil(L, 1))
    {
        if (!readHostSeed(seed))
            luaL_error(L, "Random.new could not read host entropy");
    }
    else if (lua_type(L, 1) == LUA_TNUMBER || (lua_type(L, 1) == LUA_TSTRING && lua_isnumber(L, 1)))
        seed = lua_tonumber(L, 1);
    else
        luaL_typeerror(L, 1, "number");
    pushRandom(L, normalizedSeed(L, seed));
    return 1;
}

int randomClone(lua_State* L)
{
    const uint64_t state = stateFor(L)->state;
    pushRandom(L, state);
    return 1;
}

int randomNextNumber(lua_State* L)
{
    RandomState* random = stateFor(L);
    const int count = lua_gettop(L);
    // Exactly one argument is rejected; none gives [0,1) and two or more give the range.
    if (count == 2)
    {
        luaL_where(L, 2);
        lua_pushstring(L, "Random:NextNumber requires 0 or 2 arguments");
        lua_concat(L, 2);
        lua_error(L);
    }
    if (count == 1)
    {
        lua_pushnumber(L, nextFraction(*random));
        return 1;
    }
    double minimum = numberArgument(L, 2);
    double maximum = numberArgument(L, 3);
    if (minimum > maximum)
        std::swap(minimum, maximum);
    const double fraction = nextFraction(*random);
    // Weighted endpoints avoid overflowing (maximum - minimum) for finite opposite-sign endpoints.
    double result = minimum * (1.0 - fraction) + maximum * fraction;
    if (result < minimum)
        result = minimum;
    else if (result > maximum)
        result = maximum;
    lua_pushnumber(L, result);
    return 1;
}

int randomNextInteger(lua_State* L)
{
    RandomState* random = stateFor(L);
    int64_t minimum = toInt64(numberArgument(L, 2));
    int64_t maximum = toInt64(numberArgument(L, 3));
    if (minimum > maximum)
        std::swap(minimum, maximum);
    const uint64_t width = static_cast<uint64_t>(maximum) - static_cast<uint64_t>(minimum) + 1u;
    uint64_t offset = 0;
    if (width <= UINT64_C(4294967294))
        offset = (width * static_cast<uint64_t>(nextUint32(*random))) >> 32u;
    else
    {
        // Wide ranges (measured against Studio) discard one draw and scale the next: floor(word * width / 2^32), computed
        // without overflow for any width.
        (void)nextUint32(*random);
        const uint64_t word = nextUint32(*random);
        offset = mulHigh64(word << 32u, width);
    }
    lua_pushnumber(L, static_cast<double>(static_cast<int64_t>(static_cast<uint64_t>(minimum) + offset)));
    return 1;
}

int randomNextUnitVector(lua_State* L)
{
    RandomState* random = stateFor(L);

    // Pick azimuth and height uniformly; this gives uniform area on the unit
    // sphere without the polar clustering caused by choosing three cube axes.
    // The float operations follow the user's prior native override. They are
    // not independently verified against the current Roblox engine build.
    constexpr double uint32Scale = 1.0 / 4294967296.0;
    const float angleFraction = static_cast<float>(static_cast<double>(nextUint32(*random)) * uint32Scale);
    const float heightFraction = static_cast<float>(static_cast<double>(nextUint32(*random)) * uint32Scale);
    const float angle = randomFloatMul(angleFraction, static_cast<float>(2.0 * kPi));
    const float height = randomFloatSub(randomFloatMul(heightFraction, 2.0f), 1.0f);
    const float radius = std::sqrt(std::max(0.0f, randomFloatSub(1.0f, randomFloatMul(height, height))));
    const float x = randomFloatMul(radius, static_cast<float>(std::cos(static_cast<double>(angle))));
    const float y = randomFloatMul(radius, static_cast<float>(std::sin(static_cast<double>(angle))));
    lua_pushvector(L, x, y, height);
    return 1;
}

int randomShuffleLength(lua_State* L, int tableIndex)
{
    tableIndex = lua_absindex(L, tableIndex);
    uint64_t count = 0;
    uint64_t maximum = 0;

    // Iterate raw keys so neither __pairs nor any other metamethod runs.
    lua_pushnil(L);
    while (lua_next(L, tableIndex))
    {
        if (lua_type(L, -2) == LUA_TNUMBER)
        {
            const double key = lua_tonumber(L, -2);
            if (std::isfinite(key) && key >= 1.0 && std::floor(key) == key)
            {
                if (key > static_cast<double>(kMaximumShuffleEntries))
                {
                    lua_pop(L, 2);
                    luaL_error(L, "Random:Shuffle array exceeds the local 1,000,000 item limit");
                    return 0;
                }
                ++count;
                maximum = std::max(maximum, static_cast<uint64_t>(key));
            }
        }
        lua_pop(L, 1); // value; keep the key for lua_next
    }

    if (count != maximum)
    {
        luaL_error(L, "Attempted to shuffle table containing nil values. This is not allowed because the table length may change.");
        return 0;
    }
    return static_cast<int>(maximum);
}

int randomShuffle(lua_State* L)
{
    RandomState* random = stateFor(L);
    if (lua_type(L, 2) != LUA_TTABLE)
        luaL_error(L, "invalid argument #2 (table expected, got %s)", lua_type(L, 2) == LUA_TNONE ? "no value" : luaL_typename(L, 2));
    const int tableIndex = lua_absindex(L, 2);
    if (lua_getreadonly(L, tableIndex))
    {
        luaL_error(L, "Random:Shuffle cannot modify a frozen table");
        return 0;
    }

    // Validate the full dense array before consuming random state or mutating
    // it. Positive integer keys are the array part; hash keys are ignored.
    const int length = randomShuffleLength(L, tableIndex);
    for (int index = length; index >= 2; --index)
    {
        const int other = 1 + static_cast<int>((static_cast<uint64_t>(index) * nextUint32(*random)) >> 32u);
        lua_rawgeti(L, tableIndex, index);
        lua_rawgeti(L, tableIndex, other);
        lua_pushvalue(L, -1);
        lua_rawseti(L, tableIndex, index);
        lua_pushvalue(L, -2);
        lua_rawseti(L, tableIndex, other);
        lua_pop(L, 2);
    }
    return 0;
}

int randomToString(lua_State* L)
{
    (void)stateFor(L);
    lua_pushstring(L, "Random");
    return 1;
}

int randomEqual(lua_State* L)
{
    RandomState* a = static_cast<RandomState*>(luaL_checkudata(L, 1, kMetatable));
    RandomState* b = static_cast<RandomState*>(luaL_checkudata(L, 2, kMetatable));
    lua_pushboolean(L, a->state == b->state);
    return 1;
}

int randomIndex(lua_State* L)
{
    if (lua_type(L, 2) != LUA_TSTRING)
        luaL_error(L, "invalid argument #2 (string expected, got %s)", luaL_typename(L, 2));
    const char* key = lua_tostring(L, 2);
    struct Method { const char* name; lua_CFunction function; };
    static const Method methods[] = {{"NextInteger", randomNextInteger}, {"NextNumber", randomNextNumber},
        {"NextUnitVector", randomNextUnitVector}, {"Shuffle", randomShuffle}, {"Clone", randomClone}};
    for (const Method& method : methods)
    {
        if (std::strcmp(key, method.name) == 0)
        {
            lua_pushcfunction(L, method.function, method.name);
            return 1;
        }
    }
    luaL_error(L, "%s is not a valid member of Random", key);
    return 0;
}

int randomNewIndex(lua_State* L)
{
    const char* key = lua_tostring(L, 2);
    luaL_error(L, "%s is not a valid member of Random", key ? key : "?");
    return 0;
}

void setFunction(lua_State* L, const char* name, lua_CFunction function)
{
    lua_pushcfunction(L, function, name);
    lua_setfield(L, -2, name);
}
} // namespace

void install_random_compat(lua_State* L)
{
    if (luaL_newmetatable(L, kMetatable))
    {
        setFunction(L, "__index", randomIndex);
        setFunction(L, "__newindex", randomNewIndex);
        setFunction(L, "__tostring", randomToString);
        setFunction(L, "__eq", randomEqual);
        lua_pushstring(L, "Random");
        lua_setfield(L, -2, "__type");
        lua_pushstring(L, "The metatable is locked");
        lua_setfield(L, -2, "__metatable");
        lua_setreadonly(L, -1, true);
    }
    lua_pop(L, 1);

    lua_newtable(L);
    setFunction(L, "new", randomNew);
    lua_setreadonly(L, -1, true);
    lua_setglobal(L, "Random");
}
