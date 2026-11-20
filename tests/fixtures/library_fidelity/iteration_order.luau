-- Iteration order of the standard libraries. Protected scripts can fold the order in which pairs()/next() visit a library
-- table into their keys, so the order has to match the engine, not just the set of members. Rove patches several library
-- tables after Luau builds them (coroutine, utf8, debug, os), which can move keys within the hash part.
-- Run it in Studio (a LocalScript in play mode, not only the command bar: the debug library differs there) and in Rove, and diff.
local out = {}
local libraries = {
	{"string", string}, {"table", table}, {"math", math}, {"bit32", bit32}, {"buffer", buffer}, {"utf8", utf8},
	{"os", os}, {"coroutine", coroutine}, {"debug", debug}, {"task", task},
}
for _, entry in libraries do
	local names, walk = {}, {}
	for key in entry[2] do names[#names + 1] = tostring(key) end -- generalized iteration
	local key = nil
	repeat -- explicit next() walk: must visit the same keys in the same order
		key = next(entry[2], key)
		if key ~= nil then walk[#walk + 1] = tostring(key) end
	until key == nil
	out[#out + 1] = entry[1] .. " (" .. #names .. "): " .. table.concat(names, ",")
	out[#out + 1] = entry[1] .. " next-walk equal: " .. tostring(table.concat(names, ",") == table.concat(walk, ","))
end
-- The script environment table and the metatable-less globals protected scripts enumerate.
local env, names = getfenv(), {}
for key in env do names[#names + 1] = tostring(key) end
out[#out + 1] = "getfenv(): " .. table.concat(names, ",")
-- Enum catalog order and the item order of two enums.
local enums, enumNames = Enum:GetEnums(), {}
for i = 1, math.min(#enums, 12) do enumNames[#enumNames + 1] = tostring(enums[i]) end
out[#out + 1] = "Enum:GetEnums() count/first: " .. #enums .. " / " .. table.concat(enumNames, ",")
for _, enumName in {"HumanoidRigType", "Material"} do
	local items = {}
	for _, item in Enum[enumName]:GetEnumItems() do items[#items + 1] = item.Name .. "=" .. item.Value end
	out[#out + 1] = "Enum." .. enumName .. ":GetEnumItems(): " .. table.concat(items, ",")
end
return table.concat(out, "\n")
