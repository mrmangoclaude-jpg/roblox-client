R"LOCALWORKSPACE(
local files, folders = {}, {[""]=true}
local bytes, entries = 0, 0
local FILE_LIMIT, TOTAL_LIMIT, ENTRY_LIMIT = 100*1024*1024, 256*1024*1024, 512
local MIN_FILE_LIMIT, MIN_TOTAL_LIMIT = 128*1024, 1024*1024
local MAX_FILE_LIMIT, MAX_TOTAL_LIMIT = 100*1024*1024, 256*1024*1024
local blockedExtensions={}
for extension in ("exe com scr pif cpl msc bat cmd ps1 psd1 vbs vbe js jse wsf wsh hta scf lnk zip rar 7z cab iso img xml msi msp reg inf url"):gmatch("%S+") do
    blockedExtensions[extension]=true
end
local function path(value)
    assert(type(value)=="string", "path must be a string")
    assert(#value<=1024 and not value:find("%z"), "invalid path")
    value=value:gsub("\\", "/")
    assert(value:sub(1,1)~="/" and not value:find(":"), "path must be relative to the VM workspace")
    local parts={}
    for part in value:gmatch("[^/]+") do
        if part==".." then
            assert(#parts>0,"path escapes the VM workspace")
            table.remove(parts)
        elseif part~="." then table.insert(parts,part) end
    end
    return table.concat(parts,"/")
end
local function parent(p) return p:match("^(.*)/[^/]+$") or "" end
local function reserve(p)
    if files[p]==nil and not folders[p] then
        assert(entries<ENTRY_LIMIT,"workspace entry limit exceeded")
        entries+=1
    end
end
function isfile(p) return files[path(p)]~=nil end
function isfolder(p) return folders[path(p)]==true end
local function missingFolders(p)
    local components={}
    for part in p:gmatch("[^/]+") do
        table.insert(components,part)
        assert(files[table.concat(components,"/")]==nil,"path is a file")
    end
    local pending={}
    for i=1,#components do
        local sub=table.concat(components,"/",1,i)
        if not folders[sub] then table.insert(pending,sub) end
    end
    return pending
end
function makefolder(p)
    p=path(p)
    local pending=missingFolders(p)
    assert(entries+#pending<=ENTRY_LIMIT,"workspace entry limit exceeded")
    for _,sub in pending do folders[sub]=true;entries+=1 end
end
function readfile(p)
    local value=files[path(p)];assert(value~=nil,"file does not exist");return value
end
function readfilechunk(p, offset, length)
    p=path(p)
    local value=files[p];assert(value~=nil,"file does not exist")
    assert(type(offset)=="number" and offset==offset and offset%1==0 and offset>=0,"offset must be a non-negative integer")
    assert(type(length)=="number" and length==length and length%1==0 and length>=0 and length<=64*1024,"length must be an integer from 0 to 65536")
    assert(offset<=#value,"offset is past end of file")
    if length==0 then return "" end
    return value:sub(offset+1, offset+length)
end
function getfileinfo(p)
    local value=files[path(p)];assert(value~=nil,"file does not exist")
    return #value
end
function setworkspacequota(fileBytes, totalBytes)
    assert(type(fileBytes)=="number" and fileBytes==fileBytes and fileBytes%1==0
        and fileBytes>=MIN_FILE_LIMIT and fileBytes<=MAX_FILE_LIMIT,
        "per-file quota must be an integer from 131072 to 104857600")
    assert(type(totalBytes)=="number" and totalBytes==totalBytes and totalBytes%1==0
        and totalBytes>=MIN_TOTAL_LIMIT and totalBytes<=MAX_TOTAL_LIMIT,
        "total quota must be an integer from 1048576 to 268435456")
    local largest=0
    for _,value in files do largest=math.max(largest,#value) end
    assert(fileBytes>=largest,"per-file quota is below current workspace usage")
    assert(totalBytes>=bytes,"total quota is below current workspace usage")
    FILE_LIMIT,TOTAL_LIMIT=fileBytes,totalBytes
    return FILE_LIMIT,TOTAL_LIMIT
end
function writefile(p,data)
    p=path(p);assert(type(data)=="string","file contents must be a string")
    local extension=p:match("%.([^./]+)$")
    assert(not extension or not blockedExtensions[extension:lower()],"file extension is not allowed")
    assert(not folders[p],"path is a folder")
    assert(#data<=FILE_LIMIT,"file exceeds configured byte quota")
    local size=bytes-#(files[p] or "")+#data
    assert(size<=TOTAL_LIMIT,"workspace exceeds configured byte quota")
    -- Match the provided executor's recursive parent creation. Validate all
    -- quotas and conflicting file paths before changing directory state.
    local pending=missingFolders(parent(p))
    assert(entries+#pending+(files[p]==nil and 1 or 0)<=ENTRY_LIMIT,"workspace entry limit exceeded")
    for _,sub in pending do folders[sub]=true;entries+=1 end
    reserve(p);files[p]=data;bytes=size
end
function appendfile(p,data)
    p=path(p);assert(type(data)=="string","file contents must be a string")
    writefile(p,(files[p] or "")..data)
end
function listfiles(p)
    p=path(p);assert(folders[p],"folder does not exist")
    local results={}
    for name in files do if parent(name)==p then table.insert(results,name) end end
    for name in folders do if name~="" and parent(name)==p then table.insert(results,name) end end
    table.sort(results);return results
end
function delfile(p)
    p=path(p);assert(files[p]~=nil,"file does not exist")
    bytes-=#files[p];files[p]=nil;entries-=1
end
function delfolder(p)
    p=path(p);assert(p~="","cannot delete workspace root");assert(folders[p],"folder does not exist")
    local prefix=p.."/"
    for name,value in files do
        if name:sub(1,#prefix)==prefix then bytes-=#value;files[name]=nil;entries-=1 end
    end
    for name in folders do
        if name==p or name:sub(1,#prefix)==prefix then folders[name]=nil;entries-=1 end
    end
end
local compile=loadstring
function loadfile(p) return compile(readfile(p),"@"..path(p)) end
function dofile(p,...) local fn,err=loadfile(p);assert(fn,err);return fn(...) end
runfile=dofile
local assets={}
function getcustomasset(p)
    p=path(p);assert(files[p]~=nil,"asset file does not exist")
    local uri="rbxasset://workspace/"..p:gsub("[^%w%-%._~/]",function(c)return string.format("%%%02X",string.byte(c))end)
    assets[uri]=p;return uri
end
function getcustomassetdata(uri)
    assert(type(uri)=="string" and assets[uri],"unknown workspace asset")
    return readfile(assets[uri])
end
-- Executor identity must read as a native C closure: Luraph env probes hash iscclosure(identifyexecutor).
identifyexecutor = newcclosure(function() return "Roblox Client Research", "local-vm-1" end, "identifyexecutor")
getexecutorname=identifyexecutor
local identities=setmetatable({}, {__mode="k"})
function getthreadidentity() return identities[coroutine.running()] or 2 end
function setthreadidentity(value)
    assert(type(value)=="number" and value%1==0 and value>=0 and value<=8,"identity must be an integer from 0 to 8")
    identities[coroutine.running()]=value
end
getidentity=getthreadidentity;getthreadcontext=getthreadidentity
setidentity=setthreadidentity;setthreadcontext=setthreadidentity
function hookmetamethod(object,name,callback)
    assert(type(name)=="string" and type(callback)=="function","metamethod name and function required")
    local mt=getrawmetatable(object);assert(type(mt)=="table","object has no metatable")
    local previous=rawget(mt,name);assert(type(previous)=="function","existing function metamethod required")
    local readonly=isreadonly(mt);setreadonly(mt,false)
    local ok,err=pcall(rawset,mt,name,callback);setreadonly(mt,readonly)
    assert(ok,err);return previous
end
-- Native executor helpers read as C closures; env probes hash iscclosure/setfenv on them.
getcustomasset = newcclosure(getcustomasset, "getcustomasset")
getsynasset = newcclosure(function(p) return getcustomasset(p) end, "getsynasset")
hookmetamethod = newcclosure(hookmetamethod, "hookmetamethod")
-- Workspace file helpers are native executor closures too; the env probe's setfenv
-- sweep hashes iscclosure/setfenv across every global, so Lua here diverges the key.
isfile = newcclosure(isfile, "isfile")
isfolder = newcclosure(isfolder, "isfolder")
makefolder = newcclosure(makefolder, "makefolder")
readfile = newcclosure(readfile, "readfile")
readfilechunk = newcclosure(readfilechunk, "readfilechunk")
getfileinfo = newcclosure(getfileinfo, "getfileinfo")
setworkspacequota = newcclosure(setworkspacequota, "setworkspacequota")
writefile = newcclosure(writefile, "writefile")
appendfile = newcclosure(appendfile, "appendfile")
listfiles = newcclosure(listfiles, "listfiles")
delfile = newcclosure(delfile, "delfile")
delfolder = newcclosure(delfolder, "delfolder")
loadfile = newcclosure(loadfile, "loadfile")
dofile = newcclosure(dofile, "dofile")
runfile = dofile
getcustomassetdata = newcclosure(getcustomassetdata, "getcustomassetdata")
)LOCALWORKSPACE"
