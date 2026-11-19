-- Constructors and creators called with fractional and surplus arguments, as protected scripts do.
local out = {}
local function show(v)
	if type(v) == "string" then return string.format("%q", v) end
	if type(v) == "function" or type(v) == "thread" then return type(v) end
	local ok, text = pcall(tostring, v)
	return typeof(v) .. ":" .. (ok and text or "?")
end
local function T(label, f, ...)
	local r = table.pack(pcall(f, ...))
	local parts = {}
	for i = 1, r.n do parts[i] = show(r[i]) end
	table.insert(out, label .. " -> " .. table.concat(parts, " | "))
end
local a, b, c = 0.4422446546745451, 0.94966878328634, 0.1388023259328105
local ctors = {
	{"Vector3", Vector3.new}, {"Vector2", Vector2.new}, {"Color3", Color3.new}, {"UDim2", UDim2.new}, {"UDim", UDim.new},
	{"CFrame", CFrame.new}, {"Vector3int16", Vector3int16.new}, {"Vector2int16", Vector2int16.new}, {"NumberRange", NumberRange.new},
	{"Rect", Rect.new}, {"Ray", Ray.new}, {"BrickColor", BrickColor.new}, {"Region3", Region3.new}, {"TweenInfo", TweenInfo.new},
	{"ColorSequenceKeypoint", ColorSequenceKeypoint.new}, {"NumberSequenceKeypoint", NumberSequenceKeypoint.new},
	{"PhysicalProperties", PhysicalProperties.new}, {"Random", Random.new}, {"Path2DControlPoint", Path2DControlPoint.new},
	{"NumberSequence", NumberSequence.new}, {"Axes", Axes.new}, {"Faces", Faces.new}, {"Instance", Instance.new},
	{"OverlapParams", OverlapParams.new}, {"RaycastParams", RaycastParams.new}, {"Font", Font.new}, {"DateTime", DateTime.fromUnixTimestamp},
}
for _, entry in ctors do
	T(entry[1] .. ".new(3 floats)", entry[2], a, b, c)
	T(entry[1] .. ".new(1 float)", entry[2], a)
	T(entry[1] .. ".new()", entry[2])
end
local creators = { {"table.create", table.create}, {"buffer.create", buffer.create}, {"coroutine.create", coroutine.create}, {"coroutine.wrap", coroutine.wrap} }
for _, entry in creators do
	T(entry[1] .. "(3 floats)", function(...) local r = entry[2](...) return type(r), (type(r) == "table" and #r or type(r) == "buffer" and buffer.len(r) or nil) end, 0.3088667, 0.4562241, 0.3671827)
	T(entry[1] .. "(2.7)", function(...) local r = entry[2](...) return type(r), (type(r) == "table" and #r or type(r) == "buffer" and buffer.len(r) or nil) end, 2.7)
	T(entry[1] .. "(-1)", function(...) local r = entry[2](...) return type(r) end, -1)
	T(entry[1] .. "(0/0)", function(...) local r = entry[2](...) return type(r) end, 0 / 0)
	T(entry[1] .. "('3')", function(...) local r = entry[2](...) return type(r), (type(r) == "table" and #r or type(r) == "buffer" and buffer.len(r) or nil) end, "3")
	T(entry[1] .. "()", entry[2])
end
T("pcall(Lua) returns", function() return pcall(function() return 1, 2 end) end)
T("select('#', pcall(error))", function() return select("#", pcall(error)) end)
T("unpack odd ranges", function() return select("#", unpack({1, 2, 3}, 1.5, 3.2)) end)
T("unpack huge", function() return select("#", unpack({}, 1, 1e8)) end)
T("unpack negative", function() return select("#", unpack({1, 2}, -1, 1)) end)
return table.concat(out, "\n")
