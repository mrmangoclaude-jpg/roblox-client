"""Behavioral checks for compatibility APIs, independent of UNC's score."""
import hashlib
import json
import unittest
import test_local_compat as compat


class ExtendedCompatibilityTests(unittest.TestCase):
    run_script=compat.LocalCompatibilityTests.run_script

    def test_hashes_match_independent_binary_vectors(self):
        algorithms={'sha1':'sha1','sha384':'sha384','sha512':'sha512','md5':'md5','sha256':'sha256',
                    'sha3-224':'sha3_224','sha3-256':'sha3_256','sha3-512':'sha3_512'}
        source='local input=string.char(0,255).."hello"\n'
        for name,algorithm in algorithms.items():
            expected=hashlib.new(algorithm,b'\x00\xffhello').hexdigest()
            source+=f'assert(crypt.hash(input,{json.dumps(name)})=={json.dumps(expected)})\n'
        source+='assert(not pcall(crypt.hash,input,"fake-hash"))'
        self.run_script(source)

    def test_aes_nist_block_and_binary_roundtrip(self):
        self.run_script('''
local function bytes(hex) return (hex:gsub("..",function(p)return string.char(tonumber(p,16))end)) end
local key=crypt.base64encode(bytes("2b7e151628aed2a6abf7158809cf4f3c"))
local iv=crypt.base64encode(bytes("000102030405060708090a0b0c0d0e0f"))
local plain=bytes("6bc1bee22e409f96e93d7e117393172a")
local encrypted,actual=crypt.encrypt(plain,key,iv,"CBC")
assert(crypt.base64decode(encrypted):sub(1,16)==bytes("7649abac8119b246cee98e9b12e9197d"))
assert(actual==iv and crypt.decrypt(encrypted,key,iv,"CBC")==plain)
local data=string.char(0,255)..string.rep("x",80)
key=crypt.generatekey();local a,iv1=crypt.encrypt(data,key,nil,"CBC")
local b,iv2=crypt.encrypt(data,key,nil,"CBC")
assert(a~=b and iv1~=iv2 and #crypt.base64decode(key)==32)
assert(crypt.decrypt(a,key,iv1,"CBC")==data)
assert(#crypt.base64decode(crypt.generatebytes(51))==51)
assert(crypt.generatebytes(0)=="")
assert(not pcall(crypt.generatebytes,-1))
assert(not pcall(crypt.decrypt,"invalid",key,iv1,"CBC"))
assert(not pcall(crypt.encrypt,data,crypt.base64encode("short"),iv1,"CBC"))
assert(not pcall(crypt.encrypt,data,key,iv1,"unknown"))
''')

    def test_lz4_literal_interoperability_and_sizes(self):
        self.run_script('''
assert(lz4decompress(string.char(0x50).."hello",5)=="hello")
for _,data in {"", "hello", string.rep("abc",100),string.char(0,255,1,2)} do
 local compressed=lz4compress(data)
 assert(lz4decompress(compressed,#data)==data)
 if #data>0 then assert(not pcall(lz4decompress,compressed,#data-1)) end
 assert(not pcall(lz4decompress,compressed,#data+1))
end
assert(not pcall(lz4decompress,"invalid",262145))
''')

    def test_cache_and_cloned_handles_preserve_underlying_identity(self):
        self.run_script('''
local folder=Instance.new("Folder");local part=Instance.new("Part",folder)
local clone=cloneref(part);assert(clone~=part and compareinstances(clone,part))
clone.Name="Renamed";assert(part.Name=="Renamed" and folder.Renamed==part)
cache.invalidate(part);assert(not cache.iscached(part))
local fresh=folder.Renamed;assert(fresh~=part and compareinstances(part,fresh))
assert(cache.iscached(fresh));local fire=Instance.new("Fire")
cache.replace(part,fire);assert(folder:FindFirstChild("Renamed")==fire)
cache.invalidate(part);assert(compareinstances(folder.Renamed,part))
clone:Destroy();assert(fresh.Parent==nil and part.Parent==nil)
''')

    def test_callback_and_connection_controls(self):
        self.run_script('''
local callback=Instance.new("BindableFunction");local fn=function()return 7 end
callback.OnInvoke=fn;assert(getcallbackvalue(callback,"OnInvoke")==fn)
assert(callback:Invoke()==7);callback.OnInvoke=nil;assert(getcallbackvalue(callback,"OnInvoke")==nil)
local event=Instance.new("BindableEvent");local count=0
local handler=function(n)count+=n end
event.Event:Connect(handler)
local c=getconnections(event.Event)[1]
assert(c.Function==handler and c.LuaConnection and not c.ForeignState)
assert(c.Thread==coroutine.running())
c:Disable();event:Fire(10);task.wait();assert(count==0 and not c.Enabled)
c:Enable();c:Fire(3);task.wait();assert(count==3)
c:Defer(4);task.wait();assert(count==7)
c:Disconnect();event:Fire(100);task.wait();assert(count==7 and #getconnections(event.Event)==0)
''')

    def test_constants_prototypes_and_stack_mutations(self):
        self.run_script('''
local function constant()return "before" end
assert(debug.getconstant(constant,1)=="before")
debug.setconstant(constant,1,"after");assert(constant()=="after")
assert(debug.getconstants(constant)[1]=="after")
assert(not pcall(debug.setconstant,constant,1,{}))
local function outer()local function inner()return 42 end;return inner end
local actual=outer();assert(not pcall(debug.getproto(outer,1)))
assert(debug.getproto(outer,1,true)[1]()==42)
assert(#debug.getprotos(outer)==1)
local function registers()local x="a";x=x.."b";assert(debug.getstack(1,1)=="ab") end
registers()
local function rewrite()return "before",debug.setstack(1,1,"after") end
assert(rewrite()=="after")
assert(not pcall(debug.getstack,999,1))
assert(not pcall(debug.getproto,outer,999))
''')

    def test_function_hooks_and_gc_references(self):
        self.run_script('''
local function f()return true end
local alias=f;local original=hookfunction(f,function()return false end)
assert(not f() and not alias() and original() and original~=f)
local gc=getgc();assert(table.find(gc,f) and table.find(gc,original))
local t={};assert(table.find(getgc(true),t))
local native=clonefunction(tostring)
local oldNative=hookfunction(native,function()return "hooked" end)
assert(native()=="hooked" and oldNative(42)=="42");restorefunction(native)
assert(isexecutorclosure(isexecutorclosure))
assert(isexecutorclosure(function()end) and not isexecutorclosure(print))
-- Hooking a captured closure with fewer captures must preserve its allocation
-- size through GC, and a later hook can reuse the original capture capacity.
for i=1,250 do
 local value=math.random();local target=function()return value end
 local prior=hookfunction(target,function()return 5 end)
 assert(prior()==value and target()==5)
 local other=math.random();hookfunction(target,function()return other end)
 assert(target()==other)
end
''')

    def test_namecall_forwarding_and_local_overlay(self):
        self.run_script('''
local seen;local original
original=hookmetamethod(game,"__namecall",function(...)
 seen=getnamecallmethod();return original(...)
end)
local lighting=game:GetService("Lighting");assert(seen=="GetService" and lighting.ClassName=="Lighting")
hookmetamethod(game,"__namecall",original)
assert(checkcaller());assert(isrbxactive()==true)
local gui=gethui();assert(gui==gethui() and gui:IsA("Folder"))
local f=Instance.new("Frame",gui);assert(f.Parent==gui)
local id=getthreadidentity();setthreadidentity(3);assert(getidentity()==3)
setthreadidentity(id);assert(not pcall(setidentity,-1))
''')


if __name__=='__main__':unittest.main()
