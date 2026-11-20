#include "utf8_extras.hpp"
#include <lua.h>
#include <lualib.h>
#include <algorithm>
#include <cstdint>
#include <string>
#include <utility>
#include <vector>
#include "unicode_normalization_data.inc"

namespace {
constexpr uint32_t kSBase = 0xAC00, kLBase = 0x1100, kVBase = 0x1161, kTBase = 0x11A7;
constexpr uint32_t kLCount = 19, kVCount = 21, kTCount = 28, kNCount = kVCount * kTCount, kSCount = kLCount * kNCount;

// Strict UTF-8 at `at`: rejects stray continuation bytes, overlong forms, surrogates and values above U+10FFFF.
// length == 0 reports an invalid sequence.
uint32_t decode_one(const std::string& text, size_t at, size_t& length) {
    const unsigned char c = static_cast<unsigned char>(text[at]);
    if (c < 0x80) { length = 1; return c; }
    size_t need = 0;
    uint32_t cp = 0;
    if (c >= 0xC2 && c <= 0xDF) { need = 1; cp = c & 0x1F; }
    else if (c >= 0xE0 && c <= 0xEF) { need = 2; cp = c & 0x0F; }
    else if (c >= 0xF0 && c <= 0xF4) { need = 3; cp = c & 0x07; }
    else { length = 0; return 0; }
    if (at + need >= text.size()) { length = 0; return 0; }
    for (size_t k = 1; k <= need; ++k) {
        const unsigned char cc = static_cast<unsigned char>(text[at + k]);
        if ((cc & 0xC0) != 0x80) { length = 0; return 0; }
        cp = (cp << 6) | (cc & 0x3F);
    }
    if ((need == 2 && (cp < 0x800 || (cp >= 0xD800 && cp <= 0xDFFF))) || (need == 3 && (cp < 0x10000 || cp > 0x10FFFF))) {
        length = 0;
        return 0;
    }
    length = need + 1;
    return cp;
}

bool decode_strict(const std::string& text, std::vector<uint32_t>& out) {
    size_t i = 0;
    while (i < text.size()) {
        size_t length = 0;
        const uint32_t cp = decode_one(text, i, length);
        if (length == 0) return false;
        out.push_back(cp);
        i += length;
    }
    return true;
}

void encode(uint32_t cp, std::string& out) {
    if (cp < 0x80) out += static_cast<char>(cp);
    else if (cp < 0x800) {
        out += static_cast<char>(0xC0 | (cp >> 6));
        out += static_cast<char>(0x80 | (cp & 0x3F));
    } else if (cp < 0x10000) {
        out += static_cast<char>(0xE0 | (cp >> 12));
        out += static_cast<char>(0x80 | ((cp >> 6) & 0x3F));
        out += static_cast<char>(0x80 | (cp & 0x3F));
    } else {
        out += static_cast<char>(0xF0 | (cp >> 18));
        out += static_cast<char>(0x80 | ((cp >> 12) & 0x3F));
        out += static_cast<char>(0x80 | ((cp >> 6) & 0x3F));
        out += static_cast<char>(0x80 | (cp & 0x3F));
    }
}

uint32_t combining_class(uint32_t cp) {
    const auto* end = std::end(kUnicodeCombining);
    const auto* it = std::lower_bound(std::begin(kUnicodeCombining), end, cp,
        [](const UnicodeCombining& row, uint32_t value) { return row.code_point < value; });
    return it != end && it->code_point == cp ? it->combining_class : 0;
}

void decompose(const std::vector<uint32_t>& in, std::vector<uint32_t>& out) {
    for (uint32_t cp : in) {
        if (cp >= kSBase && cp < kSBase + kSCount) {
            const uint32_t index = cp - kSBase;
            out.push_back(kLBase + index / kNCount);
            out.push_back(kVBase + (index % kNCount) / kTCount);
            if (index % kTCount) out.push_back(kTBase + index % kTCount);
            continue;
        }
        const auto* end = std::end(kUnicodeDecompositions);
        const auto* it = std::lower_bound(std::begin(kUnicodeDecompositions), end, cp,
            [](const UnicodeDecomposition& row, uint32_t value) { return row.code_point < value; });
        if (it != end && it->code_point == cp)
            out.insert(out.end(), kUnicodeDecompositionPool + it->offset, kUnicodeDecompositionPool + it->offset + it->length);
        else out.push_back(cp);
    }
    // Canonical ordering: stable-sort each run of non-starters by combining class.
    for (size_t i = 0; i < out.size();) {
        if (!combining_class(out[i])) { ++i; continue; }
        size_t j = i;
        while (j < out.size() && combining_class(out[j])) ++j;
        std::stable_sort(out.begin() + i, out.begin() + j,
            [](uint32_t a, uint32_t b) { return combining_class(a) < combining_class(b); });
        i = j;
    }
}

uint32_t compose_pair(uint32_t first, uint32_t second) {
    if (first >= kLBase && first < kLBase + kLCount && second >= kVBase && second < kVBase + kVCount)
        return kSBase + ((first - kLBase) * kVCount + (second - kVBase)) * kTCount;
    if (first >= kSBase && first < kSBase + kSCount && (first - kSBase) % kTCount == 0 &&
        second > kTBase && second < kTBase + kTCount)
        return first + (second - kTBase);
    const auto* end = std::end(kUnicodeComposites);
    const auto* it = std::lower_bound(std::begin(kUnicodeComposites), end, std::make_pair(first, second),
        [](const UnicodeComposite& row, const std::pair<uint32_t, uint32_t>& key) {
            return row.first != key.first ? row.first < key.first : row.second < key.second;
        });
    return it != end && it->first == first && it->second == second ? it->composite : 0;
}

void compose(const std::vector<uint32_t>& in, std::vector<uint32_t>& out) {
    constexpr size_t kNone = static_cast<size_t>(-1);
    size_t starter = kNone;
    uint32_t last_class = 0;
    for (uint32_t cp : in) {
        const uint32_t cls = combining_class(cp);
        if (starter != kNone) {
            const bool adjacent = out.size() - 1 == starter;
            if (adjacent || (last_class != 0 && last_class < cls)) {
                if (const uint32_t merged = compose_pair(out[starter], cp)) { out[starter] = merged; continue; }
            }
        }
        if (cls == 0) { starter = out.size(); last_class = 0; }
        else last_class = cls;
        out.push_back(cp);
    }
}

std::string normalize_argument(lua_State* L, bool compose_result) {
    size_t length = 0;
    const char* data = luaL_checklstring(L, 1, &length);
    std::vector<uint32_t> points, decomposed, composed;
    if (!decode_strict(std::string(data, length), points)) luaL_error(L, "String contains invalid UTF-8");
    decompose(points, decomposed);
    const std::vector<uint32_t>* result = &decomposed;
    if (compose_result) { compose(decomposed, composed); result = &composed; }
    std::string text;
    for (uint32_t cp : *result) encode(cp, text);
    return text;
}

int utf8_nfc(lua_State* L) {
    const std::string text = normalize_argument(L, true);
    lua_pushlstring(L, text.data(), text.size());
    return 1;
}

int utf8_nfd(lua_State* L) {
    const std::string text = normalize_argument(L, false);
    lua_pushlstring(L, text.data(), text.size());
    return 1;
}

bool in_extend_ranges(uint32_t cp) {
    const auto* begin = std::begin(kUnicodeGraphemeExtend);
    const auto* it = std::upper_bound(begin, std::end(kUnicodeGraphemeExtend), cp,
        [](uint32_t value, const UnicodeRange& row) { return value < row.first; });
    return it != begin && cp <= (it - 1)->last;
}
bool is_extend(uint32_t cp) {
    return in_extend_ranges(cp) || combining_class(cp) != 0 || (cp >= 0x1F3FB && cp <= 0x1F3FF) || (cp >= 0xE0020 && cp <= 0xE007F);
}
bool is_pictographic(uint32_t cp) {
    return (cp >= 0x1F000 && cp <= 0x1FAFF) || (cp >= 0x2600 && cp <= 0x27BF) || (cp >= 0x2300 && cp <= 0x23FF) ||
           (cp >= 0x2B00 && cp <= 0x2BFF) || cp == 0xA9 || cp == 0xAE || cp == 0x203C || cp == 0x2049 || cp == 0x2122 ||
           cp == 0x2139 || (cp >= 0x2194 && cp <= 0x21AA);
}
bool is_regional(uint32_t cp) { return cp >= 0x1F1E6 && cp <= 0x1F1FF; }
// Hangul syllable types: 1 = L, 2 = V, 3 = T, 4 = LV, 5 = LVT, 0 = other.
int hangul_type(uint32_t cp) {
    if ((cp >= 0x1100 && cp <= 0x115F) || (cp >= 0xA960 && cp <= 0xA97C)) return 1;
    if ((cp >= 0x1160 && cp <= 0x11A7) || (cp >= 0xD7B0 && cp <= 0xD7C6)) return 2;
    if ((cp >= 0x11A8 && cp <= 0x11FF) || (cp >= 0xD7CB && cp <= 0xD7FB)) return 3;
    if (cp >= kSBase && cp < kSBase + kSCount) return (cp - kSBase) % kTCount == 0 ? 4 : 5;
    return 0;
}

// Iterator state lives in upvalues: the string, the 0-based byte where the next cluster starts, and the last start byte.
// An invalid byte forms a cluster of its own, as it does in Roblox.
int graphemes_step(lua_State* L) {
    size_t size = 0;
    const char* data = lua_tolstring(L, lua_upvalueindex(1), &size);
    const std::string text(data, size);
    const lua_Integer position_value = lua_tointeger(L, lua_upvalueindex(2));
    const lua_Integer last_value = lua_tointeger(L, lua_upvalueindex(3));
    if (position_value < 0 || static_cast<size_t>(position_value) >= text.size() || position_value > last_value) return 0;
    const size_t position = static_cast<size_t>(position_value);
    size_t length = 0;
    const uint32_t cp = decode_one(text, position, length);
    size_t end = position + (length ? length : 1);
    if (length) {
        uint32_t previous = cp;
        int regional_run = is_regional(cp) ? 1 : 0;
        while (end < text.size()) {
            size_t next_length = 0;
            const uint32_t next = decode_one(text, end, next_length);
            if (!next_length) break;
            bool join = false;
            if (previous == 0x0D && next == 0x0A) join = true;
            else if (previous == 0x0D || previous == 0x0A || next == 0x0D || next == 0x0A) join = false;
            else if (is_extend(next)) join = true;
            else if (previous == 0x200D && is_pictographic(next)) join = true;
            else if (is_regional(previous) && is_regional(next) && regional_run % 2 == 1) join = true;
            else {
                const int a = hangul_type(previous), b = hangul_type(next);
                join = (a == 1 && (b == 1 || b == 2 || b == 4 || b == 5)) || ((a == 4 || a == 2) && (b == 2 || b == 3)) ||
                       ((a == 5 || a == 3) && b == 3);
            }
            if (!join) break;
            regional_run = is_regional(next) ? regional_run + 1 : 0;
            previous = next;
            end += next_length;
        }
    }
    lua_pushinteger(L, static_cast<lua_Integer>(end));
    lua_replace(L, lua_upvalueindex(2));
    lua_pushinteger(L, static_cast<lua_Integer>(position + 1));
    lua_pushinteger(L, static_cast<lua_Integer>(end));
    return 2;
}

int utf8_graphemes(lua_State* L) {
    size_t size = 0;
    luaL_checklstring(L, 1, &size);
    const auto resolve = [&](int index, lua_Integer fallback) {
        lua_Integer value = luaL_optinteger(L, index, fallback);
        if (value < 0) value = static_cast<lua_Integer>(size) + value + 1;
        return value;
    };
    lua_Integer first = resolve(2, 1), last = resolve(3, -1);
    if (first < 1) first = 1;
    if (last > static_cast<lua_Integer>(size)) last = static_cast<lua_Integer>(size);
    lua_pushvalue(L, 1);
    lua_pushinteger(L, first - 1);
    lua_pushinteger(L, last - 1);
    // The engine's iterator closure has no debug name (debug.info(it, "n") is empty).
    lua_pushcclosurek(L, graphemes_step, nullptr, 3, nullptr);
    return 1;
}
}  // namespace

void install_utf8_extras(lua_State* L) {
    lua_pushcfunction(L, utf8_graphemes, "graphemes");
    lua_setfield(L, -2, "graphemes");
    lua_pushcfunction(L, utf8_nfc, "nfcnormalize");
    lua_setfield(L, -2, "nfcnormalize");
    lua_pushcfunction(L, utf8_nfd, "nfdnormalize");
    lua_setfield(L, -2, "nfdnormalize");
}


namespace {
// coroutine.finally(thread, callback): accepted and ignored here; protected scripts only check that it exists and how it
// validates its arguments.
int coroutine_finally(lua_State* L)
{
    luaL_checktype(L, 1, LUA_TTHREAD);
    luaL_checktype(L, 2, LUA_TFUNCTION);
    return 0;
}
int global_version(lua_State* L)
{
    lua_pushstring(L, "0.744.0.7440000");
    return 1;
}
int global_settings(lua_State* L)
{
    return luaL_error(L, "The current thread cannot call 'settings' (lacking capability Plugin)"), 0;
}
}  // namespace

void install_roblox_global_extras(lua_State* L)
{
    lua_getglobal(L, "coroutine");
    if (lua_istable(L, -1))
    {
        lua_pushcfunction(L, coroutine_finally, "finally");
        lua_setfield(L, -2, "finally");
    }
    lua_pop(L, 1);
    lua_pushcfunction(L, global_version, "version");
    lua_setglobal(L, "version");
    lua_pushcfunction(L, global_settings, "settings");
    lua_setglobal(L, "settings");
}

void install_roblox_os_layout(lua_State* L)
{
    lua_getglobal(L, "os");
    if (!lua_istable(L, -1))
    {
        lua_pop(L, 1);
        return;
    }
    lua_createtable(L, 0, 4);
    for (const char* name : {"clock", "date", "difftime", "time"})
    {
        lua_getfield(L, -2, name);
        lua_setfield(L, -2, name);
    }
    lua_setglobal(L, "os");
    lua_pop(L, 1); // the old table
}
