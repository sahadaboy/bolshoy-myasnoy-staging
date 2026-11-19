"""Run a staging maintenance command with a private env file outside the checkout."""
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main():
    allowed = {'backup_staging_database', 'check_order_chat', 'check_telegram_store', 'migrate', 'showmigrations', 'check', 'deliver_order_notifications'}
    if len(sys.argv) < 2 or sys.argv[1] not in allowed or any(arg.startswith('--settings') for arg in sys.argv):
        raise SystemExit('Use an explicit supported staging maintenance command; settings overrides and data imports are disabled.')
    if sys.argv[1] == 'migrate' and '--plan' not in sys.argv[2:]:
        raise SystemExit('This local helper permits migrate --plan only. Apply reviewed migrations through the normal Render deployment.')
    if sys.argv[1] == 'deliver_order_notifications' and '--once' not in sys.argv[2:]:
        raise SystemExit('Use --once; no persistent worker is started by this helper.')
    from config.env import load_env
    path = os.environ.get('BM_STAGING_ENV_FILE', '').strip()
    if not path or not Path(path).is_file():
        raise SystemExit('Set BM_STAGING_ENV_FILE to the existing private .env.staging; do not pass secrets as command arguments.')
    load_env(Path(path))
    os.environ['DJANGO_SETTINGS_MODULE'] = 'config.settings_staging'
    from django.core.management import execute_from_command_line
    execute_from_command_line([str(ROOT/'manage.py'), *sys.argv[1:]])


if __name__ == '__main__':
    main()
