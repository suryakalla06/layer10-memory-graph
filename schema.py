from pydantic import BaseModel, Field
from typing import List, Optional, Dict
from datetime import datetime

class EmailArtifact(BaseModel):
    message_id: str
    date: Optional[datetime]
    sender: str
    recipients: List[str] = Field(default_factory=list)
    subject: Optional[str] = None
    body: str

class Entity(BaseModel):
    """
    Supports Canonicalization.
    Stores aliases to prevent duplicate nodes for the same person/thing.
    """
    entity_id: str            # Primary unique identifier
    entity_type: str          # Person, Organization, Project, etc. 
    name: str
    aliases: List[str] = Field(default_factory=list) # Handles renames/email variants 
    metadata: Dict = Field(default_factory=dict)

class Evidence(BaseModel):
    """
    Supports Strong Grounding.
    Every claim must point back to a specific source and location.
    """
    source_id: str            # Reference to EmailArtifact.message_id 
    excerpt: str              # The specific text snippet 
    start_offset: int         # Character offset for precise location 
    end_offset: int           # Character offset for precise location 
    timestamp: datetime       # When the evidence was created 

class Claim(BaseModel):
    """
    Supports Long-Term Correctness[cite: 14, 53].
    Tracks validity time and versioning.
    """
    claim_id: str
    subject_id: str           # entity_id of source
    relation: str             # e.g., "WORKS_ON", "MANAGED_BY"
    object_id: str            # entity_id of target
    
    evidence: List[Evidence]  # Cross-evidence support must not be empty for the claim to be stored.[cite: 42, 52]
    
    # Temporal Logic 
    valid_from: datetime      # When this fact became true
    valid_until: Optional[datetime] = None  # Supports reversals/edits [cite: 14, 53]
    
    status: str = "active"    # active, superseded, or deleted [cite: 62]
    version: str = "v1"       # Track extraction version [cite: 41]