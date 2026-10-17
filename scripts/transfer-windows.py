"""Copy verified installer bytes from temporary GitHub download links into a draft.

No private-repository token is needed. Links expire; installer contents are intended
for this public mirror. This script never publishes a release or replaces assets.
"""
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
from urllib.parse import urlparse
from urllib.request import urlopen


def validate(tag, assets):
    if not re.fullmatch(r'v\d+\.\d+\.\d+', tag):
        raise ValueError('Expected a stable release version')
    version = tag[1:]
    expected = {'latest.yml', f'Loki-Setup-{version}-x64.exe',
                f'Loki-Setup-{version}-x64.exe.blockmap', f'Loki-Setup-{version}-x64.msi'}
    if len(assets) != 4 or {a['name'] for a in assets} != expected:
        raise ValueError('Exactly four Windows release files required')
    for asset in assets:
        url = urlparse(asset['url'])
        if url.scheme != 'https' or url.hostname != 'release-assets.githubusercontent.com' or url.username or url.password:
            raise ValueError('Expected temporary GitHub release-asset URL')
        if not re.fullmatch(r'[a-f0-9]{64}', asset['sha256']):
            raise ValueError('Expected SHA-256 digest')
        if type(asset['size']) is not int or not 0 < asset['size'] <= 250 * 1024 * 1024:
            raise ValueError('Invalid expected asset size')


def main():
    tag = os.environ['RELEASE_TAG']
    assets = json.loads(os.environ['ASSETS_JSON'])
    validate(tag, assets)
    draft = subprocess.check_output(['gh', 'release', 'view', tag, '--json', 'isDraft', '--jq', '.isDraft'], text=True).strip()
    if draft != 'true':
        raise ValueError('Target must already exist as a draft release')
    output = Path('transferred')
    output.mkdir(exist_ok=False)
    for asset in assets:
        target = output / asset['name']
        digest = hashlib.sha256()
        size = 0
        with urlopen(asset['url'], timeout=120) as response, target.open('wb') as file:
            while chunk := response.read(1024 * 1024):
                size += len(chunk)
                if size > asset['size']:
                    raise ValueError('Downloaded file exceeds expected size')
                digest.update(chunk)
                file.write(chunk)
        if size != asset['size'] or digest.hexdigest() != asset['sha256']:
            raise ValueError('Downloaded file differs from verified source')
        print(f'Verified {asset["name"]}: {size} bytes', flush=True)
    subprocess.run(['gh', 'release', 'upload', tag, *[str(output / a['name']) for a in assets]], check=True)
    print('Four verified assets transferred. Release remains draft.')


if __name__ == '__main__':
    main()
