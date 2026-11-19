"""Publish compiled assets only, never the repository or Vite's entire public dir."""
from pathlib import Path
import re
import shutil

ROOT = Path(__file__).resolve().parents[1]


def collect(source=None, target=None):
    source = source or ROOT / 'frontend/dist'
    target = target or ROOT / '.build/frontend'
    if not (source / 'index.html').is_file():
        raise RuntimeError('Build the frontend first.')
    target.mkdir(parents=True, exist_ok=True)
    files = ['brand-logo-original.png', 'image-credits.txt', 'brand/telegram.svg', 'brand/vk.svg', 'fonts/Manrope-OFL.txt']
    for folder in ('assets', 'categories'):
        if (source / folder).is_dir():
            for path in (source / folder).iterdir():
                pattern = r'[a-zA-Z0-9][a-zA-Z0-9._-]*\.(?:js|css|woff2?|png|jpe?g|webp|svg|avif)' if folder == 'assets' else r'[a-z0-9][a-z0-9_-]*\.webp'
                if path.is_file() and not path.is_symlink() and re.fullmatch(pattern, path.name):
                    files.append(f'{folder}/{path.name}')
    for name in files:
        path = source / name
        if path.is_file() and not path.is_symlink():
            destination = target / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, destination)
    return files


if __name__ == '__main__':
    print(f'Published {len(collect())} frontend assets.')
