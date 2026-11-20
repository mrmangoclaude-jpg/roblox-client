#pragma once
#include <lua.h>
#include <chrono>
#include <deque>
#include <functional>
#include <unordered_map>
#include <vector>
#include <string>

// Number of task.spawn calls whose child is currently running inline. Roblox runs a spawned function until it yields or ends;
// the time-slice interrupt must not break it, or the spawner is handed a thread that reads as "normal" (not closable).
inline int& unbreakable_spawn_depth() { static int depth=0; return depth; }

// A bounded cooperative scheduler shared by authored source jobs and callbacks.
class SourceScheduler {
public:
    using Clock=std::chrono::steady_clock;
    SourceScheduler(lua_State* main,Clock::time_point deadline,bool persistent=false):main_(main),deadline_(deadline),persistent_(persistent){}
    // Cumulative non-yielding CPU one background task may use before it is stopped; 0 keeps the process default.
    void set_task_cpu_limit_ms(int milliseconds){task_cpu_limit_ms_=milliseconds;}
    void install(lua_State* thread);
    int run(lua_State* root,int arguments,std::function<void()> pump={});
    lua_State* callback(lua_State* from,int reference,const std::function<int(lua_State*)>& arguments,std::function<bool()> guard={},const std::string& owner="",int identity=-1);
    // Starts a callback immediately until it yields, completes, or exhausts
    // its scheduling slice. Leaves the child thread on the caller's stack.
    lua_State* callback_now(lua_State* from,int reference,const std::function<int(lua_State*)>& arguments,const std::string& owner,int identity=-1);
    void wait_signal(lua_State* thread);
    void wake_signal(lua_State* thread,const std::function<int(lua_State*)>& arguments,bool response_ready=false);
    const std::vector<std::string>& errors() const{return errors_;}
    void start(lua_State* root,int arguments=0);
    int completion(lua_State* root) const;
    const char* task_state(lua_State* thread) const;
    struct Progress {size_t resumes=0,yields=0,interruptions=0;double execution_ms=0;bool response_priority_active=false;};
    Progress task_progress(lua_State* thread) const;
    // Persistent hosts open a frame before executing authored code. Timers
    // created in it cannot resume until a later frame has begun.
    void begin_frame(){++frame_;frame_open_=true;}
    // should_yield is a side-effect-free pending-output check. When it is
    // true, the host must drain that output before calling step again.
    // Unfinished tasks and invocations remain queued across this handoff.
    void step(Clock::time_point deadline,std::function<void()> pump={},size_t max_resumes=256,
              std::function<void(Clock::time_point)> set_interrupt_deadline={},
              std::function<void()> progress_invocations={},
              std::function<bool()> should_yield={});
    void release_root(lua_State* root);
    size_t pending() const;
    size_t callback_capacity();
    size_t invocation_capacity();
    void clear_errors(){errors_.clear();}
    std::string owner(lua_State* thread) const;
    static int identity(lua_State* thread);
    static void set_identity(lua_State* thread,int identity);
    static bool has_capability(lua_State* thread,const std::string& capability);
    lua_State* spawn_owned(lua_State* from,int function_index,const std::string& owner,bool report_errors=true);
    void cancel_owner(const std::string& owner);
    lua_State* invoke_callback(lua_State* from,int reference,const std::function<int(lua_State*)>& arguments,const std::string& owner,int identity=-1);
    void release_invocation(lua_State* thread);
private:
    // Thread provenance survives ordinary coroutine.resume and scheduler
    // bookkeeping cleanup. It is inherited at VM thread creation, rather
    // than inferred from script globals or a hook's closure environment.
    struct ThreadOwner {
        SourceScheduler* scheduler;std::string owner;
        // A coroutine.resume/wrap frame retains this child on its VM stack
        // while propagating LUA_BREAK. Resume the child before that frame.
        lua_State* interrupted_child=nullptr;
        int identity=8;
    };
    static void thread_lifecycle(lua_State* parent,lua_State* thread);
    static void coroutine_interrupt(lua_State* parent,lua_Debug* debug);
    enum State{Running,Ready,Sleeping,Waiting,Done,Cancelled};
    struct Task {
        lua_State* thread=nullptr;int reference=LUA_NOREF;State state=Ready;int arguments=0;
        Clock::time_point due{},started{};bool elapsed=false;bool root=false;
        bool legacy_callback=false;
        std::function<bool()> guard;
        int result=LUA_YIELD;
        size_t queued=0;
        std::string owner;
        Clock::duration uninterrupted_cpu{};
        Progress progress;
        bool retained=false;
        bool response_ready=false;
        Clock::duration response_priority_cpu{};
        bool report_errors=true;
        size_t sleeping_frame=0;
    };
    void set_owner(Task& task,const std::string& owner);
    lua_State* main_;
    Clock::time_point deadline_;
    Clock::time_point started_=Clock::now();
    bool persistent_;
    int task_cpu_limit_ms_=0;
    std::unordered_map<lua_State*,Task> tasks_;
    std::deque<Task*> ready_;
    bool prefer_authored_=true;
    bool prefer_response_=true;
    size_t frame_=0;
    bool frame_open_=false;
    std::vector<std::string> errors_;
    int root_status_=0;
    Task& track(lua_State* thread);
    void resume(Task& task,lua_State* from);
    int resume_interrupted(lua_State* thread,lua_State* from,int arguments);
    void collect_finished();
    void enqueue(Task& task);
    Task* dequeue();
    static int task_api(lua_State* L);
    static int identity_api(lua_State* L);
    static int task_api_inner(lua_State* L);
    static int legacy_wait_api(lua_State* L);
    static int legacy_wait_continue(lua_State* L,int status);
    static int elapsed_time_api(lua_State* L);
    static int time_api(lua_State* L);
    static int legacy_schedule_api(lua_State* L);
    void wake_timer(Task& task,Clock::time_point now);
};
