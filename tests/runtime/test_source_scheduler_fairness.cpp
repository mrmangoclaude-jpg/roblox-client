#include "source_scheduler.hpp"
#include <Luau/Compiler.h>
#include <lua.h>
#include <lualib.h>
#include <algorithm>
#include <cassert>
#include <chrono>
#include <string>
#include <thread>
#include <cstdlib>
#include <vector>

using Clock = std::chrono::steady_clock;

struct InterruptDeadline {
    Clock::time_point value=Clock::time_point::max();
    lua_State* forced_thread=nullptr;
    int forced_interrupts=0;
};
static int produce_output(lua_State* L) {
    auto* produced=static_cast<bool*>(lua_touserdata(L,lua_upvalueindex(1)));
    assert(produced);
    *produced=true;
    return 0;
}

static void interrupt(lua_State* L,int gc) {
    if(gc>=0)return;
    auto* deadline=static_cast<InterruptDeadline*>(lua_callbacks(L)->userdata);
    if(deadline&&deadline->forced_thread==L&&deadline->forced_interrupts>0&&lua_isyieldable(L)) {
        --deadline->forced_interrupts;lua_break(L);return;
    }
    if(deadline&&Clock::now()>=deadline->value&&lua_isyieldable(L))lua_break(L);
}

static int response_wait(lua_State* L) {
    auto* scheduler=static_cast<SourceScheduler*>(lua_touserdata(L,lua_upvalueindex(1)));
    scheduler->wait_signal(L);
    lua_settop(L,0);
    return lua_yield(L,0);
}

static std::string string_at(lua_State* L, int index) {
    size_t size=0;
    const char* value=lua_tolstring(L,index,&size);
    return value?std::string(value,size):std::string();
}

int main() {
    lua_State* main=luaL_newstate();
    assert(main);
    InterruptDeadline interrupt_deadline;
    lua_callbacks(main)->userdata=&interrupt_deadline;
    lua_callbacks(main)->interrupt=interrupt;
    luaL_openlibs(main);
    luaL_sandbox(main);

    lua_State* environment=lua_newthread(main);
    luaL_sandboxthread(environment);
    SourceScheduler scheduler(main,Clock::now()+std::chrono::seconds(2),true);
    scheduler.install(environment);

    lua_State* root=lua_newthread(environment);
    const std::string source=R"(
order={}
task.defer(function() table.insert(order,"callback-1") end)
task.defer(function() table.insert(order,"callback-2") end)
task.delay(0.001,function() table.insert(order,"timer") end)
)";
    const std::string bytecode=Luau::compile(source);
    assert(luau_load(root,"=scheduler-fairness",bytecode.data(),bytecode.size(),0)==0);
    scheduler.start(root);
    lua_pop(environment,1);

    // Ensure the timer is expired before step() enters its expensive pump.
    std::this_thread::sleep_for(std::chrono::milliseconds(10));
    const auto first_deadline=Clock::now()+std::chrono::milliseconds(20);
    bool pumped=false;
    scheduler.step(first_deadline,[&] {
        if(!pumped) {
            pumped=true;
            std::this_thread::sleep_until(first_deadline);
        }
    });

    lua_getglobal(environment,"order");
    assert(lua_istable(environment,-1));
    lua_rawgeti(environment,-1,1);
    assert(string_at(environment,-1)=="callback-1");
    lua_pop(environment,1);
    lua_rawgeti(environment,-1,2);
    assert(string_at(environment,-1)=="callback-2");
    lua_pop(environment,1);
    lua_rawgeti(environment,-1,3);
    assert(string_at(environment,-1)=="timer");
    lua_pop(environment,2);

    // Ready callbacks and the expired timer all ran before the expensive
    // pump. Another step must not repeat any of them.
    scheduler.step(Clock::now()+std::chrono::milliseconds(20));
    lua_getglobal(environment,"order");
    assert(lua_objlen(environment,-1)==3);lua_pop(environment,1);

    // A large authored job gets a bounded larger turn; callbacks still get
    // their short turn, and both are capped by the transaction deadline.
#ifdef _WIN32
    _putenv_s("RCR_LUAU_LARGE_TEST","1");
#else
    setenv("RCR_LUAU_LARGE_TEST","1",1);
#endif
    lua_State* authored=lua_newthread(environment);
    const auto authored_code=Luau::compile("task.wait(.001);task.defer(function() callbackRan=true end);authoredRan=true");
    assert(luau_load(authored,"=authored-quantum",authored_code.data(),authored_code.size(),0)==0);
    scheduler.start(authored);lua_pop(environment,1);
    std::this_thread::sleep_for(std::chrono::milliseconds(3));
    std::vector<double> deadlines;
    const auto budget=Clock::now()+std::chrono::milliseconds(50);
    scheduler.step(budget,{},256,[&](Clock::time_point next){
        assert(next<=budget);
        deadlines.push_back(std::chrono::duration<double,std::milli>(next-Clock::now()).count());
    });
    assert(deadlines.size()==4);
    assert(deadlines[0]>4&&deadlines[0]<=8.1);
    assert(deadlines[2]>0&&deadlines[2]<=2.1);
    lua_getglobal(environment,"authoredRan");assert(lua_toboolean(environment,-1));lua_pop(environment,1);
    lua_getglobal(environment,"callbackRan");assert(lua_toboolean(environment,-1));lua_pop(environment,1);

    // Even an expensive pump must not wake a timer created in this frame.
    // Otherwise two authored poses separated by task.wait collapse into the
    // same outbound mutation batch and physics only sees the final pose.
    scheduler.begin_frame();
    lua_State* pulse=lua_newthread(environment);
    const auto pulse_code=Luau::compile(R"(
phases={1}
task.wait(0)
table.insert(phases,2)
task.delay(0,function() delayedFrame=true end)
task.wait(.001)
table.insert(phases,3)
)");
    assert(luau_load(pulse,"=frame-boundaries",pulse_code.data(),pulse_code.size(),0)==0);
    scheduler.start(pulse);lua_pop(environment,1);
    auto slow_pump=[](){std::this_thread::sleep_for(std::chrono::milliseconds(5));};
    scheduler.step(Clock::now()+std::chrono::milliseconds(50),slow_pump);
    lua_getglobal(environment,"phases");assert(lua_objlen(environment,-1)==1);lua_pop(environment,1);
    scheduler.step(Clock::now()+std::chrono::milliseconds(50),slow_pump);
    lua_getglobal(environment,"phases");assert(lua_objlen(environment,-1)==2);lua_pop(environment,1);
    lua_getglobal(environment,"delayedFrame");assert(lua_isnil(environment,-1));lua_pop(environment,1);
    scheduler.step(Clock::now()+std::chrono::milliseconds(50),slow_pump);
    lua_getglobal(environment,"phases");assert(lua_objlen(environment,-1)==3);lua_pop(environment,1);
    lua_getglobal(environment,"delayedFrame");assert(lua_toboolean(environment,-1));lua_pop(environment,1);

    // A delivered RPC response must retain prompt scheduling across CPU
    // interrupts, while ordinary callback work continues to receive turns.
    lua_pushlightuserdata(environment,&scheduler);
    lua_pushcclosure(environment,response_wait,"responseWait",1);
    lua_setglobal(environment,"responseWait");
    lua_State* rpc_root=lua_newthread(environment);
    const auto rpc_code=Luau::compile(R"(
responseDone=false
ordinaryProgress=0
responseThread=task.defer(function()
    responseWait()
    local total=0
    local untilTime=os.clock()+0.01
    while os.clock()<untilTime do total=total+1 end
    responseDone=total>0
end)
for i=1,32 do
    task.defer(function()
        while true do ordinaryProgress=ordinaryProgress+1 end
    end)
end
)");
    assert(luau_load(rpc_root,"=response-continuation-fairness",rpc_code.data(),rpc_code.size(),0)==0);
    scheduler.start(rpc_root);lua_pop(environment,1);
    auto set_interrupt_deadline=[&](Clock::time_point deadline){interrupt_deadline.value=deadline;};
    scheduler.step(Clock::now()+std::chrono::milliseconds(100),{},256,set_interrupt_deadline);
    lua_getglobal(environment,"responseThread");
    lua_State* response_thread=lua_tothread(environment,-1);assert(response_thread);lua_pop(environment,1);
    assert(std::string(scheduler.task_state(response_thread))=="waiting");
    lua_getglobal(environment,"ordinaryProgress");double ordinary_before=lua_tonumber(environment,-1);lua_pop(environment,1);
    // Exercise two actual VM interrupts deterministically. Wall-clock work
    // alone can finish after one interrupt when unrelated callbacks run
    // between its turns, making this assertion depend on machine load.
    interrupt_deadline.forced_thread=response_thread;
    interrupt_deadline.forced_interrupts=2;
    scheduler.wake_signal(response_thread,[](lua_State*){return 0;},true);
    size_t response_interruptions=0;
    bool response_done=false;
    bool response_priority_survived_interrupt=false;
    for(int frame=0;frame<12&&!response_done;frame++) {
        // Model the short scheduler slice left after host/world update work.
        scheduler.step(Clock::now()+std::chrono::milliseconds(5),{},256,set_interrupt_deadline);
        auto progress=scheduler.task_progress(response_thread);
        response_interruptions=std::max(response_interruptions,progress.interruptions);
        response_priority_survived_interrupt|=progress.response_priority_active&&progress.interruptions>0;
        lua_getglobal(environment,"responseDone");response_done=lua_toboolean(environment,-1);lua_pop(environment,1);
    }
    assert(response_done);
    assert(response_interruptions>=2);
    assert(response_priority_survived_interrupt);
    lua_getglobal(environment,"ordinaryProgress");
    assert(lua_tonumber(environment,-1)>ordinary_before);lua_pop(environment,1);

    // A real Luau yield clears the response boost immediately.
    lua_State* yield_root=lua_newthread(environment);
    const auto yield_code=Luau::compile(R"(
yieldThread=task.defer(function()
    responseWait()
    task.wait(0.001)
    yieldFinished=true
end)
)");
    assert(luau_load(yield_root,"=response-yield-clears-priority",yield_code.data(),yield_code.size(),0)==0);
    scheduler.start(yield_root);lua_pop(environment,1);
    scheduler.step(Clock::now()+std::chrono::milliseconds(100),{},256,set_interrupt_deadline);
    lua_getglobal(environment,"yieldThread");
    lua_State* yield_thread=lua_tothread(environment,-1);assert(yield_thread);lua_pop(environment,1);
    assert(std::string(scheduler.task_state(yield_thread))=="waiting");
    scheduler.wake_signal(yield_thread,[](lua_State*){return 0;},true);
    scheduler.step(Clock::now()+std::chrono::milliseconds(100),{},256,set_interrupt_deadline);
    assert(std::string(scheduler.task_state(yield_thread))=="sleeping");
    assert(!scheduler.task_progress(yield_thread).response_priority_active);

    // A long non-yielding response continuation loses its boost after 32 ms,
    // while the ordinary callback lane keeps receiving work.
    lua_State* long_root=lua_newthread(environment);
    const auto long_code=Luau::compile(R"(
longResponseThread=task.defer(function()
    responseWait()
    local total=0
    local untilTime=os.clock()+0.08
    while os.clock()<untilTime do total=total+1 end
    longResponseDone=total>0
end)
)");
    assert(luau_load(long_root,"=response-priority-budget",long_code.data(),long_code.size(),0)==0);
    scheduler.start(long_root);lua_pop(environment,1);
    scheduler.step(Clock::now()+std::chrono::milliseconds(100),{},256,set_interrupt_deadline);
    lua_getglobal(environment,"longResponseThread");
    lua_State* long_thread=lua_tothread(environment,-1);assert(long_thread);lua_pop(environment,1);
    assert(std::string(scheduler.task_state(long_thread))=="waiting");
    lua_getglobal(environment,"ordinaryProgress");double ordinary_before_long=lua_tonumber(environment,-1);lua_pop(environment,1);
    scheduler.wake_signal(long_thread,[](lua_State*){return 0;},true);
    for(int frame=0;frame<24&&scheduler.task_progress(long_thread).response_priority_active;frame++)
        scheduler.step(Clock::now()+std::chrono::milliseconds(5),{},256,set_interrupt_deadline);
    auto long_progress=scheduler.task_progress(long_thread);
    assert(!long_progress.response_priority_active);
    assert(long_progress.interruptions>=16);
    assert(std::string(scheduler.task_state(long_thread))=="ready");
    lua_getglobal(environment,"longResponseDone");assert(!lua_toboolean(environment,-1));lua_pop(environment,1);
    lua_getglobal(environment,"ordinaryProgress");
    assert(lua_tonumber(environment,-1)>ordinary_before_long);lua_pop(environment,1);

    // A host output predicate ends a long scheduler step as soon as an
    // authored callback produces work. Unrun callbacks stay queued, and the
    // producer's continuation runs normally on a later frame.
    bool output_produced=false;
    lua_pushlightuserdata(environment,&output_produced);
    lua_pushcclosure(environment,produce_output,"produceOutput",1);
    lua_setglobal(environment,"produceOutput");
    lua_State* output_root=lua_newthread(environment);
    const auto output_code=Luau::compile(R"(
outputProducer=task.defer(function()
    produceOutput()
    task.wait(0.001)
    outputProducerContinued=true
end)
outputBusyProgress=0
for i=1,24 do
    task.defer(function()
        while true do outputBusyProgress=outputBusyProgress+1 end
    end)
end
)");
    assert(luau_load(output_root,"=output-yield-preserves-work",output_code.data(),output_code.size(),0)==0);
    scheduler.start(output_root);lua_pop(environment,1);
    auto step_interrupt=[&](Clock::time_point deadline){interrupt_deadline.value=deadline;};
    auto yield_for_output=[&](){return output_produced;};
    const auto output_step_started=Clock::now();
    scheduler.step(output_step_started+std::chrono::milliseconds(250),{},256,
                   step_interrupt,{},yield_for_output);
    const auto output_step_elapsed=Clock::now()-output_step_started;
    assert(output_produced);
    assert(output_step_elapsed<std::chrono::milliseconds(100));
    lua_getglobal(environment,"outputProducer");
    lua_State* output_thread=lua_tothread(environment,-1);assert(output_thread);lua_pop(environment,1);
    assert(std::string(scheduler.task_state(output_thread))=="sleeping");
    assert(scheduler.pending()>0);
    lua_getglobal(environment,"outputProducerContinued");assert(!lua_toboolean(environment,-1));lua_pop(environment,1);
    lua_getglobal(environment,"outputBusyProgress");double output_busy_before=lua_tonumber(environment,-1);lua_pop(environment,1);

    output_produced=false; // Host consumed the output before the next step.
    std::this_thread::sleep_for(std::chrono::milliseconds(3));
    scheduler.begin_frame();
    scheduler.step(Clock::now()+std::chrono::milliseconds(250),{},256,
                   step_interrupt,{},yield_for_output);
    lua_getglobal(environment,"outputProducerContinued");assert(lua_toboolean(environment,-1));lua_pop(environment,1);
    lua_getglobal(environment,"outputBusyProgress");
    assert(lua_tonumber(environment,-1)>output_busy_before);lua_pop(environment,1);

    lua_close(main);
}
