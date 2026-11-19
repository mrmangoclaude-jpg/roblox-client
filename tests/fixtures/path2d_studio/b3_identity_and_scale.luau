local out = {}
local function rec(name, fn)
    local ok, a = pcall(fn)
    out[#out+1] = name .. "\t" .. (ok and ("ok:" .. tostring(a)) or ("err:" .. tostring(a)))
end
local cpn = Path2DControlPoint.new
local fr = Instance.new("Frame"); fr.Size = UDim2.fromOffset(100, 50)
local p = Instance.new("Path2D"); p.Parent = fr
local a = cpn(UDim2.fromOffset(0,0)); local b = cpn(UDim2.fromOffset(100,0))
p:SetControlPoints({a, b})
rec("get same obj twice", function() return tostring(p:GetControlPoint(1) == p:GetControlPoint(1)) end)
rec("get == original a", function() return tostring(p:GetControlPoint(1) == a) end)
rec("mutate a after set", function() a.Position = UDim2.fromOffset(0,40); return tostring(p:GetControlPoint(1).Position) end)
rec("mutate returned point", function() local g = p:GetControlPoint(2); g.Position = UDim2.fromOffset(100,30); return tostring(p:GetControlPoint(2).Position) end)
rec("array element identity", function() local t = p:GetControlPoints(); local t2 = p:GetControlPoints(); return tostring(t[1] == t2[1]) end)
rec("length after mutation", function() return p:GetLength() end)
rec("set Position 5", function() a.Position = 5 end)
rec("set Position nil", function() a.Position = nil end)
rec("set Position str", function() a.Position = "x" end)
rec("set LeftTangent ok", function() a.LeftTangent = UDim2.fromOffset(3,4); return tostring(a.LeftTangent) end)
rec("set RightTangent ok", function() a.RightTangent = UDim2.new(0.5,1,0.25,2); return tostring(a.RightTangent) end)
local function sc(label, make)
    rec("scale set parent " .. label, function()
        local q = Instance.new("Path2D"); local par = make(); if par then q.Parent = par end
        q:SetControlPoints({cpn(UDim2.fromScale(0.5,0.5)), cpn(UDim2.fromScale(1,1))})
        local n = #q:GetControlPoints(); q:Destroy(); return "ok n=" .. n
    end)
end
sc("nil", function() return nil end)
sc("Frame", function() return Instance.new("Frame") end)
sc("ScreenGui", function() return Instance.new("ScreenGui") end)
sc("Folder", function() return Instance.new("Folder") end)
local function ins(label, make, pt)
    rec(label, function()
        local q = Instance.new("Path2D"); local par = make(); if par then q.Parent = par end
        q:InsertControlPoint(1, pt); local n = #q:GetControlPoints(); q:Destroy(); return "ok n=" .. n
    end)
end
ins("insert offset nil parent", function() return nil end, cpn(UDim2.fromOffset(5,5)))
ins("insert scale nil parent", function() return nil end, cpn(UDim2.fromScale(0.5,0.5)))
ins("insert scale Folder parent", function() return Instance.new("Folder") end, cpn(UDim2.fromScale(0.5,0.5)))
ins("insert scale Frame parent", function() return Instance.new("Frame") end, cpn(UDim2.fromScale(0.5,0.5)))
rec("offset nil-parent curve", function()
    local q = Instance.new("Path2D")
    q:SetControlPoints({cpn(UDim2.fromOffset(0,0)), cpn(UDim2.fromOffset(10,10))})
    local r = {tostring(q:GetLength()), tostring(q:GetPositionOnCurve(0.5)), tostring(q:GetTangentOnCurve(0.5)), tostring(q:GetBoundingRect())}
    q:Destroy(); return table.concat(r, " | ")
end)
rec("offset Folder-parent curve", function()
    local q = Instance.new("Path2D"); q.Parent = Instance.new("Folder")
    q:SetControlPoints({cpn(UDim2.fromOffset(0,0)), cpn(UDim2.fromOffset(10,10))})
    local r = {tostring(q:GetLength()), tostring(q:GetPositionOnCurve(0.5))}
    q:Destroy(); return table.concat(r, " | ")
end)
rec("scale curve nil parent via Frame later", function()
    local q = Instance.new("Path2D")
    q:SetControlPoints({cpn(UDim2.fromOffset(0,0)), cpn(UDim2.fromOffset(10,10))})
    local f = Instance.new("Frame"); f.Size = UDim2.fromOffset(200, 100); q.Parent = f
    return tostring(q:GetPositionOnCurve(0.5))
end)
rec("closed 2 points segs/len", function()
    local f = Instance.new("Frame"); f.Size = UDim2.fromOffset(200, 100)
    local q = Instance.new("Path2D"); q.Parent = f; q.Closed = true
    q:SetControlPoints({cpn(UDim2.fromOffset(0,0)), cpn(UDim2.fromOffset(100,0))})
    return tostring(q:GetLength())
end)
rec("empty bounding thickness 0", function()
    local f = Instance.new("Frame"); local q = Instance.new("Path2D"); q.Parent = f; q.Thickness = 0
    return tostring(q:GetBoundingRect())
end)
rec("single point bounding", function()
    local f = Instance.new("Frame"); f.Size = UDim2.fromOffset(200, 100)
    local q = Instance.new("Path2D"); q.Parent = f
    q:SetControlPoints({cpn(UDim2.fromOffset(10,20))})
    return tostring(q:GetBoundingRect()) .. " len=" .. tostring(q:GetLength())
end)
fr:Destroy()
return table.concat(out, "\n")
