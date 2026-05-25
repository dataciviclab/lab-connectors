"""Tests per lab_connectors.gcs.

Skappa di default se GCS non raggiungibile (pytest -m gcs).
"""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from lab_connectors.gcs import check_public, list_objects, object_exists


def _mock_gcs_sdk_modules() -> dict[str, MagicMock]:
    """Crea mock per i moduli google.cloud.storage necessari al path SDK.

    ``list_objects`` con auth=True/auth=None (SDK path) fa un import
    interno ``from google.cloud.storage.retry import DEFAULT_RETRY``.
    Questo helper crea i mock per evitare ModuleNotFoundError quando
    google-cloud-storage non e' installato.

    Returns:
        Dict con i moduli mock da usare con ``patch.dict("sys.modules", ...)``.
    """
    return {
        "google": MagicMock(),
        "google.cloud": MagicMock(),
        "google.cloud.storage": MagicMock(),
        "google.cloud.storage.retry": MagicMock(),
    }


class GcsListObjectsTest(unittest.TestCase):
    """list_objects con/b senza SDK, su bucket pubblico."""

    @unittest.skip("richiede GCS reachable")
    def test_list_public_bucket_http(self) -> None:
        """Lista oggetti da un bucket pubblico via HTTP API."""
        results = list_objects("dataciviclab-clean", prefix="", limit=5, auth=False)
        self.assertIsInstance(results, list)
        if results:
            self.assertIn("name", results[0])

    def test_list_empty_prefix(self) -> None:
        """List con prefix inesistente ritorna lista vuota."""
        results = list_objects(
            "dataciviclab-clean", prefix="__nonexistent__", limit=5, auth=False
        )
        self.assertEqual(results, [])

    @patch("lab_connectors.gcs.client.urlopen")
    def test_list_http_parse(self, mock_urlopen) -> None:
        """Parsing corretto della risposta HTTP API."""
        import json
        from io import BytesIO

        data = {
            "items": [
                {
                    "name": "test/file.parquet",
                    "size": "1024",
                    "updated": "2026-01-01T00:00:00Z",
                },
            ]
        }
        mock_response = BytesIO(json.dumps(data).encode())
        mock_response.status = 200
        mock_urlopen.return_value = mock_response

        results = list_objects("test-bucket", prefix="test/", auth=False)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["name"], "test/file.parquet")
        self.assertEqual(results[0]["size"], 1024)  # int, non string


class GcsObjectExistsTest(unittest.TestCase):
    """object_exists via HEAD pubblico."""

    @patch("lab_connectors.gcs.client.urlopen")
    def test_exists_returns_true(self, mock_urlopen) -> None:
        from io import BytesIO
        mock = BytesIO(b"")
        mock.status = 200
        mock_urlopen.return_value = mock

        self.assertTrue(object_exists("test-bucket", "existing/file.parquet"))

    @patch("lab_connectors.gcs.client.urlopen")
    def test_not_found_returns_false(self, mock_urlopen) -> None:
        from urllib.error import HTTPError
        mock_urlopen.side_effect = HTTPError(
            "http://example.com", 404, "Not Found", {}, None
        )

        self.assertFalse(object_exists("test-bucket", "missing/file.parquet"))


class GcsCheckPublicTest(unittest.TestCase):
    """check_public su URL pubblico."""

    @patch("lab_connectors.gcs.client.urlopen")
    def test_accessible(self, mock_urlopen) -> None:
        from io import BytesIO
        mock = BytesIO(b"")
        mock.status = 200
        mock.headers = {"Content-Type": "application/x-parquet"}
        mock_urlopen.return_value = mock

        result = check_public("https://storage.googleapis.com/test/file.parquet")
        self.assertTrue(result["accessible"])
        self.assertEqual(result["status_code"], 200)

    @patch("lab_connectors.gcs.client.urlopen")
    def test_not_found(self, mock_urlopen) -> None:
        from urllib.error import HTTPError
        mock_urlopen.side_effect = HTTPError(
            "http://example.com", 404, "Not Found", {}, None
        )

        result = check_public("https://storage.googleapis.com/test/missing.parquet")
        self.assertFalse(result["accessible"])


class GcsUploadTest(unittest.TestCase):
    """upload_file e upload_string — test solo con mock (serve SDK)."""

    @patch("lab_connectors.gcs.client._get_storage_client")
    def test_upload_file_no_sdk_raises(self, mock_get_client) -> None:
        mock_get_client.return_value = None
        from lab_connectors.gcs import upload_file

        with self.assertRaises(RuntimeError):
            upload_file("/tmp/test.parquet", "bucket", "path/test.parquet")

    @patch("lab_connectors.gcs.client._get_storage_client")
    def test_upload_string_no_sdk_raises(self, mock_get_client) -> None:
        """upload_string senza SDK → RuntimeError."""
        mock_get_client.return_value = None
        from lab_connectors.gcs import upload_string

        with self.assertRaises(RuntimeError):
            upload_string("content", "bucket", "path/test.txt")

    @patch("lab_connectors.gcs.client._get_storage_client")
    def test_list_auth_true_no_sdk_raises(self, mock_get_client) -> None:
        """auth=True senza SDK deve fallire, non degradare a HTTP."""
        mock_get_client.return_value = None
        from lab_connectors.gcs import list_objects

        with self.assertRaises(RuntimeError):
            list_objects("test-bucket", auth=True)


class GcsListSdkPathTest(unittest.TestCase):
    """list_objects — test del path SDK (auth=True e auth=None con SDK mock)."""

    def _make_mock_blob(self, name: str, size: int = 1024) -> object:
        """Crea un oggetto mock che simula un blob GCS."""
        from datetime import datetime, timezone
        blob = type("MockBlob", (), {})()
        blob.name = name
        blob.size = size
        blob.updated = datetime(2026, 1, 1, tzinfo=timezone.utc)
        return blob

    @patch("lab_connectors.gcs.client._get_storage_client")
    def test_auth_true_with_sdk(self, mock_get_client):
        """auth=True con SDK mock → lista blob usando il client SDK."""
        mock_client = type("MockStorageClient", (), {})()
        mock_client.list_blobs = lambda bucket, **kw: [
            self._make_mock_blob("a/file1.parquet", 100),
            self._make_mock_blob("a/file2.parquet", 200),
        ]
        mock_get_client.return_value = mock_client

        with patch.dict("sys.modules", _mock_gcs_sdk_modules()):
            results = list_objects("test-bucket", prefix="a/", auth=True)
        self.assertEqual(len(results), 2)
        self.assertEqual(results[0]["name"], "a/file1.parquet")
        self.assertEqual(results[0]["size"], 100)
        self.assertEqual(results[1]["name"], "a/file2.parquet")
        self.assertEqual(results[1]["size"], 200)

    @patch("lab_connectors.gcs.client._get_storage_client")
    def test_auth_true_empty_result(self, mock_get_client):
        """auth=True con SDK mock → bucket vuoto."""
        mock_client = type("MockStorageClient", (), {})()
        mock_client.list_blobs = lambda bucket, **kw: []
        mock_get_client.return_value = mock_client

        with patch.dict("sys.modules", _mock_gcs_sdk_modules()):
            results = list_objects("test-bucket", auth=True)
        self.assertEqual(results, [])

    @patch("lab_connectors.gcs.client._get_storage_client")
    def test_auth_none_sdk_available(self, mock_get_client):
        """auth=None con SDK disponibile → usa SDK."""
        mock_client = type("MockStorageClient", (), {})()
        mock_client.list_blobs = lambda bucket, **kw: [
            self._make_mock_blob("sdk/file.parquet"),
        ]
        mock_get_client.return_value = mock_client

        with patch.dict("sys.modules", _mock_gcs_sdk_modules()):
            results = list_objects("test-bucket", prefix="sdk/", auth=None)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["name"], "sdk/file.parquet")

class GcsHttpPaginationTest(unittest.TestCase):
    """Test per la paginazione HTTP fallback (auth=None senza SDK)."""

    @patch("lab_connectors.gcs.client._get_storage_client")
    @patch("lab_connectors.gcs.client.urlopen")
    def test_auth_none_fallback_no_pagination(self, mock_urlopen, mock_get_client):
        """auth=None senza SDK → fallback HTTP, pagina singola."""
        import json
        from io import BytesIO

        mock_get_client.return_value = None

        def fake_open(url, **kw):
            data = {"items": [
                {"name": "a.parquet", "size": "100", "updated": "2026-01-01T00:00:00Z"}
            ]}
            result = BytesIO(json.dumps(data).encode())
            result.status = 200
            return result

        mock_urlopen.side_effect = fake_open

        results = list_objects("test-bucket", prefix="", auth=None)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["name"], "a.parquet")
        self.assertEqual(results[0]["size"], 100)

    @patch("lab_connectors.gcs.client._get_storage_client")
    @patch("lab_connectors.gcs.client.urlopen")
    def test_auth_none_fallback_with_pagination(self, mock_urlopen, mock_get_client):
        """auth=None senza SDK → paginazione HTTP, 2 pagine."""
        import json
        from io import BytesIO

        mock_get_client.return_value = None

        page = 0
        def fake_open(url, **kw):
            nonlocal page
            page += 1
            items = [{"name": f"p1_{i}.parquet", "size": "10",
                       "updated": "2026-01-01T00:00:00Z"} for i in range(3)]
            if page == 1:
                data = {"items": items, "nextPageToken": "token-p2"}
            else:
                data = {"items": [{"name": "p2_0.parquet", "size": "10",
                                    "updated": "2026-01-01T00:00:00Z"}]}
            result = BytesIO(json.dumps(data).encode())
            result.status = 200
            return result

        mock_urlopen.side_effect = fake_open

        results = list_objects("test-bucket", prefix="", auth=None)
        self.assertEqual(len(results), 4)
        self.assertIn("p1_0.parquet", [r["name"] for r in results])
        self.assertIn("p2_0.parquet", [r["name"] for r in results])

    @patch("lab_connectors.gcs.client._get_storage_client")
    @patch("lab_connectors.gcs.client.urlopen")
    def test_auth_none_fallback_with_limit(self, mock_urlopen, mock_get_client):
        """auth=None con limit → paginazione interrotta al raggiungimento del limite."""
        import json
        from io import BytesIO

        mock_get_client.return_value = None

        page = 0
        def fake_open(url, **kw):
            nonlocal page
            page += 1
            items = [{"name": f"p1_{i}.parquet", "size": "10",
                       "updated": "2026-01-01T00:00:00Z"} for i in range(3)]
            data = {"items": items, "nextPageToken": "token-p2"}
            result = BytesIO(json.dumps(data).encode())
            result.status = 200
            return result

        mock_urlopen.side_effect = fake_open

        # limit=1 → solo 1 risultato, nonostante ci siano 3 nella prima pagina
        results = list_objects("test-bucket", prefix="", limit=1, auth=None)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["name"], "p1_0.parquet")


if __name__ == "__main__":
    unittest.main()
