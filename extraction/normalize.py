from schema import EmailArtifact

def normalize_email(email: str) -> str:
    """
    Normalize email addresses to canonical form.
    """
    if not email:
        return ""
    return email.strip().lower()

def normalize_message_id(msg_id: str) -> str:
    """
    Remove angle brackets and whitespace from message IDs.
    """
    if not msg_id:
        return ""
        
    msg_id = msg_id.strip()
    if msg_id.startswith("<") and msg_id.endswith(">"):
        msg_id = msg_id[1:-1]
        
    return msg_id

def normalize_recipients(recipients):
    return [normalize_email(r) for r in recipients if r]

def is_valid_email(email: str) -> bool:
    if not email:
        return False
    if "@" not in email:
        return False
    return True

def normalize_email_artifact(email: EmailArtifact) -> EmailArtifact:
    """
    Safely returns a NEW validated Pydantic model with normalized fields.
    """
    return email.model_copy(update={
        "message_id": normalize_message_id(email.message_id),
        "sender": normalize_email(email.sender),
        "recipients": normalize_recipients(email.recipients)
    })