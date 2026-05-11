"""Tests per lab_connectors.gcs.

Skappa di default se GCS non raggiungibile (pytest -m gcs).
"""

from __future__ import annotations

import unittest
from unittest.mock import patch

from lab_connectors.gcs import check_public, list_objects, object_exists


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
    def test_list_auth_true_no_sdk_raises(self, mock_get_client) -> None:
        """auth=True senza SDK deve fallire, non degradare a HTTP."""
        mock_get_client.return_value = None
        from lab_connectors.gcs import list_objects

        with self.assertRaises(RuntimeError):
            list_objects("test-bucket", auth=True)


if __name__ == "__main__":
    unittest.main()
