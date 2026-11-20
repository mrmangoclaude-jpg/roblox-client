-- Engine-only math a protector can use as a "real engine" proof, hashed per group. Run in a live client and in Rove and diff the lines
-- (client values for 2026-11-20 are in engine_math_fuzz.client-hashes.txt). Set GROUP to a group name to print that group in full.
local GROUP = nil
local seed = 424242
local function rnd() seed = (seed * 1103515245 + 12345) % 2147483648 return seed / 2147483648 end
local function r(a, b) return a + (b - a) * rnd() end
local function f(v) return string.format("%.17g", v) end
local function hash(s) local h = 5381 for i = 1, #s do h = (h * 31 + string.byte(s, i)) % 4294967296 end return h end
local function v3(v) return f(v.X) .. "," .. f(v.Y) .. "," .. f(v.Z) end
local function cf(c) local t = {c:GetComponents()} for i = 1, #t do t[i] = f(t[i]) end return table.concat(t, ",") end
local function try(fn, ...) local ok, a, b, c = pcall(fn, ...) if not ok then return "ERR " .. tostring(a) end return a, b, c end
local groups, order = {}, {}
local function group(name, fn)
	local lines = {}
	local ok, err = pcall(fn, function(s) lines[#lines + 1] = s end)
	if not ok then lines[#lines + 1] = "GROUP ERROR " .. tostring(err) end
	groups[name] = table.concat(lines, "\n") order[#order + 1] = name
end
group("noise", function(add) for i = 1, 300 do add(f(math.noise(r(-50, 50), r(-50, 50), r(-50, 50)))) end for i = 1, 30 do add(f(math.noise(r(-5, 5)))) add(f(math.noise(r(-5, 5), r(-5, 5)))) end end)
group("easing", function(add)
	local ts = game:GetService("TweenService")
	for _, style in {"Linear", "Sine", "Back", "Quad", "Quart", "Quint", "Bounce", "Elastic", "Exponential", "Circular", "Cubic"} do
		for _, dir in {"In", "Out", "InOut"} do
			local row = {}
			for a = 0, 20 do row[#row + 1] = tostring(try(function() return f(ts:GetValue(a / 20, Enum.EasingStyle[style], Enum.EasingDirection[dir])) end)) end
			add(style .. dir .. ": " .. table.concat(row, " "))
		end
	end
end)
group("cframe", function(add)
	for i = 1, 80 do
		local a = CFrame.fromEulerAnglesYXZ(r(-3, 3), r(-1.5, 1.5), r(-3, 3)) + Vector3.new(r(-9, 9), r(-9, 9), r(-9, 9))
		local b = CFrame.new(r(-5, 5), r(-5, 5), r(-5, 5)) * CFrame.Angles(r(-3, 3), r(-3, 3), r(-3, 3))
		add(cf(a) .. " | " .. cf(a:Inverse()) .. " | " .. cf(a * b) .. " | " .. cf(a:Lerp(b, 0.37)))
		local x, y, z = a:ToEulerAnglesXYZ() local p, q, s = a:ToEulerAnglesYXZ() local o1, o2, o3 = a:ToOrientation()
		add(f(x) .. "," .. f(y) .. "," .. f(z) .. " | " .. f(p) .. "," .. f(q) .. "," .. f(s) .. " | " .. f(o1) .. "," .. f(o2) .. "," .. f(o3))
		add(v3(a:VectorToWorldSpace(Vector3.new(1, 2, 3))) .. " | " .. v3(a:PointToObjectSpace(Vector3.new(4, 5, 6))) .. " | " .. v3(a.LookVector) .. " | " .. v3(a.UpVector))
		local axis, angle = a:ToAxisAngle() add(v3(axis) .. "," .. f(angle) .. " | " .. cf(CFrame.lookAt(a.Position, b.Position)) .. " | " .. cf(CFrame.fromAxisAngle(Vector3.new(r(-1, 1), r(-1, 1), r(-1, 1)).Unit, r(-3, 3))))
	end
end)
group("vector3", function(add)
	for i = 1, 100 do
		local a, b = Vector3.new(r(-20, 20), r(-20, 20), r(-20, 20)), Vector3.new(r(-20, 20), r(-20, 20), r(-20, 20))
		add(v3(a.Unit) .. " | " .. f(a.Magnitude) .. " | " .. v3(a:Cross(b)) .. " | " .. f(a:Dot(b)) .. " | " .. v3(a:Lerp(b, 0.41)) .. " | " .. f(a:Angle(b)) .. " | " .. v3(a:Max(b)) .. " | " .. v3(a * 1.7 / 3) .. " | " .. tostring(a:FuzzyEq(b, 0.5)))
		local c, d = Vector2.new(r(-9, 9), r(-9, 9)), Vector2.new(r(-9, 9), r(-9, 9))
		add(f(c.Magnitude) .. "," .. f(c.Unit.X) .. "," .. f(c:Dot(d)) .. "," .. f(c:Cross(d)) .. "," .. f(c:Lerp(d, 0.3).Y) .. "," .. f(c:Angle(d)))
	end
end)
group("color3", function(add)
	for i = 1, 100 do
		local c = Color3.fromHSV(rnd(), rnd(), rnd()) local h, s, v = c:ToHSV()
		local d = Color3.fromRGB(math.floor(r(0, 255)), math.floor(r(0, 255)), math.floor(r(0, 255)))
		add(f(c.R) .. "," .. f(c.G) .. "," .. f(c.B) .. " | " .. f(h) .. "," .. f(s) .. "," .. f(v) .. " | " .. c:ToHex() .. " | " .. d:ToHex() .. " | " .. f(c:Lerp(d, 0.5).G) .. " | " .. tostring(Color3.fromHex(c:ToHex()) == c))
	end
end)
group("random", function(add)
	for seedValue = 1, 25 do
		local g = Random.new(seedValue * 7919)
		add(f(g:NextNumber()) .. "," .. g:NextInteger(1, 1000) .. "," .. f(g:NextNumber(5, 10)) .. "," .. v3(g:NextUnitVector()) .. "," .. g:NextInteger(-50, 50) .. "," .. g:NextInteger(1, 2147483647))
		local t = {1, 2, 3, 4, 5, 6, 7, 8} g:Shuffle(t) add(table.concat(t, ","))
	end
end)
group("floats", function(add)
	for _, v in {0.1 + 0.2, 1e15, 1e16, 2 ^ 53, -0.0, 1 / 3, 123456789.123456789, 5e-324, 1e100, 1 / 0, -1 / 0, 255 / 256, 100, 1e21, 0.1} do
		add(tostring(v) .. " | " .. string.format("%g %.3f %5.1f %e %.14g", v, v, v, v, v))
	end
	for i = 1, 40 do local v = r(-1e6, 1e6) add(tostring(v) .. " " .. tostring(v / 7) .. " " .. string.format("%.5g", v)) end
	local b = buffer.create(16)
	for i = 1, 60 do local v = r(-1000, 1000) buffer.writef32(b, 0, v) add(f(buffer.readf32(b, 0)) .. " " .. f(Vector3.new(v, v, v).X) .. " " .. f(UDim.new(v, 0).Scale)) end
end)
group("datetime", function(add)
	for _, ts in {0, 86399, 1700000000, 1234567890, 951782400, 4102444800} do
		local d = DateTime.fromUnixTimestamp(ts)
		local u = d:ToUniversalTime()
		add(d:ToIsoDate() .. " " .. u.Year .. "-" .. u.Month .. "-" .. u.Day .. " " .. u.Hour .. ":" .. u.Minute .. ":" .. u.Second .. " " .. d:FormatUniversalTime("LLL", "en-us") .. " " .. d:FormatUniversalTime("dddd", "en-us"))
	end
end)
if GROUP then return groups[GROUP] or "no such group" end
local result = {}
for _, name in order do result[#result + 1] = name .. ":" .. hash(groups[name]) end
return table.concat(result, " ")
