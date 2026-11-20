"""World.avatar caches its O(instances) scans; the cached answers must equal the uncached scans after any sequence of the changes
the protocol can make (instances are created with their class, parent and UserId; classes never change; removals, property updates
and reparenting of ordinary instances happen)."""
import random
import unittest

from world_replication import World

CLASSES = ['Player', 'Players', 'Model', 'Workspace', 'Humanoid', 'Part', 'Other']


def schema():
    return {'classes': [{'name': name, 'properties': []} for name in CLASSES], 'properties': [], 'names': [], 'strings': []}


class NoCache(dict):
    """A cache that never remembers anything: forces the original full scans."""
    def __setitem__(self, key, value): pass
    def get(self, key, default=None): return default


class AvatarCacheTests(unittest.TestCase):
    def test_cached_avatar_matches_uncached_scans_through_random_changes(self):
        rng = random.Random(5)
        cached = World(schema())
        reference = World(schema())
        reference.instances = cached.instances       # same data, different caching
        reference._avatar_cache = NoCache()
        next_key = [1]
        keys = []

        def add(class_name, parent=None, **properties):
            key = (1, next_key[0]); next_key[0] += 1
            cached.instances[key] = {'class': CLASSES.index(class_name), 'parent': parent, 'properties': dict(properties)}
            keys.append(key)
            return key

        workspace = add('Workspace', None, StreamingEnabled=False)
        players = add('Players')
        for step in range(3000):
            action = rng.randrange(9)
            if action == 0:
                add('Player', players, UserId=rng.choice([7, 7, 8]), Character=rng.choice([None] + keys[-3:]))
            elif action == 1:
                model = add('Model', rng.choice([workspace, players, None]))
                add('Humanoid', model, Health=rng.choice([100, 0, 50]))
                add('Part', model, Name=b'HumanoidRootPart', CFrame={'position': [1.0, 2.0, 3.0]}, Anchored=False)
            elif action == 2 and keys:
                cached.instances.pop(rng.choice(keys), None)
            elif action == 3 and keys:  # reparenting, except the instances avatar() looks for (their parent/class are fixed at creation)
                key = rng.choice(keys)
                inst = cached.instances.get(key)
                if inst and CLASSES[inst['class']] in ('Model', 'Part', 'Other', 'Players'):
                    inst['parent'] = rng.choice(keys + [None])
            elif action == 4 and keys:  # property updates that the real protocol can send after creation
                inst = cached.instances.get(rng.choice(keys))
                if inst: inst['properties']['Character'] = rng.choice(keys + [None])
            elif action == 5 and keys:
                inst = cached.instances.get(rng.choice(keys))
                if inst: inst['properties']['Health'] = rng.choice([0, 25, 100])
            elif action == 6:
                add('Workspace', None, StreamingEnabled=rng.choice([True, False]))
            elif action == 7 and keys:
                inst = cached.instances.get(rng.choice(keys))
                if inst: inst['properties']['PrimaryPart'] = rng.choice(keys + [None])
            else:
                add('Humanoid', rng.choice(keys))
            for user_id in (7, 8):
                self.assertEqual(repr(cached.avatar(user_id)), repr(reference.avatar(user_id)), (step, user_id))


if __name__ == '__main__':
    unittest.main()
