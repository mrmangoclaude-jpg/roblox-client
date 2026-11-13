-- Lightweight follower redeemer for multi-client coordinator broadcasts.
-- Exposes _G.ROVE_REDEEM(code) without duplicating UI, AI solver, or webhooks.

local Players = game:GetService("Players")
local HttpService = game:GetService("HttpService")

local CLICK_SIGNALS = { "Activated", "MouseButton1Click", "MouseButton1Up", "MouseButton1Down" }
local _getconns = getconnections or (debug and debug.getconnections)
local _cachedRF = nil
local _cachedTB = nil
local _cachedBtn = nil

local function findCodesTextBox()
    if _cachedTB and _cachedTB.Parent then return _cachedTB end
    local pg = Players.LocalPlayer and Players.LocalPlayer:FindFirstChild("PlayerGui")
    if not pg then return nil end
    local codes = pg:FindFirstChild("Codes")
    if not codes then return nil end
    local inner = codes:FindFirstChild("Codes") or codes
    local redeem = inner:FindFirstChild("CodeRedeem")
    local tb = redeem and redeem:FindFirstChild("TextBox")
    if tb and tb:IsA("TextBox") then
        _cachedTB = tb
        return tb
    end
    for _, d in ipairs(codes:GetDescendants()) do
        if d:IsA("TextBox") then
            _cachedTB = d
            return d
        end
    end
    return nil
end

local function findConfirmButton()
    if _cachedBtn and _cachedBtn.Parent then return _cachedBtn end
    local pg = Players.LocalPlayer and Players.LocalPlayer:FindFirstChild("PlayerGui")
    if not pg then return nil end
    local codes = pg:FindFirstChild("Codes")
    if not codes then return nil end
    local root = codes:FindFirstChild("Codes") or codes
    local confirm = root:FindFirstChild("Confirm")
    if confirm then
        if confirm:IsA("GuiButton") then
            _cachedBtn = confirm
            return confirm
        end
        for _, d in ipairs(confirm:GetDescendants()) do
            if d:IsA("GuiButton") then
                _cachedBtn = d
                return d
            end
        end
        _cachedBtn = confirm
        return confirm
    end
    for _, d in ipairs(root:GetDescendants()) do
        if d:IsA("GuiButton") and not string.find(string.lower(d.Name), "close") then
            _cachedBtn = d
            return d
        end
    end
    return nil
end

local function fireButtonHandlers(btn)
    if not _getconns then return 0 end
    local total = 0
    for _, signalName in ipairs(CLICK_SIGNALS) do
        local okSig, signal = pcall(function() return btn[signalName] end)
        if okSig and signal then
            local okConns, conns = pcall(_getconns, signal)
            if okConns and conns then
                for _, conn in ipairs(conns) do
                    local fired = false
                    if type(conn.Fire) == "function" then
                        fired = pcall(function() conn:Fire() end)
                    end
                    if not fired and type(conn.Function) == "function" then
                        fired = pcall(conn.Function)
                    end
                    if fired then total += 1 end
                end
            end
        end
        if total > 0 and (signalName == "Activated" or signalName == "MouseButton1Click") then
            break
        end
    end
    return total
end

function _G.ROVE_REDEEM(code)
    if type(code) ~= "string" then
        return false, "code must be a string"
    end
    code = code:gsub("^%s+", ""):gsub("%s+$", "")
    if #code == 0 or #code > 50 then
        return false, "invalid code length"
    end

    if _cachedRF and _cachedRF.Parent then
        local results = table.pack(pcall(function() return _cachedRF:InvokeServer(code) end))
        if results[1] then
            local val = results[2]
            if type(val) == "table" then
                local okEnc, enc = pcall(HttpService.JSONEncode, HttpService, val)
                val = okEnc and enc or tostring(val)
            end
            return true, "rf:" .. tostring(val)
        end
        _cachedRF = nil
    end

    local btn = findConfirmButton()
    if not btn then
        return false, "Confirm button not found"
    end
    local tb = findCodesTextBox()
    if tb and tb.Text ~= code then
        tb.Text = code
    end
    local fired = fireButtonHandlers(btn)
    if fired <= 0 then
        return false, "no firable Confirm handlers"
    end
    return true, "ui:" .. code
end

return "follower_ready"
