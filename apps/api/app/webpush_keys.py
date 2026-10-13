"""Print a VAPID key pair for web push.

    python -m app.webpush_keys

Put the private key in ``PUSH_WEBPUSH_PRIVATE_KEY`` (and keep it: every browser
that subscribed did so against its public half, so a new key means every
operator subscribes again). The public key is derived at runtime and handed to
the portal; it is printed here only so you can recognise it.
"""

from __future__ import annotations

from .services import webpush


def main() -> None:
    private = webpush.generate_private_key()
    public = webpush.public_key_of(webpush.load_private_key(private))
    print(f"PUSH_WEBPUSH_PRIVATE_KEY={private}")
    print(f"# public key (derived, for reference): {public}")


if __name__ == "__main__":
    main()
