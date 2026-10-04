"""Prepare store metadata only after anonymous artifact and label validation."""
import argparse
import json
from pathlib import Path
import urllib.request

from candidate import BASE, registry, write, previous_package
from versions import require_upgrade


def publish(candidate, destination):
    provenance = json.loads(candidate.read_text())
    repo = provenance['repository']
    channel = provenance['channel']
    version = provenance['version']
    previous = previous_package(repo, channel)
    require_upgrade(version, previous['version'] if previous else None)
    image = f'ghcr.io/{repo.lower()}/nocturne-{channel}-' + '{arch}'
    digests = {}
    for arch in provenance['platforms']:
        hass_arch = 'aarch64' if arch == 'arm64' else arch
        name = image.replace('{arch}', hass_arch).removeprefix('ghcr.io/')
        digests[hass_arch] = registry(name, version, arch, labels={
            'io.hass.version': version, 'io.hass.arch': hass_arch})
    config = json.loads((BASE / 'shared/app-spec.json').read_text())
    port = 8448 if channel == 'stable' else 8449
    config.update(name='Nocturne ' + channel.title(), version=version,
                  slug='nocturne_local' if channel == 'stable' else 'nocturne_latest',
                  description='Nocturne ' + provenance['upstream_tag'] + ' · setup assistant',
                  url='https://github.com/' + repo, image=image,
                  arch=list(digests), panel_title='Nocturne ' + channel.title())
    config['ports'] = {'8448/tcp': port}
    config['ports_description'] = {'8448/tcp': 'Nocturne HTTPS'}
    config['options']['public_url'] = 'https://homeassistant.local:' + str(port)
    provenance.update(image=image + ':' + version, digests=digests)
    folder = destination / channel
    write(folder / 'config.json', config)
    write(folder / 'provenance.json', provenance)
    catalogs = BASE / 'shared/rootfs/opt/nocturne-ha/locales'
    for path in catalogs.glob('*.json'):
        text = json.loads(path.read_text(encoding='utf-8'))
        translated = {'configuration': {
            'public_url': {'name': text['address_label'], 'description': text['domain_help']},
            'certificate': {'name': text['certificate_label'], 'description': text['certificate_help']},
            'private_key': {'name': text['key_label'], 'description': text['certificate_help']},
            'gateway_auth': {'name': text['gateway_label'], 'description': text['finish_help']},
            'skip_gateway_check': {'name': text['skip_gateway_label'], 'description': text['skip_gateway_help']},
            'language': {'name': text['language'], 'description': text['intro']},
        }, 'network': {'8448/TCP': text['address_label']}}
        write(folder / 'translations' / path.name, translated)
    for filename in ('README.md', 'DOCS.md'):
        (folder / filename).write_text(
            f'# Nocturne {channel.title()}\n\n'
            f'Package {version}; Nocturne source {provenance["commit"]}.\n\n'
            f'Open the Home Assistant web interface for multilingual setup help.\n\n'
            f'[Setup guide](https://github.com/{repo}/blob/main/docs/SETUP.en.md) · '
            f'[Source]({provenance["links"]["source_url"]})\n', encoding='utf-8')
    change_link = provenance['links']['release_url']
    changes = (f'[Nocturne release notes]({change_link})' if change_link else
               f'Main is a source snapshot. [Nocturne commit history](https://github.com/nightscout/nocturne/commits/{provenance["commit"]}/)')
    (folder / 'CHANGELOG.md').write_text(
        f'# Nocturne {channel.title()} — HA package {version}\n\n'
        f'Nocturne version/source: `{provenance["upstream_tag"]}`.\n\n'
        f'Published architectures: {", ".join(digests)}. Both use the same Nocturne source.\n\n'
        f'{changes}\n\n'
        f'- [Exact Nocturne source]({provenance["links"]["source_url"]})\n'
        f'- [HA wrapper source]({provenance["links"]["wrapper_url"]})\n'
        f'- [Upstream image build]({provenance["links"]["build_url"]})\n'
        f'- [Package provenance and image digests](provenance.json)\n\n'
        'HA package and Nocturne version numbers are separate. Publication requires native '
        'runtime, setup and recovery tests and anonymous registry verification.\n', encoding='utf-8')
    (destination / 'repository.yaml').write_text(
        'name: Nocturne Home Assistant (experimental)\nurl: https://github.com/' + repo
        + '\nmaintainer: ' + repo.split('/')[0] + '\n', encoding='utf-8')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--candidate', type=Path, required=True)
    parser.add_argument('--destination', type=Path, required=True)
    args = parser.parse_args()
    publish(args.candidate, args.destination)
