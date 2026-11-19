from pathlib import Path
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.core.files.storage import default_storage
from deploy.snapshot import read_snapshot


class Command(BaseCommand):
    help = 'Upload referenced images only to the configured Neon bucket, preserving keys. Does not create services or buckets.'

    def add_arguments(self, parser):
        parser.add_argument('folder', type=Path)
        parser.add_argument('--dry-run', action='store_true')

    def handle(self, *args, **options):
        if not getattr(settings, 'STAGING_DEPLOYMENT', False):
            raise CommandError('Use config.settings_staging with an existing Free Neon bucket.')
        folder = options['folder'].resolve()
        try:
            manifest = read_snapshot(folder)
            if options['dry_run']:
                self.stdout.write(f"Verified {len(manifest['media'])} local images. No network calls or uploads.")
                return
            from botocore.exceptions import ClientError, BotoCoreError
            client = default_storage.connection.meta.client
            bucket = default_storage.bucket_name
            for item in manifest['media']:
                key = item['key']
                try:
                    remote = client.head_object(Bucket=bucket, Key=key)
                except ClientError as exc:
                    if exc.response['Error']['Code'] not in ('404', 'NoSuchKey', 'NotFound'):
                        raise
                else:
                    body = client.get_object(Bucket=bucket, Key=key)['Body']
                    from hashlib import sha256 as hash_bytes
                    try:
                        actual = hash_bytes(body.read(item['size'] + 1)).hexdigest()
                    finally:
                        body.close()
                    if actual != item['sha256']:
                        raise CommandError('A destination image differs. Refusing to overwrite it.')
                    continue
                with (folder / 'media' / key).open('rb') as file:
                    client.put_object(Bucket=bucket, Key=key, Body=file,
                        ContentType={'.png':'image/png', '.jpg':'image/jpeg', '.jpeg':'image/jpeg', '.webp':'image/webp', '.avif':'image/avif'}[Path(key).suffix.lower()],
                        CacheControl='public, max-age=3600', Metadata={'sha256': item['sha256']})
                # Verify bytes, not just the success status or an ETag.
                body = client.get_object(Bucket=bucket, Key=key)['Body']
                from hashlib import sha256 as hash_bytes
                try:
                    if hash_bytes(body.read(item['size'] + 1)).hexdigest() != item['sha256']:
                        raise CommandError('Uploaded image checksum differs; stop and inspect the bucket.')
                finally:
                    body.close()
            self.stdout.write(self.style.SUCCESS(f"Verified {len(manifest['media'])} persistent images. Database paths unchanged."))
        except (ValueError, OSError) as exc:
            raise CommandError(str(exc)) from None
        except (ClientError, BotoCoreError):
            raise CommandError('Neon storage request failed. Check endpoint, bucket and server credentials; no secret values are logged.') from None
