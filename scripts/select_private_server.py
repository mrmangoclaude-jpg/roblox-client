#!/usr/bin/env python3
"""Resolve the user-provided Roblox server invite stored in the private directory."""
import json
from pathlib import Path
import re
from urllib.parse import parse_qs, urlsplit

from roblox_session import ROOT, RobloxSession, SessionError
from join_allocation import write_private


def resolve_invite(url, *, state_root=None, cookie=None, archive_previous=True):
    """Resolve and verify a Roblox private-server share link for one profile root."""
    state_root = Path(state_root) if state_root is not None else ROOT
    parsed = urlsplit(url)
    query = parse_qs(parsed.query)
    codes = query.get('code', [])
    if (parsed.scheme != 'https' or parsed.hostname != 'www.roblox.com'
            or parsed.path not in ('/share', '/share-links') or query.get('type') != ['Server']
            or len(codes) != 1 or not re.fullmatch(r'[a-fA-F0-9]{32}', codes[0])):
        raise SessionError('Expected a Roblox server share link')
    session = RobloxSession(cookie=cookie)
    reply = session.request('apis.roblox.com', '/sharelinks/v1/resolve-link', 'POST',
                            {'linkId': codes[0], 'linkType': 'Server'}, csrf_retry=True)
    if reply['http_status'] != 200 or reply['challenge_present'] or not isinstance(reply['data'], dict):
        raise SessionError('Roblox did not resolve the private server invite')
    invite = reply['data'].get('privateServerInviteData')
    if not isinstance(invite, dict) or invite.get('status') != 'Valid':
        raise SessionError('Private server invite is not valid for this account')
    place = invite.get('placeId')
    if (type(place) is not int or not 1 <= place < 2**53
            or not isinstance(invite.get('linkCode'), str) or not invite['linkCode']
            or any(type(invite.get(k)) is not int or invite[k] <= 0 for k in ('ownerUserId', 'privateServerId'))):
        raise SessionError('Private server invite has an unsupported structure')
    details = session.request('games.roblox.com', '/v1/games/multiget-place-details?placeIds=%d' % place)
    rows = details['data']
    if details['http_status'] != 200 or not isinstance(rows, list) or len(rows) != 1 or rows[0].get('isPlayable') is not True:
        raise SessionError('Private server place is not playable by this account')
    target = {'place_id': place, 'universe_id': invite.get('universeId'),
              'selection': 'user_selected_private_server', 'is_playable': True,
              'display_name': rows[0].get('name'), 'private_server_invite_resolved': True}
    out_dir = state_root / 'outputs/gamejoin'
    secrets_dir = state_root / 'secrets'
    out_dir.mkdir(parents=True, exist_ok=True)
    secrets_dir.mkdir(parents=True, exist_ok=True)
    current = out_dir / 'target-selection.json'
    if archive_previous and current.exists():
        previous = json.loads(current.read_text())
        archive = current.with_name('target-selection-%s.json' % previous['place_id'])
        archive.write_text(json.dumps(previous, indent=2) + '\n')
    write_private(secrets_dir / 'private-server-target.json', invite)
    current.write_text(json.dumps(target, indent=2) + '\n')
    return target


def main():
    url = json.loads((ROOT / 'secrets/private-server-link.json').read_text())['url']
    target = resolve_invite(url, state_root=ROOT)
    print(json.dumps(target, indent=2))
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except Exception as error:
        print(json.dumps({'error_type': type(error).__name__}))
        raise SystemExit(1)
