"""Secure connections checked the way Windows (and your browser) checks them (1.14.0).

Python checks secure connections against its own list of trusted certificates. Antivirus "HTTPS scanning" / web shields,
some VPNs and network filters put their own certificate in the middle: Windows trusts it (they install it there), Python
didn't, so every call to Twitch failed with "CERTIFICATE_VERIFY_FAILED: self-signed certificate in certificate chain"
and the bot kept disconnecting. truststore makes Python ask Windows instead (pip does the same). It still REFUSES
anything Windows itself doesn't trust: nothing is switched off.

When truststore isn't installed (running from source without it), everything works as before."""

import logging
import ssl

log = logging.getLogger("twitchbot.netfix")
_done = {"state": ""}


def use_system_certs() -> str:
    """Call once, as early as possible (before any connection is made). "on" | "missing" | "failed"."""
    if _done["state"]:
        return _done["state"]
    try:
        import truststore
        truststore.inject_into_ssl()
        _done["state"] = "on"
        log.info("Secure connections are checked by Windows (truststore)")
    except ImportError:
        _done["state"] = "missing"
        log.info("truststore isn't installed: secure connections use Python's own certificate list")
    except Exception:
        _done["state"] = "failed"
        log.exception("Could not use Windows' certificate check")
    return _done["state"]


def is_cert_error(exc) -> bool:
    """A secure connection refused because of its certificate (somewhere in the chain of errors)."""
    seen = 0
    while exc is not None and seen < 10:
        if isinstance(exc, ssl.SSLCertVerificationError) or "CERTIFICATE_VERIFY_FAILED" in str(exc):
            return True
        exc = exc.__cause__ or exc.__context__
        seen += 1
    return False
