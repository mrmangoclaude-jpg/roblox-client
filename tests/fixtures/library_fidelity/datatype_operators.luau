-- Arithmetic, comparison and length operators on every datatype, with same-type, number and mixed operands.
local ONLY = nil -- set to a type name to print that type in full; otherwise one checksum per type
local out = {}
local function hash(text) local h = 5381 for i = 1, #text do h = (h * 33 + string.byte(text, i)) % 4294967296 end return h end
local function clean(text)
	text = string.gsub(text, "[%w_%.%-]+:%d+: ", "")
	text = string.gsub(text, "0x%x+", "0xADDR")
	return text
end
local function show(v)
	if type(v) == "string" then return string.format("%q", clean(v)) end
	if type(v) == "function" or type(v) == "thread" then return type(v) end
	local ok, text = pcall(tostring, v)
	return typeof(v) .. ":" .. (ok and clean(text) or "?")
end
local current = {}
local function T(label, f)
	local r = table.pack(pcall(f))
	local parts = {}
	for i = 1, r.n do parts[i] = show(r[i]) end
	table.insert(current, label .. " -> " .. table.concat(parts, " | "))
end
local function flush(name)
	local text = table.concat(current, "\n")
	if ONLY == "LINES" then
		local codes = {}
		for i, line in current do codes[i] = tostring(hash(line) % 1000) end
		table.insert(out, name .. ": " .. table.concat(codes, " "))
	elseif ONLY == nil then table.insert(out, name .. " lines=" .. #current .. " hash=" .. hash(text)) elseif ONLY == name then table.insert(out, text) end
	current = {}
end
local samples = {
	Vector3 = Vector3.new(7, -9, 4), Vector2 = Vector2.new(7, -9), Vector3int16 = Vector3int16.new(7, -9, 4), Vector2int16 = Vector2int16.new(7, -9),
	CFrame = CFrame.new(1, 2, 3), UDim = UDim.new(0.5, 3), UDim2 = UDim2.new(0.5, 3, 0.25, 4), Color3 = Color3.new(0.5, 0.25, 1),
	Rect = Rect.new(0, 0, 1, 1), BrickColor = BrickColor.new("Red"), NumberRange = NumberRange.new(1, 2), Random = Random.new(1),
	Ray = Ray.new(Vector3.zero, Vector3.one), Instance = Instance.new("Folder"), EnumItem = Enum.Material.Plastic,
}
local order = { "Vector3", "Vector2", "Vector3int16", "Vector2int16", "CFrame", "UDim", "UDim2", "Color3", "Rect", "BrickColor", "NumberRange", "Random", "Ray", "Instance", "EnumItem" }
local ops = {
	{ "+", function(a, b) return a + b end }, { "-", function(a, b) return a - b end }, { "*", function(a, b) return a * b end },
	{ "/", function(a, b) return a / b end }, { "//", function(a, b) return a // b end }, { "%", function(a, b) return a % b end },
	{ "^", function(a, b) return a ^ b end }, { "<", function(a, b) return a < b end }, { "<=", function(a, b) return a <= b end },
	{ "..", function(a, b) return a .. b end },
}
for _, name in order do
	local v = samples[name]
	T(name .. " unm", function() return -v end)
	T(name .. " len", function() return #v end)
	for _, op in ops do
		T(name .. " " .. op[1] .. " same", function() return op[2](v, v) end)
		T(name .. " " .. op[1] .. " num", function() return op[2](v, 2) end)
		T(name .. " num " .. op[1], function() return op[2](2, v) end)
	end
	flush(name)
end
T("Vector3 // Vector3(0)", function() return Vector3.new(1, 2, 3) // Vector3.zero end)
T("Vector3 // 0", function() return Vector3.new(1, 2, 3) // 0 end)
T("Vector2 // 2.5", function() return Vector2.new(7, -9) // 2.5 end)
T("Vector2 // Vector2", function() return Vector2.new(7, -9) // Vector2.new(2, 2) end)
T("Vector3 mixed Vector2", function() return Vector3.new() + Vector2.new() end)
T("Vector3int16 // 2", function() return Vector3int16.new(7, -9, 4) // 2 end)
T("Vector2int16 // 2", function() return Vector2int16.new(7, -9) // 2 end)
flush("extras")
return table.concat(out, "\n")
