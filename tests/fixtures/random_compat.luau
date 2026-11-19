-- Pure, authored standalone Random tests. No services, network, imported code,
-- scene mutation, authentication program, or protection checks.
-- Fixed outputs below are copied from independently recorded Studio
-- 0.742.0.7421053 controls in the user's former runtime tests. Current Roblox
-- build 0.745 compatibility is UNVERIFIED. See random_historical_vectors.json.
local assertions = 0
local function check(condition, label)
    assertions += 1
    assert(condition, label)
end
local seeds = {{["label"]="zero",["seed"]=0,["numbers"]={0.5514556904749074,0.01723102436113014,0.883376920906403,0.9209483679665256}},{["label"]="positive-quarter",["seed"]=0.25,["numbers"]={0.5514556904749074,0.01723102436113014,0.883376920906403,0.9209483679665256}},{["label"]="positive-three-quarters",["seed"]=0.75,["numbers"]={0.5514556904749074,0.01723102436113014,0.883376920906403,0.9209483679665256}},{["label"]="one",["seed"]=1,["numbers"]={0.9484344206192203,0.061285879733742145,0.8770159548057006,0.6984932786048916}},{["label"]="positive-one-three-quarters",["seed"]=1.75,["numbers"]={0.9484344206192203,0.061285879733742145,0.8770159548057006,0.6984932786048916}},{["label"]="negative-quarter",["seed"]=-0.25,["numbers"]={0.5514556904749074,0.01723102436113014,0.883376920906403,0.9209483679665256}},{["label"]="negative-three-quarters",["seed"]=-0.75,["numbers"]={0.5514556904749074,0.01723102436113014,0.883376920906403,0.9209483679665256}},{["label"]="negative-one",["seed"]=-1,["numbers"]={0.0037155688242635435,0.5469862230236278,0.31011551315193603,0.5443109026319798}},{["label"]="negative-one-quarter",["seed"]=-1.25,["numbers"]={0.0037155688242635435,0.5469862230236278,0.31011551315193603,0.5443109026319798}},{["label"]="negative-one-three-quarters",["seed"]=-1.75,["numbers"]={0.0037155688242635435,0.5469862230236278,0.31011551315193603,0.5443109026319798}},{["label"]="negative-two",["seed"]=-2,["numbers"]={0.9766369130815973,0.6173916878197894,0.5019386789533096,0.7806833452844162}},{["label"]="positive-forty-two-half",["seed"]=42.5,["numbers"]={0.22072993115387124,0.9202737237894263,0.7635500080741559,0.5235603366883349}},{["label"]="negative-forty-two-half",["seed"]=-42.5,["numbers"]={0.13885844540895598,0.4496349811440639,0.7745333818195859,0.4082046828944817}},{["label"]="million-fraction",["seed"]=1000000.75,["numbers"]={0.4545717109838331,0.06537546251227422,0.7428979595793128,0.6837510338642543}},{["label"]="negative-million-fraction",["seed"]=-1000000.75,["numbers"]={0.7696582471097058,0.420047645962636,0.31548294872276733,0.9046310434191615}},{["label"]="signed-max",["seed"]=2147483647,["numbers"]={0.6803952727960796,0.7599827847261793,0.011592871688384401,0.08401268338130742}},{["label"]="signed-min",["seed"]=-2147483648,["numbers"]={0.002662719010272965,0.6873605829064052,0.595303471172911,0.29923470495292354}},{["label"]="unsigned-max",["seed"]=4294967295,["numbers"]={0.9906837952347612,0.9833116691437964,0.7992487394249163,0.05650629323610304}},{["label"]="near-max-3",["seed"]=9007199254740988,["numbers"]={0.15980045599158857,0.9212434928913923,0.4012914271825144,0.35750333175083376}},{["label"]="near-max-1",["seed"]=9007199254740990,["numbers"]={0.600971696577853,0.583554546890247,0.9713513708390459,0.7789389115388827}},{["label"]="max-exact",["seed"]=9007199254740991,["numbers"]={0.027684032073451197,0.09103798432822455,0.9869885996197573,0.487454948835134}},{["label"]="near-min-plus-3",["seed"]=-9007199254740988,["numbers"]={0.19178410559565975,0.25962517927986245,0.7492945731233133,0.8531836566862555}},{["label"]="near-min-plus-1",["seed"]=-9007199254740990,["numbers"]={0.6944554666007504,0.30210731332737817,0.02962928026874041,0.6420054477561171}},{["label"]="min-exact",["seed"]=-9007199254740991,["numbers"]={0.22788703655698744,0.9425859688069043,0.06775640206431996,0.2257033002980914}}}
for _, row in seeds do
    local subject = Random.new(row.seed)
    for index, expected in row.numbers do
        check(subject:NextNumber() == expected, "historical seed " .. row.label .. " draw " .. index)
    end
end
local integers = {{["minimum"]=7,["values"]={7,7,7,7,7,7,7,7,7,7,7,7,7,7,7,7},["seed"]=0,["tail"]={0.6941444896236435,0.3394915449549059,0.7528818489719791,0.8235461316294559},["maximum"]=7,["label"]="one"},{["minimum"]=-1,["values"]={0,0,-1,-1,-1,0,0,0,0,0,-1,0,0,-1,0,-1},["seed"]=0,["tail"]={0.6941444896236435,0.3394915449549059,0.7528818489719791,0.8235461316294559},["maximum"]=0,["label"]="two"},{["minimum"]=-2147483648,["values"]={221000506,-2073476963,1646591336,1807959472,1465248155,616687757,-1363535948,-1150362766,833844232,-689378567,1086119270,1389620053,-1783820802,892142889,-743460785,2036460974},["seed"]=0,["tail"]={0.034179637844052355,0.6278496826673415,0.4394172495532442,0.12368996066351659},["maximum"]=2147483646,["label"]="full-minus-one"},{["minimum"]=-2147483648,["values"]={221000507,-2073476962,1646591337,1807959473,1465248156,616687758,-1363535947,-1150362765,833844233,-689378566,1086119271,1389620054,-1783820801,892142890,-743460784,2036460975},["seed"]=0,["tail"]={0.034179637844052355,0.6278496826673415,0.4394172495532442,0.12368996066351659},["maximum"]=2147483647,["label"]="full"},{["minimum"]=2147483647,["values"]={221000507,-2073476962,1646591337,1807959473,1465248156,616687758,-1363535947,-1150362765,833844233,-689378566,1086119271,1389620054,-1783820801,892142890,-743460784,2036460975},["seed"]=0,["tail"]={0.034179637844052355,0.6278496826673415,0.4394172495532442,0.12368996066351659},["maximum"]=-2147483648,["label"]="full-reversed"},{["minimum"]=7,["values"]={7,7,7,7,7,7,7,7,7,7,7,7,7,7,7,7},["seed"]=1,["tail"]={0.6677645558245757,0.16052582957389097,0.681655643871908,0.4219438454588578},["maximum"]=7,["label"]="one"},{["minimum"]=-1,["values"]={0,0,-1,-1,0,0,-1,0,-1,-1,0,-1,-1,-1,0,0},["seed"]=1,["tail"]={0.6677645558245757,0.16052582957389097,0.681655643871908,0.4219438454588578},["maximum"]=0,["label"]="two"},{["minimum"]=-2147483648,["values"]={1926011169,-1884262800,1619271194,852522139,-578176269,-1805118660,-911899530,1582594724,720543279,-1458030461,780205048,-335248633,-125032046,-1887636472,-1612991268,92329281},["seed"]=1,["tail"]={0.973324272981462,0.00994352402372335,0.6988344412022772,0.5257279731697247},["maximum"]=2147483646,["label"]="full-minus-one"},{["minimum"]=-2147483648,["values"]={1926011170,-1884262799,1619271195,852522140,-578176268,-1805118659,-911899529,1582594725,720543280,-1458030460,780205049,-335248632,-125032045,-1887636471,-1612991267,92329282},["seed"]=1,["tail"]={0.973324272981462,0.00994352402372335,0.6988344412022772,0.5257279731697247},["maximum"]=2147483647,["label"]="full"},{["minimum"]=2147483647,["values"]={1926011170,-1884262799,1619271195,852522140,-578176268,-1805118659,-911899529,1582594725,720543280,-1458030460,780205049,-335248632,-125032045,-1887636471,-1612991267,92329282},["seed"]=1,["tail"]={0.973324272981462,0.00994352402372335,0.6988344412022772,0.5257279731697247},["maximum"]=-2147483648,["label"]="full-reversed"}}
for _, row in integers do
    local subject, reversed = Random.new(row.seed), Random.new(row.seed)
    for index, expected in row.values do
        check(subject:NextInteger(row.minimum, row.maximum) == expected, "historical integer " .. row.label .. index)
        check(reversed:NextInteger(row.maximum, row.minimum) == expected, "historical reversed " .. row.label .. index)
    end
    for index, expected in row.tail do
        check(subject:NextNumber() == expected, "historical integer tail " .. row.label .. index)
        check(reversed:NextNumber() == expected, "historical reversed tail " .. row.label .. index)
    end
end
local mixed = {{["seed"]=2,["steps"]={{["minimum"]=-5,["maximum"]=9,["value"]=-2,["kind"]="integer",["tail"]={0.979155023879744,0.7584412376915272,0.4441316602872157}},{["minimum"]=-2147483648,["maximum"]=2147483647,["value"]=2057955157,["kind"]="integer",["tail"]={0.7584412376915272,0.4441316602872157,0.5642798268597854}},{["minimum"]=7,["maximum"]=7,["value"]=7,["kind"]="integer",["tail"]={0.05177339510024554,0.15532075367964143,0.16125809530827212}},{["minimum"]=-2147483648,["maximum"]=2147483646,["value"]=-1925118611,["kind"]="integer",["tail"]={0.15532075367964143,0.16125809530827212,0.26199205374126555}},{["value"]=0.15532075367964143,["kind"]="number",["tail"]={0.16125809530827212,0.26199205374126555,0.48044414289546616}},{["minimum"]=-2147483648,["maximum"]=2147483645,["value"]=276079752,["kind"]="integer",["tail"]={0.6306100767481276,0.2907778896070067,0.4358649343439481}},{["minimum"]=2147483647,["maximum"]=-2147483647,["value"]=560966008,["kind"]="integer",["tail"]={0.2907778896070067,0.4358649343439481,0.7002606375695919}},{["minimum"]=0,["maximum"]=2147483647,["value"]=562623651,["kind"]="integer",["tail"]={0.48044414289546616,0.0375059408684878,0.2511461339193072}},{["minimum"]=-1073741824.75,["maximum"]=1073741824.75,["value"]=-449301061,["kind"]="integer",["tail"]={0.4358649343439481,0.7002606375695919,0.8136375072065616}}}},{["seed"]=3,["steps"]={{["minimum"]=-5,["maximum"]=9,["value"]=-4,["kind"]="integer",["tail"]={0.08055106903906832,0.6619159774736423,0.10111153088180305}},{["minimum"]=-2147483648,["maximum"]=2147483647,["value"]=-1801519441,["kind"]="integer",["tail"]={0.6619159774736423,0.10111153088180305,0.9689549443373163}},{["minimum"]=7,["maximum"]=7,["value"]=7,["kind"]="integer",["tail"]={0.3858381217955416,0.22627412180907827,0.4310749047363538}},{["minimum"]=-2147483648,["maximum"]=2147483646,["value"]=-490321535,["kind"]="integer",["tail"]={0.22627412180907827,0.4310749047363538,0.04872144868503403}},{["value"]=0.22627412180907827,["kind"]="number",["tail"]={0.4310749047363538,0.04872144868503403,0.577477156856614}},{["minimum"]=-2147483648,["maximum"]=2147483645,["value"]=2014146147,["kind"]="integer",["tail"]={0.7159633495451592,0.8862192817145775,0.1734465073276025}},{["minimum"]=2147483647,["maximum"]=-2147483647,["value"]=927555523,["kind"]="integer",["tail"]={0.8862192817145775,0.1734465073276025,0.4292730840912306}},{["minimum"]=0,["maximum"]=2147483647,["value"]=104628514,["kind"]="integer",["tail"]={0.577477156856614,0.2248932284241185,0.11156738792296338}},{["minimum"]=-1073741824.75,["maximum"]=1073741824.75,["value"]=829399592,["kind"]="integer",["tail"]={0.1734465073276025,0.4292730840912306,0.4809563227723277}}}}}
for _, row in mixed do
    local subject = Random.new(row.seed)
    for index, step in row.steps do
        local actual = if step.kind == "number" then subject:NextNumber()
            else subject:NextInteger(step.minimum, step.maximum)
        check(actual == step.value, "historical mixed draw " .. index)
        local probe = subject:Clone()
        for tailIndex, expected in step.tail do
            check(probe:NextNumber() == expected, "historical mixed state " .. index .. ":" .. tailIndex)
        end
    end
end
-- Independently stated normalization contracts, including negative fractions.
for _, pair in {{-0.75,0},{-1.75,-1},{42.5,42},{-1000000.75,-1000000}} do
    local a,b = Random.new(pair[1]),Random.new(pair[2])
    for index=1,8 do check(a:NextNumber()==b:NextNumber(), "seed truncation " .. index) end
end
for _, range in {{-9.8,-3.9,-9,-3},{9.8,3.9,3,9},{-0.9,0.9,0,0},
    {-2147483648.75,2147483647.75,-2147483648,2147483647}} do
    local a,b = Random.new(7),Random.new(7)
    for index=1,8 do
        check(a:NextInteger(range[1],range[2])==b:NextInteger(range[3],range[4]), "bound truncation " .. index)
    end
    check(a:NextNumber()==b:NextNumber(), "bound truncation state")
end
-- Clone state must be independent even if one stream consumes its suffix first.
local original = Random.new(314159)
original:NextNumber()
local clone = original:Clone()
local suffix = {}
for i=1,16 do suffix[i]=original:NextInteger(-2147483648,2147483647) end
for i=1,16 do check(clone:NextInteger(-2147483648,2147483647)==suffix[i], "clone independence " .. i) end
local invalid = {
    function(r) r:NextNumber(1) end,
    function(r) r:NextInteger(1) end,
}
for _, operation in invalid do
    local subject = Random.new(11)
    local probe = subject:Clone()
    check(not pcall(operation,subject), "invalid argument rejected")
    check(subject:NextNumber()==probe:NextNumber(), "invalid argument preserves state")
end
-- Studio accepts NaN, infinite, huge and numeric-string seeds; only a non-number is rejected.
for _, seed in {true,{}} do
    check(not pcall(Random.new,seed), "invalid seed rejected")
end
check(not pcall(function() Random.new(1).NextNumber({}) end), "wrong receiver rejected")
check(not pcall(function() Random.new(1).NextInteger({},1,2) end), "wrong receiver integer rejected")
check(not pcall(function() Random.new(1).Clone({}) end), "wrong receiver clone rejected")
check(table.isfrozen(Random), "constructor table readonly")
check(getmetatable(Random.new(1))=="Random", "metatable protected")
for _, subject in {Random.new(),Random.new(nil)} do
    local draw = subject:NextNumber()
    check(draw==draw and draw>=0 and draw<=1, "host entropy seed gives finite draw")
end
local low, high = -1e308, 1e308
local large = Random.new(1):NextNumber(low,high)
check(large==large and large>=low and large<=high, "finite wide floating bounds")
return assertions
