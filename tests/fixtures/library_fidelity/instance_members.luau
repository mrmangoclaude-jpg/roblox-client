-- The members protected scripts read from common objects: type, native-function record, identity and error behaviour.
local out = {}
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
local function T(label, f, ...)
	local r = table.pack(pcall(f, ...))
	local parts = {}
	for i = 1, r.n do parts[i] = show(r[i]) end
	table.insert(out, label .. " -> " .. table.concat(parts, " | "))
end
local frame = Instance.new("Frame")
local gui = Instance.new("ScreenGui")
local path = Instance.new("Path2D")
local folder = Instance.new("Folder")
local objects = {
	{"Frame", frame, {"Parent", "Size", "Position", "ChildRemoved", "DescendantAdded", "Name", "ClassName", "AbsoluteSize", "Visible", "BackgroundColor3", "AnchorPoint", "ZIndex", "Changed", "AttributeChanged", "ChildAdded", "AncestryChanged", "Destroying"}},
	{"Path2D", path, {"Parent", "Color3", "Thickness", "Visible", "ZIndex", "ControlPointChanged", "SelectedControlPoint", "Name", "ClassName"}},
	{"ScreenGui", gui, {"Destroy", "Parent", "Enabled", "DisplayOrder", "ResetOnSpawn", "IgnoreGuiInset", "Name", "ClassName", "GetChildren", "ClearAllChildren", "FindFirstChild", "WaitForChild", "IsA", "Clone", "IsDescendantOf"}},
	{"DataModel", game, {"Parent", "Name", "ClassName", "ChildRemoved", "DescendantAdded", "GetService", "GetChildren", "FindService", "IsLoaded", "PlaceId", "GameId", "JobId", "Loaded", "BindToClose", "Workspace", "Players", "Close"}},
	{"Workspace", workspace, {"Parent", "Name", "ClassName", "ChildRemoved", "DescendantAdded", "Gravity", "CurrentCamera", "Raycast", "GetServerTimeNow", "DistributedGameTime", "Terrain", "FilteringEnabled", "StreamingEnabled"}},
	{"Folder", folder, {"Parent", "Name", "ClassName", "ChildRemoved", "DescendantAdded", "IsPropertyModified", "GetChildren", "Destroy", "WaitForChild", "GetDescendants", "FindFirstAncestor", "GetAttributes", "SetAttribute", "GetTags", "AddTag", "HasTag", "GetFullName", "Archivable", "ClearAllChildren", "IsAncestorOf", "GetPropertyChangedSignal", "GetAttributeChangedSignal"}},
	{"HttpService", game:GetService("HttpService"), {"Parent", "Name", "ClassName", "ChildRemoved", "DescendantAdded", "GetAsync", "PostAsync", "RequestAsync", "JSONEncode", "JSONDecode", "GenerateGUID", "UrlEncode", "GetSecret"}},
	{"RunService", game:GetService("RunService"), {"Parent", "Name", "ClassName", "ChildRemoved", "DescendantAdded", "IsStudio", "IsClient", "IsServer", "IsRunning", "IsEdit", "IsRunMode", "Heartbeat", "RenderStepped", "Stepped", "PreRender", "PreAnimation", "PostSimulation", "BindToRenderStep", "UnbindFromRenderStep", "SetRobloxGuiFocused"}},
}
for _, entry in objects do
	local label, obj, members = entry[1], entry[2], entry[3]
	for _, name in members do
		T(label .. "." .. name, function()
			local v = obj[name]
			if type(v) == "function" then
				local s, l, n, a, va = debug.info(v, "slnaf")
				return "function", s, l, n, a, va, v == obj[name], debug.info(v, "f") == v
			end
			local t = typeof(v)
			if t == "RBXScriptSignal" then return t, tostring(v), v == obj[name], rawequal(v, obj[name]) end
			if t == "Instance" then return t, v.ClassName end
			return t
		end)
	end
end
T("Folder:IsPropertyModified('Name')", function() return folder:IsPropertyModified("Name") end)
T("Folder:IsPropertyModified('Nope')", function() return folder:IsPropertyModified("Nope") end)
T("Folder:IsPropertyModified()", function() return folder:IsPropertyModified() end)
T("Folder.IsPropertyModified()", function() return folder.IsPropertyModified() end)
T("Folder.IsPropertyModified(1)", function() return folder.IsPropertyModified(1) end)
T("Folder:GetChildren() n", function() return #folder:GetChildren() end)
T("Folder.GetChildren()", function() return folder.GetChildren() end)
T("Folder:WaitForChild('x', 0.01)", function() return folder:WaitForChild("x", 0.01) end)
T("Folder:Destroy() ret", function() return Instance.new("Folder"):Destroy() end)
T("Folder.Destroy()", function() return folder.Destroy() end)
T("Frame.Size = UDim2", function() frame.Size = UDim2.new(0, 155, 0, 258) return frame.Size end)
T("Frame.Position = UDim2", function() frame.Position = UDim2.new(0, 0, 0, 0) return frame.Position end)
T("Frame.Size = bad", function() frame.Size = 5 end)
T("Frame.Parent = gui", function() frame.Parent = gui return frame.Parent == gui end)
T("Path2D.Parent = frame", function() path.Parent = frame return path.Parent == frame end)
T("Path2D parent gui", function() local p = Instance.new("Path2D") p.Parent = gui return p.Parent == gui end)
T("Path2D parent folder", function() local p = Instance.new("Path2D") p.Parent = folder return p.Parent == folder end)
T("gui:Destroy() then Frame.Parent", function() local g = Instance.new("ScreenGui") local f = Instance.new("Frame") f.Parent = g g:Destroy() return f.Parent, f.Name end)
T("tostring frame/gui/path", function() return tostring(frame), tostring(gui), tostring(path), tostring(folder) end)
T("typeof game/workspace", function() return typeof(game), typeof(workspace), tostring(game) ~= nil, tostring(workspace) end)
T("game == game", function() return game == game, game == workspace.Parent, workspace.Parent == game end)
T("game:GetService alias", function() return game:GetService("Workspace") == workspace, game.Workspace == workspace, game:FindService("Workspace") == workspace end)
T("game.Parent/Name types", function() return typeof(game.Parent), type(game.Name) end)
T("Instance.new args", function() return Instance.new("Folder", workspace).Parent == workspace end)
T("Instance.new extra arg", function() return Instance.new("Folder", nil, 5).Parent end)
T("Instance.new(Folder, 5)", function() return Instance.new("Folder", 5) end)
return table.concat(out, "\n")
