import requests

import logging
logger = logging.getLogger(__name__)

from ..api_helpers import _api_auth, _raise_for_status

def send_email_pridec(subject: str,
                     message: str,
                     dhis_url: str,
                     user: str | None = None,
                     pwd: str | None = None,
                     token: str | None = None
                     ) -> dict:
    """Email every member of the PRIDE-C user group through DHIS2.

    Looks up the email addresses of the users in the ``PRIDE-C`` user group,
    then sends one message to all of them via
    ``/api/33/email/notification``. Users without an email address are
    skipped. The DHIS2 instance must have an email server configured.

    Args:
        subject: Subject line of the email.
        message: Body of the email, as plain text or HTML.
        dhis_url: Base URL of the DHIS2 instance (with or without a trailing slash).
        user: DHIS2 username. Required with `pwd` if `token` is not provided.
        pwd: DHIS2 password. Required with `user` if `token` is not provided.
        token: DHIS2 personal access token. Takes precedence over `user`/`pwd`.

    Returns:
        ``{"status": "sent", "recipients": [<email>, ...]}`` once DHIS2 has
        accepted the email.

    Raises:
        ValueError: If credentials are missing, if there is no ``PRIDE-C``
            user group, or if none of its users has an email address.
        requests.HTTPError: If the group lookup or the send returns an
            error status (e.g. 409 if no email server is configured).
        requests.ConnectionError: If the server cannot be reached.
    """
    headers, auth = _api_auth(user=user, pwd=pwd, token=token)

    dhis_url = f"{dhis_url.rstrip('/')}"

    # Fetch emails of all users in the PRIDE-C group
    response = requests.get(
        f"{dhis_url}/api/33/userGroups",
        headers = headers,
        auth = auth,
        params = {"filter": "name:eq:PRIDE-C", "fields": "users[email]"},
        timeout = 60
    )
    _raise_for_status(response, "look up PRIDE-C user group emails")

    groups = response.json().get("userGroups", [])
    if not groups:
        raise ValueError("No user group named PRIDE-C found")

    users = groups[0].get("users", [])
    emails = [u["email"] for u in users if u.get("email")]

    if not emails:
        raise ValueError("No email addresses found for users in the PRIDE-C group")

    # Send the email
    response = requests.post(
        f"{dhis_url}/api/33/email/notification",
        headers=headers,
        auth = auth,
        data={
            "recipients": ",".join(emails),
            "subject": subject,
            "message": message,
        },
        timeout = 600
    )
    _raise_for_status(response, "send email")

    return {"status": "sent", "recipients": emails}
