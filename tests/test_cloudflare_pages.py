import base64
import io
import json
from pathlib import Path
import tarfile
import tempfile
import unittest
from unittest.mock import MagicMock, patch
from urllib.error import HTTPError

from scripts.cloudflare_pages import (
    DEFAULT_PROJECT, REQUIRED_FILES, SUPABASE_REF, allow_login_redirects,
    ensure_project, settings, unpack, validate_site, verify,
)

ENV = {"CLOUDFLARE_ACCOUNT_ID": "a" * 32, "CLOUDFLARE_API_TOKEN": "synthetic-cloudflare-token"}
PROJECT = {"success": True, "result": {"name": DEFAULT_PROJECT, "subdomain": DEFAULT_PROJECT + ".pages.dev", "production_branch": "main"}}


def site_files(root, key="sb_publishable_synthetic"):
    for name in REQUIRED_FILES:
        file = root / name
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_text('{"generated_at":"2026-10-20T00:00:00Z"}' if name.endswith('.json') else '<html>synthetic</html>')
    config = {"url": f"https://{SUPABASE_REF}.supabase.co", "anonKey": key}
    (root / 'supabase-runtime-config.js').write_text('window.COIN_RECOMAND_SUPABASE = Object.freeze(' + json.dumps(config) + ');')


class CloudflarePagesTests(unittest.TestCase):
    def test_missing_configuration_is_optional_but_partial_settings_fail(self):
        self.assertIsNone(settings({}))
        self.assertEqual(settings(ENV)["project"], DEFAULT_PROJECT)
        with self.assertRaisesRegex(ValueError, "둘 다"):
            settings({"CLOUDFLARE_ACCOUNT_ID": "a" * 32})
        for change in [{"CLOUDFLARE_ACCOUNT_ID": "bad"}, {"CLOUDFLARE_PAGES_PROJECT": "site;echo-secret"}, {"CLOUDFLARE_PAGES_PROJECT": "other.example.com"}]:
            with self.assertRaises(ValueError):
                settings({**ENV, **change})

    @patch('scripts.cloudflare_pages.request_json')
    def test_existing_project_is_used_without_creation(self, request):
        request.return_value = PROJECT
        url = ensure_project(settings(ENV))
        self.assertEqual(url, f'https://{DEFAULT_PROJECT}.pages.dev')
        self.assertEqual(request.call_count, 1)

    @patch('scripts.cloudflare_pages.request_json')
    def test_only_missing_project_is_created_with_main_branch(self, request):
        request.side_effect = [HTTPError('https://example.invalid', 404, '', {}, io.BytesIO()), PROJECT]
        ensure_project(settings(ENV))
        self.assertEqual(request.call_args.args[2:], ('POST', {'name': DEFAULT_PROJECT, 'production_branch': 'main'}))

    @patch('scripts.cloudflare_pages.request_json')
    def test_credential_errors_are_not_treated_as_missing_projects(self, request):
        request.side_effect = HTTPError('https://example.invalid', 403, '', {}, io.BytesIO(b'synthetic-cloudflare-token'))
        with self.assertRaisesRegex(RuntimeError, 'HTTP 403') as caught:
            ensure_project(settings(ENV))
        self.assertNotIn(ENV['CLOUDFLARE_API_TOKEN'], str(caught.exception))
        self.assertEqual(request.call_count, 1)

    @patch('scripts.cloudflare_pages.request_json')
    def test_project_identity_branch_and_other_publisher_are_validated(self, request):
        for fields in [{'subdomain': 'another.pages.dev'}, {'name': 'another'}, {'production_branch': 'preview'}, {'source': {'type': 'github', 'config': {'production_deployments_enabled': True}}}]:
            request.return_value = {**PROJECT, 'result': {**PROJECT['result'], **fields}}
            with self.assertRaises(RuntimeError):
                ensure_project(settings(ENV))

    @patch('scripts.cloudflare_pages.request_json')
    def test_login_redirects_preserve_existing_settings_and_use_exact_paths(self, request):
        old = 'https://jijunkyoung.github.io/coin-recomand/**'
        def reply(url, token, method='GET', payload=None):
            if method == 'GET': return {'uri_allow_list': old, 'smtp_pass': 'private-existing-password'}
            self.assertEqual(set(payload), {'uri_allow_list'})
            urls = payload['uri_allow_list'].split(',')
            self.assertIn(old, urls)
            self.assertIn(f'https://{DEFAULT_PROJECT}.pages.dev/us-stocks', urls)
            self.assertIn(f'https://{DEFAULT_PROJECT}.pages.dev/us-stocks.html', urls)
            self.assertFalse(any('*' in value for value in urls if value != old))
            return payload
        request.side_effect = reply
        allow_login_redirects(f'https://{DEFAULT_PROJECT}.pages.dev', 'synthetic-management-token')
        self.assertEqual(request.call_count, 2)
        with self.assertRaises(ValueError):
            allow_login_redirects('https://untrusted.invalid', 'synthetic-management-token')

    def test_artifact_requires_generated_login_file_and_public_keys_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            site_files(root)
            validate_site(root)
            (root / 'supabase-runtime-config.js').unlink()
            with self.assertRaisesRegex(ValueError, 'supabase-runtime-config'):
                validate_site(root)
            privileged = 'header.' + base64.urlsafe_b64encode(b'{"role":"service_role"}').decode().rstrip('=') + '.sig'
            site_files(root, privileged)
            with self.assertRaisesRegex(ValueError, '공개'):
                validate_site(root)

    def test_unpack_preserves_this_run_files_and_rejects_traversal_and_links(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            root = tmp / 'source'; root.mkdir(); site_files(root)
            archive = tmp / 'artifact.tar'
            with tarfile.open(archive, 'w') as tar:
                tar.add(root, arcname='.')
            unpack(archive, tmp / 'published')
            self.assertEqual((root / 'data/latest.json').read_bytes(), (tmp / 'published/data/latest.json').read_bytes())
            for name, kind in [('../outside.txt', tarfile.REGTYPE), ('link', tarfile.SYMTYPE)]:
                with tarfile.open(archive, 'w') as tar:
                    member = tarfile.TarInfo(name); member.type = kind; member.linkname = '/outside'
                    tar.addfile(member)
                with self.assertRaisesRegex(ValueError, '상위 경로|링크'):
                    unpack(archive, tmp / 'blocked')

    @patch('scripts.cloudflare_pages.urlopen')
    def test_deployment_verification_reads_only_public_built_files(self, urlopen):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); site_files(root)
            def response(request, timeout):
                self.assertIn('.pages.dev/', request.full_url)
                self.assertNotIn('/functions/', request.full_url)
                name = request.full_url.split('.pages.dev/')[1].split('?')[0]
                stream = io.BytesIO((root / name).read_bytes())
                return stream
            urlopen.side_effect = response
            verify(root, f'https://{DEFAULT_PROJECT}.pages.dev')
            self.assertEqual(urlopen.call_count, 6)

    def test_workflow_reuses_generated_artifact_and_keeps_deployments_independent(self):
        workflow = Path('.github/workflows/analyze-and-deploy.yml').read_text()
        github, cloudflare = workflow.split('\n  deploy:\n', 1)[1].split('\n  deploy_cloudflare:\n', 1)
        self.assertIn('    needs: analyze\n', github)
        self.assertIn('    needs: analyze\n', cloudflare)
        self.assertIn("if: github.ref == 'refs/heads/main'", cloudflare)
        self.assertIn('uses: actions/download-artifact@', cloudflare)
        self.assertIn('name: github-pages\n', cloudflare)
        self.assertIn('uses: cloudflare/wrangler-action@', cloudflare)
        self.assertIn('pages deploy cloudflare-site', cloudflare)
        self.assertNotIn('deployments: write', cloudflare)


if __name__ == '__main__':
    unittest.main()
