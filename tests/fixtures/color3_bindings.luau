-- Run with a host that calls install_color3_bindings before source execution.
local function near(a, b, epsilon)
    return math.abs(a - b) <= (epsilon or 1e-6)
end

local red = Color3.new(1, 0, 0)
assert(typeof(red) == "Color3")
assert(red.R == 1 and red.G == 0 and red.B == 0)
assert(tostring(red) == "1, 0, 0")
assert(red == Color3.fromRGB(255, 0, 0))
assert(red ~= Color3.new(1, 0, 0.001))
assert(Color3.new() == Color3.new(0, 0, 0))
assert(Color3.new(2, -1, 0.5).R == 2)
local scaled = Color3.fromRGB(510, -255, 128)
assert(scaled.R == 2 and scaled.G == -1 and near(scaled.B, 128 / 255))

local orange = Color3.fromHex("#Fa0")
assert(orange == Color3.fromHex("ffaa00"))
assert(orange:ToHex() == "ffaa00")
local roundTrip = Color3.fromHex(orange:ToHex())
assert(roundTrip == orange)

local green = Color3.fromHSV(1 / 3, 1, 1)
assert(near(green.R, 0) and near(green.G, 1) and near(green.B, 0))
local h, s, v = green:ToHSV()
assert(near(h, 1 / 3) and near(s, 1) and near(v, 1))
local redHue, redSat, redValue = red:ToHSV()
assert(redHue == 1 and redSat == 1 and redValue == 1)

local middle = Color3.new(0, 0, 0):Lerp(Color3.new(1, 1, 1), 0.5)
assert(middle == Color3.new(0.5, 0.5, 0.5))
assert(middle:ToHex() == "808080")

assert(not pcall(Color3.fromHex, "#gg0000"))
assert(not pcall(Color3.fromHex, "abcd"))
assert(not pcall(Color3.new, 0 / 0, 0, 0))
assert(not pcall(function() red.R = 0 end))

-- ToHSV components are float32 (Studio-verified bit-exact). 191/255 rounds to
-- the f32 value below, not the double 0.7490196078431373.
local blue = Color3.fromRGB(64, 128, 255)
local bh, bs, bv = blue:ToHSV()
assert(bh == 0.6108202338218689 and bs == 0.74901962280273438 and bv == 1)
local warm = Color3.fromRGB(255, 128, 64)
local _, ws, wv = warm:ToHSV()
assert(ws == 0.74901962280273438 and wv == 1)

-- The whole conversion runs in float32; computing in double then rounding once
-- at the end diverges in the last ULP for channels like 123/255 (Studio-verified).
local mixed = Color3.fromRGB(123, 45, 67)
local mh, ms, mv = mixed:ToHSV()
assert(mh == 0.95299148559570312 and ms == 0.63414627313613892 and mv == 0.48235294222831726)

return true
