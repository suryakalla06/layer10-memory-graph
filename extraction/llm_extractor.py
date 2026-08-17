import os
import uuid
import time
from datetime import datetime
from pydantic import BaseModel
from typing import List

# Import the new, supported SDK
from google import genai
from google.genai import types

from schema import Entity, Claim, Evidence, EmailArtifact
from extraction.quality import passes_quality_gate

# Initialize the new genai client (it automatically finds GEMINI_API_KEY)
client = genai.Client()

# --- LLM-Specific Schemas ---
class LLMEvidence(BaseModel):
    excerpt: str
    start_offset: int
    end_offset: int

class LLMClaim(BaseModel):
    subject_id: str
    relation: str
    object_id: str
    evidence: List[LLMEvidence]

class LLMEntity(BaseModel):
    entity_id: str
    entity_type: str
    name: str
    aliases: List[str]

class ExtractionResult(BaseModel):
    entities: List[LLMEntity]
    claims: List[LLMClaim]


def extract_knowledge_from_email(email: EmailArtifact) -> dict:
    """
    Passes the email body to the LLM and maps the result to our main schema.
    Includes retry logic and automated mapping for Layer10 operational stability.
    """
    if not email.body or len(email.body) < 20:
        return {"entities": [], "claims": []}

    prompt = f"""
    You are an expert knowledge extraction system for a corporate long-term memory graph.
    Analyze the following email and extract Entities (People, Companies, Projects) and Claims (relationships between them).
    
    Email Metadata:
    Message-ID: {email.message_id}
    Date: {email.date}
    Sender: {email.sender}
    Recipients: {', '.join(email.recipients) if email.recipients else 'None'}
    Subject: {email.subject or 'No Subject'}
    
    Email Body:
    {email.body}
    
    RULES:
    1. Relations: "WORKS_FOR", "DISCUSSED_TOPIC", "MANAGES", "COMMITTED_TO".
    2. Excerpts: MUST be exact, verbatim substrings.
    3. Offsets: Provide exact character start/end offsets.
    4. REFERENTIAL INTEGRITY: Every single subject_id and object_id used in a Claim MUST be explicitly defined in the Entities list with a valid entity_type!
    """

    # Exponential Backoff Retry Logic (3 attempts)
    for attempt in range(3):
        try:
            response = client.models.generate_content(
                model='gemini-2.5-flash-lite', 
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=ExtractionResult,
                    temperature=0.1,
                ),
            )
            
            llm_result = ExtractionResult.model_validate_json(response.text)
            
            # 1. Automate Entities completely!
            final_entities = [
                Entity(**ent.model_dump()) 
                for ent in llm_result.entities
            ]
                
            final_claims = []
            for c in llm_result.claims:
                # 2. Automate Evidence (Unpack LLM offsets/excerpt, add Python source/time)
                final_evidence = [
                    Evidence(
                        **ev.model_dump(),
                        source_id=email.message_id,
                        timestamp=email.date or datetime.now()
                    ) for ev in c.evidence
                ]
                    
                # 3. Automate Claims (Unpack LLM relations, add Python IDs/Time/Evidence)
                new_claim = Claim(
                    **c.model_dump(exclude={'evidence'}), 
                    claim_id=str(uuid.uuid4()),
                    evidence=final_evidence,
                    valid_from=email.date or datetime.now()
                )
                
                # 4. Apply the Quality Gate!
                if passes_quality_gate(new_claim):
                    final_claims.append(new_claim)
                
            return {"entities": final_entities, "claims": final_claims}

        except Exception as e:
            if "429" in str(e):
                if attempt < 2:
                    print(f"  ⚠️ Rate limit hit. Retrying in {2 ** attempt} seconds...")
                    time.sleep(2 ** attempt)
                    continue

                # Quota exhausted. Return NOTHING.
                #
                # This branch used to inject a hardcoded "Western Trading Desk"
                # entity and a synthetic MANAGES claim so the explorer always had
                # something to render. Those claims entered the graph
                # indistinguishable from extracted ones — in a pipeline whose
                # entire purpose is that no ungrounded fact is ever stored. A
                # demo that shows an empty graph is honest; a demo that shows
                # invented facts is not, and it quietly falsifies every
                # downstream count, context pack and citation.
                #
                # The header-extraction path is unaffected and still populates
                # the graph from all 1,000 emails, so an exhausted quota now
                # degrades the semantic layer rather than corrupting it.
                print(
                    f"  ❌ API quota exhausted for {email.message_id}. "
                    f"Returning no claims — the graph stays smaller rather than wrong."
                )
                return {"entities": [], "claims": []}

            print(f"Extraction failed for email {email.message_id}: {e}")
            break

    return {"entities": [], "claims": []}

if __name__ == "__main__":
    test_email = EmailArtifact(
        message_id="test-123",
        date=datetime.now(),
        sender="john.doe@enron.com",
        subject="Project Raptor Update",
        body="Hi team, I just wanted to confirm that Jane Smith is now managing the Raptor project."
    )
    
    print("Sending to Gemini for extraction...\n")
    extracted_data = extract_knowledge_from_email(test_email)
    
    print(f"Found {len(extracted_data['entities'])} Entities")
    print(f"Found {len(extracted_data['claims'])} Claims")