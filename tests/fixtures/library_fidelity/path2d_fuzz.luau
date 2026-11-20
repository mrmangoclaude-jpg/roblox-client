-- Path2D differential fuzz. A protector proves "this is the real engine" with math an emulator cannot guess, and Path2D's
-- spline/arc-length math is exactly that: each protected script embeds its OWN random control points and sample positions
-- and mixes the engine's answers into its keys. The Rove port was checked against one script's inputs only, so compare it
-- against Studio on many generated inputs. Run in Studio (command bar is fine) and in Rove, then diff the text bit for bit.
-- The generator is a self-contained LCG, so both sides build identical cases without depending on Random.
local seed = 20261120
local function rnd()
	seed = (seed * 1103515245 + 12345) % 2147483648
	return seed / 2147483648
end
local function scale() return (math.floor(rnd() * 17) - 8) / 16 end -- -0.5 .. 0.5 in steps of 1/16, like the protector's values
local function offset() return math.floor(rnd() * 25) - 12 end
local function udim2() return UDim2.new(scale(), offset(), scale(), offset()) end
local function zero() return UDim2.new(0, 0, 0, 0) end
local function fmt(v) return string.format("%.17g", v) end
local function show(v)
	local t = typeof(v)
	if t == "UDim2" then return fmt(v.X.Scale) .. "," .. v.X.Offset .. "," .. fmt(v.Y.Scale) .. "," .. v.Y.Offset end
	if t == "Vector2" then return fmt(v.X) .. "," .. fmt(v.Y) end
	if t == "number" then return fmt(v) end
	return t .. ":" .. tostring(v)
end
local out = {}
local samples = {0, 0.125, 0.2222222238779068, 0.28571429848670959, 0.4, 0.5, 0.625, 0.875, 1, -0.5, 1.5}
for case = 1, 80 do
	local screen = Instance.new("ScreenGui")
	local frame = Instance.new("Frame")
	-- Offset-sized frames like the protected guard's; every 8th case sizes the frame with Scale, which the offline model never covered.
	local scaled = case % 8 == 0
	frame.Size = scaled and UDim2.new(0.5, 0, 0.25, 0) or UDim2.new(0, 40 + math.floor(rnd() * 300), 0, 40 + math.floor(rnd() * 300))
	frame.Parent = screen
	local path = Instance.new("Path2D")
	path.Parent = frame
	local points = {}
	local count = 2 + math.floor(rnd() * 4)
	for i = 1, count do
		local kind = math.floor(rnd() * 3) -- 0: full point, 1: position only, 2: tangents zeroed
		if kind == 0 then points[i] = Path2DControlPoint.new(udim2(), udim2(), udim2())
		elseif kind == 1 then points[i] = Path2DControlPoint.new(udim2())
		else points[i] = Path2DControlPoint.new(udim2(), zero(), zero()) end
	end
	out[#out + 1] = "case " .. case .. (scaled and " scaled-frame" or "") .. " points=" .. count
	local ok, err = pcall(path.SetControlPoints, path, points)
	out[#out + 1] = "  set: " .. tostring(ok) .. (ok and "" or " " .. tostring(err))
	if ok then
		local lok, length = pcall(path.GetLength, path)
		out[#out + 1] = "  length: " .. (lok and show(length) or "ERR " .. tostring(length))
		for _, method in {"GetPositionOnCurve", "GetTangentOnCurve", "GetPositionOnCurveArcLength", "GetTangentOnCurveArcLength"} do
			local row = {}
			for _, t in samples do
				local mok, value = pcall(path[method], path, t)
				row[#row + 1] = mok and show(value) or "ERR " .. tostring(value)
			end
			out[#out + 1] = "  " .. method .. ": " .. table.concat(row, " | ")
		end
		local gok, got = pcall(path.GetControlPoints, path)
		out[#out + 1] = "  controlPoints back: " .. tostring(gok and #got or got)
	end
	screen:Destroy()
end
return table.concat(out, "\n")
