import pandas as pd
import email
import uuid
from email import policy
from typing import List
from schema import EmailArtifact
from email.utils import parsedate_to_datetime

def extract_body(msg):
    """
    Extract plain text body from email message.
    Handles multipart emails safely.
    """
    if msg.is_multipart():
        for part in msg.walk():
            content_type = part.get_content_type()
            if content_type == "text/plain":
                return part.get_content().strip()
        return ""
    else:
        return msg.get_content().strip()

def parse_recipients(to_field) -> List[str]:
    """
    Convert recipient field to list of emails.
    """
    if not to_field:
        return []

    if isinstance(to_field, list):
        to_field = ",".join(to_field)

    return [x.strip() for x in to_field.split(",") if x.strip()]

def parse_email(raw_email: str) -> EmailArtifact:
    msg = email.message_from_string(raw_email, policy=policy.default)
    
    # Convert string date to datetime object
    raw_date = msg.get("Date")
    parsed_date = parsedate_to_datetime(raw_date) if raw_date else None

    # Bulletproof the ID: If missing, generate a random one so Pydantic doesn't crash
    msg_id = msg.get("Message-ID")
    if not msg_id:
        msg_id = f"missing-id-{uuid.uuid4().hex[:8]}"

    return EmailArtifact(
        message_id=msg_id,
        date=parsed_date, 
        sender=msg.get("From") or "unknown_sender@enron.com", # Fallback for missing sender
        recipients=parse_recipients(msg.get_all("To", [])),
        subject=msg.get("Subject"),
        body=extract_body(msg)
    )

def load_and_parse_emails(csv_path):
    df = pd.read_csv(csv_path)
    artifacts = []

    for raw_email in df["message"]:
        try:
            artifact = parse_email(raw_email)
            artifacts.append(artifact)
        except Exception as e:
            # If Pydantic hates a specific email, skip it instead of crashing the pipeline
            print(f"Skipping a corrupted email: {e}")
            continue

    return artifacts

if __name__ == "__main__":
    emails = load_and_parse_emails("data/emails_subset_1000.csv")
    print("Parsed emails:", len(emails))
    print()
    example = emails[0]
    print("Example parsed email:")
    print(example)