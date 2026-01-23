import requests


class BaseHttpClient:
    """
    Shared HTTP layer.
    Handles base URL, auth, headers, and request execution.
    """

    def __init__(self, base_url, token=None, verify_ssl=False, timeout=10):
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.verify_ssl = verify_ssl
        self.timeout = timeout

    def _headers(self):
        headers = {
            "Content-Type": "application/json"
        }
        if self.token:
            headers["Authorization"] = f"Token {self.token}"
        return headers

    def request(self, method, path, **kwargs):
        url = f"{self.base_url}{path}"
        return requests.request(
            verify=self.verify_ssl,
            method=method,
            url=url,
            headers=self._headers(),
            timeout=self.timeout,
            **kwargs
        )
