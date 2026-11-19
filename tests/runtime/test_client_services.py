"""Offline Luau integration tests for local Debris and Players queries."""
import copy
import json
import os
from pathlib import Path
import sys
import time
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
import local_runtime
import persistent_runtime
if os.environ.get('LUAU_TEST_HOST'):
    local_runtime.RUST_HOST = Path(os.environ['LUAU_TEST_HOST'])
    if not local_runtime.RUST_HOST.is_file():
        raise RuntimeError('LUAU_TEST_HOST must point to a completed build')
    persistent_runtime.RUST_HOST = local_runtime.RUST_HOST

SNAPSHOT = json.loads((ROOT / 'tests/fixtures/world_snapshot.json').read_text())
DEBRIS_ID = 'scope:debris-fixture'


def with_debris_service():
    snapshot = copy.deepcopy(SNAPSHOT)
    snapshot['class_parents']['Debris'] = 'Instance'
    snapshot['nodes'].append({
        'id': DEBRIS_ID, 'class_name': 'Debris', 'name': 'Debris',
        'parent': None, 'properties': {},
    })
    snapshot['services']['Debris'] = DEBRIS_ID
    return snapshot


def with_negative_id_player():
    snapshot = with_debris_service()
    snapshot['nodes'].extend([
        {
            'id': 'scope:character-negative', 'class_name': 'Model',
            'name': 'NegativeIdCharacter', 'parent': 'scope:workspace',
            'properties': {},
        },
        {
            'id': 'scope:player-negative', 'class_name': 'Player',
            'name': 'NegativeIdPlayer', 'parent': 'scope:players',
            'properties': {
                'UserId': -42,
                'Character': {'$ref': 'scope:character-negative'},
            },
        },
    ])
    return snapshot


@unittest.skipUnless(local_runtime.RUST_HOST.is_file(), 'build the persistent Luau host first')
class ClientServiceTests(unittest.TestCase):
    def setUp(self):
        self.host = persistent_runtime.PersistentLuauHost(with_debris_service())
        self.addCleanup(self.host.close)

    def execute(self, source, timeout_ms=1000):
        result = self.host.call({'op': 'execute', 'source': source, 'timeout_ms': timeout_ms})
        mutations = list(result.get('mutations', []))
        if result.get('completed'):
            result['mutations'] = mutations
            return result
        job_id = result.get('job_id')
        if type(job_id) is not int:
            result['mutations'] = mutations
            return result
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            poll = self.host.call({'op': 'poll', 'timeout_ms': 100})
            mutations.extend(poll.get('mutations', []))
            for completed in poll.get('completed_jobs', []):
                if completed.get('job_id') == job_id:
                    mutations.extend(completed.get('mutations', []))
                    completed['mutations'] = mutations
                    return completed
        result['mutations'] = mutations
        return result

    def test_stats_service_is_local_and_preserves_identity(self):
        result = self.execute('''
local before=game:FindService("Stats")
local stats=game:GetService("Stats")
local hasUnmeasuredValue=pcall(function()return stats.DataReceiveKbps end)
return before==nil,stats.ClassName,stats.Parent==game,
       stats==game:GetService("Stats"),stats==game:FindService("Stats"),
       hasUnmeasuredValue
''')
        self.assertTrue(result['ok'], result)
        self.assertEqual(result['values'], [True, 'Stats', True, True, True, False])

    def test_game_and_workspace_global_aliases_share_identity(self):
        result = self.execute('''
return game == Game, workspace == Workspace,
       typeof(Game), typeof(Workspace),
       Game.Name == game.Name, Game.ClassName,
       workspace == game:GetService("Workspace"),
       Game == workspace.Parent, Game.Parent == nil,
       tostring(Game) == tostring(game)
''')
        self.assertTrue(result['ok'], result)
        self.assertEqual(result['values'], [True, True, 'Instance', 'Instance', True, 'DataModel', True, True, True, True])

    def test_encoding_service_base64_uses_buffers(self):
        result = self.execute('''
assert(game:FindService("EncodingService")==nil)
local encoding=game:GetService("EncodingService")
assert(encoding==game:FindService("EncodingService") and encoding.Parent==game)
assert(encoding.ClassName=="EncodingService")
local binary=string.char(0,255,254).."hello"
local input=buffer.fromstring(binary)
local encoded=encoding:Base64Encode(input)
assert(buffer.tostring(encoded)=="AP/+aGVsbG8=" and buffer.tostring(input)==binary)
assert(buffer.tostring(encoding:Base64Decode(encoded))==binary)
assert(buffer.len(encoding:Base64Decode(encoding:Base64Encode(buffer.create(0))))==0)
assert(not pcall(encoding.Base64Encode,encoding,binary))
assert(not pcall(encoding.Base64Encode,workspace,input))
assert(not pcall(encoding.Base64Decode,encoding,buffer.fromstring("a?!=")))
return true
''')
        self.assertTrue(result['ok'], result)
        self.assertEqual(result['values'], [True])

    def test_encoding_service_hashes_match_binary_vectors(self):
        result = self.execute('''
local encoding=game:GetService("EncodingService")
local cases={
    {Enum.HashAlgorithm.Blake2b,32,
        "0e5751c026e543b2e8ab2eb06099daa1d1e5df47778f7787faab45cdf12fe3a8",
        "37ab512cd01adbac3140abde00cbd8f77d5bcfb02f295ca884042cd0d81c0e2f"},
    {Enum.HashAlgorithm.Blake3,32,
        "af1349b9f5f9a1a6a0404dea36dcc9499bcb25c9adc112b7cc9a93cae41f3262",
        "0bc94efd42851bf801345789bf903713ec9c890b8a809d1f5a04024a0a680f4a"},
    {Enum.HashAlgorithm.Md5,16,
        "d41d8cd98f00b204e9800998ecf8427e",
        "136654676b4aed7ed5dffff8ad58ef36"},
    {Enum.HashAlgorithm.Sha1,20,
        "da39a3ee5e6b4b0d3255bfef95601890afd80709",
        "c51b034207816f9c4ba679d1602f3e838dedb377"},
    {Enum.HashAlgorithm.Sha256,32,
        "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
        "a8b2beedb2cb53792d92eb492452bf399e8ba7fa5659c1c916b0ec7410e06cc5"},
}
local bytes={}
for i=0,255 do bytes[i+1]=string.char(i) end
local payload=string.rep(table.concat(bytes),9)
local function hex(value)
    return (value:gsub(".",function(c) return string.format("%02x",string.byte(c)) end))
end
for index,case in cases do
    local algorithm,length,empty,binary=unpack(case)
    assert(algorithm.Value==index-1 and algorithm.EnumType==Enum.HashAlgorithm)
    for _,vector in {{"",empty},{payload,binary}} do
        local input,expected=unpack(vector)
        local inputBuffer=buffer.fromstring(input)
        local digest=encoding:ComputeBufferHash(inputBuffer,algorithm)
        local digestString=encoding:ComputeStringHash(input,algorithm)
        assert(typeof(digest)=="buffer" and buffer.len(digest)==length)
        assert(type(digestString)=="string" and #digestString==length)
        assert(hex(digestString)==expected and buffer.tostring(digest)==digestString)
        buffer.writeu8(digest,0,(buffer.readu8(digest,0)+1)%256)
        assert(buffer.tostring(inputBuffer)==input)
        assert(buffer.tostring(encoding:ComputeBufferHash(inputBuffer,algorithm))==digestString)
    end
end
local sha256=Enum.HashAlgorithm.Sha256
local input=buffer.fromstring("test")
assert(not pcall(encoding.ComputeBufferHash,encoding,"test",sha256))
assert(not pcall(encoding.ComputeStringHash,encoding,input,sha256))
assert(not pcall(encoding.ComputeStringHash,encoding,123,sha256))
assert(not pcall(encoding.ComputeStringHash,encoding,"test",Enum.CompressionAlgorithm.Zstd))
assert(not pcall(encoding.ComputeBufferHash,encoding,input,"Sha256"))
assert(not pcall(encoding.ComputeBufferHash,workspace,input,sha256))
return true
''')
        self.assertTrue(result['ok'], result)
        self.assertEqual(result['values'], [True])

    def test_encoding_service_zstd_interoperates_and_checks_frame_sizes(self):
        import base64
        import zstandard
        data = b'Luau\x00fixture\xff' * 64
        fixture = base64.b64encode(zstandard.ZstdCompressor().compress(data)).decode()
        unknown = base64.b64encode(
            zstandard.ZstdCompressor(write_content_size=False).compress(data)).decode()
        oversized = base64.b64encode(
            zstandard.ZstdCompressor().compress(b'x' * (32 * 1024 * 1024 + 1))).decode()
        result = self.execute(f'''
local fixture=buffer.fromstring(base64.decode("{fixture}"))
local unknown=buffer.fromstring(base64.decode("{unknown}"))
local oversized=buffer.fromstring(base64.decode("{oversized}"))
''' + '''
local encoding=game:GetService("EncodingService")
local zstd=Enum.CompressionAlgorithm.Zstd
assert(zstd.Name=="Zstd" and zstd.Value==0)
local source=string.rep("Luau"..string.char(0).."fixture"..string.char(255),64)
assert(encoding:GetDecompressedBufferSize(fixture,zstd)==#source)
assert(buffer.tostring(encoding:DecompressBuffer(fixture,zstd))==source)
local raw=buffer.fromstring(source)
for _,level in {-7,1,22} do
    local compressed=encoding:CompressBuffer(raw,zstd,level)
    assert(zstddecompress(buffer.tostring(compressed))==source)
end
local empty=encoding:CompressBuffer(buffer.create(0),zstd)
assert(encoding:GetDecompressedBufferSize(empty,zstd)==0)
assert(buffer.len(encoding:DecompressBuffer(empty,zstd))==0)
local invalid=buffer.fromstring("bad frame")
local truncated=buffer.fromstring(buffer.tostring(fixture):sub(1,-2))
for _,data in {invalid,unknown,oversized} do
    assert(encoding:GetDecompressedBufferSize(data,zstd)==nil)
    assert(not pcall(encoding.DecompressBuffer,encoding,data,zstd))
end
assert(not pcall(encoding.DecompressBuffer,encoding,truncated,zstd))
assert(not pcall(encoding.CompressBuffer,encoding,raw,Enum.Axis.X))
for _,level in {-8,1.5,23,math.huge} do
    assert(not pcall(encoding.CompressBuffer,encoding,raw,zstd,level))
end
return true
''')
        self.assertTrue(result['ok'], result)
        self.assertEqual(result['values'], [True])

    def test_players_queries_return_replicated_service_members_and_identity(self):
        result = self.execute('''
local players = game:GetService("Players")
local current = players.LocalPlayer
local character = current.Character
local listed = players:GetPlayers()
local legacy = players:getPlayers()
return #listed, listed[1] == current, #legacy, legacy[1] == current,
       players:GetPlayerByUserId(current.UserId) == current,
       players:GetPlayerByUserId(987654321) == nil,
       players:GetPlayerFromCharacter(character) == current,
       players:GetPlayerFromCharacter(workspace) == nil
''')
        self.assertTrue(result['ok'], result)
        self.assertEqual(result['values'], [1, True, 1, True, True, True, True, True])
        self.assertEqual(result['mutations'], [])

    def test_players_queries_support_negative_studio_user_ids(self):
        host = persistent_runtime.PersistentLuauHost(with_negative_id_player())
        self.addCleanup(host.close)
        result = host.call({'op': 'execute', 'source': '''
local players = game:GetService("Players")
local found = players:GetPlayerByUserId(-42)
return #players:GetPlayers(), found and found.Name,
       players:GetPlayerFromCharacter(found.Character) == found,
       players:GetPlayerByUserId(-43) == nil
''', 'timeout_ms': 1000})
        self.assertTrue(result['ok'], result)
        self.assertEqual(result['values'], [2, 'NegativeIdPlayer', True, True])

    def test_players_queries_follow_current_parent_and_character_references(self):
        result = self.execute('''
local players = game:GetService("Players")
local current = players.LocalPlayer
local character = current.Character
local before = #players:GetPlayers()
local by_id = players:GetPlayerByUserId(current.UserId)
current.Character = nil
return before, by_id == current, players:GetPlayerFromCharacter(character) == nil,
       players:GetPlayerFromCharacter(workspace.FixtureCharacter) == nil
''')
        self.assertTrue(result['ok'], result)
        self.assertEqual(result['values'], [1, True, True, True])

    def test_debris_add_item_is_non_yielding_uses_default_and_destroys_normally(self):
        result = self.execute('''
local debris = game:GetService("Debris")
local deferred = Instance.new("Part")
debris:AddItem(deferred)
local default_did_not_yield = deferred.Parent == nil
local part = Instance.new("Part")
part.Parent = workspace
local destroying = false
part.Destroying:Connect(function() destroying = true end)
local returned = debris:AddItem(part, 0.015)
local stayed = part.Parent == workspace

task.wait(0.06)
return returned == nil, default_did_not_yield, stayed, part.Parent == nil, destroying
''')
        self.assertTrue(result['ok'], result)
        self.assertEqual(result['values'], [True, True, True, True, True])
        self.assertEqual(result['mutations'][-1]['kind'], 'destroy')

    def test_services_interoperate_across_tags_tweens_players_and_debris(self):
        result = self.execute('''
local players = game:GetService("Players")
local localPlayer = players.LocalPlayer
local collection = game:GetService("CollectionService")
local debris = game:GetService("Debris")
local tweenService = game:GetService("TweenService")
local removedCount = 0
local removedInstance
collection:GetInstanceRemovedSignal("cleanup-target"):Connect(function(instance)
    removedCount += 1
    removedInstance = instance
end)
local part = Instance.new("Part")
part.Parent = workspace
part:AddTag("cleanup-target")
assert(collection:GetTagged("cleanup-target")[1] == part)
local info = TweenInfo.new(2.5, Enum.EasingStyle.Quad, Enum.EasingDirection.Out, 3, true, .25)
assert(info.Time == 2.5 and info.RepeatCount == 3 and info.Reverses)
assert(info.EasingStyle == Enum.EasingStyle.Quad and info.EasingDirection == Enum.EasingDirection.Out)
local eased = tweenService:GetValue(.25, info.EasingStyle, info.EasingDirection)
assert(math.abs(eased - .4375) < 1e-6)
debris:AddItem(part, .03)
task.wait(.09)
return players:GetPlayerByUserId(localPlayer.UserId) == localPlayer,
       players:GetPlayerFromCharacter(localPlayer.Character) == localPlayer,
       part.Parent == nil, #collection:GetTagged("cleanup-target"),
       removedCount, removedInstance == part, eased
''')
        self.assertTrue(result['ok'], result)
        self.assertEqual(result['values'], [True, True, True, 0, 1, True, 0.4375])
        self.assertEqual(result['mutations'][-1]['kind'], 'destroy')

    def test_debris_queue_survives_the_source_job_that_scheduled_it(self):
        first = self.execute('''
item = Instance.new("Part")
item.Parent = workspace
game:GetService("Debris"):AddItem(item, 0.03)
return item.Parent == workspace
''')
        self.assertTrue(first['ok'], first)
        self.assertEqual(first['values'], [True])
        second = self.execute('task.wait(0.09); return item.Parent == nil')
        self.assertTrue(second['ok'], second)
        self.assertEqual(second['values'], [True])

    def test_debris_cleanup_survives_task_cancellation(self):
        result = self.execute('''
local item = Instance.new("Part")
item.Parent = workspace
game:GetService("Debris"):AddItem(item, 0.03)
local unrelated = task.spawn(function() task.wait(10) end)
task.cancel(unrelated)
task.wait(0.09)
return item.Parent == nil
''')
        self.assertTrue(result['ok'], result)
        self.assertEqual(result['values'], [True])

    def test_debris_cap_destroys_oldest_queued_item(self):
        result = self.execute('''
local debris = game:GetService("Debris")
local item = Instance.new("Folder")
item.Parent = workspace
for _ = 1, 1001 do debris:AddItem(item, 1000) end
return item.Parent == nil
''', timeout_ms=2000)
        self.assertTrue(result['ok'], result)
        self.assertEqual(result['values'], [True])

    def test_invalid_debris_lifetimes_fail_without_an_unbounded_timer(self):
        result = self.execute('''
local debris = game:GetService("Debris")
local item = Instance.new("Folder")
local infinite = pcall(function() debris:AddItem(item, math.huge) end)
local not_number = pcall(function() debris:AddItem(item, "soon") end)
return infinite, not_number, item.Parent == nil
''')
        self.assertTrue(result['ok'], result)
        self.assertEqual(result['values'], [False, False, True])


if __name__ == '__main__':
    unittest.main()
