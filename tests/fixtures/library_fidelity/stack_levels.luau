-- Which function sits at each call-stack level while an error handler runs. Protected scripts compare these
-- against the base functions they just called, so the stack shape has to match Roblox exactly.
local out = {}
local named = {
	[error] = "error", [xpcall] = "xpcall", [pcall] = "pcall", [getmetatable] = "getmetatable", [setmetatable] = "setmetatable",
	[tostring] = "tostring", [tonumber] = "tonumber", [rawget] = "rawget", [rawset] = "rawset", [select] = "select",
	[assert] = "assert", [type] = "type", [next] = "next", [typeof] = "typeof", [string.rep] = "rep", [string.sub] = "sub",
	[bit32.band] = "band", [buffer.create] = "create", [table.insert] = "insert", [coroutine.wrap] = "wrap",
}
local function label(f)
	if f == nil then return "nil" end
	return named[f] or (debug.info(f, "s") == "[C]" and "C?" or "lua")
end
local function levels(extra)
	local parts = {}
	for level = 1, 6 do
		local ok, f = pcall(debug.info, level, "f")
		parts[#parts + 1] = (ok and label(f) or "err")
	end
	return table.concat(parts, ",")
end
local function record(name, f, ...)
	local seen
	local function handler(message)
		seen = levels()
		return message
	end
	local ok = xpcall(f, handler, ...)
	table.insert(out, name .. " ok=" .. tostring(ok) .. " levels=" .. tostring(seen))
end
record("getmetatable()", getmetatable)
record("setmetatable()", setmetatable)
record("tostring()", tostring)
record("rawget()", rawget)
record("rawset()", rawset)
record("select()", select)
record("assert()", assert)
record("error('x')", error, "x")
record("type()", type)
record("next()", next)
record("typeof()", typeof)
record("rep()", string.rep)
record("sub()", string.sub)
record("band('a')", bit32.band, "a")
record("create()", buffer.create)
record("insert()", table.insert)
record("wrap()", coroutine.wrap)
record("lua error", function() error("boom") end)
record("lua nested", function() local function inner() error("boom") end inner() end)
-- Direct levels from plain Lua call chains, with and without pcall in between.
local function atLevel(n) return label(debug.info(n, "f")) end
table.insert(out, "plain lvl1=" .. atLevel(1) .. " lvl2=" .. atLevel(2) .. " lvl3=" .. atLevel(3))
table.insert(out, "via pcall: " .. tostring(select(2, pcall(function() return levels() end))))
table.insert(out, "via xpcall: " .. tostring(select(2, xpcall(function() return levels() end, print))))
table.insert(out, "via coroutine: " .. tostring(select(2, coroutine.resume(coroutine.create(function() return levels() end)))))
-- debug.info options on base functions.
for _, pair in { { "getmetatable", getmetatable }, { "tostring", tostring }, { "xpcall", xpcall }, { "bit32.band", bit32.band },
	{ "buffer.writeu32", buffer.writeu32 }, { "string.gmatch", string.gmatch }, { "task.spawn", task.spawn }, { "coroutine.wrap", coroutine.wrap },
	{ "debug.info", debug.info }, { "table.insert", table.insert }, { "utf8.char", utf8.char }, { "math.floor", math.floor } } do
	local s, l, n, a1, a2, f = debug.info(pair[2], "slnaf")
	table.insert(out, pair[1] .. " slnaf=" .. tostring(s) .. "," .. tostring(l) .. "," .. tostring(n) .. "," .. tostring(a1) .. "," .. tostring(a2) .. "," .. tostring(f == pair[2]))
end
return table.concat(out, "\n")
