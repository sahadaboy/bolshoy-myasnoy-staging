"""Create a reviewed code-only copy for a private staging repository."""
import argparse
from pathlib import Path
import shutil
from check_release import forbidden

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', default='.staging-release')
    args = parser.parse_args()
    output = (ROOT / args.output).resolve()
    if output != ROOT / '.staging-release' or output.exists():
        parser.error('Use the new .staging-release directory. Existing copies are never overwritten.')
    output.mkdir()
    roots = ['config', 'shop', 'storefront', 'deploy', '.github', 'frontend/src', 'frontend/tunnel', 'frontend/public']
    names = ['manage.py', 'Dockerfile', 'render.yaml', 'requirements-staging.txt', '.dockerignore', '.gitignore', '.gitattributes',
             '.env.staging.example', 'frontend/package.json', 'frontend/pnpm-lock.yaml', 'frontend/index.html', 'frontend/vite.config.ts',
             'frontend/tsconfig.json', 'frontend/tsconfig.app.json', 'frontend/tsconfig.node.json', 'docs/staging.md']
    for directory in roots:
        names.extend(file.relative_to(ROOT).as_posix() for file in (ROOT / directory).rglob('*') if file.is_file())
    copied = 0
    for name in sorted(set(names)):
        source = ROOT / name
        if forbidden(name) or '__pycache__' in source.parts or source.suffix == '.pyc' or source.is_symlink():
            continue
        destination = output / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)
        copied += 1
    (output / 'README.md').write_text('# Большой Мясной — staging\n\nИнструкция: [Render Free + Neon Free](docs/staging.md).\n\nЗаказы и уведомления принудительно выключены. Секреты, базы и медиа переносятся отдельно.\n', encoding='utf-8')
    print(f'Prepared {copied} code/assets files in {output}. No Git repository, cloud service or paid resource was created.')


if __name__ == '__main__':
    main()
