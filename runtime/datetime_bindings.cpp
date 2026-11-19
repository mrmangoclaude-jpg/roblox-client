#include "datetime_bindings.hpp"

#include <lua.h>
#include <lualib.h>

#include <array>
#include <chrono>
#include <cmath>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <ctime>
#include <limits>

namespace {
constexpr const char* kDateTimeMeta = "LocalLuau.DateTime";
constexpr int64_t kMinMillis = -17987443200000LL;
constexpr int64_t kMaxMillis = 253402300799999LL;
struct DateTimeValue { int64_t millis; };

bool leap_year(int64_t year) {
    return year % 4 == 0 && (year % 100 != 0 || year % 400 == 0);
}
int days_in_month(int64_t year, int64_t month) {
    static constexpr int days[] = {31,28,31,30,31,30,31,31,30,31,30,31};
    return days[month - 1] + (month == 2 && leap_year(year) ? 1 : 0);
}

// Gregorian civil date conversion, with 1970-01-01 as day zero.
int64_t days_from_civil(int64_t year, unsigned month, unsigned day) {
    year -= month <= 2;
    const int64_t era = (year >= 0 ? year : year - 399) / 400;
    const unsigned yoe = static_cast<unsigned>(year - era * 400);
    const unsigned doy = (153 * (month + (month > 2 ? -3 : 9)) + 2) / 5 + day - 1;
    const unsigned doe = yoe * 365 + yoe / 4 - yoe / 100 + doy;
    return era * 146097 + static_cast<int64_t>(doe) - 719468;
}
struct CivilDate { int64_t year; unsigned month; unsigned day; };
CivilDate civil_from_days(int64_t z) {
    z += 719468;
    const int64_t era = (z >= 0 ? z : z - 146096) / 146097;
    const unsigned doe = static_cast<unsigned>(z - era * 146097);
    const unsigned yoe = (doe - doe / 1460 + doe / 36524 - doe / 146096) / 365;
    int64_t year = static_cast<int64_t>(yoe) + era * 400;
    const unsigned doy = doe - (365 * yoe + yoe / 4 - yoe / 100);
    const unsigned mp = (5 * doy + 2) / 153;
    const unsigned day = doy - (153 * mp + 2) / 5 + 1;
    const unsigned month = mp + (mp < 10 ? 3 : -9);
    year += month <= 2;
    return {year, month, day};
}
int64_t floor_div(int64_t value, int64_t divisor) {
    int64_t quotient = value / divisor;
    if (value % divisor < 0) --quotient;
    return quotient;
}
DateTimeValue* check_datetime(lua_State* L, int index) {
    return static_cast<DateTimeValue*>(luaL_checkudata(L, index, kDateTimeMeta));
}
void push_datetime(lua_State* L, int64_t millis, int64_t minimum=kMinMillis, int64_t maximum=kMaxMillis) {
    if (millis < minimum || millis > maximum) {
        luaL_error(L, "DateTime timestamp is outside the supported 1400-9999 range");
        return;
    }
    auto* result = static_cast<DateTimeValue*>(lua_newuserdatatagged(L, sizeof(DateTimeValue), 0));
    result->millis = millis;
    luaL_getmetatable(L, kDateTimeMeta);
    lua_setmetatable(L, -2);
}
bool finite_floor(lua_State* L, int index, int64_t minimum, int64_t maximum, int64_t& result) {
    double value = luaL_checknumber(L, index);
    if (!std::isfinite(value) || value < static_cast<double>(minimum) - 1.0
        || value > static_cast<double>(maximum) + 1.0) return false;
    double floored = std::floor(value);
    if (floored < static_cast<double>(minimum) || floored > static_cast<double>(maximum)) return false;
    result = static_cast<int64_t>(floored);
    return true;
}
int64_t make_millis(lua_State* L, int first) {
    const int count = lua_gettop(L) - first + 1;
    if (count < 0 || count > 7) {
        luaL_error(L, "fromUniversalTime expects at most 7 time components");
        return 0;
    }
    std::array<int64_t,7> values{1970,1,1,0,0,0,0};
    for (int i = 0; i < count; ++i) {
        int64_t value = 0;
        if (!finite_floor(L, first + i, -1000000000000LL, 1000000000000LL, value)) {
            luaL_error(L, "DateTime components must be finite and bounded");
            return 0;
        }
        values[static_cast<size_t>(i)] = value;
    }
    const auto year = values[0], month = values[1], day = values[2];
    if (year < 1400 || year > 9999 || month < 1 || month > 12
        || day < 1 || day > days_in_month(year, month)) {
        luaL_error(L, "Invalid Gregorian date or year outside 1400-9999");
        return 0;
    }
    const int64_t days = days_from_civil(year, static_cast<unsigned>(month), static_cast<unsigned>(day));
    // Before multiplying, bound time components to leave int64 headroom. The
    // final supported timestamp range is much smaller than these guards.
    constexpr int64_t kComponentGuard = 1000000000000LL;
    for (size_t i = 3; i < values.size(); ++i) {
        if (values[i] < -kComponentGuard || values[i] > kComponentGuard) {
            luaL_error(L, "DateTime time components are too large");
            return 0;
        }
    }
    const int64_t day_millis = days * 86400000LL;
    // Boost time_duration, as used by Studio, gives the entire time portion a
    // negative sign if ANY time component is negative (even a millisecond).
    bool negative=false;
    for(size_t i=3;i<values.size();++i){if(values[i]<0){negative=true;values[i]=-values[i];}}
    int64_t time_millis = ((values[3] * 60 + values[4]) * 60 + values[5]) * 1000 + values[6];
    if(negative)time_millis=-time_millis;
    if ((time_millis > 0 && day_millis > std::numeric_limits<int64_t>::max() - time_millis)
        || (time_millis < 0 && day_millis < std::numeric_limits<int64_t>::min() - time_millis)) {
        luaL_error(L, "DateTime time components overflow");
        return 0;
    }
    return day_millis + time_millis;
}

int from_unix_seconds(lua_State* L) {
    double seconds = luaL_checknumber(L, 1);
    if (!std::isfinite(seconds) || seconds < static_cast<double>(kMinMillis) / 1000.0 - 1.0
        || seconds > static_cast<double>(kMaxMillis) / 1000.0 + 1.0) {
        luaL_error(L, "Unix timestamp is outside the supported 1400-9999 range"); return 0;
    }
    // This constructor has one-second precision. Truncation toward zero also
    // matches negative sub-second values (for example -0.0001 -> Unix epoch).
    const double whole_seconds = std::trunc(seconds);
    const double millis = whole_seconds * 1000.0;
    if (millis < static_cast<double>(kMinMillis) || millis > static_cast<double>(kMaxMillis)) {
        luaL_error(L, "Unix timestamp is outside the supported 1400-9999 range"); return 0;
    }
    push_datetime(L, static_cast<int64_t>(millis));
    return 1;
}
int from_unix_millis(lua_State* L) {
    int64_t millis = 0;
    if (!finite_floor(L, 1, kMinMillis, kMaxMillis, millis)) {
        luaL_error(L, "Unix millisecond timestamp is outside the supported 1400-9999 range");
        return 0;
    }
    push_datetime(L, millis);
    return 1;
}
int from_universal_time(lua_State* L) {
    push_datetime(L, make_millis(L, 1));
    return 1;
}
// Studio 0.745 uses the device's CURRENT UTC offset for local conversion,
// including dates in a different daylight-saving season. Do not use mktime
// with the requested date: that would apply historical DST rules instead.
int64_t current_local_offset() {
    const std::time_t now=std::time(nullptr);
    std::tm local{};
#ifdef _WIN32
    if(localtime_s(&local,&now)!=0)return 0;
    return static_cast<int64_t>(_mkgmtime(&local)-now)*1000;
#else
    if(!localtime_r(&now,&local))return 0;
    return static_cast<int64_t>(local.tm_gmtoff)*1000;
#endif
}
int from_local_time(lua_State* L) {
    const int64_t wall=make_millis(L,1);
    const int64_t offset=current_local_offset();
    if(wall<kMinMillis||wall>kMaxMillis){luaL_error(L,"Local DateTime is outside the supported 1400-9999 range");return 0;}
    push_datetime(L,wall-offset,kMinMillis-offset,kMaxMillis-offset);return 1;
}
int from_iso_date(lua_State* L) {
    size_t length = 0;
    const char* text = luaL_checklstring(L, 1, &length);
    // Bounded ISO calendar subset measured against Studio 0.745. Optional
    // date/time fields default to January 1 / midnight; fractions truncate to ms.
    if(length<4||length>4096){lua_pushnil(L);return 1;}
    size_t at=0;
    auto number=[&](int count,int& out){
        if(at+count>length)return false;
        out=0;
        for(int i=0;i<count;++i){char c=text[at++];if(c<'0'||c>'9')return false;out=out*10+c-'0';}
        return true;
    };
    auto invalid=[&](){lua_pushnil(L);return 1;};
    int year=0,month=1,day=1,hour=0,minute=0,second=0,millis=0;
    if(!number(4,year))return invalid();
    if(at<length&&text[at]=='-'){++at;if(!number(2,month))return invalid();
        if(at<length&&text[at]=='-'){++at;if(!number(2,day))return invalid();}}
    if(year<1400||year>9999||month<1||month>12||day<1||day>days_in_month(year,month))return invalid();
    if(at<length){
        if(text[at]!='T'&&text[at]!='t'&&text[at]!=' ')return invalid();
        ++at;
        if(at<length){
            if(!number(2,hour))return invalid();
            if(at<length&&text[at]==':'){++at;if(!number(2,minute))return invalid();
                if(at<length&&text[at]==':'){++at;if(!number(2,second))return invalid();}}
            if(at<length&&text[at]=='.'){
                ++at;int digits=0;
                while(at<length&&text[at]>='0'&&text[at]<='9'){
                    if(digits<3)millis=millis*10+text[at]-'0';
                    ++digits;++at;
                }
                for(int i=digits;i<3;++i)millis*=10;
            }
        }
    }
    int offsetMinutes=0;
    if(at<length&&(text[at]=='+'||text[at]=='-')){
        int sign=text[at++]=='+'?1:-1,oh=0,om=0;
        if(!number(2,oh))return invalid();
        if(at<length&&text[at]==':'){++at;if(!number(2,om))return invalid();}
        if(at!=length)return invalid();
        offsetMinutes=sign*(oh*60+om);
        if(offsetMinutes < -12*60 || offsetMinutes > 14*60)return invalid();
    }
    // Studio accepts Z/z and an unconsumed suffix after the time; retain that
    // behavior instead of imposing a stricter internet timestamp grammar.
    const int64_t value=days_from_civil(year,month,day)*86400000LL
        +hour*3600000LL+minute*60000LL+second*1000LL+millis-offsetMinutes*60000LL;
    if(value<kMinMillis||value>kMaxMillis)return invalid();
    push_datetime(L,value);return 1;
}
int now(lua_State* L) {
    auto millis = std::chrono::duration_cast<std::chrono::milliseconds>(
        std::chrono::system_clock::now().time_since_epoch()).count();
    push_datetime(L,millis); return 1;
}
int push_time_components(lua_State* L,int64_t millis) {
    if(millis<kMinMillis||millis>kMaxMillis){luaL_error(L,"DateTime components are outside the supported 1400-9999 range");return 0;}
    const int64_t days = floor_div(millis,86400000LL);
    int64_t remainder = millis - days*86400000LL;
    auto civil = civil_from_days(days);
    lua_createtable(L,0,7);
    auto set=[&](const char* name,int64_t value){lua_pushinteger(L,value);lua_setfield(L,-2,name);};
    set("Year",civil.year);set("Month",civil.month);set("Day",civil.day);
    set("Hour",remainder/3600000);remainder%=3600000;
    set("Minute",remainder/60000);remainder%=60000;
    set("Second",remainder/1000);set("Millisecond",remainder%1000);
    return 1;
}
int universal_time(lua_State* L) {return push_time_components(L,check_datetime(L,1)->millis);}
int local_time(lua_State* L) {return push_time_components(L,check_datetime(L,1)->millis+current_local_offset());}
int to_iso_date(lua_State* L) {
    const int64_t millis=check_datetime(L,1)->millis;
    if(millis<kMinMillis||millis>kMaxMillis){luaL_error(L,"UTC DateTime is outside the supported 1400-9999 range");return 0;}
    const int64_t days=floor_div(millis,86400000LL);
    int64_t remainder=millis-days*86400000LL;
    auto civil=civil_from_days(days);
    int hour=static_cast<int>(remainder/3600000);remainder%=3600000;
    int minute=static_cast<int>(remainder/60000);remainder%=60000;
    int second=static_cast<int>(remainder/1000);
    char buffer[32];
    std::snprintf(buffer,sizeof(buffer),"%04lld-%02u-%02uT%02d:%02d:%02dZ",
        static_cast<long long>(civil.year),civil.month,civil.day,hour,minute,second);
    lua_pushstring(L,buffer); return 1;
}
int index(lua_State* L) {
    auto* value=check_datetime(L,1);const char* key=luaL_checkstring(L,2);
    if(std::strcmp(key,"UnixTimestampMillis")==0)lua_pushnumber(L,static_cast<double>(value->millis));
    else if(std::strcmp(key,"UnixTimestamp")==0)lua_pushnumber(L,static_cast<double>(floor_div(value->millis,1000)));
    else if(std::strcmp(key,"ToUniversalTime")==0)lua_pushcfunction(L,universal_time,"DateTime:ToUniversalTime");
    else if(std::strcmp(key,"ToLocalTime")==0)lua_pushcfunction(L,local_time,"DateTime:ToLocalTime");
    else if(std::strcmp(key,"ToIsoDate")==0)lua_pushcfunction(L,to_iso_date,"DateTime:ToIsoDate");
    else {lua_pushnil(L);}
    return 1;
}
int equal(lua_State* L) {
    auto* a=static_cast<DateTimeValue*>(lua_touserdata(L,1));
    auto* b=static_cast<DateTimeValue*>(lua_touserdata(L,2));
    bool valid_a=luaL_getmetafield(L,1,"__type")!=LUA_TNIL;
    if(valid_a)lua_pop(L,1);
    bool valid_b=luaL_getmetafield(L,2,"__type")!=LUA_TNIL;
    if(valid_b)lua_pop(L,1);
    lua_pushboolean(L,valid_a&&valid_b&&a&&b&&a->millis==b->millis);return 1;
}
int tostring_value(lua_State* L) {
    auto* value=check_datetime(L,1);char buffer[64];
    std::snprintf(buffer,sizeof(buffer),"%lld",static_cast<long long>(value->millis));
    lua_pushstring(L,buffer);return 1;
}
void set_constructor(lua_State* L,const char* name,lua_CFunction function) {
    lua_pushcfunction(L,function,name);lua_setfield(L,-2,name);
}
}

void install_datetime_bindings(lua_State* L) {
    luaL_newmetatable(L,kDateTimeMeta);
    lua_pushcfunction(L,index,"DateTime.__index");lua_setfield(L,-2,"__index");
    lua_pushcfunction(L,equal,"DateTime.__eq");lua_setfield(L,-2,"__eq");
    lua_pushcfunction(L,tostring_value,"DateTime.__tostring");lua_setfield(L,-2,"__tostring");
    lua_pushliteral(L,"DateTime");lua_setfield(L,-2,"__type");
    lua_pushliteral(L,"The metatable is locked");lua_setfield(L,-2,"__metatable");
    lua_pop(L,1);

    lua_createtable(L,0,6);
    set_constructor(L,"now",now);
    set_constructor(L,"fromUnixTimestamp",from_unix_seconds);
    set_constructor(L,"fromUnixTimestampMillis",from_unix_millis);
    set_constructor(L,"fromUniversalTime",from_universal_time);
    set_constructor(L,"fromLocalTime",from_local_time);
    set_constructor(L,"fromIsoDate",from_iso_date);
    lua_setreadonly(L,-1,true);
    lua_setglobal(L,"DateTime");
}
