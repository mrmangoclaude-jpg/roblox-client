local zero = UDim.new()
assert(zero.Scale == 0 and zero.Offset == 0)

local first = UDim.new(0.5, 10.9)
assert(first.Scale == 0.5 and first.Offset == 10)
assert(first + UDim.new(0.25, 5) == UDim.new(0.75, 15))
assert(first - UDim.new(0.25, 5) == UDim.new(0.25, 5))
assert(tostring(first) == "0.5, 10")
assert(tostring(UDim.new(1, 0)) == "1, 0")

local a = UDim2.new(0.5, 10, 1, 20)
assert(a.X == a.Width and a.Y == a.Height)
assert(a.X.Scale == 0.5 and a.X.Offset == 10)
assert(a.Y.Scale == 1 and a.Y.Offset == 20)
assert(UDim2.fromScale(0.25, 0.75) == UDim2.new(0.25, 0, 0.75, 0))
assert(UDim2.fromOffset(40, 60) == UDim2.new(0, 40, 0, 60))
assert(UDim2.new(UDim.new(0.5, 10), UDim.new(1, 20)) == a)

local b = UDim2.new(0.25, 4, 0, 8)
assert(a + b == UDim2.new(0.75, 14, 1, 28))
assert(a - b == UDim2.new(0.25, 6, 1, 12))
assert(a:Lerp(b, 0.5) == UDim2.new(0.375, 7, 0.5, 14))
assert(tostring(a) == "{0.5, 10}, {1, 20}")

assert(not pcall(function() UDim.new(0 / 0, 0) end))
assert(not pcall(function() UDim.new(0, math.huge) end))
assert(not pcall(function() UDim2.fromScale(0, 0 / 0) end))
assert(not pcall(function() UDim2.fromOffset(0, 1e20) end))
assert(not pcall(function() return a + UDim.new() end))

-- Lerp computes scale in float32: this midpoint lands just above the f32 tie
-- and rounds up (Studio-verified bit-exact), unlike naive double math which
-- hits the exact tie and rounds to even.
local la = UDim2.new(0.2168044, 31, 0.193200797, 7)
local lb = UDim2.new(0.561694264, 187, 0.780333221, 167)
local lr = la:Lerp(lb, 0.5)
assert(lr.X.Scale == 0.38924932479858398)
assert(lr.Y.Scale == 0.48676702380180359)
assert(lr.X.Offset == 109 and lr.Y.Offset == 87)

return "UDim bindings passed"
