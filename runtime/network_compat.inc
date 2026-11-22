using NetworkJson=nlohmann::json;
NetworkJson network_value(lua_State* L,int index,int depth=0) {
    if(depth>4)throw std::runtime_error("network options nesting limit exceeded");
    index=lua_absindex(L,index);
    if(lua_isnil(L,index))return nullptr;
    if(lua_isboolean(L,index))return lua_toboolean(L,index)!=0;
    if(lua_type(L,index)==LUA_TNUMBER){auto n=lua_tonumber(L,index);if(!std::isfinite(n))throw std::runtime_error("nonfinite network option");if(std::floor(n)==n&&std::abs(n)<9007199254740992.0)return int64_t(n);return n;}
    if(lua_type(L,index)==LUA_TSTRING){size_t size=0;auto* data=lua_tolstring(L,index,&size);if(size>1024*1024)throw std::runtime_error("network option exceeds limit");return std::string(data,size);}
    if(lua_istable(L,index)){NetworkJson result=NetworkJson::object();int count=0;lua_pushnil(L);while(lua_next(L,index)){if(++count>128||lua_type(L,-2)!=LUA_TSTRING)throw std::runtime_error("network options require bounded string keys");size_t size=0;auto* key=lua_tolstring(L,-2,&size);result[std::string(key,size)]=network_value(L,-1,depth+1);lua_pop(L,1);}return result;}
    throw std::runtime_error("unsupported network option type");
}
void push_network_value(lua_State* L,const NetworkJson& value) {
    if(value.is_null())lua_pushnil(L);else if(value.is_boolean())lua_pushboolean(L,value.get<bool>());
    else if(value.is_number())lua_pushnumber(L,value.get<double>());
    else if(value.is_string()){const auto& s=value.get_ref<const std::string&>();lua_pushlstring(L,s.data(),s.size());}
    else if(value.is_array()){lua_createtable(L,value.size(),0);int i=0;for(const auto& item:value){push_network_value(L,item);lua_rawseti(L,-2,++i);}}
    else {lua_createtable(L,0,value.size());for(auto it=value.begin();it!=value.end();++it){push_network_value(L,it.value());lua_setfield(L,-2,it.key().c_str());}}
}
int network_bridge(lua_State* L) {
    try {
        luaL_checktype(L,1,LUA_TTABLE);auto input=network_value(L,1).dump();
        auto* bindings=static_cast<const SourceBindings*>(lua_touserdata(L,lua_upvalueindex(1)));
        unsigned char* output=nullptr;size_t length=0;
        if(bindings->codec(100,reinterpret_cast<const unsigned char*>(input.data()),input.size(),&output,&length))throw std::runtime_error("network request exceeds limit");
        auto release=[&](unsigned char* p){bindings->release(p,length);};std::unique_ptr<unsigned char,decltype(release)> owner(output,release);
        auto result=NetworkJson::parse(output,output+length);if(result.contains("error"))throw std::runtime_error(result["error"].get<std::string>());
        push_network_value(L,result);return 1;
    }catch(const std::exception& e){luaL_error(L,"network: %s",e.what());return 0;}
}
void install_network_compat(lua_State* L,const SourceBindings* bindings) {
    static const char* source=R"NETWORK(
local bridge=...
local encode,decode=crypt.base64encode,crypt.base64decode
local function await(request)
 local id=bridge({operation="start",request=request}).id
 while true do
  local result=bridge({operation="result",id=id})
  if result.ready then assert(not result.value.error,result.value.error);return result.value end
  task.wait(0.005)
 end
end
local methods={GET=true,POST=true,PUT=true,PATCH=true,DELETE=true,HEAD=true,OPTIONS=true}
local scriptBytecode,compileSource=getscriptbytecode,loadstring
function decompile(script)
 local bytes=scriptBytecode(script)
 assert(#bytes<=512*1024,"bytecode exceeds 512 KiB")
 local source=await({operation="decompile",BytecodeBase64=encode(bytes)}).Source
 local fn,err=compileSource(source,"=decompiled-source")
 assert(fn,"decompiler returned invalid source: "..tostring(err))
 return source
end
local function requestHeaders(headers,cookies)
 if cookies==nil then return headers end
 assert(type(cookies)=="table","request Cookies must be a table")
 local merged={};local count=0
 if headers~=nil then
  assert(type(headers)=="table","request Headers must be a table")
  for name,value in pairs(headers) do
   count+=1;assert(count<=128,"request Headers exceed limit");merged[name]=value
  end
 end
 local values={};local size=0;count=0
 for name,value in pairs(cookies) do
  count+=1;assert(count<=128,"request Cookies exceed limit")
  assert(type(name)=="string" and type(value)=="string","request Cookies must contain text")
  size+=#name+#value+3;assert(size<=8192,"request Cookie header exceeds limit")
  table.insert(values,name.."="..value)
 end
 if #values>0 then
  table.sort(values)
  local key="Cookie"
  for name in pairs(merged) do
   if type(name)=="string" and string.lower(name)=="cookie" then key=name;break end
  end
  if merged[key]~=nil then
   assert(type(merged[key])=="string","Cookie header must be text")
   table.insert(values,1,merged[key])
  end
  merged[key]=table.concat(values,"; ")
 end
 return merged
end
function request(options)
 -- Match the real client's executor error text: Luraph fingerprints exact
 -- messages from misuse of request(nil)/request({}) as key inputs.
 if type(options)~="table" then error(string.format("attempt to index %s with 'Url'",type(options)),0) end
 if type(options.Url)~="string" then error("invalid url for http request",0) end
 local method=options.Method or "GET"
 assert(type(method)=="string","HTTP method must be text")
 method=string.upper(method)
 assert(methods[method],"Invalid HTTP method")
 local request={operation="http",Url=options.Url,Method=method,Headers=requestHeaders(options.Headers,options.Cookies)}
 if options.Body~=nil then request.BodyBase64=encode(options.Body) end
 local result=await(request);result.Body=decode(result.BodyBase64);result.BodyBase64=nil
 return result
end
http_request=request;http={request=request}
local httpRequest=request
function HttpGet(url, cache)
 assert(type(url)=="string","invalid argument #1 (Instance expected, got "..tostring(type(url))..")")
 assert(cache==nil or type(cache)=="boolean","HttpGet cache flag must be boolean")
 local result=httpRequest({Url=url,Method="GET"})
 assert(result.Success,"HttpGet failed: HTTP "..tostring(result.StatusCode).." "..tostring(result.StatusMessage))
 return result.Body
end
httpget=HttpGet;http.HttpGet=HttpGet
WebSocket={}
function WebSocket.connect(url)
 local id=await({operation="connect",Url=url}).id
 local messages=Instance.new("BindableEvent");local closed=Instance.new("BindableEvent")
 local active=true;local socket={OnMessage=messages.Event,OnClose=closed.Event}
 function socket:Send(data,binary)
  assert(active,"WebSocket is closed")
  await({operation="send",id=id,BodyBase64=encode(data),binary=binary==true})
 end
 function socket:Close()
  if not active then return end
  active=false;await({operation="close",id=id});closed:Fire()
 end
 task.spawn(function()
  while active do
   local ok,result=pcall(bridge,{operation="poll",id=id})
   if not active then break end
   if not ok then active=false;closed:Fire();warn(result);break end
   for _,data in ipairs(result.messages) do messages:Fire(decode(data)) end
   if result.closed then active=false;closed:Fire();break end
   task.wait(0.01)
  end
 end)
 return socket
end
WebSocket.Connect=WebSocket.connect
ws=WebSocket;Websocket=WebSocket;websocket=WebSocket
return function(self,url,cache)
 assert(typeof(self)=="Instance" and self.ClassName=="DataModel","HttpGet requires DataModel")
 return HttpGet(url,cache)
end
)NETWORK";
    auto code=Luau::compile(source);if(luau_load(L,"=network-compat",code.data(),code.size(),0))lua_error(L);
    lua_pushlightuserdata(L,const_cast<SourceBindings*>(bindings));lua_pushcclosurek(L,network_bridge,"network bridge",1,nullptr);lua_call(L,1,1);lua_setfield(L,LUA_REGISTRYINDEX,"Headless.HttpGet");
}
