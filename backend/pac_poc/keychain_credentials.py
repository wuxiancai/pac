from __future__ import annotations

import subprocess
import sys
from collections.abc import Callable, Sequence
from typing import Protocol


PROVIDER_KEYCHAIN_SERVICE = "com.personal-ai-assistant.phase0.provider"
PROVIDER_ACCOUNTS = frozenset({"deepseek", "openrouter", "qwen"})


class CredentialUnavailable(RuntimeError):
    """A provider credential is missing or could not be read from Keychain."""


class CredentialProvider(Protocol):
    def get(self, account: str) -> str: ...


CommandRunner = Callable[..., subprocess.CompletedProcess[str]]


class MacOSKeychainCredentialProvider:
    """Read only named provider secrets from the user's login Keychain."""

    def __init__(
        self,
        *,
        command: Sequence[str] = ("/usr/bin/security",),
        runner: CommandRunner = subprocess.run,
    ) -> None:
        self._command = tuple(command)
        self._runner = runner

    def get(self, account: str) -> str:
        if sys.platform != "darwin":
            raise CredentialUnavailable("provider credentials require macOS Keychain")
        if account not in PROVIDER_ACCOUNTS:
            raise CredentialUnavailable("provider credential identity is not allowed")
        try:
            result = self._runner(
                [
                    *self._command,
                    "find-generic-password",
                    "-s",
                    PROVIDER_KEYCHAIN_SERVICE,
                    "-a",
                    account,
                    "-w",
                ],
                check=True,
                capture_output=True,
                text=True,
                stdin=subprocess.DEVNULL,
                timeout=10,
            )
        except (OSError, subprocess.SubprocessError):
            raise CredentialUnavailable(
                "provider credential is missing or unavailable in Keychain"
            ) from None
        secret = result.stdout.rstrip("\r\n")
        if not secret:
            raise CredentialUnavailable("provider credential is empty in Keychain")
        return secret
