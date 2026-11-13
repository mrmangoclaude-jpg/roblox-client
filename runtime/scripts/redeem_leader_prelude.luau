-- Non-destructive leader bridge prepended in-memory before the leader script.
-- Captures outgoing code redemptions (via Codes UI Confirm or Net RF:InvokeServer)
-- and broadcasts them once to the local Rove multi-session coordinator HTTP API.

do
    local _ROVE_API_URL = __ROVE_API_URL__
    local _ROVE_TOKEN = __ROVE_TOKEN__
    local _ROVE_SENDER = __ROVE_SENDER__
    local _ROVE_HTTP = game:GetService("HttpService")
    local _ROVE_PLAYERS = game:GetService("Players")
    local _roveSent = {}

    local function _roveBroadcast(code)
        if type(code) ~= "string" then return end
        code = code:gsub("^%s+", ""):gsub("%s+$", "")
        if #code < 2 or #code > 50 or code == "PROBE" then return end
        local now = os.clock()
        if _roveSent[code] and (now - _roveSent[code]) < 10 then return end
        _roveSent[code] = now
        if type(request) ~= "function" then return end
        task.spawn(function()
            pcall(request, {
                Url = _ROVE_API_URL,
                Method = "POST",
                Headers = {
                    ["Content-Type"] = "application/json",
                    ["X-Rove-Token"] = _ROVE_TOKEN,
                },
                Body = _ROVE_HTTP:JSONEncode({
                    code = code,
                    sender = _ROVE_SENDER,
                }),
            })
        end)
    end

    local function _roveReadCodesTextBox()
        local lp = _ROVE_PLAYERS.LocalPlayer
        local pg = lp and lp:FindFirstChild("PlayerGui")
        local codes = pg and pg:FindFirstChild("Codes")
        if not codes then return nil end
        local inner = codes:FindFirstChild("Codes") or codes
        local redeem = inner:FindFirstChild("CodeRedeem")
        local tb = redeem and redeem:FindFirstChild("TextBox")
        if tb and tb:IsA("TextBox") and #tb.Text > 0 then
            return tb.Text
        end
        for _, d in ipairs(codes:GetDescendants()) do
            if d:IsA("TextBox") and #d.Text > 0 then
                return d.Text
            end
        end
        return nil
    end

    local _origGetConns = getconnections
    if type(_origGetConns) == "function" then
        getconnections = function(signal, ...)
            local conns = _origGetConns(signal, ...)
            if type(conns) ~= "table" then return conns end
            local lp = _ROVE_PLAYERS.LocalPlayer
            local pg = lp and lp:FindFirstChild("PlayerGui")
            if not (pg and pg:FindFirstChild("Codes")) then return conns end
            local wrapped = {}
            for i, conn in ipairs(conns) do
                local okFire, origFire = pcall(function() return conn.Fire end)
                local okFn, origFn = pcall(function() return conn.Function end)
                if (okFire and type(origFire) == "function") or (okFn and type(origFn) == "function") then
                    local proxy = {}
                    if okFire and type(origFire) == "function" then
                        proxy.Fire = function(_, ...)
                            local text = _roveReadCodesTextBox()
                            if text then _roveBroadcast(text) end
                            return origFire(conn, ...)
                        end
                    end
                    if okFn and type(origFn) == "function" then
                        proxy.Function = function(...)
                            local text = _roveReadCodesTextBox()
                            if text then _roveBroadcast(text) end
                            return origFn(...)
                        end
                    end
                    setmetatable(proxy, { __index = conn, __newindex = conn })
                    wrapped[i] = proxy
                else
                    wrapped[i] = conn
                end
            end
            return wrapped
        end
        if type(debug) == "table" and debug.getconnections == _origGetConns then
            debug.getconnections = getconnections
        end
    end

    if type(hookmetamethod) == "function" and type(getnamecallmethod) == "function" then
        local _origNC
        _origNC = hookmetamethod(game, "__namecall", function(self, ...)
            local method = getnamecallmethod()
            if method == "InvokeServer" and select("#", ...) == 1 then
                local candidate = select(1, ...)
                if type(candidate) == "string" and #candidate >= 2 and #candidate <= 50 and candidate:match("^[%w_%-]+$") then
                    local okRF, isRF = pcall(function() return self:IsA("RemoteFunction") and self.Name:match("^RF/") ~= nil end)
                    if okRF and isRF then
                        _roveBroadcast(candidate)
                    end
                end
            end
            return _origNC(self, ...)
        end)
    end
end
