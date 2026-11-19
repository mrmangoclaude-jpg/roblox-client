"""Real local compatibility semantics, beyond the UNC smoke assertions."""
import os
from pathlib import Path
import unittest
from unittest import mock
import test_cframe_transforms as transforms


class LocalCompatibilityTests(unittest.TestCase):
    def run_script(self,source,snapshot=None):
        # Source extensions are installed by the Rust supervisor. The plain
        # C++ host intentionally retains its smaller bytecode/engine surface.
        path=Path(os.environ.get('CFRAME_PERSISTENT_HOST',str(transforms.DEFAULT_HOSTS[1])))
        with mock.patch.object(transforms,'HOSTS',[path]):
            return transforms.CFrameTransformTests.run_script(self,source,snapshot)

    def test_string_metatable_is_locked_but_raw_access_exposes_it(self):
        self.run_script('''
assert(getmetatable("")=="The metatable is locked")
assert(getmetatable("abc")=="The metatable is locked")
local raw=getrawmetatable("")
assert(type(raw)=="table" and raw.__index==string)
assert(getmetatable(1)==nil and getmetatable(true)==nil)
assert(getmetatable(print)==nil and getmetatable({})==nil)
''')

    def test_file_binary_roundtrip_listing_and_recursive_deletion(self):
        self.run_script('''
makefolder("a/b");writefile("a/b/data",string.char(0,255).."hi")
appendfile("a/b/data","!");assert(readfile("a\\\\b/./data")==string.char(0,255).."hi!")
assert(isfolder("a") and not isfile("a"))
assert(#listfiles("a")==1 and listfiles("a")[1]=="a/b")
assert(listfiles("a/b")[1]=="a/b/data")
makefolder("ab");writefile("ab/keep","yes");delfolder("a")
assert(not isfolder("a/b") and not isfile("a/b/data"))
assert(readfile("ab/keep")=="yes");delfile("ab/keep");assert(not isfile("ab/keep"))
''')

    def test_paths_limits_and_failed_writes_preserve_contents(self):
        self.run_script('''
setworkspacequota(128*1024,1024*1024)
for _,p in {"../bad","a/../../bad","/tmp/bad","C:\\bad","a"..string.char(0).."b"} do
    assert(not pcall(writefile,p,"no"))
end
assert(not pcall(delfolder,"."))
writefile("file","original")
assert(not pcall(makefolder,"file/child"))
assert(not pcall(writefile,"file/child","bad"))
assert(not pcall(writefile,"file",string.rep("x",128*1024+1)))
assert(readfile("file")=="original")
for i=1,7 do writefile("full"..i,string.rep("x",128*1024)) end
assert(not pcall(writefile,"overflow",string.rep("x",128*1024)))
delfile("full1");writefile("replacement",string.rep("y",128*1024))
assert(#readfile("replacement")==128*1024)
''')

    def test_loadfile_compile_errors_arguments_and_environment(self):
        self.run_script('''
writefile("script.luau","return ..., getgenv().fileTest")
getgenv().fileTest=42
local a,b=assert(loadfile("script.luau"))(17);assert(a==17 and b==42)
local a,b=dofile("script.luau",9);assert(a==9 and b==42)
writefile("script.luau","local =")
local fn,err=loadfile("script.luau");assert(fn==nil and type(err)=="string")
assert(not pcall(dofile,"script.luau"))
''')

    def test_writes_create_missing_parents_without_partial_failed_directories(self):
        self.run_script('''
setworkspacequota(128*1024,1024*1024)
writefile("created/deep/file",string.char(0,255))
assert(isfolder("created") and isfolder("created/deep"))
assert(readfile("created/deep/file")==string.char(0,255))
appendfile("appended/nested/file","a");appendfile("appended/nested/file","b")
assert(readfile("appended/nested/file")=="ab")
assert(not pcall(writefile,"oversized/nested/file",string.rep("x",128*1024+1)))
assert(not isfolder("oversized"))
writefile("blocked","original")
assert(not pcall(writefile,"blocked/nested/file","bad"))
assert(readfile("blocked")=="original" and not isfolder("blocked/nested"))
assert(not pcall(writefile,"invalid/nested/file",{}))
assert(not isfolder("invalid"))
''')

    def test_recursive_write_entry_quota_checks_the_file_and_parents_together(self):
        self.run_script('''
for i=1,510 do writefile("entry"..i,"")end
assert(not pcall(writefile,"missing/deep/file","no"))
assert(not isfolder("missing") and not isfile("missing/deep/file"))
writefile("last/file","ok")
assert(readfile("last/file")=="ok" and #listfiles("")==511)
assert(not pcall(writefile,"overflow/file","no"))
assert(not isfolder("overflow"))
''')

    def test_parent_components_normalize_only_within_the_virtual_workspace(self):
        self.run_script('''
writefile("group/unused/../file","first")
assert(readfile("group/file")=="first" and not isfolder("group/unused"))
appendfile("group/./nested/../file"," second")
assert(readfile("group/file")=="first second")
assert(isfile("group/../group/file"))
assert(listfiles("group/nested/..")[1]=="group/file")
assert(getcustomasset("group/../group/file")==getcustomasset("group/file"))
for _,p in {"../escape","group/../../escape","group/../.."}do
 assert(not pcall(writefile,p,"bad"))
 assert(not pcall(readfile,p))
end
assert(not pcall(delfolder,"group/.."))
assert(readfile("group/file")=="first second")
delfile("group/nested/../file");assert(not isfile("group/file"))
''')

    def test_debug_reports_real_functions_and_upvalues(self):
        self.run_script('''
local value=math.random();local function f(a,...) return value,a,... end
local info=debug.getinfo(f)
assert(info.func==f and info.numparams==1 and info.is_vararg==1 and info.nups==1)
assert(type(info.source)=="string" and info.what=="Lua")
assert(debug.getupvalue(f,1)==value and debug.getupvalues(f)[1]==value)
debug.setupvalue(f,1,"changed");assert(f()=="changed")
assert(not pcall(debug.getupvalue,f,2))
assert(not pcall(debug.setupvalue,f,99,true))
assert(not pcall(debug.getupvalue,f,0))
assert(debug.getinfo(print).what=="C")
assert(debug.getinfo(99999)==nil)
assert(not pcall(debug.getinfo,-1))
assert(not pcall(debug.setupvalue,loadstring,1,false))
assert(assert(loadstring("return 7"))()==7)
''')

    def test_locked_metatables_and_table_readonly_state(self):
        self.run_script('''
local mt={__metatable="locked",__index=function()return 1 end}
local t=setmetatable({},mt);assert(getrawmetatable(t)==mt)
assert(setrawmetatable(t,{__index=function()return 2 end})==t and t.foo==2)
setrawmetatable(t,nil);assert(getrawmetatable(t)==nil and t.foo==nil)
table.freeze(t);assert(isreadonly(t));assert(not pcall(function()t.foo=3 end))
setreadonly(t,false);t.foo=3;assert(t.foo==3 and not isreadonly(t))
setreadonly(t,true);assert(not pcall(function()t.foo=4 end))
local proxy=newproxy();local proxyMeta={__index={value=7}}
assert(setrawmetatable(proxy,proxyMeta)==proxy and proxy.value==7)
assert(identifyexecutor()=="Roblox Client Research" and getexecutorname==identifyexecutor)
''')

    def test_workspace_persists_within_vm_and_isolated_between_vms(self):
        import persistent_runtime
        path=Path(os.environ.get('CFRAME_PERSISTENT_HOST',str(transforms.DEFAULT_HOSTS[1])))
        with mock.patch.object(persistent_runtime,'RUST_HOST',path):
            first=persistent_runtime.PersistentLuauHost(transforms.SNAPSHOT)
            second=persistent_runtime.PersistentLuauHost(transforms.SNAPSHOT)
        self.addCleanup(first.close);self.addCleanup(second.close)
        for host,source in [(first,'writefile("persist","hello")'),
                            (first,'assert(readfile("persist")=="hello")'),
                            (second,'assert(not isfile("persist"))')]:
            result=host.call({'op':'execute','source':source});self.assertTrue(result['ok'],result)


if __name__=='__main__':unittest.main()
