local out = {}
local function rec(name, fn)
    local ok, a = pcall(fn)
    out[#out+1] = name .. "\t" .. (ok and ("ok:" .. tostring(a)) or ("err:" .. tostring(a)))
end
local cpn = Path2DControlPoint.new
local function mk(parent)
    local q = Instance.new("Path2D")
    q:SetControlPoints({cpn(UDim2.fromOffset(0,0)), cpn(UDim2.fromOffset(10,10)), cpn(UDim2.fromOffset(20,0))})
    if parent then q.Parent = parent end
    return q
end
local fr = Instance.new("Frame"); fr.Size = UDim2.fromOffset(100, 50)
local q = mk(fr)
rec("Frame Update 1", function() q:UpdateControlPoint(1, cpn(UDim2.fromOffset(1,1))); return tostring(q:GetControlPoint(1).Position) end)
rec("Frame Update 2", function() q:UpdateControlPoint(2, cpn(UDim2.fromOffset(2,2))); return tostring(q:GetControlPoint(2).Position) end)
rec("Frame Update 3", function() q:UpdateControlPoint(3, cpn(UDim2.fromOffset(3,3))); return tostring(q:GetControlPoint(3).Position) end)
rec("Frame Update 9", function() q:UpdateControlPoint(9, cpn(UDim2.fromOffset(3,3))) end)
rec("Frame Remove 3", function() q:RemoveControlPoint(3); return #q:GetControlPoints() end)
rec("Frame Remove 1 (2 left)", function() q:RemoveControlPoint(1); return #q:GetControlPoints() end)
rec("Frame Remove 1 (1 left)", function() q:RemoveControlPoint(1); return #q:GetControlPoints() end)
local q2 = mk(fr)
rec("Frame2 Remove 3 of 3", function() q2:RemoveControlPoint(3); return #q2:GetControlPoints() end)
local q3 = mk(nil)
rec("nil Update 1", function() q3:UpdateControlPoint(1, cpn(UDim2.fromOffset(1,1))) end)
rec("nil Remove 3", function() q3:RemoveControlPoint(3) end)
rec("nil Remove 1", function() q3:RemoveControlPoint(1) end)
local q4 = mk(fr)
rec("Frame Insert 4", function() q4:InsertControlPoint(4, cpn(UDim2.fromOffset(5,5))); return #q4:GetControlPoints() end)
rec("Frame Insert 5 (n=4)", function() q4:InsertControlPoint(5, cpn(UDim2.fromOffset(5,5))); return #q4:GetControlPoints() end)
rec("Frame Insert 7 (n=5)", function() q4:InsertControlPoint(7, cpn(UDim2.fromOffset(5,5))) end)
rec("Frame Insert -1", function() q4:InsertControlPoint(-1, cpn(UDim2.fromOffset(5,5))) end)
fr:Destroy()
return table.concat(out, "\n")
