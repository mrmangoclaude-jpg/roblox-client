-- Shapes of tostring() for each type. Luraph hashes these into its keys. Addresses vary, so only the shape is reported.
local out = {}
local function shape(label, value)
	local text = tostring(value)
	local hex = string.match(text, "0x(%x+)")
	local prefix = string.match(text, "^(%a+: )") or "?"
	table.insert(out, label .. " -> prefix=" .. prefix .. " hexlen=" .. tostring(hex and #hex) .. " len=" .. #text .. " pattern=" .. tostring(string.match(text, "^%a+: 0x%x+$") ~= nil))
end
shape("print", print)
shape("lua function", function() end)
shape("table", {})
shape("thread", coroutine.create(function() end))
shape("buffer", buffer.create(1))
shape("newproxy", newproxy(true))
shape("Instance", Instance.new("Folder"))
shape("Vector3", Vector3.new())
shape("CFrame", CFrame.new())
shape("Random", Random.new(1))
shape("Enum", Enum.Material)
shape("EnumItem", Enum.Material.Plastic)
shape("RBXScriptSignal", game.Changed)
shape("task.wait", task.wait)
shape("string.format", string.format)
local texts = {
	tostring(nil), tostring(true), tostring(1), tostring(1.5), tostring(-0), tostring(0/0), tostring(math.huge), tostring(-math.huge),
	tostring(1e15), tostring(1e16), tostring(2^53), tostring(0.1), tostring(1/3), tostring(123456789012), tostring(1e100),
	tostring(Vector3.new(1, 2, 3)), tostring(Vector2.new(1.5, 2)), tostring(CFrame.new(1, 2, 3)), tostring(Color3.new(1, 0.5, 0)),
	tostring(UDim2.new(0.5, 3, 1, -4)), tostring(Enum.Material.Plastic), tostring(Enum.Material), tostring(Instance.new("Folder")),
	tostring(Rect.new(0, 0, 1, 1)), tostring(BrickColor.new("Red")), tostring(NumberRange.new(1, 2)), tostring(TweenInfo.new()),
	tostring(Random.new(1)), tostring(game), tostring(workspace), tostring(typeof), tostring(Ray.new(Vector3.zero, Vector3.one)),
}
table.insert(out, "values: " .. table.concat(texts, " ; "))
table.insert(out, "format: " .. string.format("%s|%d|%5.2f|%q|%x|%g|%i", "a", 3, 1.256, "q\n", 255, 0.1, 7))
table.insert(out, "concat: " .. tostring(1) .. tostring(2.0) .. tostring(-1.5e-7))
return table.concat(out, "\n")
