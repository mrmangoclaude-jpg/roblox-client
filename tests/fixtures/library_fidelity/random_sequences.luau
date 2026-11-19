-- Random sequences must match Roblox exactly: protected scripts derive keys from them.
local out = {}
local function clean(text)
	text = string.gsub(text, "[%w_%.%-]+:%d+: ", "")
	text = string.gsub(text, "0x%x+", "0xADDR")
	return text
end
local function num(v) return string.format("%.17g", v) end
local function T(label, f)
	local r = table.pack(pcall(f))
	local parts = {}
	for i = 1, r.n do
		local v = r[i]
		parts[i] = type(v) == "number" and num(v) or (type(v) == "string" and string.format("%q", clean(v)) or (typeof(v) == "Vector3" and ("V3(" .. num(v.X) .. "," .. num(v.Y) .. "," .. num(v.Z) .. ")") or tostring(v)))
	end
	table.insert(out, label .. " -> " .. table.concat(parts, " | "))
end
for _, seed in {0, 1, 42, 12345, -7, 4294967295, 4294967296, 1.5, 1e10, -0.5} do
	T("seed " .. tostring(seed), function()
		local r = Random.new(seed)
		return r:NextNumber(), r:NextNumber(), r:NextInteger(1, 1000), r:NextInteger(-5, 5), r:NextNumber(2, 7), r:NextInteger(1, 2 ^ 31 - 1)
	end)
	T("seed " .. tostring(seed) .. " unit/shuffle", function()
		local r = Random.new(seed)
		local v = r:NextUnitVector()
		local t = {1, 2, 3, 4, 5, 6, 7, 8}
		r:Shuffle(t)
		return v, table.concat(t, ","), r:NextNumber()
	end)
end
T("clone continues", function()
	local r = Random.new(99)
	r:NextNumber()
	local c = r:Clone()
	return r:NextNumber(), c:NextNumber(), r:NextInteger(1, 100), c:NextInteger(1, 100)
end)
T("large integer ranges", function()
	local r = Random.new(5)
	return r:NextInteger(0, 2 ^ 32), r:NextInteger(-2 ^ 31, 2 ^ 31), r:NextInteger(1, 1)
end)
T("NextInteger(5,1)", function() return Random.new(1):NextInteger(5, 1) end)
T("NextNumber(1,0)", function() return Random.new(1):NextNumber(1, 0) end)
T("NextInteger()", function() return Random.new(1):NextInteger() end)
T("NextInteger(1.5, 4.5)", function() return Random.new(1):NextInteger(1.5, 4.5) end)
T("Shuffle(1)", function() return Random.new(1):Shuffle(1) end)
T("Shuffle({}, extra)", function() return Random.new(1):Shuffle({}) end)
T("Random.new('x')", function() return Random.new("x") end)
T("Random.new(nan)", function() return Random.new(0 / 0):NextNumber() end)
T("Random.new(inf)", function() return Random.new(math.huge):NextNumber() end)
T("typeof Random", function() return typeof(Random.new(1)) end)
T("tostring Random", function() return tostring(Random.new(1)) end)
T("NextUnitVector name", function() return debug.info(Random.new(1).NextUnitVector, "n") end)
T("method identity", function() local r = Random.new(1) return r.NextNumber == r.NextNumber, r.NextNumber == Random.new(2).NextNumber end)
T("Random member nope", function() return Random.new(1).Nope end)
T("Random metatable", function() return getmetatable(Random.new(1)) end)
T("Random lib members", function() local k = {} for key in pairs(Random) do table.insert(k, key) end table.sort(k) return table.concat(k, ",") end)
return table.concat(out, "\n")
