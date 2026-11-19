local out = {}
local function rec(name, fn)
    local ok, a = pcall(fn)
    out[#out+1] = name .. "\t" .. (ok and ("ok:" .. tostring(a)) or ("err:" .. tostring(a)))
end
local cpn = Path2DControlPoint.new
local U = UDim2.fromOffset(1,2)
rec("eq 0 args", function() return tostring(cpn() == cpn()) end)
rec("eq 1 arg", function() return tostring(cpn(U) == cpn(U)) end)
rec("eq 3 args", function() return tostring(cpn(U,U,U) == cpn(U,U,U)) end)
rec("eq diff", function() return tostring(cpn(U) == cpn(UDim2.fromOffset(9,9))) end)
rec("eq alias", function() local x = cpn(U); local y = x; return tostring(x == y) end)
rec("rawequal fresh", function() return tostring(rawequal(cpn(U), cpn(U))) end)
rec("ne", function() return tostring(cpn(U) ~= cpn(U)) end)
local f = Instance.new("Frame"); f.Size = UDim2.fromOffset(100, 50)
local p = Instance.new("Path2D"); p.Parent = f
local a = cpn(UDim2.fromOffset(0,0)); local b = cpn(UDim2.fromOffset(100,0))
p:SetControlPoints({a, b})
local g = p:GetControlPoint(1)
rec("rawequal g a", function() return tostring(rawequal(g, a)) end)
rec("g == a", function() return tostring(g == a) end)
rec("a mutate -> a.Position", function() a.Position = UDim2.fromOffset(0,40); return tostring(a.Position) end)
rec("a mutate -> g.Position", function() return tostring(g.Position) end)
rec("a mutate -> path point", function() return tostring(p:GetControlPoint(1).Position) end)
rec("a mutate -> g == a now", function() return tostring(g == a) end)
rec("a mutate -> path == a now", function() return tostring(p:GetControlPoint(1) == a) end)
rec("g mutate -> path point", function() g.Position = UDim2.fromOffset(5,5); return tostring(p:GetControlPoint(1).Position) end)
rec("reset+length", function() p:SetControlPoints({a, b}); return tostring(p:GetLength()) .. " " .. tostring(p:GetControlPoint(1).Position) end)
local function methods(q, pt)
    local r = {}
    local function m(label, fn) local ok, e = pcall(fn); r[#r+1] = label .. "=" .. (ok and "ok" or ("E[" .. tostring(e):sub(1, 38) .. "]")) end
    m("GetCP", function() q:GetControlPoint(1) end)
    m("GetCPs", function() q:GetControlPoints() end)
    m("Update", function() q:UpdateControlPoint(1, pt) end)
    m("Remove", function() q:RemoveControlPoint(3) end)
    m("Insert", function() q:InsertControlPoint(1, pt) end)
    m("Len", function() q:GetLength() end)
    m("Pos", function() q:GetPositionOnCurve(0.5) end)
    m("Tan", function() q:GetTangentOnCurve(0.5) end)
    m("PosArc", function() q:GetPositionOnCurveArcLength(0.5) end)
    m("BR", function() q:GetBoundingRect() end)
    return table.concat(r, " ")
end
local kinds = {
    {"nil", function() return nil end}, {"Folder", function() return Instance.new("Folder") end},
    {"Frame", function() return Instance.new("Frame") end}, {"ScreenGui", function() return Instance.new("ScreenGui") end},
    {"TextLabel", function() return Instance.new("TextLabel") end},
}
for _, k in ipairs(kinds) do
    rec("matrix " .. k[1], function()
        local q = Instance.new("Path2D")
        q:SetControlPoints({cpn(UDim2.fromOffset(0,0)), cpn(UDim2.fromOffset(10,10)), cpn(UDim2.fromOffset(20,0))})
        local par = k[2](); if par then q.Parent = par end
        local s = methods(q, cpn(UDim2.fromOffset(1,1)))
        q:Destroy(); return s
    end)
end
rec("closed triangle", function()
    local fr = Instance.new("Frame"); fr.Size = UDim2.fromOffset(400, 500)
    local q = Instance.new("Path2D"); q.Parent = fr; q.Closed = true
    q:SetControlPoints({cpn(UDim2.fromOffset(0,0)), cpn(UDim2.fromOffset(300,0)), cpn(UDim2.fromOffset(300,400))})
    return tostring(q:GetLength()) .. " pos1=" .. tostring(q:GetPositionOnCurve(1)) .. " pos0.9=" .. tostring(q:GetPositionOnCurve(0.9)) .. " br=" .. tostring(q:GetBoundingRect())
end)
rec("open triangle", function()
    local fr = Instance.new("Frame"); fr.Size = UDim2.fromOffset(400, 500)
    local q = Instance.new("Path2D"); q.Parent = fr
    q:SetControlPoints({cpn(UDim2.fromOffset(0,0)), cpn(UDim2.fromOffset(300,0)), cpn(UDim2.fromOffset(300,400))})
    return tostring(q:GetLength())
end)
local fr2 = Instance.new("Frame"); fr2.Size = UDim2.fromOffset(100, 50)
local q2 = Instance.new("Path2D"); q2.Parent = fr2
q2:SetControlPoints({cpn(UDim2.fromOffset(10,0)), cpn(UDim2.fromOffset(20,0)), cpn(UDim2.fromOffset(30,0))})
for _, i in ipairs({0.4, 0.5, 1.4, 1.5, 2.5, 3.4, 3.5, -0.5}) do
    rec("GetCP(" .. i .. ")", function() return tostring(q2:GetControlPoint(i).Position) end)
end
fr2:Destroy(); f:Destroy()
return table.concat(out, "\n")
