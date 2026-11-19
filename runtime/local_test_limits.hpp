#pragma once
#include <cstdlib>
#include <cstring>
#include <cstddef>
// Explicit compatibility-test process profile. Normal limits stay unchanged.
inline bool large_local_test() {
    const char* value=std::getenv("RCR_LUAU_LARGE_TEST");return value&&std::strcmp(value,"1")==0;
}
inline size_t local_test_source_limit(size_t normal){return normal;}
inline int local_test_time_limit(){
    if(!large_local_test())return 2000;
    // Diagnostic knob for the compatibility profile only: ROVE_TEST_TIME_LIMIT_MS raises the cumulative CPU cap.
    const char* override_ms=std::getenv("ROVE_TEST_TIME_LIMIT_MS");
    const int parsed=override_ms?std::atoi(override_ms):0;
    return parsed>=1000&&parsed<=3600000?parsed:30000;
}
inline int local_test_memory_limit(){return 512;}
