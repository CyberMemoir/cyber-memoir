"""Read a current protected snapshot for tests of rules other than edit conflicts."""


def matching_revision(client, auth, path):
    identifier = path.removesuffix("/decision")
    response = client.get(identifier, headers=auth)
    # Preserve tests for missing IDs/unauthorized callers without inventing a
    # valid snapshot. Conflict tests use explicit captured tags, never this helper.
    return {**auth, "If-Match": response.headers.get("etag", '"not-a-snapshot"')}
