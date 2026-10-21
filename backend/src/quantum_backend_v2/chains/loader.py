"""Load and validate the packaged registry before application startup."""

from __future__ import annotations

import sys
from importlib.resources import files
from pathlib import Path

from pydantic import ValidationError

from quantum_backend_v2.chains.models import ChainRegistry

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib


class RegistryConfigurationError(ValueError):
    """Invalid registry configuration, with input values deliberately omitted."""


def load_chain_registry(path: str | Path | None = None) -> ChainRegistry:
    try:
        source = Path(path) if path is not None else files(__package__).joinpath("registry.toml")
        with source.open("rb") as stream:
            data = tomllib.load(stream)
        return ChainRegistry.model_validate(data)
    except ValidationError as exc:
        # Validators use fixed messages. Locations can contain user-supplied keys.
        errors = exc.errors(include_url=False, include_context=False, include_input=False)
        messages = "; ".join(dict.fromkeys(error["msg"] for error in errors))
        raise RegistryConfigurationError(f"invalid chain registry: {messages}") from None
    except OSError:
        raise RegistryConfigurationError("unable to read chain registry file") from None
    except ValueError:
        # Parser errors can include pasted credentials.
        raise RegistryConfigurationError("invalid chain registry TOML") from None
