local out = {}
local function rec(name, fn)
    local ok, a = pcall(fn)
    out[#out+1] = name .. "\t" .. (ok and ("ok:" .. tostring(a)) or ("err:" .. tostring(a)))
end
local cpn = Path2DControlPoint.new
local function pts(n) local t = {} for i = 1, n do t[i] = cpn(UDim2.fromOffset(i * 10, i * 5)) end return t end
local function pos(q, i) return tostring(q:GetControlPoint(i).Position) end
local sg = Instance.new("ScreenGui"); local fr = Instance.new("Frame"); fr.Size = UDim2.fromOffset(158, 267)
fr.Parent = sg
local q = Instance.new("Path2D"); q.Parent = fr
q:SetControlPoints(pts(6))
rec("A n after set", function() return #q:GetControlPoints() end)
rec("A Update 1", function() q:UpdateControlPoint(1, cpn(UDim2.fromOffset(99,99))); return pos(q,1) end)
rec("A n/pos1 after Update", function() return #q:GetControlPoints() .. " " .. pos(q,1) end)
rec("A Insert 1", function() q:InsertControlPoint(1, cpn(UDim2.fromOffset(77,77))) end)
rec("A n/pos1 after Insert", function() return #q:GetControlPoints() .. " " .. pos(q,1) end)
rec("A Remove 1", function() q:RemoveControlPoint(1) end)
rec("A n/pos1 after Remove", function() return #q:GetControlPoints() .. " " .. pos(q,1) end)
rec("A len after all", function() return q:GetLength() end)
local q2 = Instance.new("Path2D"); q2:SetControlPoints(pts(3)); q2.Parent = fr
rec("B Update 2", function() q2:UpdateControlPoint(2, cpn(UDim2.fromOffset(99,99))) end)
rec("B n/pos2 after Update", function() return #q2:GetControlPoints() .. " " .. pos(q2,2) end)
rec("B Remove 2", function() q2:RemoveControlPoint(2) end)
rec("B n after Remove", function() return #q2:GetControlPoints() end)
rec("B Insert 4 (n=3)", function() q2:InsertControlPoint(4, cpn(UDim2.fromOffset(55,55))) end)
rec("B n after Insert4", function() return #q2:GetControlPoints() end)
local q3 = Instance.new("Path2D"); q3.Parent = fr
rec("C ins1", function() q3:InsertControlPoint(1, cpn(UDim2.fromOffset(10,10))); return #q3:GetControlPoints() end)
rec("C ins2 at 2", function() q3:InsertControlPoint(2, cpn(UDim2.fromOffset(20,20))); return #q3:GetControlPoints() end)
rec("C ins3 at 1", function() q3:InsertControlPoint(1, cpn(UDim2.fromOffset(5,5))); return #q3:GetControlPoints() .. " " .. pos(q3,1) end)
rec("C update 2", function() q3:UpdateControlPoint(2, cpn(UDim2.fromOffset(15,15))); return pos(q3,2) end)
rec("C remove 1", function() q3:RemoveControlPoint(1); return #q3:GetControlPoints() .. " " .. pos(q3,1) end)
rec("C remove last", function() q3:RemoveControlPoint(2); q3:RemoveControlPoint(1); return #q3:GetControlPoints() end)
rec("C len", function() return q3:GetLength() end)
local q4 = Instance.new("Path2D"); q4.Parent = fr
q4:InsertControlPoint(1, cpn(UDim2.fromOffset(1,1)))
q4:SetControlPoints(pts(4))
rec("D set after insert -> update 1", function() q4:UpdateControlPoint(1, cpn(UDim2.fromOffset(9,9))); return pos(q4,1) end)
rec("D remove 4", function() q4:RemoveControlPoint(4); return #q4:GetControlPoints() end)
sg:Destroy()
return table.concat(out, "\n")
