#pragma once
#include "api_trace.hpp"
#include "world_bindings.hpp"
#include "source_scheduler.hpp"
#include "closure_bindings.hpp"
#include <Luau/Compiler.h>
#include <lualib.h>

// Source/catalog loading belongs to the persistent VM, independent of movement.
class ScriptExecution {
    using Json=world_bindings::Json;
    lua_State* environment;
    world_bindings::World& world;
    SourceScheduler& scheduler;
    Json catalog=Json::object(),local_sources=Json::object();
    size_t local_sources_bytes=2;
    Json builtin_scripts=Json::array();
    int interface_ref=LUA_NOREF;
    bool initial_ready=true;

    std::string instance_id(lua_State* L,int index) {
        Json value=world_bindings::capture_value(L,world,index);
        if(!value.is_object()||!value.contains("$ref"))throw std::runtime_error("script Instance required");
        auto id=value.at("$ref").get<std::string>();auto it=world.nodes.find(id);
        if(it==world.nodes.end()||(it->second.class_name!="LocalScript"&&it->second.class_name!="ModuleScript"&&it->second.class_name!="Script"))
            throw std::runtime_error("script Instance required");
        return id;
    }
    static int bridge(lua_State* L) {
        auto& self=*static_cast<ScriptExecution*>(lua_touserdata(L,lua_upvalueindex(1)));
        try{return self.invoke(L,lua_tointeger(L,lua_upvalueindex(2)));}
        catch(const std::exception& error){luaL_error(L,"script runtime: %s",error.what());return 0;}
    }
    int invoke(lua_State* L,int operation) {
        if(operation==0) {
            for(const auto& id:world_bindings::get_script_order(world)) { auto& node=world.nodes.at(id);
                if(node.script_code.is_object()&&node.script_code.value("authored_override",false))continue;
                if(local_sources.contains(id))node.script_code=local_sources[id];
                else if(catalog.contains(id))node.script_code=catalog[id];
                else if(!node.script_origin.empty()&&(!node.script_code.is_object()||(!node.script_code.contains("source")&&!node.script_code.contains("bytecode_hex")))) {
                    auto origin=world.nodes.find(node.script_origin);if(origin!=world.nodes.end()&&origin->second.script_code.is_object())node.script_code=origin->second.script_code;
                }
            }
            if(lua_toboolean(L,1))return 0; // refresh only: the caller discards the rows
            Json rows=world_bindings::script_nodes(world);lua_createtable(L,rows.size(),0);int table=lua_gettop(L),index=0;
            for(const auto& row:rows) {
                lua_createtable(L,0,7);auto id=row.at("id").get<std::string>();
                world_bindings::push_instance(L,world,id);lua_setfield(L,-2,"instance");
                lua_pushlstring(L,id.data(),id.size());lua_setfield(L,-2,"id");
                lua_pushboolean(L,row.at("destroyed").get<bool>());lua_setfield(L,-2,"destroyed");
                for(const char* name:{"Disabled","Enabled"})if(row.contains(name)&&row[name].is_boolean()) {
                    lua_pushboolean(L,row[name].get<bool>());lua_setfield(L,-2,name);
                }
                if(row.contains("RunContext")&&row["RunContext"].is_number()){lua_pushnumber(L,row["RunContext"].get<double>());lua_setfield(L,-2,"RunContext");}
                lua_rawseti(L,table,++index);
            }
            return 1;
        }
        if(operation==1) {
            auto id=instance_id(L,1);luaL_checktype(L,2,LUA_TTABLE);
            auto& node=world.nodes.at(id);
            const Json* item=node.script_code.is_object()&&node.script_code.value("authored_override",false)?&node.script_code:local_sources.contains(id)?&local_sources[id]:catalog.contains(id)?&catalog[id]:node.script_code.is_object()?&node.script_code:nullptr;
            if((!item||(!item->contains("source")&&!item->contains("bytecode_hex")))&&!node.script_origin.empty()) {
                std::string origin=node.script_origin;
                for(int depth=0;depth<64&&!origin.empty();++depth) {
                    auto it=world.nodes.find(origin);if(it==world.nodes.end())break;
                    const Json* inherited=local_sources.contains(origin)?&local_sources[origin]:catalog.contains(origin)?&catalog[origin]:it->second.script_code.is_object()?&it->second.script_code:nullptr;
                    if(inherited&&(inherited->contains("source")||inherited->contains("bytecode_hex"))){item=inherited;break;}
                    origin=it->second.script_origin;
                }
            }
            if(!item||(!item->contains("source")&&!item->contains("bytecode_hex"))) {
                lua_pushnil(L);auto reason=item?item->value("reason","code_unavailable"):"code_unavailable";
                lua_pushstring(L,reason.c_str());lua_pushboolean(L,0);return 3;
            }
            std::string code,source;
            if(item->contains("source")){source=item->at("source").get<std::string>();code=Luau::compile(source);}
            else {
                const auto hex=item->at("bytecode_hex").get<std::string>();code.reserve(hex.size()/2);
                auto nibble=[](char c)->int{if(c>='0'&&c<='9')return c-'0';if(c>='a'&&c<='f')return c-'a'+10;return -1;};
                for(size_t i=0;i<hex.size();i+=2){int a=nibble(hex[i]),b=nibble(hex[i+1]);if(a<0||b<0)throw std::runtime_error("invalid bytecode encoding");code.push_back(char(a*16+b));}
            }
            auto name="="+world_bindings::instance_script_chunkname(world,id);
            if(world.load_script(L,name.c_str(),code,source)!=0){lua_pushnil(L);lua_insert(L,-2);lua_pushboolean(L,1);return 3;}
            lua_pushvalue(L,2);lua_setfenv(L,-2);return 1;
        }
        if(operation==2) {luaL_checktype(L,1,LUA_TFUNCTION);std::string owner=luaL_checkstring(L,2);scheduler.spawn_owned(L,1,owner,false);return 1;}
        if(operation==13) {
            // Outcome of a finished body thread: true plus its return values, false plus its error, or nothing when it did not finish normally.
            luaL_checktype(L,1,LUA_TTHREAD);lua_State* body=lua_tothread(L,1);
            // lua_costatus only calls a thread finished once its stack is empty, but the return values stay on it, so read the raw state.
            const int status=lua_status(body);
            if(status==LUA_YIELD||status==LUA_BREAK)return 0;
            if(status!=LUA_OK){lua_pushboolean(L,0);lua_xpush(body,L,-1);return 2;}
            lua_Debug frame{};if(lua_getinfo(body,0,"s",&frame))return 0; // still has frames: not finished
            const int count=lua_gettop(body);luaL_checkstack(L,count+2,"too many body results");
            lua_pushboolean(L,1);for(int i=1;i<=count;++i)lua_xpush(body,L,i);return count+1;
        }
        if(operation==3) {std::string owner=luaL_checkstring(L,1);world_bindings::stop_script_tasks(L,world,owner);return 0;}
        if(operation==4) {luaL_checktype(L,1,LUA_TTHREAD);lua_pushboolean(L,scheduler.completion(lua_tothread(L,1))!=LUA_YIELD);return 1;}
        if(operation==5) {
            auto id=instance_id(L,1);size_t length=0;const char* text=luaL_checklstring(L,2,&length);
            if(length>128*1024)throw std::runtime_error("script source exceeds 128 KiB");
            Json entry{{"source",std::string(text,length)}};size_t entry_bytes=Json(id).dump().size()+entry.dump().size()+2;size_t old_bytes=local_sources.contains(id)?Json(id).dump().size()+local_sources[id].dump().size()+2:0;
            if(local_sources_bytes-old_bytes+entry_bytes>4*1024*1024)throw std::runtime_error("local source catalog exceeds 4 MiB");
            local_sources_bytes=local_sources_bytes-old_bytes+entry_bytes;local_sources[id]=std::move(entry);world.nodes.at(id).script_code=local_sources[id];return 0;
        }
        if(operation==6){push_method(L,"status");lua_call(L,0,1);return 1;}
        if(operation==7){auto id=instance_id(L,1);lua_pushlstring(L,id.data(),id.size());return 1;}
        if(operation==8){world_bindings::push_player_scripts(L,world);return 1;}
        if(operation==9){auto id=instance_id(L,1);auto& node=world.nodes.at(id);const Json* code=local_sources.contains(id)?&local_sources[id]:catalog.contains(id)?&catalog[id]:node.script_code.is_object()?&node.script_code:nullptr;
            bool ready=code&&(code->contains("source")||code->contains("bytecode_hex")||(code->value("reason","")!="verification_pending"&&code->value("reason","")!="code_unavailable"));lua_pushboolean(L,ready);return 1;}
        if(operation==10){lua_pushboolean(L,initial_ready);return 1;}
        if(operation==11){return world_bindings::clone_client_template(L);}
        if(operation==12) {
            lua_createtable(L,builtin_scripts.size(),0);int list=lua_gettop(L),index=0;
            for(const auto& entry:builtin_scripts) {
                lua_createtable(L,0,3);
                lua_createtable(L,entry.at("path").size(),0);int path=lua_gettop(L),part=0;
                for(const auto& segment:entry.at("path")){const auto& name=segment.get_ref<const std::string&>();lua_pushlstring(L,name.data(),name.size());lua_rawseti(L,path,++part);}
                lua_setfield(L,-2,"path");lua_pushstring(L,entry.at("class_name").get_ref<const std::string&>().c_str());lua_setfield(L,-2,"class_name");
                if(entry.contains("source")){const auto& source=entry.at("source").get_ref<const std::string&>();lua_pushlstring(L,source.data(),source.size());lua_setfield(L,-2,"source");}
                lua_rawseti(L,list,++index);
            }
            return 1;
        }
        throw std::runtime_error("unknown script runtime operation");
    }
    void push_bridge(lua_State* L,int operation) {
        lua_pushlightuserdata(L,this);lua_pushinteger(L,operation);lua_pushcclosurek(L,bridge,"script runtime",2,nullptr);
    }
    void push_method(lua_State* L,const char* name){lua_getref(L,interface_ref);lua_getfield(L,-1,name);lua_remove(L,-2);}
public:
    ScriptExecution(lua_State* L,world_bindings::World& w,SourceScheduler& tasks,const Json& snapshot)
        :environment(L),world(w),scheduler(tasks) {
        initial_ready=snapshot.value("initial_replication_complete",true);
        builtin_scripts=snapshot.value("builtin_player_scripts",Json::array());
        if(!builtin_scripts.is_array()||builtin_scripts.size()>256||builtin_scripts.dump().size()>1024*1024)throw std::runtime_error("invalid builtin player script bundle");
        for(const auto& entry:builtin_scripts) {
            if(!entry.is_object()||!entry.contains("path")||!entry["path"].is_array()||entry["path"].empty()||entry["path"].size()>16)throw std::runtime_error("invalid builtin script path");
            for(const auto& part:entry["path"])if(!part.is_string()||part.get_ref<const std::string&>().empty()||part.get_ref<const std::string&>().size()>128)throw std::runtime_error("invalid builtin script name");
            const auto cls=entry.value("class_name","");
            if(cls!="LocalScript"&&cls!="ModuleScript"&&cls!="Folder")throw std::runtime_error("invalid builtin script class");
            if(cls!="Folder"&&(!entry.contains("source")||!entry["source"].is_string()||entry["source"].get_ref<const std::string&>().size()>128*1024))throw std::runtime_error("invalid builtin script source");
        }
        update(snapshot.value("script_sources",Json::object()));
        static constexpr const char* bootstrap=R"SCRIPTS(
local scan, compile, spawn, stop, ended, identify, playerScripts, codeReady, initialReady, cloneTemplate, builtinScripts, registerSource, threadResult = ...
local executor = getfenv()
-- Copy the engine root once and make it the actual fallback for authored and
-- game scopes. Removing a global must not reveal it again through a fallback.
-- The fallback is the stock Roblox environment: executor functions (getgc, hookfunction, request, the executor
-- debug members, ...) belong to the authored scope only. A game's own scripts never see them in Roblox, and
-- protected scripts fingerprint exactly that (library key sets, global names).
local pristine = {}
for key,value in getmetatable(executor).__index do pristine[key]=value end
for key,value in executor do if pristine[key]==nil then pristine[key]=value end end
local stock = {}
for name in string.gmatch("assert collectgarbage error gcinfo getfenv getmetatable ipairs loadstring newproxy next pairs pcall print "
    .. "printidentity rawequal rawget rawlen rawset require select setfenv setmetatable settings stats tonumber tostring type typeof "
    .. "unpack version xpcall bit32 buffer coroutine debug math os string table task utf8 vector delay elapsedTime game shared "
    .. "spawn tick time wait warn workspace script plugin ypcall _G _VERSION", "%S+") do stock[name] = true end
local notStock = {Drawing=true, WebSocket=true}
local base = {}
for key,value in pristine do
    if type(key)=="string" and (stock[key] or (string.match(key, "^%u") and not notStock[key])) then base[key]=value end
end
if type(pristine.debug)=="table" then
    -- The engine's debug library as a client script sees it: these twelve members and no executor additions.
    local stockDebug = {}
    for _, name in {"info","traceback","profilebegin","profileend","setmemorycategory","resetmemorycategory","getmemorycategory","dumpcodesize","dumpheap","dumprefs","tracerefs","loadmodule"} do
        stockDebug[name] = pristine.debug[name]
    end
    base.debug = table.freeze(stockDebug)
end
-- loadstring exists but is disabled in game scripts.
base.loadstring = newcclosure(function() error("loadstring() is not available", 2) end, "loadstring")
base._G={};base.shared=shared
-- The executor scope keeps everything the engine root provides, as a copy that later removals cannot reveal.
local full = {}
for key,value in pristine do full[key]=value end
full._G=base._G;full.shared=shared
setmetatable(executor,{__index=full})
getrenv = newcclosure(function() return base end, "getrenv")
local modules, scripts = {}, {}
local copied = setmetatable({}, {__mode="k"})
local bootstrapErrors = {}
local builtinsInstalled = false
local function installBuiltins(target)
    if builtinsInstalled or not target then return end
    local paths, overridden = {}, {}
    for _, row in builtinScripts() do
        local path = row.path
        local root = path[1]
        if #path == 1 and target:FindFirstChild(root) then overridden[root] = true end
        if not overridden[root] then
            local parent = #path == 1 and target or paths[table.concat(path, "/", 1, #path-1)]
            assert(parent, "Builtin player script parent is missing")
            local instance = Instance.new(row.class_name)
            instance.Name = path[#path]
            if row.source then registerSource(instance, row.source) end
            instance.Parent = parent
            paths[table.concat(path, "/")] = instance
        end
    end
    builtinsInstalled = true
end
local function cloneableTree(root)
    if (root:IsA("LuaSourceContainer")) and not codeReady(root) then return false end
    for _, child in root:GetDescendants() do
        if child:IsA("LuaSourceContainer") and not codeReady(child) then return false end
    end
    return true
end
local function mirror(source, target)
    if not source or not target then return end
    local seen = copied[target]
    if not seen then seen = {}; copied[target] = seen end
    for _, child in source:GetChildren() do
        if not seen[child] then
            if target:FindFirstChild(child.Name) then seen[child] = true
            elseif cloneableTree(child) then
                local ok, clone = pcall(cloneTemplate, child)
                if ok then
                    seen[child] = true
                    if clone then clone.Parent = target end
                elseif not bootstrapErrors[child] then
                    bootstrapErrors[child] = tostring(clone)
                    warn("Client template: " .. tostring(clone))
                end
            end
        end
    end
end
local function prepareTemplates()
    if not initialReady() then return end
    local players = game:FindService("Players")
    local player = players and players.LocalPlayer
    if not player then return end
    local starter = game:FindService("StarterPlayer")
    local scripts = playerScripts()
    mirror(starter and starter:FindFirstChild("StarterPlayerScripts"), scripts)
    installBuiltins(scripts)
    local ok, character = pcall(function()return player.Character end)
    if ok and character and character:IsDescendantOf(game) then
        mirror(starter and starter:FindFirstChild("StarterCharacterScripts"), character)
    end
    mirror(game:FindService("StarterGui"), player:FindFirstChildOfClass("PlayerGui"))
    mirror(game:FindService("StarterPack"), player:FindFirstChildOfClass("Backpack"))
end
local function environmentFor(instance)
    -- A game script's own environment holds exactly _G, script and shared; its metatable is locked.
    return setmetatable({script=instance, _G=base._G, shared=shared}, {__index=base, __metatable="The metatable is locked"})
end
-- A module or script body runs directly as its thread's function, as in Roblox. A protected-call wrapper would cost one
-- C-call level that protected scripts can measure (they nest coroutines until "C stack overflow" and use the depth), so
-- the outcome is read off the finished thread instead.
local function finishBroken(entry)
    if entry.state == "loading" and entry.thread and ended(entry.thread) then
        local result = table.pack(threadResult(entry.thread))
        if result[1] == true then
            if result.n ~= 2 then entry.state, entry.error = "failed", "Module code must return exactly one value"
            else entry.state, entry.value = "loaded", result[2] end
        elseif result[1] == false then
            entry.state, entry.error = "failed", tostring(result[2])
        else
            entry.state, entry.error, entry.thread = "failed", "Module task terminated before returning", nil
        end
    end
end
-- require("./sibling"), require("../uncle") and require("@self/child"): paths resolve against the calling script.
local function resolvePath(path)
    local caller
    for level = 2, 6 do
        local f = debug.info(level, "f")
        if not f then break end
        local ok, env = pcall(getfenv, f)
        local s = ok and type(env) == "table" and rawget(env, "script")
        if typeof(s) == "Instance" then caller = s break end
    end
    local node, first = nil, true
    for part in string.gmatch(path, "[^/]+") do
        if first then
            first = false
            if not caller then return nil end
            if part == "." then node = caller.Parent elseif part == ".." then node = caller.Parent and caller.Parent.Parent
            elseif part == "@self" then node = caller else return nil end
        elseif part == ".." then node = node and node.Parent
        elseif part ~= "." then node = node and node:FindFirstChild(part) end
    end
    return node
end
function require(module)
    if type(module) == "string" then module = resolvePath(module) end
    if typeof(module) ~= "Instance" or not module:IsA("ModuleScript") then
        error("Attempted to call require with invalid argument(s).", 2)
    end
    local moduleId = identify(module)
    local entry = modules[moduleId]
    if not entry then
        local scope = environmentFor(module)
        local fn, message, hasCode = compile(module, scope)
        while not fn and message == "verification_pending" do
            task.wait(0.005)
            if modules[moduleId] then return require(module) end
            fn, message, hasCode = compile(module, scope)
        end
        if not fn then
            if hasCode then modules[moduleId] = {state="failed", error=tostring(message), id=moduleId, instance=module} end
            error("Module code unavailable: " .. tostring(message), 2)
        end
        entry = {state="loading", id=moduleId,instance=module,scope=scope}
        modules[moduleId] = entry
        entry.thread = spawn(fn, "module:" .. entry.id)
    end
    while entry.state == "loading" do
        finishBroken(entry)
        if entry.state == "loading" then task.wait(0.001) end
    end
    if entry.state == "failed" then error(entry.error, 2) end
    return entry.value
end
-- require is a native function in Roblox (debug.info reports "[C]"); wrap the script-runtime version so it looks like one.
local nativeRequire = newcclosure(require, "require")
base.require=nativeRequire;full.require=nativeRequire
executor.require=nil
function getscriptclosure(instance)
    local fn,message=compile(instance,environmentFor(instance));assert(fn,message);return fn
end
getscriptfunction=getscriptclosure
function getloadedmodules()
    local result={};for _,entry in modules do finishBroken(entry);if entry.state=="loaded" then table.insert(result,entry.instance) end end;return result
end
function getrunningscripts()
    local result={};for instance,entry in scripts do if entry.active and entry.thread and entry.state~="failed" then table.insert(result,instance) end end
    for _,entry in modules do if entry.state=="loading" or entry.state=="loaded" then table.insert(result,entry.instance) end end
    return result
end
function getsenv(instance)
    local id=identify(instance)
    local entry=modules[id]
    if not entry then for _,candidate in scripts do if candidate.id==id then entry=candidate;break end end end
    assert(entry and entry.scope,"script has no instantiated environment");return entry.scope
end
local function read(instance, key)
    local ok, value = pcall(function() return instance[key] end)
    if ok then return value end
end
local function eligible(row, player, character)
    local instance = row.instance
    if row.destroyed or not instance:IsDescendantOf(game) then return false end
    if row.Disabled == true or row.Enabled == false then return false end
    if instance.ClassName == "Script" then return row.RunContext == 2 end
    if instance.ClassName ~= "LocalScript" then return false end
    local parent = instance.Parent
    while parent and parent ~= game do
        if parent.ClassName == "ReplicatedFirst" or parent == character then return true end
        if player and parent.Parent == player and (parent.ClassName == "PlayerScripts" or parent.ClassName == "PlayerGui" or parent.ClassName == "Backpack") then return true end
        parent = parent.Parent
    end
    return false
end
local function status()
    local result = {local_scripts=0, running=0, completed=0, failed=0, blocked=0, stopped=0,
                    modules_loaded=0, modules_loading=0, modules_failed=0, details={}}
    result.bootstrap_errors = 0
    for _ in bootstrapErrors do result.bootstrap_errors += 1 end
    for instance, entry in scripts do
        result.local_scripts += 1
        if result[entry.state] ~= nil then result[entry.state] += 1 end
        if #result.details < 128 then
            table.insert(result.details, {id=entry.id, name=instance.Name, state=entry.state, error=entry.error})
        end
    end
    for _, entry in modules do
        finishBroken(entry)
        local key = "modules_" .. entry.state
        result[key] = (result[key] or 0) + 1
    end
    return result
end
local function reconcile()
    scan(true) -- Refresh code retained by cloned script instances (rows are not needed).
    prepareTemplates()
    -- Script starts are queued, so this context stays stable during the scan.
    -- Resolve it once: a missing Character can otherwise scan the whole world
    -- for every LocalScript while initial replication is still in progress.
    local players = game:FindService("Players")
    local player = players and players.LocalPlayer
    local character = player and read(player, "Character")
    local present, starts = {}, 0
    for _, row in scan() do
        local instance = row.instance
        if instance.ClassName ~= "ModuleScript" then
            present[instance] = true
            local entry = scripts[instance]
            local shouldRun = eligible(row, player, character)
            if entry and entry.active and not shouldRun then
                stop("script:" .. entry.id)
                entry.active, entry.state, entry.thread = false, "stopped", nil
            end
            if shouldRun and (not entry or not entry.active) and starts < 8 then
                entry = entry or {id=row.id}
                scripts[instance] = entry
                local scope=environmentFor(instance)
                local fn, message, hasCode = compile(instance, scope)
                if not fn then
                    entry.state, entry.error = hasCode and "failed" or "blocked", tostring(message)
                    if hasCode then entry.active = true; warn(instance.Name .. ": " .. tostring(message)); starts += 1 end
                else
                    entry.scope=scope
                    entry.active, entry.state, entry.error = true, "running", nil
                    starts += 1
                    entry.thread = spawn(fn, "script:" .. entry.id)
                end
            elseif entry and entry.state == "running" and entry.thread and ended(entry.thread) then
                local result = table.pack(threadResult(entry.thread))
                if result[1] == true then
                    entry.state, entry.error = "completed", nil
                elseif result[1] == false then
                    entry.state, entry.error = "failed", tostring(result[2])
                    warn(instance.Name .. ": " .. tostring(result[2]))
                else
                    entry.state, entry.error = "failed", "Script task terminated before completing"
                    warn(instance.Name .. ": " .. entry.error) -- a task stopped by the CPU cap would otherwise vanish silently
                end
            end
        end
    end
    for instance, entry in scripts do
        if not present[instance] and entry.active then
            stop("script:" .. entry.id)
            entry.active, entry.state, entry.thread = false, "stopped", nil
        end
    end
    local result = status()
    -- Starts are capped per pass: the host must call again while eligible scripts are still waiting to start.
    result.more_pending = starts >= 8
    return result
end
return {reconcile=reconcile, status=status}
)SCRIPTS";
        std::string code=Luau::compile(bootstrap);
        if(world.load_script(L,"=script-runtime",code,bootstrap)!=0)throw std::runtime_error("cannot load script runtime");
        for(int operation:{0,1,2,3,4,7,8,9,10,11,12,5,13})push_bridge(L,operation);
        if(lua_pcall(L,13,1,0)!=0)throw std::runtime_error(lua_tostring(L,-1));
        interface_ref=lua_ref(L,-1);lua_pop(L,1);
        for(const char* name:{"getrenv","getscriptclosure","getscriptfunction","getloadedmodules","getrunningscripts","getsenv"}) {
            lua_getglobal(L,name);mark_executor_closure(L,-1);lua_pop(L,1);
        }
        lua_getglobal(L,"client");lua_setreadonly(L,-1,false);
        push_bridge(L,5);lua_setfield(L,-2,"registerScriptSource");
        push_bridge(L,6);lua_setfield(L,-2,"scriptStatus");lua_setreadonly(L,-1,true);lua_pop(L,1);
    }
    void update(const Json& incoming) {
        if(!incoming.is_object()||incoming.size()>4096||incoming.dump().size()>4*1024*1024)throw std::runtime_error("invalid script source catalog");
        for(auto it=incoming.begin();it!=incoming.end();++it) {
            const auto& entry=it.value();if(!entry.is_object())throw std::runtime_error("invalid script code entry");
            if(entry.contains("source")&&(!entry["source"].is_string()||entry["source"].get_ref<const std::string&>().size()>128*1024))throw std::runtime_error("invalid script source");
            if(entry.contains("bytecode_hex")) {
                if(!entry["bytecode_hex"].is_string())throw std::runtime_error("invalid script bytecode");
                const auto& hex=entry["bytecode_hex"].get_ref<const std::string&>();
                bool short_session_code=!entry.value("signature_verified",false)
                    &&entry.value("provenance","")=="session_small_bytecode"
                    &&entry.value("admission","")=="pinned_session_rsb_luau13_14_no_trailer_under_256"
                    &&hex.size()>=4&&hex.size()<512
                    &&(hex.compare(0,4,"0d03")==0||hex.compare(0,4,"0e03")==0);
                if((!entry.value("signature_verified",false)&&!short_session_code)
                   ||hex.size()>2*1024*1024||hex.size()%2)
                    throw std::runtime_error("unverified or oversized script bytecode");
            }
        }
        catalog=incoming;
        for(auto it=catalog.begin();it!=catalog.end();++it) {
            auto node=world.nodes.find(it.key());if(node!=world.nodes.end()&&!local_sources.contains(it.key()))node->second.script_code=it.value();
        }
    }
    void set_initial_ready(bool value){initial_ready=value;}
    Json reconcile() {
        const auto traced_start=std::chrono::steady_clock::now();
        struct ReconcileTimer{lua_State* L;std::chrono::steady_clock::time_point start;~ReconcileTimer(){
            if(api_trace_enabled())api_trace(L,"reconcile_ms",std::to_string(std::chrono::duration<double,std::milli>(std::chrono::steady_clock::now()-start).count()));}} reconcile_timer{environment,traced_start};
        push_method(environment,"reconcile");
        if(lua_pcall(environment,0,1,0)!=0){std::string error=lua_tostring(environment,-1);lua_pop(environment,1);throw std::runtime_error(error);}
        Json result=world_bindings::capture_value(environment,world,-1);lua_pop(environment,1);return result;
    }
};
