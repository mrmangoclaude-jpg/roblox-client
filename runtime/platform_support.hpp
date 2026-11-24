#include <ctime>
#pragma once
#include <cstddef>
#include <fstream>
#include <stdexcept>
#include <string>
#include <vector>
#ifdef _WIN32
#ifndef NOMINMAX
#define NOMINMAX
#endif
#include <windows.h>
#include <bcrypt.h>
// Legacy Windows SDK macros collide with C++ identifiers in the runtime.
#undef near
#undef far
#undef small
inline int host_wide_main(int argc,wchar_t** argv,int (*entry)(int,char**)) {
    std::vector<std::string> values;
    std::vector<char*> pointers;
    values.reserve(argc); pointers.reserve(argc+1);
    for(int i=0;i<argc;i++) {
        int size=WideCharToMultiByte(CP_UTF8,WC_ERR_INVALID_CHARS,argv[i],-1,nullptr,0,nullptr,nullptr);
        if(size<=0)return 2;
        values.emplace_back(static_cast<size_t>(size),'\0');
        if(!WideCharToMultiByte(CP_UTF8,WC_ERR_INVALID_CHARS,argv[i],-1,values.back().data(),size,nullptr,nullptr))return 2;
        values.back().resize(size-1); pointers.push_back(values.back().data());
    }
    pointers.push_back(nullptr);
    return entry(argc,pointers.data());
}
constexpr int RTLD_LOCAL=0, RTLD_NOW=0;
inline void* dlopen(const char* path,int) { return reinterpret_cast<void*>(LoadLibraryA(path)); }
inline void* dlsym(void* handle,const char* name) {
    return reinterpret_cast<void*>(GetProcAddress(reinterpret_cast<HMODULE>(handle),name));
}
#else
#include <dlfcn.h>
#endif

inline bool host_entropy(void* data,size_t size) {
#ifdef _WIN32
    return size<=0xffffffffu && BCryptGenRandom(nullptr,static_cast<PUCHAR>(data),
        static_cast<ULONG>(size),BCRYPT_USE_SYSTEM_PREFERRED_RNG)==0;
#else
    std::ifstream source("/dev/urandom",std::ios::binary);
    return source && bool(source.read(static_cast<char*>(data),static_cast<std::streamsize>(size)));
#endif
}

// The Windows CRT ignores POSIX TZ strings (e.g. Etc/GMT+8), while Roblox and
// the Studio probe harness honour them. Parse the common forms ourselves so
// local-time conversion and os.date("%z") agree with Studio on every platform.
// POSIX Etc/GMT+N / GMT-N invert the sign; bare +HH:MM offsets do not.
inline bool timezone_offset_from_env(long& out_seconds)
{
    const char* env=std::getenv("TZ");
    if(!env||!*env)return false;
    const std::string text(env);
    const size_t sign=text.find_first_of("+-");
    if(sign==std::string::npos)return false;
    int hours=0,minutes=0;
    if(std::sscanf(text.c_str()+sign+1,"%d:%d",&hours,&minutes)<1)return false;
    if(hours<0||hours>23||minutes<0||minutes>59)return false;
    int direction=(text[sign]=='-')?-1:1;
    if(sign>0)direction=-direction; // GMT/UTC prefix: POSIX inverted sign
    out_seconds=static_cast<long>(direction)*(hours*3600+minutes*60);
    return true;
}

// Seconds by which local wall-clock time is ahead of UTC. MinGW's _mkgmtime
// misbehaves on this toolchain, so derive it from the civil date fields.
inline long local_timezone_offset_seconds()
{
    long from_env=0;
    if(timezone_offset_from_env(from_env))return from_env;
    std::time_t stamp=std::time(nullptr);
    std::tm local{}, utc{};
#if defined(_WIN32)
    localtime_s(&local,&stamp); gmtime_s(&utc,&stamp);
#else
    localtime_r(&stamp,&local); gmtime_r(&stamp,&utc);
#endif
    auto days_from_civil=[](int year,int month,int day)->long long
    {
        year-=month<=2?1:0;
        const int era=(year>=0?year:year-399)/400;
        const unsigned yoe=static_cast<unsigned>(year-era*400);
        const unsigned doy=(153u*static_cast<unsigned>(month+(month>2?-3:9))+2)/5+static_cast<unsigned>(day)-1;
        const unsigned doe=yoe*365+yoe/4-yoe/100+doy;
        return static_cast<long long>(era)*146097+static_cast<long long>(doe)-719468;
    };
    auto as_seconds=[&](const std::tm& value)->long long
    {
        return days_from_civil(value.tm_year+1900,value.tm_mon+1,value.tm_mday)*86400
             + static_cast<long long>(value.tm_hour)*3600
             + static_cast<long long>(value.tm_min)*60
             + value.tm_sec;
    };
    return static_cast<long>(as_seconds(local)-as_seconds(utc));
}
