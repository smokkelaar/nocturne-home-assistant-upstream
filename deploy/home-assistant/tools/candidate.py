"""Resolve paired upstream artifacts and assemble isolated build contexts."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import urllib.error
import urllib.request
from versions import require_upgrade

BASE = Path(__file__).resolve().parents[1]
UPSTREAM = 'nightscout/nocturne'
ACCEPT = ', '.join(['application/vnd.oci.image.index.v1+json',
                   'application/vnd.docker.distribution.manifest.list.v2+json',
                   'application/vnd.oci.image.manifest.v1+json',
                   'application/vnd.docker.distribution.manifest.v2+json'])


class UpstreamNotReady(Exception):
    pass


def fetch(url, headers=None):
    request = urllib.request.Request(url, headers={'User-Agent': 'nocturne-ha-publisher', **(headers or {})})
    with urllib.request.urlopen(request, timeout=30) as response:
        raw = response.read(10_000_001)
        if len(raw) > 10_000_000:
            raise ValueError('Metadata exceeds size limit')
        digest = 'sha256:' + hashlib.sha256(raw).hexdigest()
        advertised = response.headers.get('Docker-Content-Digest')
        if advertised and digest != advertised:
            raise ValueError('Registry digest mismatch')
        return json.loads(raw), digest


def github(path, repository=UPSTREAM):
    token = os.environ.get('GH_TOKEN')
    return fetch(f'https://api.github.com/repos/{repository}/{path}',
                 {'Authorization': 'Bearer ' + token} if token else {})[0]


def registry(repository, reference, arch, revision=None, labels=None):
    auth = fetch(f'https://ghcr.io/token?service=ghcr.io&scope=repository:{repository}:pull')[0]
    headers = {'Authorization': 'Bearer ' + auth['token'], 'Accept': ACCEPT}
    image, digest = fetch(f'https://ghcr.io/v2/{repository}/manifests/{reference}', headers)
    if 'manifests' in image:
        matches = [m for m in image['manifests'] if m.get('platform', {}).get('os') == 'linux'
                   and m['platform'].get('architecture') == arch]
        if len(matches) != 1:
            raise ValueError('Expected exactly one image for ' + arch)
        digest = matches[0]['digest']
        image, actual = fetch(f'https://ghcr.io/v2/{repository}/manifests/{digest}', headers)
        if actual != digest:
            raise ValueError('Child manifest digest mismatch')
    config_digest = image['config']['digest']
    config, actual = fetch(f'https://ghcr.io/v2/{repository}/blobs/{config_digest}', headers)
    if actual != config_digest or config.get('architecture') != arch or config.get('os') != 'linux':
        raise ValueError('Image platform/config mismatch')
    environment = dict(x.split('=', 1) for x in config.get('config', {}).get('Env', []) if '=' in x)
    label = config.get('config', {}).get('Labels', {}).get('org.opencontainers.image.revision')
    embedded = label or environment.get('GIT_COMMIT')
    if revision and embedded != revision:
        raise ValueError('API source revision mismatch')
    for key, expected in (labels or {}).items():
        if config.get('config', {}).get('Labels', {}).get(key) != expected:
            raise ValueError('HA label mismatch: ' + key)
    return digest


def paired_run(commit, branch=None):
    suffix = f'&branch={branch}' if branch else ''
    runs = github('actions/workflows/docker-publish.yml/runs?per_page=50&head_sha=' + commit + suffix)
    matching = [run for run in runs['workflow_runs'] if run.get('head_sha') == commit]
    for run in matching:
        if run.get('conclusion') != 'success':
            continue
        jobs = github(f"actions/runs/{run['id']}/jobs?per_page=100")['jobs']
        names = {j['name']: j['conclusion'] for j in jobs}
        if names.get('build-and-push') == 'success' or all(names.get(k) == 'success'
                for k in ('dotnet-images', 'web-image', 'report')):
            return run['id']
    if not matching or (matching[0].get('status') is not None and matching[0]['status'] != 'completed'):
        raise UpstreamNotReady('Upstream publication has not completed for ' + commit)
    raise ValueError('No complete paired upstream publishing run for ' + commit)


def recipe_hash():
    digest = hashlib.sha256()
    for path in sorted(BASE.rglob('*')):
        if path.is_file() and '__pycache__' not in path.parts:
            digest.update(path.relative_to(BASE).as_posix().encode())
            digest.update(path.read_bytes())
    return digest.hexdigest()


def links(commit, release, wrapper_repository, wrapper_commit, workflow_run):
    if not re.fullmatch(r'[0-9a-f]{40}', commit) or not re.fullmatch(r'[0-9a-f]{40}', wrapper_commit):
        raise ValueError('Source links require full commit SHAs')
    return {
        'source_url': f'https://github.com/{UPSTREAM}/tree/{commit}',
        'release_url': f'https://github.com/{UPSTREAM}/releases/tag/{release}' if release else None,
        'wrapper_url': f'https://github.com/{wrapper_repository}/tree/{wrapper_commit}/deploy/home-assistant',
        'build_url': f'https://github.com/{UPSTREAM}/actions/runs/{workflow_run}',
    }


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')


def previous_package(owner_repo, channel):
    try:
        return fetch(f'https://raw.githubusercontent.com/{owner_repo}/home-assistant/{channel}/config.json')[0]
    except urllib.error.HTTPError as error:
        if error.code != 404:
            raise
        return None


def baseline_for_arch(previous, arch):
    # A newly supported architecture has no previous image to restore from.
    # The workflow rehearses cold restore using the candidate itself instead.
    if not previous or arch not in previous['platforms']:
        return ''
    return previous['image'].replace('{arch}', 'aarch64' if arch == 'arm64' else arch)


def require_complete_pr_matrix(matrix, deferred, platforms):
    expected = {(channel, arch) for channel in ('stable', 'main') for arch in platforms}
    included = matrix.get('include', [])
    actual = {(item['channel'], item['arch']) for item in included}
    if deferred or actual != expected or len(included) != len(expected):
        missing = ', '.join(f'{channel}/{arch}' for channel, arch in sorted(expected - actual))
        pending = ', '.join(sorted({item['channel'] for item in deferred}))
        details = []
        if missing:
            details.append('missing ' + missing)
        if pending:
            details.append('upstream publication pending for ' + pending)
        raise ValueError('PR validation requires every Stable/Main image; ' + '; '.join(details))


def select(destination, owner_repo, version, wrapper_commit, platforms, force=False):
    if not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', owner_repo):
        raise ValueError('Invalid repository')
    require_upgrade(version)
    release = github('releases/latest')
    if release['draft'] or release['prerelease'] or not re.fullmatch(r'v[0-9]+\.[0-9]+\.[0-9]+', release['tag_name']):
        raise ValueError('Stable requires a regular published release')
    stable_commit = github('commits/' + release['tag_name'])['sha']
    # Resolve the branch first: a paginated run list can omit the current build.
    # paired_run below requires successful images for this exact source revision.
    # If its publisher is still running, leave the existing store intact and retry.
    main_commit = github('commits/main')['sha']
    recipe = recipe_hash()
    matrix = []
    deferred = []
    for channel, commit, tag in [('stable', stable_commit, release['tag_name'][1:]),
                                 ('main', main_commit, 'main-' + main_commit[:7])]:
        previous = None
        try:
            previous = fetch(f'https://raw.githubusercontent.com/{owner_repo}/home-assistant/{channel}/provenance.json')[0]
        except urllib.error.HTTPError as error:
            if error.code != 404:
                raise
        if not force and previous and previous['commit'] == commit and previous['recipe'] == recipe and previous['platforms'] == platforms:
            continue
        try:
            run_id = paired_run(commit, 'main' if channel == 'main' else None)
        except UpstreamNotReady as error:
            deferred.append({'channel': channel, 'commit': commit, 'reason': str(error)})
            print(f'::notice title=Upstream publication pending::{channel}: {error}; retry on the next scheduled run.')
            continue
        published = previous_package(owner_repo, channel)
        require_upgrade(version, published['version'] if published else None)
        refs = links(commit, release['tag_name'] if channel == 'stable' else None,
                     owner_repo, wrapper_commit, run_id)
        provenance = {'channel': channel, 'commit': commit, 'upstream_tag': tag,
                      'upstream_run': run_id, 'recipe': recipe, 'version': version,
                      'wrapper_commit': wrapper_commit, 'repository': owner_repo,
                      'platforms': platforms, 'links': refs,
                      'baseline_image': previous.get('image') if previous else None, 'images': {}}
        request = urllib.request.Request(f'https://raw.githubusercontent.com/{UPSTREAM}/{commit}/.github/workflows/docker-publish.yml', headers={'User-Agent': 'nocturne-ha-publisher'})
        with urllib.request.urlopen(request, timeout=30) as response:
            workflow = response.read(200_000).decode('utf-8')
        pnpm = re.search(r'PNPM_VERSION: [\"\']?([0-9]+\.[0-9]+\.[0-9]+)', workflow)
        if not pnpm:
            raise ValueError('Upstream must declare a pinned PNPM_VERSION')
        for arch in platforms:
            pins = {kind: registry(f'{UPSTREAM}/nocturne-{kind}', tag, arch,
                                  commit if kind == 'api' else None) for kind in ('api', 'web')}
            provenance['images'][arch] = pins
            context = destination / f'{channel}-{arch}'
            shutil.copytree(BASE / 'shared/rootfs', context / 'rootfs', dirs_exist_ok=True)
            shutil.copytree(BASE / 'shared/build', context / 'build', dirs_exist_ok=True)
            dockerfile = (BASE / 'shared/Dockerfile.in').read_text().replace('{{PNPM_VERSION}}', pnpm[1])
            for kind, pin in pins.items():
                dockerfile = re.sub(rf'FROM ghcr.io/nightscout/nocturne/nocturne-{kind}@sha256:[0-9a-f]{{64}}',
                                   f'FROM ghcr.io/{UPSTREAM}/nocturne-{kind}@{pin}', dockerfile)
            dockerfile = re.sub(r'ARG BUILD_VERSION=\S+', 'ARG BUILD_VERSION=' + version, dockerfile)
            dockerfile = re.sub(r'ARG BUILD_ARCH=\S+', 'ARG BUILD_ARCH=' + ('aarch64' if arch == 'arm64' else arch), dockerfile)
            dockerfile = dockerfile.replace('https://github.com/smokkelaar/nocturne-home-assistant',
                                            'https://github.com/' + owner_repo)
            (context / 'Dockerfile').write_text(dockerfile, encoding='utf-8')
            metadata = json.loads((context / 'rootfs/opt/nocturne-ha/version.json').read_text())
            metadata.update(app='0.2.0', package=version, nocturne=tag if channel == 'stable' else 'main@' + commit[:7],
                            source_commit=commit, base_commit=commit, channel=channel, links=refs,
                            name='Nocturne ' + channel.title(), default_public_url='https://homeassistant.local:' + ('8448' if channel == 'stable' else '8449'),
                            cookie_namespace='NocturneOfficial_' if channel == 'stable' else 'NocturneLatest_')
            write(context / 'rootfs/opt/nocturne-ha/version.json', metadata)
            matrix.append({'channel': channel, 'arch': arch,
                           'hass_arch': 'aarch64' if arch == 'arm64' else arch,
                           'runner': 'ubuntu-24.04-arm' if arch == 'arm64' else 'ubuntu-24.04',
                           'context': context.as_posix(), 'baseline': baseline_for_arch(previous, arch)})
        write(destination / (channel + '.json'), provenance)
    write(destination / 'matrix.json', {'include': matrix})
    write(destination / 'deferred.json', deferred)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--repository', required=True)
    parser.add_argument('--version', required=True)
    parser.add_argument('--commit', required=True)
    parser.add_argument('--platforms', default='amd64')
    parser.add_argument('--force', action='store_true')
    args = parser.parse_args()
    platforms = args.platforms.split(',')
    if not platforms or any(p not in ('amd64', 'arm64') for p in platforms) or len(set(platforms)) != len(platforms):
        raise SystemExit('Unsupported platforms')
    select(args.output, args.repository, args.version, args.commit, platforms, args.force)
