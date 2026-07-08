import requests
from requests.auth import HTTPBasicAuth

import logging
logger = logging.getLogger(__name__)

def send_email_pridec(subject : str, 
                     message : str,
                     dhis_url: str,
                     user: str | None = None, 
                     pwd: str | None = None, 
                     token: str | None = None
                     ):
    """
    Send email to all PRIDE-C users

    Args:
        subject: subject of email message
        message: email message, can be plain text or HTML
        dhis_url: URL of the DHIS2 instance.
        user: Username for the DHIS2 instance. Required if `token` is not provided.
        pwd: Password for the DHIS2 instance. Required if `token` is not provided.
        token: Personal access token for the DHIS2 instance. Can be provided
            instead of `user` and `pwd`.
    
    Returns:
        requests.Response: Response object from POST request
    """
    if not token and not (user and pwd):
        raise ValueError("Authentication required: provide either a token or both user and pwd")
    
    # Authentication setup
    headers = {'Authorization': f'ApiToken {token}'} if token else {}
    auth = None if token else HTTPBasicAuth(user, pwd)

    dhis_url = f"{dhis_url.rstrip('/')}"

    # Fetch emails of all users in the PRIDE-C group
    response = requests.get(
        f"{dhis_url}/api/33/userGroups",
        headers = headers,
        auth = auth,
        params = {"filter": "name:eq:PRIDE-C", "fields": "users[email]"}
    )
    response.raise_for_status()

    users = response.json()["userGroups"][0]["users"]
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
        }
    )
    response.raise_for_status()

    return {"status": "sent", "recipients": emails}