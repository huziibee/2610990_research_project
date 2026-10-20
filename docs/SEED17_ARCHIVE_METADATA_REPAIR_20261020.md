# Exact-byte archive metadata recovery

The cloud private-release check in run 39474482983 stopped before decryption with `REGISTERED_ENCRYPTED_ARCHIVE_CHANGED`. The ciphertext is unchanged and matches the author-approved SHA-256 `4290647c43bb69f0caf36c32601f9c6b2693eb399d8f42cf33fcf6ac151d48d0`.

The sidecar metadata had been normalized to LF (742 bytes; SHA-256 `fc9365bc643aff688bf9f3588c7a672d1296aec0d47f0db45fc174aaaeb26421`). Restoring its original CRLF bytes produces exactly the EXISTING author-approved hash `c215c0bf41ffba7b99858d622e4ec7acfe7c48beef7e48878bd24a273391ea4c` (760 bytes). No metadata value, ciphertext, source reference, review receipt, policy hash, or human approval is changed. This restores the bytes selected by the original release; it does not normalize the policy to accept different bytes.

Added `protected_reference_archive/** -text` to protect those bytes across Windows and Linux checkouts. Four regression tests now verify ciphertext digest, sidecar digest, metadata bindings/counts, and checkout attributes without decrypting any reference.

The same cloud job had an empty `AUTHOR_REVIEW_AES_KEY_BASE64`. Once the byte repair passes, the original key must still be supplied through that secret, or the existing approved local workspace must be used. Do not create a new key or publish the old key. This fix does not establish private reference semantic correctness, authorize inference, or complete the technical freeze.
